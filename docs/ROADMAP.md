# Arbiter Roadmap & Architecture Decisions

## Communication Strategy

Arbiter uses Discord for two purposes:

| Purpose | Module | Description |
|---------|--------|-------------|
| **Notifications** | `notifications/discord.py` | Trade alerts, signals, errors |
| **Signals** | `collectors/discord_collector.py` | Read messages → signal input |

---

## Discord And Telegram

### For Notifications
- Already integrated into workflow
- Cleaner alert formatting
- Easier to manage

### For Signals
- Discord is **cleaner and safer** than Telegram
- Telegram is noisy: pump groups, scams, garbage signals
- Discord servers are more curated
- You control the signal sources

### Telegram (active secondary feed)
Telegram is better for:
- OSINT/firehose of early signals
- Breaking news channels
- Crypto signal groups

**Decision:** Keep Discord for notifications and curated social inputs. Add Telegram as an explicit fast-signal intake, using Telethon for channel/group reads.

---

## Signal Sources (Priority Order)

| Priority | Source | Module | Status |
|----------|--------|--------|--------|
| 1 | YFinance (market data) | `yfinance_collector.py` | ✅ Working |
| 2 | GDELT (news/events) | `gdelt_collector.py` | ✅ Working |
| 3 | FRED (macro) | `fred_collector.py` | ✅ Working |
| 4 | EIA (energy) | `eia_collector.py` | ✅ Working |
| 5 | Discord (social) | `discord_collector.py` | ✅ Configured |
| 6 | Telegram (fast social) | `telegram_collector.py` | ✅ Working (Telethon) |

---

## Implementation Phases

### Phase 1: Core (DONE)
- [x] YFinance market data
- [x] GDELT news collector
- [x] Energy Shock strategy
- [x] Public API backend
- [x] Local paper backend
- [x] Discord notifications
- [x] Basic daemon

### Phase 2: Signals (DONE)
- [x] Discord collector (read messages → signals)
- [x] FRED collector integration
- [x] EIA collector integration
- [x] Delta engine (new vs repeated vs decayed)
- [x] Telegram collector migration from Bot API to Telethon

### Phase 3: Polish (IN PROGRESS)
- [ ] Backtesting module
- [x] CLI status display
- [x] Discord webhook notifications
- [x] Dry-run mode for safe testing

---

## Discord Collector Spec

### Purpose
Read messages from Discord channels → convert to signal events

### Sources
1. **Financial news bots** - automated news feeds
2. **Trading community channels** - sentiment + chatter
3. **Custom bot outputs** - FundRunner signal logs

### Minimal Implementation

```python
class DiscordCollector:
    """Read messages from Discord → signal events."""
    
    name = "discord"
    priority = 4
    category = "social"
    
    async def fetch(self) -> list[dict]:
        # Read messages from configured channels
        # Return raw message dicts
        pass
    
    def transform(self, messages: list[dict]) -> list[NormalizedEvent]:
        # Classify sentiment
        # Extract entities (oil, energy, etc.)
        # Return NormalizedEvent list
```

### Message → Signal Classification

Simple keyword approach:
```python
BULLISH_KEYWORDS = ["oil", "crude", "energy", "supply disruption"]
BEARISH_KEYWORDS = ["demand", "oversupply", "recession"]

def classify(text):
    if any(k in text for k in BULLISH_KEYWORDS):
        return "bullish"
    if any(k in text for k in BEARISH_KEYWORDS):
        return "bearish"
    return "neutral"
```

---

## Data Flow (Updated)

```
┌─────────────────────────────────────┐
│           COLLECTORS                 │
├─────────────────────────────────────┤
│  YFinance ──► Market confirmation   │
│  GDELT ──────► News/events          │
│  FRED ───────► Macro regime         │
│  EIA ────────► Energy context       │
│  Discord ────► Social sentiment      │
└──────────────┬──────────────────────┘
               ▼
┌─────────────────────────────────────┐
│         NORMALIZE                    │
│    Canonical event schema            │
└──────────────┬──────────────────────┘
               ▼
┌─────────────────────────────────────┐
│           DELTA ENGINE                │
│   New / Intensified / Decayed       │
└──────────────┬──────────────────────┘
               ▼
┌─────────────────────────────────────┐
│         SIGNAL ENGINE                │
│    Energy Shock Scoring              │
└──────────────┬──────────────────────┘
               ▼
┌─────────────────────────────────────┐
│          EXECUTION                   │
│   Public API or Local Paper         │
└──────────────┬──────────────────────┘
               ▼
┌─────────────────────────────────────┐
│          NOTIFICATIONS               │
│   Discord → Trade alerts            │
└─────────────────────────────────────┘
```

---

## Telegram Process Notes

Telegram is now part of the collection plan, with these guardrails:

### Sources
- News channels (Reuters, Bloomberg)
- Trading signal channels
- Geopolitical feeds

### Preferred access model
- Use Telethon user sessions for read access to channels/groups
- Keep Bot API support only as a fallback path
- Track monitored chats in `TELEGRAM_SOURCE_CHATS`
- Keep session naming stable with `TELEGRAM_SESSION_NAME`

### Trade-offs
| Pros | Cons |
|------|------|
| Faster breaking signals | Very noisy |
| More raw data | Scams/pumps |
| Crypto-friendly | Harder to filter |

**Decision:** Telegram stays additive, not primary. It should increase speed without overruling higher-confidence market and macro confirmation.

---

## Key Files

| File | Purpose |
|------|---------|
| `src/arbiter/collectors/telegram_collector.py` | Telegram → signals (Telethon) |
| `src/arbiter/collectors/discord_collector.py` | Discord → signals |
| `src/arbiter/notifications/discord.py` | Arbiter → Discord |
| `src/arbiter/scheduler/daemon.py` | Main loop |

---

## Next Steps

1. **Test current daemon** with Public API + Discord notifications
2. **Run live trading** when ready (remove --dry-run)
3. **Add backtesting** for strategy validation
