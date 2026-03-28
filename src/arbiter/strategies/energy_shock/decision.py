"""Decision adapter for the energy shock strategy."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Optional

from arbiter.config.settings import DEFAULT_TRADE_AMOUNT
from arbiter.execution.order_executor import TradeDecision
from arbiter.execution.positions import PositionService
from arbiter.execution.public_client import PublicClient
from arbiter.signals.risk import build_risk_budget, clamp_trade_amount
from arbiter.strategies.energy_shock.state import StateManager
from arbiter.strategies.energy_shock.strategy import (
    EnergySignal,
    PositionState,
    StrategyConfig,
    TradeAction,
    build_energy_signal,
    calculate_position_size,
    check_entry_conditions,
    check_exit_conditions,
    compute_event_pressure,
    score_market_confirmation,
    score_risk_regime,
)


@dataclass
class MarketSnapshot:
    """Reduced market context needed by the energy strategy."""

    xle_price: float
    xle_change: float
    uso_change: float
    spy_change: float
    vix_price: float


@dataclass
class StrategyDecision:
    """Combined strategy signal and trade decision."""

    signal: EnergySignal
    trade: Optional[TradeDecision]
    status: str
    note: str


def build_market_snapshot(
    market_data: dict, fred_data: Optional[dict] = None
) -> MarketSnapshot:
    """Extract the market fields used by the strategy from collector output.

    Args:
        market_data: YFinance collector output
        fred_data: FRED collector raw output (optional, for authoritative VIX)
    """
    xle_data = market_data.get("XLE", {})
    uso_data = market_data.get("USO", {})
    spy_data = market_data.get("SPY", {})
    vix_data = market_data.get("VIXY", {})

    # Prefer FRED VIXCLS over VIXY when available
    vix_price = float(vix_data.get("price", 20.0) or 20.0)
    if fred_data and "VIXCLS" in fred_data:
        fred_vix = fred_data["VIXCLS"].get("value")
        if fred_vix is not None and fred_vix > 0:
            vix_price = float(fred_vix)

    return MarketSnapshot(
        xle_price=float(xle_data.get("price", 0.0) or 0.0),
        xle_change=float(xle_data.get("change_pct", 0.0) or 0.0),
        uso_change=float(uso_data.get("change_pct", 0.0) or 0.0),
        spy_change=float(spy_data.get("change_pct", 0.0) or 0.0),
        vix_price=vix_price,
    )


class EnergyShockDecisionEngine:
    """Turn energy-shock scoring into Public-native trade decisions."""

    def __init__(
        self,
        client: Optional[PublicClient] = None,
        state_manager: Optional[StateManager] = None,
        config: Optional[StrategyConfig] = None,
    ):
        self.client = client or PublicClient()
        self.positions = PositionService(self.client)
        self.state_manager = state_manager or StateManager()
        self.config = config or StrategyConfig()

    def evaluate(
        self,
        market_data: dict,
        event_pressure: Optional[float] = None,
        fred_data: Optional[dict] = None,
        fred_events: Optional[list] = None,
        gdelt_events: Optional[list] = None,
        discord_events: Optional[list] = None,
        telegram_events: Optional[list] = None,
        eia_events: Optional[list] = None,
    ) -> StrategyDecision:
        """Evaluate current context and optionally emit a TradeDecision."""
        snapshot = build_market_snapshot(market_data, fred_data=fred_data)
        resolved_event_pressure = event_pressure
        if resolved_event_pressure is None:
            resolved_event_pressure = compute_event_pressure(
                fred_events or [],
                gdelt_events or [],
                discord_events or [],
                telegram_events or [],
                eia_events or [],
            )
        signal = build_energy_signal(
            event_pressure=resolved_event_pressure,
            market_confirmation=score_market_confirmation(
                snapshot.xle_change,
                snapshot.uso_change,
                snapshot.spy_change,
            ),
            risk_regime=score_risk_regime(snapshot.vix_price, snapshot.spy_change),
            config=self.config,
        )

        state = self.state_manager.load()
        current_position = self.positions.get_position(self.config.trade_symbol)
        position_state = self._build_position_state(current_position, state)

        if position_state is not None:
            should_exit, reason, desc = check_exit_conditions(
                position_state,
                snapshot.xle_price or current_position.current_price,
                signal,
                self.config,
            )
            if should_exit:
                qty = (
                    max(round(current_position.qty, 5), 0.00001)
                    if current_position
                    else position_state.quantity
                )
                return StrategyDecision(
                    signal=signal,
                    trade=TradeDecision(
                        symbol=self.config.trade_symbol,
                        side="sell",
                        qty=qty,
                        confidence=signal.confidence,
                        reasoning=desc,
                        timestamp=datetime.now(UTC).isoformat(),
                    ),
                    status="exit",
                    note=reason.value,
                )

        can_enter, reason = check_entry_conditions(
            signal,
            position_state,
            state.last_trade_time,
            self.config,
        )
        if not can_enter or signal.action != TradeAction.BUY:
            return StrategyDecision(
                signal=signal, trade=None, status="hold", note=reason
            )

        account = self.client.get_account()
        requested_amount = (
            calculate_position_size(signal, self.config) or DEFAULT_TRADE_AMOUNT
        )
        budget = build_risk_budget(account, self.config.max_position_pct)
        amount_usd = clamp_trade_amount(requested_amount, budget)
        if amount_usd <= 0:
            return StrategyDecision(
                signal=signal,
                trade=None,
                status="hold",
                note="No available risk budget for trade",
            )

        return StrategyDecision(
            signal=signal,
            trade=TradeDecision(
                symbol=self.config.trade_symbol,
                side="buy",
                amount_usd=amount_usd,
                confidence=signal.confidence,
                reasoning=signal.reasoning,
                timestamp=datetime.now(UTC).isoformat(),
            ),
            status="entry",
            note="Entry conditions met",
        )

    def record_execution(self, trade: TradeDecision, execution_price: float) -> None:
        """Update strategy state after a successful trade."""
        state = self.state_manager.load()
        if trade.side == "buy":
            qty = float(trade.qty or 0)
            if qty <= 0 and execution_price > 0:
                qty = max(round(trade.amount_usd / execution_price, 5), 0.00001)
            self.state_manager.update_position(
                PositionState(
                    symbol=trade.symbol,
                    entry_price=execution_price,
                    entry_date=datetime.now(UTC),
                    quantity=qty,
                    peak_price=execution_price,
                )
            )
            return

        if trade.side == "sell" and state.position:
            self.state_manager.update_position(None)

    def _build_position_state(
        self,
        current_position,
        state,
    ) -> Optional[PositionState]:
        if current_position is None:
            return state.position

        if state.position and state.position.symbol == current_position.symbol:
            state.position.quantity = round(current_position.qty, 5)
            state.position.peak_price = max(
                state.position.peak_price,
                current_position.current_price,
            )
            return state.position

        current_price = current_position.current_price or 0.0
        return PositionState(
            symbol=current_position.symbol,
            entry_price=current_price,
            entry_date=datetime.now(UTC),
            quantity=max(round(current_position.qty, 5), 0.00001),
            peak_price=current_price,
        )
