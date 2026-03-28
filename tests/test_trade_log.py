from __future__ import annotations

import tempfile
import unittest

from arbiter.storage.trade_log import TradeLogger


class TradeLoggerTests(unittest.TestCase):
    def test_log_trade_and_read_back_recent_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = TradeLogger(storage_dir=tmpdir)

            logger.log_trade({"symbol": "AAPL", "side": "buy"}, {"orderId": "1"})
            logger.log_trade({"symbol": "MSFT", "side": "sell"}, {"orderId": "2"})

            entries = logger.read_trades(limit=1)

            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0]["decision"]["symbol"], "MSFT")
            self.assertEqual(entries[0]["order"]["orderId"], "2")


if __name__ == "__main__":
    unittest.main()
