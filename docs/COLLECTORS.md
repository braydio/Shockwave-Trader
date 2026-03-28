# Arbiter Collectors Specification

**Data ingestion layer — Crucix-inspired, trade-optimized**

---

## Collector Interface

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

@dataclass
class NormalizedEvent:
    id: str
    timestamp: str
    source: str
    category: str           # market | macro | news | social | commodity
    entities: list[str]
    direction: str          # bullish | bearish | neutral
    magnitude: float        # 0-1
    confidence: float       # 0-1
    raw: dict               # Original payload


class BaseCollector(ABC):
    name: str
    priority: int = 1       # 1 = highest priority

    @abstractmethod
    async def fetch(self) -> dict:
        """Fetch raw data from source"""
        pass

    @abstractmethod
    def transform(self, raw: dict) -> list[NormalizedEvent]:
        """Transform raw data into normalized events"""
        pass

    async def run(self) -> list[NormalizedEvent]:
        """Full fetch + transform pipeline"""
        raw = await self.fetch()
        return self.transform(raw)
```

---

## 1. YFinance Collector

**Purpose:** Market context, benchmarks, regime detection

**API:** `yfinance` Python package (no API key needed)

**Implementation:**

```python
import yfinance as yf

class YFinanceCollector(BaseCollector):
    name = "yfinance"
    priority = 1

    SYMBOLS = {
        "SPY": "S&P 500",
        "QQQ": "NASDAQ",
        "XLE": "Energy",
        "VIX": "Volatility"
    }

    async def fetch(self) -> dict:
        data = {}
        for symbol in self.SYMBOLS:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="1d")
            if not hist.empty:
                data[symbol] = {
                    "price": float(hist["Close"].iloc[-1]),
                    "change_pct": float(hist["Close"].pct_change().iloc[-1] * 100)
                }
        return data

    def transform(self, raw: dict) -> list[NormalizedEvent]:
        events = []
        for symbol, info in raw.items():
            events.append(NormalizedEvent(
                id=f"yfinance_{symbol}_{int(time.time())}",
                timestamp=datetime.utcnow().isoformat(),
                source="yfinance",
                category="market",
                entities=[symbol],
                direction="bullish" if info["change_pct"] > 0 else "bearish",
                magnitude=min(abs(info["change_pct"]) / 3, 1.0),  # Normalize to 0-1
                confidence=0.9,
                raw=info
            ))
        return events
```

**Output Example:**

```json
{
  "id": "yfinance_XLE_1710950400",
  "timestamp": "2026-03-20T18:30:00Z",
  "source": "yfinance",
  "category": "market",
  "entities": ["XLE", "energy"],
  "direction": "bullish",
  "magnitude": 0.74,
  "confidence": 0.9
}
```

---

## 2. FRED Collector

**Purpose:** Macro regime, economic health, risk-on/off classification

**API:** `fredapi` package (free API key from fred.stlouisfed.org)

**Implementation:**

```python
class FREDCollector(BaseCollector):
    name = "fred"
    priority = 2

    INDICATORS = {
        "DGS10": "10-Year Treasury",
        "DGS2": "2-Year Treasury",
        "VIXCLS": "VIX",
        "DCOILBRENTEU": "Oil Price"
    }

    def fetch(self) -> dict:
        # Use fredapi or requests to FRED API
        # ...
        return data

    def transform(self, raw: dict) -> list[NormalizedEvent]:
        events = []

        # Yield curve slope
        if "DGS10" in raw and "DGS2" in raw:
            slope = raw["DGS10"] - raw["DGS2"]
            events.append(NormalizedEvent(
                id=f"fred_yield_curve_{int(time.time())}",
                timestamp=datetime.utcnow().isoformat(),
                source="fred",
                category="macro",
                entities=["yield_curve"],
                direction="bullish" if slope > 0 else "bearish",
                magnitude=min(abs(slope) / 2, 1.0),
                confidence=0.85,
                raw={"slope": slope}
            ))

        # VIX regime
        if "VIXCLS" in raw:
            vix = raw["VIXCLS"]
            events.append(NormalizedEvent(
                id=f"fred_vix_{int(time.time())}",
                timestamp=datetime.utcnow().isoformat(),
                source="fred",
                category="macro",
                entities=["volatility"],
                direction="bearish" if vix > 25 else "bullish",
                magnitude=min(vix / 50, 1.0),
                confidence=0.9,
                raw={"vix": vix}
            ))

        return events
```

---

## 3. GDELT Collector

**Purpose:** Global narrative, event-driven signals, sentiment

**API:** GDELT HTTP API (no key needed)

**Implementation:**

```python
class GDELTCollector(BaseCollector):
    name = "gdelt"
    priority = 3

    def fetch(self) -> dict:
        url = (
            "https://api.gdeltproject.org/api/v2/doc/doc?"
            "format=json&mode=artlist&maxrecords=25&"
            "query=stock OR market OR economy OR trade"
        )
        response = requests.get(url, timeout=30)
        return response.json()

    def transform(self, raw: dict) -> list[NormalizedEvent]:
        events = []
        articles = raw.get("articles", [])[:10]  # Top 10

        for article in articles:
            events.append(NormalizedEvent(
                id=f"gdelt_{hash(article['url'])}_{int(time.time())}",
                timestamp=article.get("seendate", ""),
                source="gdelt",
                category="news",
                entities=self._extract_entities(article),
                direction=self._classify_sentiment(article),
                magnitude=self._calculate_intensity(article),
                confidence=0.6,  # Lower confidence for news
                raw=article
            ))
        return events

    def _extract_entities(self, article: dict) -> list[str]:
        # Simple keyword extraction
        text = article.get("title", "") + " " + article.get("snippet", "")
        keywords = []
        for word in ["oil", "tech", "fed", "inflation", "china", "trade"]:
            if word.lower() in text.lower():
                keywords.append(word)
        return keywords or ["general"]
```

---

## 4. EIA Collector

**Purpose:** Energy regime, oil/gas signals, commodities context

**API:** EIA API (free key from eia.gov)

**Implementation:**

```python
class EIACollector(BaseCollector):
    name = "eia"
    priority = 5

    async def fetch(self) -> dict:
        # EIA Petroleum Status Report
        url = "https://api.eia.gov/v2/petroleum/pri/sum/data/"
        params = {"api_key": EIA_API_KEY, "frequency": "weekly"}
        response = requests.get(url, params=params)
        return response.json()

    def transform(self, raw: dict) -> list[NormalizedEvent]:
        events = []

        # Oil inventory change
        # ... parse EIA data ...

        events.append(NormalizedEvent(
            id=f"eia_oil_{int(time.time())}",
            timestamp=datetime.utcnow().isoformat(),
            source="eia",
            category="commodity",
            entities=["oil", "XLE", "energy"],
            direction="bullish" if inventory_change < 0 else "bearish",
            magnitude=min(abs(inventory_change) / 10, 1.0),
            confidence=0.8,
            raw=raw
        ))

        return events
```

---

## 5. Telegram Collector

**Purpose:** Fast sentiment, leaks, breaking news

**API:** Telethon user session (preferred), Bot API as legacy fallback

**Preferred env:**

```bash
TELEGRAM_API_ID=123456
TELEGRAM_API_HASH=your_hash
TELEGRAM_SESSION_NAME=arbiter
TELEGRAM_SOURCE_CHATS=channel_one,channel_two
```

**Implementation:**

```python
class TelegramCollector(BaseCollector):
    name = "telegram"
    priority = 4

    def fetch(self) -> dict:
        # Preferred: Telethon client reads configured chats/channels
        # Legacy fallback: bot polling when only TELEGRAM_BOT_TOKEN exists
        ...

    def transform(self, raw: dict) -> list[NormalizedEvent]:
        events = []

        for msg in raw.get("messages", []):
            if self._is_tradeable(msg):
                events.append(NormalizedEvent(
                    id=f"telegram_{msg['message_id']}_{int(time.time())}",
                    timestamp=datetime.fromtimestamp(msg["date"]).isoformat(),
                    source="telegram",
                    category="social",
                    entities=self._extract_entities(msg),
                    direction=self._classify(msg),
                    magnitude=self._calculate_urgency(msg),
                    confidence=0.5,  # Lower - social signals
                    raw=msg
                ))

        return events
```

---

## Collector Execution

```python
import asyncio

async def run_all_collectors() -> list[NormalizedEvent]:
    collectors = [
        YFinanceCollector(),
        FREDCollector(),
        GDELTCollector(),
        TelegramCollector(),
        EIACollector(),
    ]

    # Run all in parallel, collect successes
    tasks = [collector.run() for collector in collectors]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    all_events = []
    for result in results:
        if isinstance(result, list):
            all_events.extend(result)
        elif isinstance(result, Exception):
            print(f"Collector failed: {result}")

    return all_events
```

---

## Priority Matrix

| Collector | Priority | API Key | Reliability | Signal Quality |
|-----------|----------|---------|-------------|----------------|
| YFinance | 1 | None | High | Market context |
| FRED | 2 | Free | High | Macro regime |
| GDELT | 3 | None | Medium | Narrative |
| Telegram | 4 | Telethon session preferred | Varies | Fast sentiment |
| EIA | 5 | Free | High | Energy |

---

## Error Handling

```python
class CollectorError(Exception):
    """Base exception for collector errors"""
    pass

async def safe_fetch(collector: BaseCollector) -> list[NormalizedEvent]:
    try:
        return await collector.run()
    except Exception as e:
        print(f"[{collector.name}] Error: {e}")
        return []  # Graceful degradation
```
