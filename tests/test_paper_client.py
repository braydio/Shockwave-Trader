from __future__ import annotations

import tempfile
import unittest

from arbiter.execution.paper_client import PaperClient


class PaperClientTests(unittest.TestCase):
    def test_buy_and_sell_update_cash_positions_and_orders(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            client = PaperClient(
                starting_cash=1000.0,
                state_file=f"{tmpdir}/paper_account.json",
            )
            client._get_market_price = lambda symbol: 50.0  # type: ignore[method-assign]

            buy_order = client.submit_order("AAPL", None, "buy", amount=125.0)
            account_after_buy = client.get_account()
            position = client.get_position("AAPL")

            self.assertEqual(buy_order.status, "filled")
            self.assertEqual(account_after_buy.cash, 875.0)
            self.assertIsNotNone(position)
            self.assertEqual(position.qty, 2.5)
            self.assertEqual(position.market_value, 125.0)

            sell_order = client.submit_order("AAPL", 1.25, "sell")
            account_after_sell = client.get_account()
            position_after_sell = client.get_position("AAPL")

            self.assertEqual(sell_order.status, "filled")
            self.assertEqual(account_after_sell.cash, 937.5)
            self.assertIsNotNone(position_after_sell)
            self.assertEqual(position_after_sell.qty, 1.25)
            self.assertEqual(len(client.get_orders(status="filled")), 2)


if __name__ == "__main__":
    unittest.main()
