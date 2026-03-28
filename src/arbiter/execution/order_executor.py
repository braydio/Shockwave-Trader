"""Trade decision validation and execution for Arbiter."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from arbiter.config.settings import (
    COOLDOWN_HOURS,
    DEFAULT_TRADE_AMOUNT,
    MAX_DAILY_TRADES,
    MAX_POSITION_PCT,
    STORAGE_DIR,
)
from arbiter.execution.public_client import Order
from arbiter.lib.errors import TradingError
from arbiter.lib.logger import log_event, setup_logger
from arbiter.storage.trade_log import TradeLogger


@dataclass
class TradeDecision:
    """Normalized decision object passed into the executor."""

    symbol: str
    side: str
    amount_usd: float = DEFAULT_TRADE_AMOUNT
    qty: float = 0.0
    confidence: float = 0.0
    reasoning: str = ""
    timestamp: str = ""


@dataclass
class TradeResult:
    """Result of an execution attempt."""

    success: bool
    order_id: Optional[str]
    message: str
    timestamp: str
    order: Optional[Order] = None


class OrderExecutor:
    """Validate, size, execute, and log trades for any execution backend."""

    def __init__(
        self,
        client=None,
        logger=None,
        trade_logger: Optional[TradeLogger] = None,
        storage_dir: Optional[str] = None,
        cooldown_hours: int = COOLDOWN_HOURS,
        max_position_pct: float = MAX_POSITION_PCT,
        max_daily_trades: int = MAX_DAILY_TRADES,
    ):
        if client is None:
            from arbiter.execution.client import create_execution_client

            self.client = create_execution_client()
        else:
            self.client = client
        if self.client is None:
            raise TradingError("No execution backend is configured")
        self.logger = logger or setup_logger("arbiter.execution")
        self.trade_logger = trade_logger or TradeLogger(storage_dir=storage_dir)
        self.cooldown_hours = cooldown_hours
        self.max_position_pct = max_position_pct
        self.max_daily_trades = max_daily_trades
        self.storage_dir = Path(storage_dir or STORAGE_DIR)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.cooldown_file = self.storage_dir / "cooldowns.json"
        self.cooldowns = self._load_cooldowns()

    def execute(self, decision: TradeDecision) -> TradeResult:
        """Validate and execute a trade decision."""
        normalized = self._normalize_decision(decision)

        self._check_cooldown(normalized.symbol)
        self._check_daily_trade_limit()

        qty = normalized.qty or self._size_order(
            normalized.symbol, normalized.amount_usd
        )
        if qty <= 0:
            raise TradingError(
                f"Unable to determine a valid order quantity for {normalized.symbol}",
                symbol=normalized.symbol,
            )

        if normalized.side == "buy":
            self._check_exposure(normalized.symbol, qty)

        submit_kwargs = {
            "symbol": normalized.symbol,
            "qty": qty,
            "side": normalized.side,
        }
        if normalized.side == "buy" and normalized.amount_usd > 0:
            submit_kwargs["amount"] = normalized.amount_usd
        order = self.client.submit_order(**submit_kwargs)

        self._update_cooldown(normalized.symbol)
        decision_payload = asdict(normalized)
        decision_payload["qty"] = qty
        self.trade_logger.log_trade(decision_payload, order)
        log_event(
            self.logger,
            "trade_executed",
            {
                "symbol": normalized.symbol,
                "side": normalized.side,
                "qty": qty,
                "order_id": order.id,
                "confidence": normalized.confidence,
            },
        )

        return TradeResult(
            success=True,
            order_id=order.id,
            message=f"Submitted {normalized.side} order for {qty:g} {normalized.symbol}",
            timestamp=datetime.now(timezone.utc).isoformat(),
            order=order,
        )

    def _normalize_decision(self, decision: TradeDecision) -> TradeDecision:
        timestamp = decision.timestamp or datetime.now(timezone.utc).isoformat()
        return TradeDecision(
            symbol=decision.symbol.upper(),
            side=decision.side.lower(),
            amount_usd=decision.amount_usd,
            qty=float(decision.qty or 0),
            confidence=decision.confidence,
            reasoning=decision.reasoning,
            timestamp=timestamp,
        )

    def _load_cooldowns(self) -> dict[str, str]:
        if not self.cooldown_file.exists():
            return {}
        return json.loads(self.cooldown_file.read_text(encoding="utf-8"))

    def _save_cooldowns(self) -> None:
        self.cooldown_file.write_text(
            json.dumps(self.cooldowns, indent=2),
            encoding="utf-8",
        )

    def _check_cooldown(self, symbol: str) -> None:
        last_trade = self.cooldowns.get(symbol)
        if not last_trade:
            return
        cutoff = datetime.now(timezone.utc) - timedelta(hours=self.cooldown_hours)
        last_trade_dt = datetime.fromisoformat(last_trade)
        if last_trade_dt >= cutoff:
            raise TradingError(
                f"{symbol} is still in cooldown until {(last_trade_dt + timedelta(hours=self.cooldown_hours)).isoformat()}",
                symbol=symbol,
            )

    def _update_cooldown(self, symbol: str) -> None:
        self.cooldowns[symbol] = datetime.now(timezone.utc).isoformat()
        self._save_cooldowns()

    def _check_daily_trade_limit(self) -> None:
        today = datetime.now(timezone.utc).date()
        trades_today = 0
        for entry in self.trade_logger.read_trades(limit=500):
            try:
                logged_at = datetime.fromisoformat(entry["timestamp"]).date()
            except (KeyError, ValueError):
                continue
            if logged_at == today:
                trades_today += 1
        if trades_today >= self.max_daily_trades:
            raise TradingError(
                f"Daily trade limit reached ({self.max_daily_trades})",
            )

    def _check_exposure(self, symbol: str, qty: float) -> None:
        account = self.client.get_account()
        current_price = self.client.get_price(symbol)
        if not current_price:
            raise TradingError(
                f"Could not determine current price for {symbol}",
                symbol=symbol,
            )

        position_value = current_price * qty
        max_position_value = account.equity * self.max_position_pct
        if position_value > max_position_value:
            raise TradingError(
                f"Order exceeds max exposure: ${position_value:,.2f} > ${max_position_value:,.2f}",
                symbol=symbol,
                order_details={"qty": qty, "price": current_price},
            )

    def _size_order(self, symbol: str, amount_usd: float) -> float:
        current_price = self.client.get_price(symbol)
        if not current_price or current_price <= 0:
            return 0.0
        return max(round(amount_usd / current_price, 5), 0.0)
