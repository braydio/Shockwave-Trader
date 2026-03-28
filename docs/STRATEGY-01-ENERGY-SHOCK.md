# Strategy 01: Energy Shock Confirmation

**Trade thesis:** When geopolitical or supply-side stress pushes oil-risk higher, and market price action confirms it, rotate into liquid energy exposure.

---

## Core Concept

Trade when **three layers align**:

| Layer | Source | Question |
|-------|--------|----------|
| **A** - Narrative/Catalyst | GDELT + Telegram + EIA | Is there real-world oil supply risk? |
| **B** - Market Confirmation | YFinance (XLE, USO, SPY) | Is the market agreeing? |
| **C** - Regime Filter | VIX + SPY | Is the environment suitable for risk? |

```
world event → oil risk thesis → market confirms → execute constrained energy trade
```

---

## Tradable Universe

| Instrument | Role | Priority |
|------------|------|----------|
| **XLE** | Primary trade | Required |
| USO | Crude proxy | Optional confirmation |
| SPY | Market context | Required for regime |
| VIX | Panic filter | Required for regime |

---

## Strategy Thesis Categories

### Bucket A — Supply Disruption
- Refinery outage
- Pipeline disruption
- Production cut
- Export interruption
- Infrastructure damage

### Bucket B — Geopolitical Escalation
- Conflict near oil-producing regions
- Sanctions affecting supply
- Shipping route instability
- Military escalation near chokepoints

### Bucket C — Inventory Tightening
- Bullish EIA inventory draw
- Repeated inventory declines
- Supply-side surprise

### Bucket D — Narrative Acceleration
- Multiple sources discussing oil squeeze
- Energy spike headlines
- Shipping disruption chatter

---

## Scoring Model

### Event Pressure Score (0.0 - 1.0)

```python
event_pressure = (
    0.45 * gdelt_score +
    0.30 * telegram_score +
    0.25 * eia_event_score
)
```

### Market Confirmation Score (0.0 - 1.0)

```python
market_confirmation = weighted score of:
- XLE > +0.8% today
- USO > +1.0% today
- XLE outperforming SPY by > 0.75%
```

### Risk Regime Score (0.0 - 1.0)

```python
risk_regime_score = {
    VIX < 20 and SPY stable → 1.0 (good)
    VIX 20-24 or SPY weak → 0.5 (cautious)
    VIX > 24 or SPY selloff → 0.0 (blocked)
}
```

### Signal Confidence

```python
signal_confidence = (
    0.50 * event_pressure +
    0.35 * market_confirmation +
    0.15 * risk_regime_score
)
```

---

## Entry Logic

**All conditions must be true:**

| Condition | Threshold | Source |
|-----------|-----------|--------|
| Catalyst is real | `event_pressure >= 0.65` | GDELT + Telegram + EIA |
| Market agreeing | `market_confirmation >= 0.60` | YFinance |
| Environment suitable | `risk_regime >= 0.50` | VIX + SPY |
| Freshness | New/intensified event in 6h | Delta engine |
| Cooldown | No XLE buy in 24h | Trade log |

**Final filter:** `signal_confidence >= 0.68`

---

## Exit Logic

| Exit Type | Trigger | Action |
|-----------|---------|--------|
| **Thesis Deterioration** | `event_pressure < 0.35` AND `market_confirmation < 0.40` | Exit full |
| **Stop Loss** | Position PnL <= -2.5% | Exit full |
| **Take Profit** | Position PnL >= +4% | Exit 50%, trailing stop on remainder |
| **Trailing Stop** | Price drops 1.5% from peak | Exit remaining |
| **Max Holding** | 5 trading days without intensification | Exit full |

---

## Position Sizing

```python
base_size = min($500, 5% of strategy capital)

size_multiplier = min(1.0, 0.5 + 0.5 * signal_confidence)

final_size = base_size * size_multiplier
```

**Reduce size if:**
- VIX between 20-24
- SPY weak
- Confirmation barely above threshold

---

## Delta Logic

| Delta Type | Weight | Treatment |
|------------|--------|-----------|
| `new` | 1.00 | Strong positive |
| `intensified` | 1.20 | Very strong positive |
| `repeated` | 0.25 | Small positive |
| `decayed` | -0.60 | Negative |
| `duplicate` | 0.00 | No contribution |

---

## Event Tags

Important tags for energy strategy:

```
supply_disruption
inventory_draw
shipping_risk
geopolitical_escalation
sanctions_supply_risk
refinery_outage
middle_east
opec
```

---

## Example Decision

**Scenario:**
- GDELT: spike in tanker disruption + conflict escalation
- Telegram: route stress + export interruption chatter
- EIA: bullish inventory draw
- XLE: +1.2%
- USO: +1.8%
- SPY: flat
- VIX: 18.7

**Scores:**
```
event_pressure = 0.78
market_confirmation = 0.74
risk_regime_score = 0.87

signal_confidence = 0.50*0.78 + 0.35*0.74 + 0.15*0.87 = 0.78
```

**Decision:** BUY XLE

**Explanation:**
> "Bought XLE because energy supply-risk narrative intensified across GDELT and Telegram, EIA inventory data supported tightening conditions, and market price action confirmed the thesis with XLE and USO both outperforming."

---

## Implementation Functions

```python
score_gdelt_energy_events(events) -> float
score_telegram_energy_events(events) -> float
score_eia_energy_context(events) -> float
score_market_confirmation(prices) -> float
score_risk_regime(vix, spy_trend) -> float
build_energy_signal(event_pressure, market_confirmation, risk_regime) -> dict
check_entry_conditions(signal, positions, cooldowns) -> bool
check_exit_conditions(position, signal) -> str
```

---

## v2 Extensions

| Extension | Description |
|-----------|-------------|
| v2a | ACLED/conflict feed for geopolitical classification |
| v2b | Ships/chokepoints for direct shipping disruption detection |
| v2c | Pair trade mode (long XLE / short IWM) |
| v2d | Options mode for high-confidence signals |
