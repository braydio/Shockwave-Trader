"""Energy Shock Confirmation Strategy - Strategy 01.

Implements: Collect -> Normalize -> Delta -> Score -> Trade -> Explain
"""

from arbiter.strategies.energy_shock.strategy import (
    # Core classes
    EnergySignal,
    PositionState,
    StrategyConfig,
    TradeAction,
    ExitReason,
    # Scoring functions
    score_fred_energy_events,
    score_gdelt_energy_events,
    score_discord_energy_events,
    score_telegram_energy_events,
    score_eia_energy_context,
    score_market_confirmation,
    score_risk_regime,
    compute_event_pressure,
    compute_signal_confidence,
    build_energy_signal,
    is_energy_related,
    # Entry/Exit logic
    check_entry_conditions,
    check_exit_conditions,
    calculate_position_size,
    calculate_quantity,
    # Constants
    ENERGY_TAGS,
    ENERGY_ENTITIES,
)

from arbiter.strategies.energy_shock.state import StateManager, StrategyState
from arbiter.strategies.energy_shock.decision import (
    EnergyShockDecisionEngine,
    MarketSnapshot,
    StrategyDecision,
    build_market_snapshot,
)

__all__ = [
    # Classes
    "EnergySignal",
    "PositionState",
    "StrategyConfig",
    "StrategyState",
    "StateManager",
    "EnergyShockDecisionEngine",
    "MarketSnapshot",
    "StrategyDecision",
    "build_market_snapshot",
    "TradeAction",
    "ExitReason",
    # Scoring
    "score_fred_energy_events",
    "score_gdelt_energy_events",
    "score_discord_energy_events",
    "score_telegram_energy_events",
    "score_eia_energy_context",
    "score_market_confirmation",
    "score_risk_regime",
    "compute_event_pressure",
    "compute_signal_confidence",
    "build_energy_signal",
    "is_energy_related",
    # Logic
    "check_entry_conditions",
    "check_exit_conditions",
    "calculate_position_size",
    "calculate_quantity",
    # Constants
    "ENERGY_TAGS",
    "ENERGY_ENTITIES",
]
