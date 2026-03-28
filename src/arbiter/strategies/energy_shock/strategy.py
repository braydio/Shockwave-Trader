"""Energy Shock Confirmation Strategy - Strategy 01.

Trade when geopolitical/supply-side stress pushes oil-risk higher
and market price action confirms it.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Optional
import json
from pathlib import Path

from arbiter.collectors.base import NormalizedEvent
from arbiter.lib.logger import setup_logger


logger = setup_logger("energy_shock")


class TradeAction(Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"
    EXIT = "exit"


class ExitReason(Enum):
    THESIS_DETERIORATION = "thesis_deterioration"
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"
    TRAILING_STOP = "trailing_stop"
    MAX_HOLDING = "max_holding"
    NONE = "none"


# Energy-relevant event tags
ENERGY_TAGS = {
    "supply_disruption",
    "inventory_draw",
    "shipping_risk",
    "geopolitical_escalation",
    "sanctions_supply_risk",
    "refinery_outage",
    "middle_east",
    "opec",
    "pipeline",
    "tanker",
    "chokepoint",
    "crude",
    "oil",
    "energy",
    "nat_gas",
    "gasoline",
}

# Entity keywords that suggest energy relevance
ENERGY_ENTITIES = {
    "oil",
    "energy",
    "xle",
    "uso",
    "crude",
    "opec",
    "brent",
    "wti",
    "saudi",
    "iran",
    "iraq",
    "russia",
    "pipelines",
    "tanker",
    "refinery",
    "nat gas",
    "lng",
    "petroleum",
    "energy sector",
    "middle east",
    "persian gulf",
    "strait of hormuz",
    "suez canal",
}


@dataclass
class EnergySignal:
    """Signal output from energy strategy."""

    action: TradeAction
    confidence: float
    event_pressure: float
    market_confirmation: float
    risk_regime: float
    reasoning: str
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass
class PositionState:
    """Current position state for exit decisions."""

    symbol: str
    entry_price: float
    entry_date: datetime
    quantity: float
    peak_price: float = 0.0
    partial_exited: bool = False


@dataclass
class StrategyConfig:
    """Configuration for energy shock strategy."""

    # Entry thresholds
    event_pressure_min: float = 0.65
    market_confirmation_min: float = 0.60
    risk_regime_min: float = 0.50
    trade_confidence_min: float = 0.68

    # Risk parameters
    stop_loss_pct: float = 0.025
    take_profit_pct: float = 0.04
    trailing_stop_pct: float = 0.015
    max_holding_days: int = 5
    cooldown_hours: int = 24

    # Sizing
    base_usd: float = 500.0
    max_position_pct: float = 0.05

    # Symbols
    trade_symbol: str = "XLE"
    confirm_symbols: list = field(default_factory=lambda: ["USO", "SPY", "VIXY"])

    # Freshness
    freshness_window_hours: int = 6

    @classmethod
    def from_dict(cls, config: dict) -> "StrategyConfig":
        """Create from dictionary."""
        return cls(
            event_pressure_min=config.get("event_pressure_min", 0.65),
            market_confirmation_min=config.get("market_confirmation_min", 0.60),
            risk_regime_min=config.get("risk_regime_min", 0.50),
            trade_confidence_min=config.get("trade_confidence_min", 0.68),
            stop_loss_pct=config.get("stop_loss_pct", 0.025),
            take_profit_pct=config.get("take_profit_pct", 0.04),
            trailing_stop_pct=config.get("trailing_stop_pct", 0.015),
            max_holding_days=config.get("max_holding_days", 5),
            cooldown_hours=config.get("cooldown_hours", 24),
            base_usd=config.get("base_usd", 500.0),
            max_position_pct=config.get("max_position_pct", 0.05),
            trade_symbol=config.get("trade_symbol", "XLE"),
            confirm_symbols=config.get("confirm_symbols", ["USO", "SPY", "VIXY"]),
            freshness_window_hours=config.get("freshness_window_hours", 6),
        )


def is_energy_related(event: NormalizedEvent) -> bool:
    """Check if event is energy-related."""
    event_entities = {e.lower() for e in event.entities}
    event_tags = {t.lower() for t in event.raw.get("tags", [])}

    # Check entities
    for keyword in ENERGY_ENTITIES:
        if keyword in event_entities:
            return True

    # Check tags
    if event_tags & ENERGY_TAGS:
        return True

    # Check raw text for keywords
    raw_text = json.dumps(event.raw).lower()
    for keyword in ["oil", "energy", "crude", "opec", "tanker", "pipeline"]:
        if keyword in raw_text:
            return True

    return False


def score_gdelt_energy_events(events: list[NormalizedEvent]) -> float:
    """Score GDELT events for energy relevance.

    Args:
        events: List of normalized events from GDELT collector

    Returns:
        Score from 0.0 to 1.0
    """
    energy_events = [e for e in events if e.source == "gdelt" and is_energy_related(e)]

    if not energy_events:
        return 0.0

    # Weight by magnitude and confidence
    weighted_sum = sum(e.magnitude * e.confidence for e in energy_events)

    # Normalize by number of events (capped)
    num_events = min(len(energy_events), 5)
    score = (weighted_sum / num_events) if num_events > 0 else 0.0

    # Boost if multiple events
    if len(energy_events) > 2:
        score *= 1.1

    return min(score, 1.0)


def score_discord_energy_events(events: list[NormalizedEvent]) -> float:
    """Score Discord events for energy relevance.

    Args:
        events: List of normalized events from Discord collector

    Returns:
        Score from 0.0 to 1.0
    """
    energy_events = [
        e for e in events if e.source == "discord" and is_energy_related(e)
    ]

    if not energy_events:
        return 0.0

    # Discord signals are fast but less authoritative than GDELT
    weighted_sum = sum(
        e.magnitude * e.confidence * 0.8  # Discount slightly
        for e in energy_events
    )

    num_events = min(len(energy_events), 3)
    score = (weighted_sum / num_events) if num_events > 0 else 0.0

    # Urgency bonus
    urgency = sum(e.raw.get("urgency", 0.5) for e in energy_events) / len(energy_events)
    score *= 0.8 + 0.4 * urgency

    return min(score, 1.0)


def score_telegram_energy_events(events: list[NormalizedEvent]) -> float:
    """Score Telegram events for energy relevance.

    Args:
        events: List of normalized events from Telegram collector

    Returns:
        Score from 0.0 to 1.0
    """
    energy_events = [
        e for e in events if e.source == "telegram" and is_energy_related(e)
    ]

    if not energy_events:
        return 0.0

    # Telegram is fast but less authoritative than GDELT
    weighted_sum = sum(e.magnitude * e.confidence * 0.8 for e in energy_events)

    num_events = min(len(energy_events), 3)
    score = (weighted_sum / num_events) if num_events > 0 else 0.0

    # Urgency bonus
    urgency = sum(e.raw.get("urgency", 0.5) for e in energy_events) / len(energy_events)
    score *= 0.8 + 0.4 * urgency

    return min(score, 1.0)


def score_eia_energy_context(events: list[NormalizedEvent]) -> float:
    """Score EIA events for energy context.

    Args:
        events: List of normalized events from EIA collector

    Returns:
        Score from 0.0 to 1.0
    """
    energy_events = [e for e in events if e.source == "eia" and is_energy_related(e)]

    if not energy_events:
        return 0.0

    # EIA is authoritative but slow-moving
    # Bullish EIA events get positive scores
    bullish_sum = sum(
        e.magnitude * e.confidence for e in energy_events if e.direction == "bullish"
    )

    # Bearish events reduce score
    bearish_sum = sum(
        e.magnitude * e.confidence for e in energy_events if e.direction == "bearish"
    )

    score = (bullish_sum - 0.5 * bearish_sum) / len(energy_events)
    return max(0.0, min(score, 1.0))


def score_fred_energy_events(events: list[NormalizedEvent]) -> float:
    """Score FRED events for energy context.

    Args:
        events: List of normalized events from FRED collector

    Returns:
        Score from 0.0 to 1.0
    """
    energy_events = [e for e in events if e.source == "fred" and is_energy_related(e)]

    if not energy_events:
        return 0.0

    # FRED is authoritative macro data - WTI oil is most energy-relevant
    bullish_sum = sum(
        e.magnitude * e.confidence for e in energy_events if e.direction == "bullish"
    )
    bearish_sum = sum(
        e.magnitude * e.confidence for e in energy_events if e.direction == "bearish"
    )

    # Yield curve slope: bullish = positive (risk-on for energy)
    # VIX: bearish = high volatility (mixed signal)
    # WTI: bullish = oil price up (energy bullish)
    score = (bullish_sum - 0.3 * bearish_sum) / len(energy_events)
    return max(0.0, min(score, 1.0))


def score_market_confirmation(
    xle_change: float,
    uso_change: float,
    spy_change: float,
    xle_threshold: float = 0.8,
    uso_threshold: float = 1.0,
    relative_strength_threshold: float = 0.75,
) -> float:
    """Score market confirmation for energy trade.

    Args:
        xle_change: XLE % change today
        uso_change: USO % change today
        spy_change: SPY % change today
        xle_threshold: XLE threshold for score (default 0.8%)
        uso_threshold: USO threshold for score (default 1.0%)
        relative_strength_threshold: XLE vs SPY outperformance threshold

    Returns:
        Score from 0.0 to 1.0
    """
    score = 0.0

    # XLE momentum
    if xle_change >= xle_threshold:
        score += 0.4 * min(xle_change / 3.0, 1.0)
    elif xle_change >= 0:
        score += 0.2 * (xle_change / xle_threshold)

    # USO confirmation
    if uso_change >= uso_threshold:
        score += 0.3 * min(uso_change / 3.0, 1.0)
    elif uso_change >= 0:
        score += 0.15 * (uso_change / uso_threshold)

    # Relative strength vs market
    relative_strength = xle_change - spy_change
    if relative_strength >= relative_strength_threshold:
        score += 0.3 * min(relative_strength / 2.0, 1.0)
    elif relative_strength >= 0:
        score += 0.15 * (relative_strength / relative_strength_threshold)

    return min(score, 1.0)


def score_risk_regime(vix: float, spy_change: float) -> float:
    """Score risk regime for trade suitability.

    Args:
        vix: Current VIX level
        spy_change: SPY % change today

    Returns:
        Score from 0.0 to 1.0 (1.0 = good environment)
    """
    # VIX scoring
    if vix < 20:
        vix_score = 1.0
    elif vix < 24:
        vix_score = 0.6
    elif vix < 30:
        vix_score = 0.2
    else:
        vix_score = 0.0

    # SPY scoring
    if spy_change >= 0:
        spy_score = 1.0
    elif spy_change >= -1.0:
        spy_score = 0.7
    elif spy_change >= -2.0:
        spy_score = 0.3
    else:
        spy_score = 0.0

    # Combine (VIX is more important)
    regime_score = 0.6 * vix_score + 0.4 * spy_score

    return regime_score


def compute_event_pressure(
    fred_events: list[NormalizedEvent],
    gdelt_events: list[NormalizedEvent],
    discord_events: list[NormalizedEvent],
    telegram_events: list[NormalizedEvent],
    eia_events: list[NormalizedEvent],
) -> float:
    """Compute overall event pressure score.

    Formula:
        event_pressure = 0.20*fred + 0.30*gdelt + 0.15*discord + 0.15*telegram + 0.20*eia
    """
    fred_score = score_fred_energy_events(fred_events)
    gdelt_score = score_gdelt_energy_events(gdelt_events)
    discord_score = score_discord_energy_events(discord_events)
    telegram_score = score_telegram_energy_events(telegram_events)
    eia_score = score_eia_energy_context(eia_events)

    event_pressure = (
        0.20 * fred_score
        + 0.30 * gdelt_score
        + 0.15 * discord_score
        + 0.15 * telegram_score
        + 0.20 * eia_score
    )

    logger.info(
        f"Event pressure: {event_pressure:.3f} "
        f"(fred={fred_score:.3f}, gdelt={gdelt_score:.3f}, discord={discord_score:.3f}, telegram={telegram_score:.3f}, eia={eia_score:.3f})"
    )

    return event_pressure


def compute_signal_confidence(
    event_pressure: float, market_confirmation: float, risk_regime: float
) -> float:
    """Compute final signal confidence.

    Formula:
        confidence = 0.50 * event_pressure + 0.35 * market_confirmation + 0.15 * risk_regime
    """
    return 0.50 * event_pressure + 0.35 * market_confirmation + 0.15 * risk_regime


def build_energy_signal(
    event_pressure: float,
    market_confirmation: float,
    risk_regime: float,
    config: Optional[StrategyConfig] = None,
) -> EnergySignal:
    """Build energy signal from component scores.

    Args:
        event_pressure: Event pressure score
        market_confirmation: Market confirmation score
        risk_regime: Risk regime score
        config: Strategy configuration

    Returns:
        EnergySignal with action and reasoning
    """
    config = config or StrategyConfig()

    confidence = compute_signal_confidence(
        event_pressure, market_confirmation, risk_regime
    )

    # Determine action
    if confidence >= config.trade_confidence_min:
        if (
            event_pressure >= config.event_pressure_min
            and market_confirmation >= config.market_confirmation_min
            and risk_regime >= config.risk_regime_min
        ):
            action = TradeAction.BUY
            reasoning = (
                f"Energy shock signal: confidence={confidence:.2f}, "
                f"event={event_pressure:.2f}, market={market_confirmation:.2f}, "
                f"regime={risk_regime:.2f}"
            )
        else:
            action = TradeAction.HOLD
            reasoning = (
                "Confidence threshold met but individual scores below entry thresholds"
            )
    else:
        action = TradeAction.HOLD
        reasoning = (
            f"Confidence {confidence:.2f} below threshold {config.trade_confidence_min}"
        )

    return EnergySignal(
        action=action,
        confidence=confidence,
        event_pressure=event_pressure,
        market_confirmation=market_confirmation,
        risk_regime=risk_regime,
        reasoning=reasoning,
    )


def check_entry_conditions(
    signal: EnergySignal,
    position: Optional[PositionState],
    last_trade_time: Optional[datetime],
    config: StrategyConfig,
) -> tuple[bool, str]:
    """Check if entry conditions are met.

    Returns:
        Tuple of (can_enter, reason)
    """
    # Already in position
    if position is not None:
        return False, "Already in position"

    # Check confidence
    if signal.confidence < config.trade_confidence_min:
        return (
            False,
            f"Confidence {signal.confidence:.2f} below {config.trade_confidence_min}",
        )

    # Check individual thresholds
    if signal.event_pressure < config.event_pressure_min:
        return (
            False,
            f"Event pressure {signal.event_pressure:.2f} below {config.event_pressure_min}",
        )

    if signal.market_confirmation < config.market_confirmation_min:
        return (
            False,
            f"Market confirmation {signal.market_confirmation:.2f} below {config.market_confirmation_min}",
        )

    if signal.risk_regime < config.risk_regime_min:
        return (
            False,
            f"Risk regime {signal.risk_regime:.2f} below {config.risk_regime_min}",
        )

    # Check cooldown
    if last_trade_time:
        hours_since = (datetime.now(UTC) - last_trade_time).total_seconds() / 3600
        if hours_since < config.cooldown_hours:
            return False, f"Cooldown active: {hours_since:.1f}h since last trade"

    return True, "Entry conditions met"


def check_exit_conditions(
    position: PositionState,
    current_price: float,
    signal: EnergySignal,
    config: StrategyConfig,
) -> tuple[bool, ExitReason, str]:
    """Check if exit conditions are met.

    Returns:
        Tuple of (should_exit, reason, description)
    """
    pnl_pct = (current_price - position.entry_price) / position.entry_price

    # Update peak price
    if current_price > position.peak_price:
        position.peak_price = current_price

    # Stop loss
    if pnl_pct <= -config.stop_loss_pct:
        return True, ExitReason.STOP_LOSS, f"Stop loss: PnL={pnl_pct:.2%}"

    # Take profit (partial)
    if pnl_pct >= config.take_profit_pct and not position.partial_exited:
        return True, ExitReason.TAKE_PROFIT, f"Take profit: PnL={pnl_pct:.2%}"

    # Trailing stop
    if position.partial_exited:
        drawdown = (position.peak_price - current_price) / position.peak_price
        if drawdown >= config.trailing_stop_pct:
            return (
                True,
                ExitReason.TRAILING_STOP,
                f"Trailing stop: drawdown={drawdown:.2%}",
            )

    # Max holding
    holding_days = (datetime.now(UTC) - position.entry_date).days
    if holding_days >= config.max_holding_days:
        return True, ExitReason.MAX_HOLDING, f"Max holding: {holding_days} days"

    # Thesis deterioration
    if signal.event_pressure < 0.35 and signal.market_confirmation < 0.40:
        return (
            True,
            ExitReason.THESIS_DETERIORATION,
            (
                f"Thesis deteriorated: event={signal.event_pressure:.2f}, "
                f"market={signal.market_confirmation:.2f}"
            ),
        )

    return False, ExitReason.NONE, "Hold position"


def calculate_position_size(signal: EnergySignal, config: StrategyConfig) -> float:
    """Calculate position size in dollars.

    Args:
        signal: Energy signal with confidence
        config: Strategy configuration

    Returns:
        Dollar amount to trade
    """
    # Base size
    base_size = config.base_usd

    # Confidence multiplier
    size_multiplier = min(1.0, 0.5 + 0.5 * signal.confidence)

    # VIX adjustment
    vix_factor = 1.0
    if 20 <= signal.risk_regime < 50:
        vix_factor = 0.7
    elif signal.risk_regime < 20:
        vix_factor = 0.4

    final_size = base_size * size_multiplier * vix_factor

    logger.info(
        f"Position size: ${final_size:.2f} "
        f"(base=${base_size}, multiplier={size_multiplier:.2f}, vix_factor={vix_factor:.2f})"
    )

    return final_size


def calculate_quantity(price: float, amount: float) -> int:
    """Calculate quantity from dollar amount.

    Args:
        price: Current price
        amount: Dollar amount

    Returns:
        Integer quantity
    """
    qty = int(amount / price)
    return max(1, qty)
