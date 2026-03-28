# Arbiter

**Ingestion → Signal → Execution Framework**

Trade when the world changes and the market confirms it.

---

## What is Arbiter?

Arbiter is a trading system that:

1. **Collects** data from multiple sources (news, social, macro, market)
2. **Detects changes** using delta logic (new vs. repeated vs. decayed)
3. **Scores** signals using configurable strategies
4. **Executes** trades via Public API or a local paper account with risk controls

```
Collectors → Normalize → Delta Engine → Signal Engine → Execution Backend
```

---

## Strategy 01: Energy Shock Confirmation

**Trade thesis:** When geopolitical or supply-side stress pushes oil-risk higher, and market price action confirms it, rotate into liquid energy exposure.

### Three-Layer Alignment

| Layer | Source | Question |
|-------|--------|----------|
| Narrative/Catalyst | GDELT + FRED + EIA | Is there real-world oil supply risk? |
| Market Confirmation | YFinance (XLE, USO, SPY) | Is the market agreeing? |
| Regime Filter | VIX + SPY | Is the environment suitable for risk? |

### Entry Rules

```
event_pressure >= 0.65
market_confirmation >= 0.60
risk_regime >= 0.50
signal_confidence >= 0.68
+ no position + not in cooldown
```

### Exit Rules

- **Stop loss:** -2.5%
- **Take profit:** +4% (exit 50%, trailing stop on remainder)
- **Thesis deterioration:** event < 0.35 AND market < 0.40
- **Max holding:** 5 trading days

---

## Quick Start

### 1. Install

```bash
cd ~/Production/Crucible/Arbiter
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 2. Configure

```bash
cp .env.example .env
```

Edit `.env` with your API keys:

```bash
# Public API
PUBLIC_API_ACCESS_TOKEN=your_public_access_token
PUBLIC_API_SECRET_KEY=your_public_secret_key

# Discord (optional - get webhook from Discord channel settings)
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
DISCORD_NOTIFICATIONS_ENABLED=true
DISCORD_BOT_TOKEN=your_discord_bot_token
DISCORD_SIGNAL_CHANNELS=123456789012345678,234567890123456789

# Telegram via Telethon (preferred for channel/group reads)
TELEGRAM_API_ID=123456
TELEGRAM_API_HASH=your_telegram_api_hash
TELEGRAM_SESSION_NAME=arbiter
TELEGRAM_SOURCE_CHATS=channel_one,channel_two
```

Keep only one definition per env var. If a key appears twice in `.env`, the later entry wins.

### 3. Test CLI

```bash
python main.py
```

### 4. Run Daemon

```bash
# Dry run (no trades)
python -m arbiter.scheduler.daemon --dry-run --cycle 60

# Local paper trading
python -m arbiter.scheduler.daemon --backend paper --cycle 300

# Live with Public API
python -m arbiter.scheduler.daemon --backend public --cycle 300
```

---

## Execution Backends

Arbiter supports multiple execution backends:

| Backend | Config | Best For |
|---------|--------|----------|
| **Public API** | `PUBLIC_API_ACCESS_TOKEN` or `PUBLIC_API_SECRET_KEY` | Live Public brokerage trading |
| **Local Paper** | `EXECUTION_BACKEND=paper`, `PAPER_STARTING_CASH` | Brokerless local simulation |

### Selecting Backend

```bash
# Auto-detect (default - uses Public if configured, otherwise paper)
python -m arbiter.scheduler.daemon

# Explicit selection
python -m arbiter.scheduler.daemon --backend public
python -m arbiter.scheduler.daemon --backend paper
```

---

## Discord Notifications

Get alerts for trades and signals in Discord:

1. In Discord, go to channel settings → Integrations → Webhooks
2. Create webhook, copy URL
3. Add to `.env`:

```bash
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/your_webhook_id/token
DISCORD_NOTIFICATIONS_ENABLED=true
```

### Alert Types

| Level | Trigger | Message |
|-------|---------|---------|
| 🚀 ENTRY | Trade opened | Symbol, qty, price, confidence, reasoning |
| 🏁 EXIT | Trade closed | Symbol, P&L, exit reason |
| ⚠️ ERROR | System error | Error message, cycle number |

---

## Running Modes

### Interactive CLI

```bash
python main.py
```

Options:
- [1] Market Data - View current prices
- [2] Account Info - View account
- [3] Open Positions - View current holdings

### Background Daemon (tmux)

```bash
# Start in tmux
tmux new -s arbiter
python -m arbiter.scheduler.daemon --backend public --cycle 300

# Detach: Ctrl+B, D

# Reattach later
tmux attach -t arbiter
```

### Systemd Service (Production)

Create `/etc/systemd/system/arbiter.service`:

```ini
[Unit]
Description=Arbiter Trading Daemon
After=network.target

[Service]
Type=simple
User=braydenchaffee
WorkingDirectory=/home/braydenchaffee/Production/Crucible/Arbiter
ExecStart=/home/braydenchaffee/Production/Crucible/Arbiter/.venv/bin/python -m arbiter.scheduler.daemon --backend public
Restart=always
RestartSec=10
Environment="PUBLIC_API_ACCESS_TOKEN=xxx"

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable arbiter
sudo systemctl start arbiter
sudo systemctl status arbiter
```

---

## Configuration

### Environment Variables

```bash
# Execution Backend
EXECUTION_BACKEND=auto                    # auto, public, or paper
PUBLIC_API_ACCESS_TOKEN=your_public_access_token
PUBLIC_API_SECRET_KEY=your_public_secret_key
PUBLIC_API_BASE=https://api.public.com

PAPER_STARTING_CASH=10000                # Local paper account starting balance
PAPER_STATE_FILE=storage/paper_account.json

# Execution
MAX_POSITION_PCT=0.2                     # Max 20% per trade
COOLDOWN_HOURS=24                        # Hours between trades
DEFAULT_TRADE_AMOUNT=500                 # Base trade size

# Notifications
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
DISCORD_NOTIFICATIONS_ENABLED=true

# Scheduler
CYCLE_INTERVAL_SECONDS=300               # 5 minutes

# Free API Keys
FRED_API_KEY=your_fred_key              # fred.stlouisfed.org
EIA_API_KEY=your_eia_key                # eia.gov
```

### Strategy Config

Edit `src/arbiter/strategies/energy_shock/config.yaml`:

```yaml
thresholds:
  event_pressure_min: 0.65
  market_confirmation_min: 0.60
  risk_regime_min: 0.50
  trade_confidence_min: 0.68

risk:
  stop_loss_pct: 0.025
  take_profit_pct: 0.04
  trailing_stop_pct: 0.015
  max_holding_days: 5
```

---

## Project Structure

```
arbiter/
├── docs/                          # Strategy & architecture docs
│   ├── ARCHITECTURE.md
│   ├── STRATEGY-01-ENERGY-SHOCK.md
│   ├── COLLECTORS.md
│   └── EXECUTION.md
├── src/arbiter/
│   ├── collectors/                 # Data ingestion
│   │   ├── base.py               # BaseCollector + NormalizedEvent
│   │   ├── yfinance_collector.py # Market data
│   │   ├── gdelt_collector.py    # News/events
│   │   ├── fred_collector.py     # Macro data
│   │   └── eia_collector.py      # Energy data
│   ├── notifications/
│   │   └── discord.py            # Discord alerts
│   ├── strategies/
│   │   └── energy_shock/         # Strategy 01
│   │       ├── strategy.py       # Scoring functions
│   │       ├── state.py          # Position management
│   │       └── config.yaml       # Strategy config
│   ├── execution/
│   │   ├── client.py             # Backend selector
│   │   ├── public_client.py      # Public API client
│   │   └── paper_client.py      # Local paper account
│   ├── scheduler/
│   │   └── daemon.py             # Background runner
│   ├── config/
│   │   └── settings.py          # Configuration
│   └── lib/
│       ├── errors.py
│       └── logger.py
├── storage/                        # State & logs
├── main.py                         # CLI entry point
├── .env.example
└── pyproject.toml
```

---

## Data Flow

```
┌─────────────┐
│  Collectors │  ← YFinance, GDELT, FRED, EIA
└──────┬──────┘
       ▼
┌─────────────┐
│  Normalize  │  → Canonical event schema
└──────┬──────┘
       ▼
┌─────────────┐
│   Signal    │  → EnergySignal with confidence
└──────┬──────┘
       ▼
┌─────────────┐
│ Execution   │  → Public API or local paper
└─────────────┘
       │
       ▼
┌─────────────┐
│  Discord    │  → Trade alerts
└─────────────┘
```

---

## Logging

Logs are written to:
- `storage/logs/` - Event and trade logs
- `storage/*.json` - Cached data
- `storage/energy_shock_state.json` - Position state

View logs:
```bash
tail -f storage/logs/arbiter.daemon_*.log
```

---

## Dependencies

```
requests>=2.28.0
python-dotenv>=1.0.0
yfinance>=0.2.0
rich>=13.0.0
pyyaml>=6.0
```

---

## Disclaimer

**This is for educational purposes only. Trading involves risk. Past performance does not guarantee future results. Always do your own research and never trade more than you can afford to lose.**

---

## License

MIT
