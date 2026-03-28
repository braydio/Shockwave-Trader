# Arbiter Architecture

**Ingestion → Signal → Execution Framework**

*Derived from Crucix intelligence architecture, adapted for trade decision + execution*

---

## Overview

Arbiter is NOT a dashboard system. It's a decision engine:

```
Collectors → Normalize → Delta Engine → Signal Engine → Public API Execution
```

Every component exists to answer one question: **"What's worth trading right now, and why?"**

---

## System Layout

```
arbiter/
├── collectors/          # External data ingestion (Crucix-style)
├── normalize/          # Raw → canonical event schema
├── delta/              # Change detection + memory
├── signals/            # Scoring + strategy logic
├── execution/          # Public API + trade lifecycle
├── storage/            # SQLite / Parquet / Chroma
├── scheduler/          # Orchestration loop
├── config/             # Thresholds + API keys
└── strategies/         # Named trading strategies
```

---

## Core Philosophy

| Crucix | Arbiter |
|--------|---------|
| Watch the world | Trade with purpose |
| Situational awareness | Decision quality |
| Dashboard theater | Signal + execution |
| Many feeds | Right feeds |

**Rule:** Steal the ingestion, normalization, and delta logic. Do not steal the visual identity.

---

## Data Flow

```
┌─────────────┐    ┌────────────┐    ┌─────────┐    ┌──────────┐    ┌───────────┐
│  Collectors │───▶│ Normalize  │───▶│  Delta  │───▶│  Signal  │───▶│ Execution │
│  (parallel) │    │  (schema)  │    │ Engine  │    │  Engine  │    │  (Public) │
└─────────────┘    └────────────┘    └─────────┘    └──────────┘    └───────────┘
       │                                                    │
       ▼                                                    ▼
   External APIs                                      Trade Decisions
   - yfinance                                         - Validated
   - FRED                                             - Sized
   - GDELT                                            - Logged
   - Telegram
   - EIA
```

---

## Collector Contract

Every collector MUST follow this interface:

```python
class BaseCollector:
    name: str
    priority: int  # 1 = highest

    async def fetch(self) -> dict:
        """Raw fetch from API"""

    async def transform(self, raw: dict) -> list[dict]:
        """Return list of normalized events"""
```

---

## Canonical Event Schema

Everything normalizes to ONE schema:

```python
NormalizedEvent = {
    "id": str,              # source_timestamp_hash
    "timestamp": str,       # ISO 8601
    "source": str,          # yfinance, fred, gdelt, etc.

    "category": str,        # market | macro | news | social | commodity

    "entities": list[str],  # ["oil", "XLE", "inflation"]
    "direction": str,       # bullish | bearish | neutral

    "magnitude": float,     # 0 → 1
    "confidence": float,    # 0 → 1

    "raw": dict            # Original payload
}
```

---

## Delta Engine

**This is the secret sauce.** Detect **change**, not just data.

### Delta Types

| Type | Condition |
|------|----------|
| `new` | Never seen before |
| `intensified` | Magnitude increased > 0.2 |
| `weakened` | Magnitude decreased > 0.2 |
| `repeated` | Same event again |
| `decayed` | Old event fading |

### State Storage

```
storage/
├── last_events.json      # Previous run snapshot
├── hot_memory.json       # Recent significant events
└── cold_memory.parquet   # Historical archive
```

---

## Signal Engine

### Entity Aggregation

```python
entity_scores = {
    "oil": 0.78,
    "tech": -0.32,
    "XLE": 0.81
}
```

### Multi-Source Confirmation

```python
if signal_confirmed_by(oil, sources=[gdelt, eia, yfinance]):
    confidence *= 1.5  # Boost confidence
```

### Strategy Layer

```python
class EnergyMomentum(Strategy):
    def evaluate(self, signals) -> TradeDecision:
        if entity_scores["oil"] > 0.7 and macro_regime != "risk_off":
            return TradeDecision(symbol="XLE", side="buy", confidence=0.82)
```

---

## Execution (Public API)

### Trade Decision Object

```python
TradeDecision = {
    "symbol": str,
    "side": "buy" | "sell",
    "amount_usd": float,
    "confidence": float,
    "reasoning": str
}
```

### Execution Rules

- Cooldown per symbol (configurable)
- Max exposure limits
- Duplicate position prevention
- Pre-trade sanity check (price movement)

### Execution Flow

```
Signal → Validate → Size → Execute → Log
```

---

## Scheduler Loop

```python
while True:
    events = await run_all_collectors()     # Parallel fetch
    normalized = normalize(events)           # Schema transform
    deltas = compute_deltas(normalized)     # Change detection
    signals = generate_signals(deltas)      # Scoring
    trades = decide_trades(signals)         # Strategy

    execute(trades)

    sleep(300)  # 5 minute cycles
```

---

## Priority Collectors

| Priority | Collector | Purpose |
|----------|-----------|---------|
| 1 | yfinance | Market context |
| 2 | fred | Macro regime |
| 3 | gdelt | Global narrative |
| 4 | telegram | Fast sentiment |
| 5 | eia | Energy macro |

---

## What Makes Arbiter Win

You are NOT building:
> "Cool world dashboard"

You ARE building:
> "System that notices change → reasons → executes → explains"
