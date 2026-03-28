"""Arbiter daemon - Background scheduler for strategy execution.

Supports multiple execution backends:
- Public API (default)
- Local paper trading
"""

from __future__ import annotations

import asyncio
import signal
from datetime import UTC, datetime
from typing import Optional

from rich.console import Console

from arbiter.collectors.discord_collector import DiscordCollector
from arbiter.collectors.eia_collector import EIACollector
from arbiter.collectors.fred_collector import FREDCollector
from arbiter.collectors.gdelt_collector import GDELTCollector
from arbiter.collectors.telegram_collector import TelegramCollector
from arbiter.collectors.yfinance_collector import YFinanceCollector
from arbiter.config.settings import (
    CYCLE_INTERVAL_SECONDS,
    DISCORD_NOTIFICATIONS_ENABLED,
    DISCORD_WEBHOOK_URL,
    OPENAI_ADVISOR_ENABLED,
)
from arbiter.delta.compute import annotate_deltas, build_snapshot
from arbiter.delta.state import DeltaState
from arbiter.execution.client import create_execution_client, ExecutionBackend
from arbiter.execution.order_executor import OrderExecutor
from arbiter.llm import OpenAITradeAdvisor, TradeHypothesisRequest
from arbiter.lib.logger import log_event, setup_logger
from arbiter.notifications.discord import DiscordNotifier, TradeAlert, AlertLevel
from arbiter.signals.risk import build_risk_budget
from arbiter.strategies.energy_shock import (
    EnergyShockDecisionEngine,
    EnergySignal,
    StrategyConfig,
    StateManager,
)

console = Console()
logger = setup_logger("arbiter.daemon")


class ArbiterDaemon:
    """Background daemon for running Arbiter strategy cycles."""

    def __init__(
        self,
        cycle_seconds: int = CYCLE_INTERVAL_SECONDS,
        dry_run: bool = False,
        backend: Optional[ExecutionBackend] = None,
    ):
        self.cycle_seconds = cycle_seconds
        self.dry_run = dry_run
        self.backend = backend
        self.running = False
        self.cycle_count = 0
        self.config = StrategyConfig()
        self.state_manager = StateManager()
        self.delta_state = DeltaState()
        self.client = None
        self.executor: Optional[OrderExecutor] = None
        self.decision_engine: Optional[EnergyShockDecisionEngine] = None
        self.discord: Optional[DiscordNotifier] = None
        self.trade_advisor: Optional[OpenAITradeAdvisor] = None

        self.market_data: dict = {}
        self.fred_raw: dict = {}
        self.delta_events: list = []
        self.events_by_source: dict[str, list] = {
            "fred": [],
            "eia": [],
            "gdelt": [],
            "discord": [],
            "telegram": [],
        }

    def _get_backend_name(self) -> str:
        """Get backend display name."""
        if self.backend == ExecutionBackend.PUBLIC:
            return "Public API"
        if self.backend == ExecutionBackend.PAPER:
            return "Paper"
        return "Auto"

    async def initialize(self) -> None:
        """Initialize clients and state."""
        logger.info("Initializing Arbiter daemon...")

        # Initialize execution client
        self.client = create_execution_client(self.backend)
        if self.client:
            try:
                account = self.client.get_account()
                logger.info(
                    "Connected to %s. Equity: $%0.2f",
                    self._get_backend_name(),
                    account.equity,
                )
                if not self.dry_run:
                    self.executor = OrderExecutor(client=self.client)
                console.print(f"[green]Connected to {self._get_backend_name()}[/green]")
            except Exception as exc:
                logger.warning("Could not connect: %s", exc)
                logger.warning("Running in simulation mode")
                self.dry_run = True
                self.client = create_execution_client(ExecutionBackend.PAPER)

        # Initialize Discord notifications
        if DISCORD_NOTIFICATIONS_ENABLED and DISCORD_WEBHOOK_URL:
            self.discord = DiscordNotifier(webhook_url=DISCORD_WEBHOOK_URL)
            logger.info("Discord notifications enabled")
            console.print("[green]Discord notifications enabled[/green]")

        if OPENAI_ADVISOR_ENABLED:
            advisor = OpenAITradeAdvisor()
            if advisor.is_configured():
                self.trade_advisor = advisor
                logger.info("OpenAI trade advisor enabled")
                console.print("[green]OpenAI trade advisor enabled[/green]")
            else:
                logger.warning(
                    "OPENAI_ADVISOR_ENABLED=true but OPENAI_API_KEY is not configured"
                )

        self.decision_engine = EnergyShockDecisionEngine(
            client=self.client or create_execution_client(ExecutionBackend.PAPER),
            state_manager=self.state_manager,
            config=self.config,
        )

        state = self.state_manager.load()
        if state.position:
            logger.info("Resuming with position: %s", state.position.symbol)

        console.print("[green]Arbiter daemon initialized[/green]")

    async def fetch_all_data(self) -> None:
        """Fetch market and event data in parallel."""
        yfinance = YFinanceCollector()
        fred = FREDCollector()
        eia = EIACollector()
        gdelt = GDELTCollector(max_articles=15)
        discord = DiscordCollector()
        telegram = TelegramCollector()

        market_task = yfinance.fetch()
        fred_fetch_task = fred.fetch()
        eia_task = eia.run()
        gdelt_task = gdelt.run()
        discord_task = discord.run()
        telegram_task = telegram.run()

        (
            market_data,
            fred_raw,
            eia_events,
            gdelt_events,
            discord_events,
            telegram_events,
        ) = await asyncio.gather(
            market_task,
            fred_fetch_task,
            eia_task,
            gdelt_task,
            discord_task,
            telegram_task,
            return_exceptions=True,
        )

        self.market_data = market_data if isinstance(market_data, dict) else {}
        self.fred_raw = fred_raw if isinstance(fred_raw, dict) else {}

        # Transform FRED raw data to events
        fred = FREDCollector()
        fred_events = fred.transform(self.fred_raw) if self.fred_raw else []

        self.events_by_source["fred"] = fred_events

        current_event_stream = []
        for maybe_events in (eia_events, gdelt_events, discord_events, telegram_events):
            if isinstance(maybe_events, list):
                current_event_stream.extend(maybe_events)

        previous_snapshot = self.delta_state.load_last_events()
        self.delta_events = annotate_deltas(current_event_stream, previous_snapshot)
        self.delta_state.save_last_events(build_snapshot(current_event_stream))

        hot_memory = self.delta_state.update_hot_memory(self.delta_events)
        hot_events = self.delta_state.materialize_events(hot_memory)
        self.events_by_source["eia"] = [
            event for event in hot_events if event.source == "eia"
        ]
        self.events_by_source["gdelt"] = [
            event for event in hot_events if event.source == "gdelt"
        ]
        self.events_by_source["discord"] = [
            event for event in hot_events if event.source == "discord"
        ]
        self.events_by_source["telegram"] = [
            event for event in hot_events if event.source == "telegram"
        ]

    def _send_discord_entry(self, trade, price: float, signal):
        """Send entry notification to Discord."""
        if not self.discord:
            return
        alert = TradeAlert(
            level=AlertLevel.ENTRY,
            symbol=trade.symbol,
            side=trade.side,
            qty=trade.qty,
            price=price,
            confidence=signal.confidence,
            reasoning=trade.reasoning,
        )
        self.discord.send_trade(alert)

    def _send_discord_exit(
        self, position, current_price: float, exit_reason: str, signal
    ):
        """Send exit notification to Discord."""
        if not self.discord:
            return
        pnl_pct = (current_price - position.entry_price) / position.entry_price
        alert = TradeAlert(
            level=AlertLevel.EXIT,
            symbol=position.symbol,
            side="sell",
            qty=position.quantity,
            price=current_price,
            confidence=signal.confidence,
            reasoning=exit_reason,
            pnl_pct=pnl_pct,
            exit_reason=exit_reason,
        )
        self.discord.send_trade(alert)

    def _send_discord_error(self, error: str):
        """Send error notification to Discord."""
        if self.discord:
            self.discord.send_error(error, f"Cycle {self.cycle_count}")

    def _build_trade_hypothesis(
        self,
        strategy_decision,
        signal: EnergySignal,
        price: float,
    ) -> TradeHypothesisRequest:
        """Package the current signal, market state, and risk budget for review."""
        trade = strategy_decision.trade
        if trade is None:
            raise ValueError("Cannot build a trade hypothesis without a trade")

        account = None
        if self.client is not None:
            try:
                account = self.client.get_account()
            except Exception as exc:
                logger.warning("Could not fetch account for advisor context: %s", exc)

        position_size = "Unavailable"
        if account is not None:
            budget = build_risk_budget(account, self.config.max_position_pct)
            requested_notional = trade.amount_usd or (trade.qty * price)
            position_size = (
                f"Requested ${requested_notional:,.2f}; "
                f"available ${budget.available_trade_value:,.2f}; "
                f"max position ${budget.max_position_value:,.2f}; "
                f"buying power ${budget.buying_power:,.2f}; "
                f"equity ${budget.equity:,.2f}"
            )

        market_parts = []
        for symbol in ("XLE", "USO", "SPY", "VIXY"):
            data = self.market_data.get(symbol, {})
            symbol_price = data.get("price")
            if symbol_price is None:
                continue
            change = data.get("change_pct", 0.0)
            market_parts.append(f"{symbol} ${float(symbol_price):.2f} ({change:+.2f}%)")

        if price > 0 and trade.symbol not in {"XLE", "USO", "SPY", "VIXY"}:
            market_parts.insert(0, f"{trade.symbol} ${price:.2f}")

        price_context = "; ".join(market_parts) if market_parts else "Unavailable"
        risk_notes = (
            f"Signal confidence {signal.confidence:.3f}; "
            f"event pressure {signal.event_pressure:.3f}; "
            f"market confirmation {signal.market_confirmation:.3f}; "
            f"risk regime {signal.risk_regime:.3f}; "
            f"status {strategy_decision.status}; "
            f"note {strategy_decision.note}"
        )

        return TradeHypothesisRequest(
            symbol=trade.symbol,
            side=trade.side,
            thesis=trade.reasoning,
            price_context=price_context,
            risk_notes=risk_notes,
            position_size=position_size,
        )

    def _maybe_review_trade_hypothesis(
        self,
        strategy_decision,
        signal: EnergySignal,
        price: float,
    ) -> None:
        """Run the OpenAI trade review before execution when enabled."""
        if self.trade_advisor is None or strategy_decision.trade is None:
            return

        try:
            hypothesis = self._build_trade_hypothesis(strategy_decision, signal, price)
            review = self.trade_advisor.review(hypothesis)
            logger.info(
                "OpenAI trade review for %s %s: %s",
                strategy_decision.trade.side,
                strategy_decision.trade.symbol,
                review,
            )
            console.print("\n[bold magenta]AI Trade Review[/bold magenta]")
            console.print(review)
            console.print()
        except Exception as exc:
            logger.warning("OpenAI trade review failed: %s", exc)

    def display_status(self, signal: Optional[EnergySignal] = None):
        """Display current status to console."""
        state = self.state_manager.load()

        xle = self.market_data.get("XLE", {})
        spy = self.market_data.get("SPY", {})
        vix = self.market_data.get("VIXY", {})

        console.print("\n[bold cyan]Market[/bold cyan]")
        for symbol, data in [("XLE", xle), ("SPY", spy), ("VIXY", vix)]:
            change = data.get("change_pct", 0.0)
            color = "green" if change > 0 else "red" if change < 0 else "yellow"
            price = data.get("price", 0.0)
            console.print(
                f"  {symbol:5}: ${price:8.2f} [{color}]{change:+6.2f}%[/{color}]"
            )

        if signal:
            console.print(f"\n[bold cyan]Signal[/bold cyan]")
            console.print(f"  Confidence: {signal.confidence:.3f}")
            console.print(f"  Event:      {signal.event_pressure:.3f}")
            console.print(f"  Market:     {signal.market_confirmation:.3f}")
            console.print(f"  Regime:     {signal.risk_regime:.3f}")

        if state.position:
            pos = state.position
            days = (datetime.now(UTC) - pos.entry_date).days
            console.print(
                f"\n[yellow]Position:[/yellow] {pos.quantity} {pos.symbol} @ ${pos.entry_price:.2f} ({days}d)"
            )
        else:
            console.print(f"\n[dim]No position[/dim]")

        console.print(
            f"[dim]FRED: {len(self.events_by_source['fred'])} | EIA: {len(self.events_by_source['eia'])} | GDELT: {len(self.events_by_source['gdelt'])} | Discord: {len(self.events_by_source['discord'])} | Telegram: {len(self.events_by_source['telegram'])} | Delta: {len(self.delta_events)}[/dim]"
        )
        console.print(
            f"[dim]Backend: {self._get_backend_name()} | Mode: {'DRY RUN' if self.dry_run else 'LIVE'}[/dim]"
        )

    async def run_cycle(self, show_timestamp: bool = True) -> Optional[EnergySignal]:
        """Run one strategy cycle."""
        self.cycle_count += 1
        timestamp = datetime.now().strftime("%H:%M:%S")
        if show_timestamp:
            console.print(
                f"[bold yellow]▶ Cycle {self.cycle_count} @ {timestamp}[/bold yellow]"
            )
        logger.info("=== Cycle %s at %s ===", self.cycle_count, timestamp)

        await self.fetch_all_data()

        if self.decision_engine is None:
            await self.initialize()

        strategy_decision = self.decision_engine.evaluate(
            market_data=self.market_data,
            fred_data=self.fred_raw,
            fred_events=self.events_by_source["fred"],
            gdelt_events=self.events_by_source["gdelt"],
            discord_events=self.events_by_source["discord"],
            telegram_events=self.events_by_source["telegram"],
            eia_events=self.events_by_source["eia"],
        )
        signal = strategy_decision.signal

        if strategy_decision.trade is not None:
            logger.info(
                "%s SIGNAL: %s",
                strategy_decision.status.upper(),
                strategy_decision.trade.reasoning,
            )

            price = self.market_data.get("XLE", {}).get("price", 0.0)
            self._maybe_review_trade_hypothesis(strategy_decision, signal, price)

            # Discord notification
            if strategy_decision.status == "entry":
                self._send_discord_entry(strategy_decision.trade, price, signal)

            if not self.dry_run and self.executor:
                try:
                    result = self.executor.execute(strategy_decision.trade)
                    execution_price = price or 0.0
                    self.decision_engine.record_execution(
                        strategy_decision.trade,
                        float(execution_price),
                    )
                    log_event(
                        logger,
                        strategy_decision.status,
                        {
                            "symbol": strategy_decision.trade.symbol,
                            "side": strategy_decision.trade.side,
                            "confidence": signal.confidence,
                            "reasoning": strategy_decision.trade.reasoning,
                            "order_id": result.order_id,
                        },
                    )
                except Exception as exc:
                    logger.error("Failed to submit order: %s", exc)
                    self._send_discord_error(f"Order failed: {exc}")
            else:
                logger.info(
                    "[DRY RUN] Would %s %s (%s)",
                    strategy_decision.trade.side,
                    strategy_decision.trade.symbol,
                    strategy_decision.note,
                )
        else:
            logger.info("HOLD: %s", strategy_decision.note)

        log_event(
            logger,
            "signal",
            {
                "cycle": self.cycle_count,
                "action": signal.action.value,
                "confidence": signal.confidence,
                "event_pressure": signal.event_pressure,
                "market_confirmation": signal.market_confirmation,
                "risk_regime": signal.risk_regime,
                "backend": self.backend.value if self.backend else "unknown",
                "discord_events": len(self.events_by_source["discord"]),
                "telegram_events": len(self.events_by_source["telegram"]),
                "delta_events": len(self.delta_events),
            },
        )

        self.display_status(signal)
        return signal

    async def run(self) -> None:
        """Run the daemon until interrupted."""
        await self.initialize()
        self.running = True
        console.print(f"\n[green]Arbiter running[/green]")
        console.print(
            f"Cycle: {self.cycle_seconds}s | Backend: {self._get_backend_name()} | Mode: {'DRY RUN' if self.dry_run else 'LIVE'}"
        )
        console.print("Ctrl+C to stop\n")

        while self.running:
            try:
                await self.run_cycle()
                await asyncio.sleep(self.cycle_seconds)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Cycle error: %s", exc, exc_info=True)
                self._send_discord_error(str(exc))
                await asyncio.sleep(10)
            finally:
                if not self.running:
                    from arbiter.collectors.telegram_collector import TelegramCollector

                    await TelegramCollector.close()
                    logger.info("Closed Telegram session")

        logger.info("Daemon stopped")

    def stop(self) -> None:
        """Stop the daemon."""
        self.running = False


async def _main(
    cycle_seconds: int = CYCLE_INTERVAL_SECONDS,
    dry_run: bool = False,
    backend: Optional[str] = None,
    fast: bool = False,
) -> None:
    """Main entry point."""
    if fast:
        cycle_seconds = 3  # Fast mode: 3 seconds per cycle
        console.print("[yellow]⚡ FAST MODE enabled (3s cycles)[/yellow]")

    backend_enum = None
    if backend:
        backend = backend.lower()
        if backend == "public":
            backend_enum = ExecutionBackend.PUBLIC
        elif backend == "paper":
            backend_enum = ExecutionBackend.PAPER

    daemon = ArbiterDaemon(
        cycle_seconds=cycle_seconds,
        dry_run=dry_run,
        backend=backend_enum,
    )

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, daemon.stop)

    await daemon.run()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Arbiter daemon")
    parser.add_argument(
        "--cycle",
        "-c",
        type=int,
        default=CYCLE_INTERVAL_SECONDS,
        help="Cycle interval (seconds)",
    )
    parser.add_argument(
        "--dry-run", "-d", action="store_true", help="Dry run mode (no trades)"
    )
    parser.add_argument(
        "--backend", "-b", choices=["public", "paper"], help="Execution backend"
    )
    parser.add_argument(
        "--fast", "-f", action="store_true", help="Fast mode (3s cycles for demo)"
    )
    args = parser.parse_args()

    asyncio.run(
        _main(
            cycle_seconds=args.cycle,
            dry_run=args.dry_run,
            backend=args.backend,
            fast=args.fast,
        )
    )
