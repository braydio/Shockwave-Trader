# Arbiter — User Guide

Arbiter is an automated trading system that watches for **energy supply shocks** (geopolitical events, oil disruptions, refinery outages) and trades XLE (Energy Select Sector Fund) when conditions are right.

---

## What Does It Do?

```
Monitors:                    Detects:                    Then:
────────────────────────────────────────────────────────────────────
• Oil prices (EIA)         Energy supply shock      BUY XLE
• Geopolitical news (GDELT) + Market confirms      
• Macro data (FRED)         = Trade signal          
• Telegram/Discord                                    
• Market prices (YFinance)                           
```

---

## Quick Start

### 1. Setup

```bash
cd ~/Production/Crucible/Arbiter
cp .env.example .env
```

### 2. Add Your API Keys

Edit `.env` with your keys:

| Key | Required | Where to Get |
|-----|----------|--------------|
| `PUBLIC_API_SECRET_KEY` | Yes | [Public.com](https://public.com) |
| `EIA_API_KEY` | Recommended | [EIA.gov](https://eia.gov) (free) |
| `FRED_API_KEY` | Recommended | [Fred.StLouisFed.org](https://fred.stlouisfed.org) (free) |
| `TELEGRAM_API_ID`, `TELEGRAM_API_HASH` | Optional | [My.Telegram.org](https://my.telegram.org) |

### 3. Run

```bash
# Dry-run mode (watches but doesn't trade)
PYTHONPATH=src venv/bin/python3 -m arbiter.scheduler.daemon --dry-run --cycle 300

# Live trading
PYTHONPATH=src venv/bin/python3 -m arbiter.scheduler.daemon --cycle 300
```

Press `Ctrl+C` to stop.

---

## Understanding the Output

When Arbiter runs, you'll see:

```
Market
  XLE  : $   61.52  +1.25%
  SPY  : $  645.09  +0.32%
  VIXY : $   35.49  -2.10%

Signal
  Confidence: 0.72
  Event:      0.65
  Market:     0.58
  Regime:     0.82

FRED: 3 | EIA: 1 | GDELT: 5 | Telegram: 3 | Delta: 2
Backend: Public API | Mode: DRY RUN
```

### What Each Means:

| Field | Meaning | What You Want |
|-------|---------|---------------|
| **Confidence** | Overall signal strength (0-1) | > 0.68 to trade |
| **Event** | Geopolitical/macro pressure | High = news supporting trade |
| **Market** | XLE outperforming SPY | High = price confirms |
| **Regime** | Low VIX + SPY up | > 0.5 = good environment |

### Status Messages:

| Status | Meaning |
|--------|---------|
| **HOLD** | Conditions not met — waiting |
| **BUY** | Entering position |
| **SELL** | Exiting position |

---

## What Triggers a Trade?

Arbiter only buys when ALL of these are true:

1. **Event Pressure** ≥ 0.65
   - Geopolitical news about oil/supply
   - Telegram alerts mentioning energy
   - EIA showing supply concerns

2. **Market Confirmation** ≥ 0.60
   - XLE up > 0.8%
   - USO confirming
   - XLE outperforming SPY

3. **Risk Regime** ≥ 0.50
   - VIX < 24 (not panic)
   - SPY not crashing

4. **Confidence** ≥ 0.68
   - Weighted score combining all above

---

## Exit Rules

Arbiter sells when:

| Rule | Trigger |
|------|---------|
| Stop Loss | -2.5% loss |
| Take Profit | +4% gain |
| Trailing Stop | After take profit, -1.5% from peak |
| Max Holding | 5 days |
| Thesis Broken | Event pressure < 0.35 AND market < 0.40 |

---

## Risk Controls

- **Max position**: 20% of account equity
- **Cooldown**: 4 hours between trades
- **Max daily trades**: 10 per day
- **Default trade size**: $500

---

## Data Sources

| Source | What It Monitors | Update Frequency |
|--------|------------------|------------------|
| **EIA** | Brent crude spot price | Daily |
| **FRED** | Yield curve, VIX, WTI oil | Daily |
| **GDELT** | Global news about oil/energy | Every cycle |
| **Telegram** | Fast alerts from channels | Every cycle |
| **YFinance** | XLE, SPY, USO, VIXY prices | Every cycle |

---

## Troubleshooting

### "Confidence below threshold"

Normal — means no clear energy shock signal. Arbiter is being patient.

### "No position"

You're not in a trade. Good — means it's waiting for the right setup.

### "Event pressure: 0.00"

No geopolitical events detected. Also normal on quiet news days.

### Rate limit errors (GDELT)

Normal — GDELT limits requests. Arbiter caches results for 1 hour.

### Want to see more frequent cycles?

```bash
--cycle 60   # Every 60 seconds (fast)
--cycle 300  # Every 5 minutes (default)
--cycle 900   # Every 15 minutes (relaxed)
```

---

## Notifications

When a trade happens, Discord gets a message:

- **Entry**: Symbol, side, quantity, price, confidence
- **Exit**: Symbol, P&L %, exit reason
- **Errors**: What went wrong

Configure in `.env`:

```bash
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
DISCORD_NOTIFICATIONS_ENABLED=true
```

---

## Command Reference

```bash
--dry-run          # Watch only, no trades (RECOMMENDED first)
--cycle 300       # Run every N seconds (default: 300)
--backend public   # Use Public.com API
--backend paper   # Use local paper trading
```

---

## Want to Change Settings?

Edit `src/arbiter/strategies/energy_shock/strategy.py`:

```python
@dataclass
class StrategyConfig:
    # Lower to trade more often
    trade_confidence_min: float = 0.68
    
    # Adjust risk parameters
    stop_loss_pct: float = 0.025    # 2.5% stop
    take_profit_pct: float = 0.04   # 4% profit target
    
    # Trade size
    base_usd: float = 500.00
    max_position_pct: float = 0.20  # 20% of account
```

---

## Need Help?

- Check `docs/ARCHITECTURE.md` for how it works
- Check `docs/ROADMAP.md` for future plans
- Run with `--dry-run` to test safely first
