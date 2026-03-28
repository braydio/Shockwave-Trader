"""Local paper-trading backend with persisted state."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import uuid4

from arbiter.config.settings import PAPER_STARTING_CASH, PAPER_STATE_FILE
from arbiter.execution.public_client import Account, Order, OrderHistoryEntry, Position


class PaperClient:
    """Simulate a brokerage account locally with immediate market fills."""

    def __init__(
        self,
        starting_cash: float = PAPER_STARTING_CASH,
        state_file: str = PAPER_STATE_FILE,
    ):
        self.starting_cash = float(starting_cash)
        self.state_file = Path(state_file)
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.account_id = "paper-local"
        self._state = self._load_state()

    def _default_state(self) -> dict:
        return {
            "cash": self.starting_cash,
            "positions": {},
            "orders": [],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    def _load_state(self) -> dict:
        if not self.state_file.exists():
            state = self._default_state()
            self._save_state(state)
            return state

        try:
            data = json.loads(self.state_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = self._default_state()
            self._save_state(data)
            return data

        data.setdefault("cash", self.starting_cash)
        data.setdefault("positions", {})
        data.setdefault("orders", [])
        return data

    def _save_state(self, state: Optional[dict] = None) -> None:
        if state is not None:
            self._state = state
        self._state["updated_at"] = datetime.now(timezone.utc).isoformat()
        self.state_file.write_text(
            json.dumps(self._state, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    @staticmethod
    def _to_float(value) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def _get_market_price(self, symbol: str) -> Optional[float]:
        try:
            import yfinance as yf
        except ImportError as exc:
            raise RuntimeError(
                "yfinance is required for local paper pricing. Install project dependencies first."
            ) from exc

        ticker = yf.Ticker(symbol.upper())
        fast_info = getattr(ticker, "fast_info", None)
        if fast_info:
            for field in ("lastPrice", "regularMarketPrice", "previousClose"):
                price = self._to_float(fast_info.get(field))
                if price > 0:
                    return price

        history = ticker.history(period="1d", interval="1m")
        if history.empty:
            history = ticker.history(period="5d", interval="1d")
        if history.empty:
            return None

        close = history["Close"].dropna()
        if close.empty:
            return None
        return self._to_float(close.iloc[-1])

    def get_price(self, symbol: str) -> Optional[float]:
        position = self._state["positions"].get(symbol.upper())
        market_price = self._get_market_price(symbol)
        if market_price:
            return market_price
        if position:
            return self._to_float(position.get("current_price"))
        return None

    def get_account(self) -> Account:
        positions = self.get_positions()
        cash = self._to_float(self._state.get("cash"))
        market_value = sum(position.market_value for position in positions)
        equity = cash + market_value
        return Account(
            account_id=self.account_id,
            buying_power=cash,
            cash=cash,
            equity=equity,
        )

    def get_positions(self) -> list[Position]:
        normalized: list[Position] = []
        for symbol, raw in self._state.get("positions", {}).items():
            qty = self._to_float(raw.get("qty"))
            if qty <= 0:
                continue
            current_price = self.get_price(symbol) or self._to_float(
                raw.get("current_price")
            )
            avg_entry_price = self._to_float(raw.get("avg_entry_price"))
            market_value = qty * current_price
            unrealized_pl = (current_price - avg_entry_price) * qty
            raw["current_price"] = current_price
            normalized.append(
                Position(
                    symbol=symbol,
                    qty=qty,
                    market_value=market_value,
                    unrealized_pl=unrealized_pl,
                    current_price=current_price,
                )
            )
        self._save_state()
        return normalized

    def get_position(self, symbol: str) -> Optional[Position]:
        target = symbol.upper()
        for position in self.get_positions():
            if position.symbol == target:
                return position
        return None

    def submit_order(
        self,
        symbol: str,
        qty: Optional[float],
        side: str,
        order_type: str = "market",
        time_in_force: str = "day",
        amount: Optional[float] = None,
    ) -> Order:
        symbol = symbol.upper()
        side = side.lower()

        price = self.get_price(symbol)
        if not price or price <= 0:
            raise ValueError(f"Could not determine a market price for {symbol}")

        if amount is not None and amount > 0 and side == "buy":
            qty = round(float(amount) / price, 5)
        else:
            qty = float(qty or 0.0)
        if qty <= 0:
            raise ValueError("Paper orders require a positive quantity")

        cash = self._to_float(self._state.get("cash"))
        positions = self._state.setdefault("positions", {})
        current = positions.get(symbol, {"qty": 0.0, "avg_entry_price": 0.0})
        current_qty = self._to_float(current.get("qty"))
        avg_entry_price = self._to_float(current.get("avg_entry_price"))
        order_value = price * qty

        if side == "buy":
            if order_value > cash:
                raise ValueError(
                    f"Insufficient paper cash for {qty:g} {symbol} at ${price:.2f}"
                )
            new_qty = current_qty + qty
            total_cost = (current_qty * avg_entry_price) + order_value
            positions[symbol] = {
                "qty": new_qty,
                "avg_entry_price": total_cost / new_qty,
                "current_price": price,
            }
            self._state["cash"] = cash - order_value
        elif side == "sell":
            if qty > current_qty:
                raise ValueError(
                    f"Cannot sell {qty:g} {symbol}; only {current_qty:g} held"
                )
            remaining_qty = current_qty - qty
            self._state["cash"] = cash + order_value
            if remaining_qty > 0:
                positions[symbol] = {
                    "qty": remaining_qty,
                    "avg_entry_price": avg_entry_price,
                    "current_price": price,
                }
            else:
                positions.pop(symbol, None)
        else:
            raise ValueError("Paper orders support only buy and sell")

        created_at = datetime.now(timezone.utc).isoformat()
        order = Order(
            id=str(uuid4()),
            symbol=symbol,
            side=side,
            qty=qty,
            status="filled",
            created_at=created_at,
        )
        self._state.setdefault("orders", []).append(
            {
                **asdict(order),
                "filled_avg_price": price,
                "order_type": order_type,
                "time_in_force": time_in_force,
                "account_id": self.account_id,
            }
        )
        self._save_state()
        return order

    def get_orders(self, status: str = "open") -> list[Order]:
        requested_status = status.lower() if status else None
        orders: list[Order] = []
        for raw in self._state.get("orders", []):
            order = Order(
                id=str(raw.get("id", "")),
                symbol=str(raw.get("symbol", "")),
                side=str(raw.get("side", "")).lower(),
                qty=self._to_float(raw.get("qty")),
                status=str(raw.get("status", "")).lower(),
                created_at=str(raw.get("created_at", "")),
            )
            if requested_status and order.status != requested_status:
                continue
            orders.append(order)
        return list(reversed(orders))

    def get_order_history(self, limit: int = 50) -> list[OrderHistoryEntry]:
        entries: list[OrderHistoryEntry] = []
        for raw in reversed(self._state.get("orders", [])):
            entries.append(
                OrderHistoryEntry(
                    id=str(raw.get("id", "")),
                    symbol=str(raw.get("symbol", "")),
                    side=str(raw.get("side", "")).lower(),
                    qty=self._to_float(raw.get("qty")),
                    status=str(raw.get("status", "")).lower(),
                    created_at=str(raw.get("created_at", "")),
                    description=f"paper {raw.get('order_type', 'market')} order",
                )
            )
            if limit > 0 and len(entries) >= limit:
                break
        return entries

    def cancel_order(self, order_id: str) -> bool:
        for raw in self._state.get("orders", []):
            if raw.get("id") == order_id and raw.get("status") not in {
                "filled",
                "canceled",
            }:
                raw["status"] = "canceled"
                self._save_state()
                return True
        return False
