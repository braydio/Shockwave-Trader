"""YFinance collector for market context."""

from typing import Optional
import asyncio

from arbiter.collectors.base import BaseCollector, NormalizedEvent


class YFinanceCollector(BaseCollector):
    """Collect market data from Yahoo Finance.

    Provides:
    - Price data for major indices and ETFs
    - Daily change percentages
    - Volatility context
    """

    name = "yfinance"
    priority = 1
    category = "market"

    # Symbols to track
    SYMBOLS = {
        "SPY": "S&P 500",
        "QQQ": "NASDAQ",
        "DIA": "Dow Jones",
        "XLE": "Energy",
        "XLK": "Technology",
        "XLF": "Financials",
        "VIXY": "Volatility",
        "GLD": "Gold",
        "USO": "Oil",
    }

    def __init__(self, tickers: Optional[list[str]] = None):
        self.tickers = tickers or list(self.SYMBOLS.keys())

    async def fetch(self) -> dict:
        """Fetch market data for tracked symbols."""
        try:
            import yfinance as yf
        except ImportError:
            return {}

        data = {}
        tickers_obj = yf.Tickers(" ".join(self.tickers))

        for symbol in self.tickers:
            try:
                ticker = tickers_obj.tickers[symbol]
                hist = ticker.history(period="1d")

                if not hist.empty:
                    close = float(hist["Close"].iloc[-1])
                    prev_close = (
                        float(hist["Open"].iloc[-1]) if len(hist) > 1 else close
                    )
                    change_pct = (
                        ((close - prev_close) / prev_close * 100) if prev_close else 0
                    )

                    data[symbol] = {
                        "price": close,
                        "change_pct": change_pct,
                        "volume": int(hist["Volume"].iloc[-1])
                        if "Volume" in hist
                        else 0,
                        "name": self.SYMBOLS.get(symbol, symbol),
                    }
            except Exception:
                continue

        return data

    def transform(self, raw: dict) -> list[NormalizedEvent]:
        """Transform market data into normalized events."""
        events = []

        for symbol, info in raw.items():
            change_pct = abs(info["change_pct"])

            # Determine direction
            if info["change_pct"] > 0.5:
                direction = "bullish"
            elif info["change_pct"] < -0.5:
                direction = "bearish"
            else:
                direction = "neutral"

            # Magnitude based on change percentage
            magnitude = min(change_pct / 5, 1.0)  # 5% = max magnitude

            # Confidence based on volume (higher volume = more confidence)
            volume_factor = min(info.get("volume", 0) / 10_000_000, 1.0)
            confidence = 0.7 + (0.2 * volume_factor)

            entities = [symbol]
            if symbol in self.SYMBOLS:
                entities.append(self.SYMBOLS[symbol].lower())

            event = self._make_event(
                entities=entities,
                direction=direction,
                magnitude=magnitude,
                confidence=confidence,
                raw=info,
            )
            events.append(event)

        return events


async def test_collector():
    """Test the collector."""
    collector = YFinanceCollector()
    raw = await collector.fetch()
    print(f"Raw data: {raw}")

    events = collector.transform(raw)
    print(f"\nEvents ({len(events)}):")
    for e in events:
        print(f"  {e.source}: {e.entities} {e.direction} {e.magnitude:.2f}")


if __name__ == "__main__":
    asyncio.run(test_collector())
