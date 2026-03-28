from __future__ import annotations

import tempfile
import unittest

from arbiter.execution.order_executor import OrderExecutor, TradeDecision
from arbiter.execution.public_client import Account, Order
from arbiter.lib.errors import TradingError


class FakeClient:
    def __init__(self, price: float = 100.0):
        self.price = price
        self.submitted_orders: list[dict[str, object]] = []

    def get_account(self) -> Account:
        return Account(account_id="brok-1", buying_power=10000.0, cash=5000.0, equity=10000.0)

    def get_price(self, symbol: str) -> float:
        return self.price

    def submit_order(self, symbol: str, qty: float, side: str, amount=None) -> Order:
        self.submitted_orders.append(
            {"symbol": symbol, "qty": qty, "side": side, "amount": amount}
        )
        return Order(
            id="ord-1",
            symbol=symbol,
            side=side,
            qty=qty,
            status="submitted",
            created_at="2026-03-20T12:00:00Z",
        )


class OrderExecutorTests(unittest.TestCase):
    def test_execute_sizes_order_logs_trade_and_submits(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            client = FakeClient(price=50.0)
            executor = OrderExecutor(
                client=client,
                storage_dir=tmpdir,
                cooldown_hours=4,
                max_position_pct=0.2,
                max_daily_trades=10,
            )

            result = executor.execute(
                TradeDecision(
                    symbol="AAPL",
                    side="buy",
                    amount_usd=150.0,
                    confidence=0.9,
                    reasoning="test",
                )
            )

            self.assertTrue(result.success)
            self.assertEqual(client.submitted_orders[0]["qty"], 3.0)
            self.assertEqual(client.submitted_orders[0]["amount"], 150.0)
            self.assertEqual(len(executor.trade_logger.read_trades()), 1)

    def test_execute_rejects_symbol_in_cooldown(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            executor = OrderExecutor(client=FakeClient(), storage_dir=tmpdir)
            executor.cooldowns["AAPL"] = "2030-01-01T00:00:00+00:00"
            executor._save_cooldowns()

            with self.assertRaises(TradingError):
                executor.execute(TradeDecision(symbol="AAPL", side="buy", amount_usd=100.0))

    def test_execute_rejects_buy_when_position_exceeds_max_exposure(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            client = FakeClient(price=500.0)
            executor = OrderExecutor(
                client=client,
                storage_dir=tmpdir,
                max_position_pct=0.02,
            )

            with self.assertRaises(TradingError):
                executor.execute(TradeDecision(symbol="AAPL", side="buy", amount_usd=1000.0))


if __name__ == "__main__":
    unittest.main()
