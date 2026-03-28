# Arbiter Developer Onboarding

Welcome to Arbiter — a real-time trading signal detection and execution system.

---

## What is Arbiter?

Arbiter monitors multiple data sources to detect **energy supply shocks** (geopolitical events, oil disruptions, etc.) and executes trades via Public API or a local paper account.

```
Data Sources          Pipeline              Execution
─────────────────────────────────────────────────────────────────
YFinance      →     Collectors       →    Public API
GDELT        →     Normalize        →    Local Paper
FRED         →     Delta Engine     →    
EIA          →     Signal Scoring   →    
Telegram     →     Decision Engine  →    
Discord      →                          
```

---

## Project Structure

```
Arbiter/
├── src/arbiter/
│   ├── collectors/          # Data ingestion (7 collectors)
│   │   ├── yfinance_collector.py    # Market prices
│   │   ├── gdelt_collector.py     # News events
│   │   ├── fred_collector.py       # Macro (yield curve, VIX)
│   │   ├── eia_collector.py       # Energy (Brent spot)
│   │   ├── telegram_collector.py   # Telethon channels
│   │   └── discord_collector.py    # Discord signals
│   │
│   ├── delta/               # Track new vs repeated events
│   │   ├── compute.py              # Delta calculations
│   │   └── state.py                # Hot memory persistence
│   │
│   ├── strategies/           # Trading strategies
│   │   └── energy_shock/
│   │       ├── strategy.py         # Scoring logic
│   │       ├── decision.py         # Entry/exit decisions
│   │       └── state.py             # Position tracking
│   │
│   ├── execution/            # Trade execution
│   │   ├── client.py               # Backend factory
│   │   ├── public_client.py        # Public.com API
│   │   ├── paper_client.py         # Local paper trading
│   │   └── order_executor.py        # Trade validation
│   │
│   ├── notifications/         # Discord alerts
│   │   └── discord.py             # Webhook notifications
│   │
│   ├── scheduler/            # Main daemon
│   │   └── daemon.py              # Async cycle loop
│   │
│   └── config/
│       └── settings.py            # All environment config
│
├── .env                       # Your API keys (copy from .env.example)
├── pyproject.toml             # Dependencies
└── venv/                     # Virtual environment
```

---

## Key Concepts

### 1. Collectors

Each collector fetches from one data source and returns **NormalizedEvent** objects:

```python
@dataclass
class NormalizedEvent:
    id: str
    timestamp: str
    source: str          # "gdelt", "telegram", "eia", etc.
    category: str       # "market", "news", "social", "macro"
    entities: list[str] # ["oil", "geopolitical"]
    direction: str      # "bullish", "bearish", "neutral"
    magnitude: float    # 0-1
    confidence: float   # 0-1
    raw: dict          # Original data
```

### 2. Delta Engine

Tracks whether events are **new**, **repeated**, or **decayed** across cycles:

```python
# Cycle 1: "oil disruption in Middle East" → NEW
# Cycle 2: "oil disruption intensifies"    → INTENSIFIED  
# Cycle 3: Same story from different source → REPEATED
# Cycle 4: No new oil news                  → DECAYED
```

### 3. Signal Scoring

The Energy Shock strategy scores signals from 5 sources:

| Source | Weight | Purpose |
|--------|--------|---------|
| GDELT | 30% | Geopolitical news |
| EIA | 20% | Brent spot price |
| FRED | 20% | Yield curve, VIX, WTI |
| Telegram | 15% | Fast alerts |
| Discord | 15% | Social signals |

**Formula:**
```
event_pressure = 0.30*gdelt + 0.20*eia + 0.20*fred + 0.15*telegram + 0.15*discord
confidence = 0.50*event_pressure + 0.35*market_confirmation + 0.15*risk_regime
```

### 4. Execution Backends

Two execution options:

| Backend | Config | Use |
|---------|--------|-----|
| **Public API** | `PUBLIC_API_SECRET_KEY` | Live trading |
| **Local Paper** | `EXECUTION_BACKEND=paper`, `PAPER_STARTING_CASH` | Safe simulation |

---

## Development Setup

### 1. Clone and setup

```bash
cd ~/Production/Crucible/Arbiter
cp .env.example .env
python3 -m venv venv
source venv/bin/activate  # or: venv\Scripts\activate on Windows
pip install -r requirements.txt  # or: pip install -e .
```

### 2. Configure API keys

Edit `.env`:

```bash
# Required for Public API trading
PUBLIC_API_SECRET_KEY=your_key_here

# Optional: EIA for energy data
EIA_API_KEY=your_key_here

# Optional: FRED for macro data  
FRED_API_KEY=your_key_here

# Optional: Telegram for fast signals
TELEGRAM_API_ID=12345678
TELEGRAM_API_HASH=your_hash
TELEGRAM_SOURCE_CHATS=@channel1,@channel2
```

### 3. Run tests

```bash
PYTHONPATH=src venv/bin/python3 -m unittest discover tests -v
```

### 4. Run a cycle

```bash
# Dry-run (no trades)
PYTHONPATH=src venv/bin/python3 -m arbiter.scheduler.daemon --dry-run --cycle 60

# Live trading
PYTHONPATH=src venv/bin/python3 -m arbiter.scheduler.daemon --cycle 300
```

---

## Adding a New Collector

### Step 1: Create the collector

```python
# src/arbiter/collectors/my_collector.py

from arbiter.collectors.base import BaseCollector, NormalizedEvent

class MyCollector(BaseCollector):
    name = "my_source"
    priority = 3  # Lower = runs first
    category = "news"

    async def fetch(self) -> dict:
        # Fetch raw data from API
        return await asyncio.to_thread(self._fetch_sync)

    def _fetch_sync(self) -> dict:
        # Synchronous API call
        response = requests.get(...)
        return response.json()

    def transform(self, raw: dict) -> list[NormalizedEvent]:
        events = []
        for item in raw.get("items", []):
            events.append(
                self._make_event(
                    entities=["energy"],  # Keywords found
                    direction="bullish",   # or "bearish"
                    magnitude=0.7,         # 0-1
                    confidence=0.8,        # 0-1
                    raw=item,
                )
            )
        return events
```

### Step 2: Register in daemon

```python
# src/arbiter/scheduler/daemon.py

from arbiter.collectors.my_collector import MyCollector

# In fetch_all_data():
my_task = mycollector.run()
# Add to asyncio.gather()
```

### Step 3: Wire to strategy

```python
# src/arbiter/strategies/energy_shock/strategy.py

def compute_event_pressure(fred_events, gdelt_events, discord_events, telegram_events, eia_events):
    # Add your new source
    my_score = score_my_collector_events(my_events)
    return 0.30*gdelt + 0.20*eia + ... + 0.10*my_score
```

---

## Key Files Reference

| File | Purpose |
|------|---------|
| `daemon.py` | Main loop, cycles every N seconds |
| `decision.py` | Entry/exit logic, position management |
| `strategy.py` | Signal scoring, thresholds |
| `settings.py` | All config, env vars |
| `public_client.py` | Public.com API wrapper |
| `discord.py` | Trade notifications |

---

## Common Tasks

### Change trading symbol

Edit `src/arbiter/strategies/energy_shock/strategy.py`:

```python
@dataclass
class StrategyConfig:
    trade_symbol: str = "XLE"  # Change to USO, XOM, etc.
```

### Adjust confidence threshold

```python
@dataclass  
class StrategyConfig:
    trade_confidence_min: float = 0.68  # Lower = more aggressive
```

### Add new Telegram channel

Edit `.env`:

```bash
TELEGRAM_SOURCE_CHATS=@bloomberg,@marketsAlpha,@newChannel
```

---

## Architecture Decisions

- **Async all the things**: All collectors run in parallel via `asyncio.gather()`
- **Delta over raw**: Events go through delta engine to detect escalation
- **Confidence gates**: Won't trade without meeting all thresholds
- **Dry-run default**: Safe by default, explicit `--dry-run=false` for live

---

## Questions?

1. Check `docs/ARCHITECTURE.md` for system design
2. Check `docs/ROADMAP.md` for future plans
3. Check source code comments for implementation details
