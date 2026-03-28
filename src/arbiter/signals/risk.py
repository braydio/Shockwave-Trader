"""Risk helpers for Arbiter trade sizing and validation."""

from __future__ import annotations

from dataclasses import dataclass

from arbiter.execution.public_client import Account


@dataclass
class RiskBudget:
    """Basic risk budget for a prospective trade."""

    equity: float
    max_position_value: float
    buying_power: float
    available_trade_value: float


def build_risk_budget(account: Account, max_position_pct: float) -> RiskBudget:
    """Build a simple risk budget from account state."""
    max_position_value = account.equity * max_position_pct
    available_trade_value = min(max_position_value, account.buying_power)
    return RiskBudget(
        equity=account.equity,
        max_position_value=max_position_value,
        buying_power=account.buying_power,
        available_trade_value=max(available_trade_value, 0.0),
    )


def clamp_trade_amount(requested_amount: float, budget: RiskBudget) -> float:
    """Clamp a requested trade amount into the available risk budget."""
    if requested_amount <= 0:
        return 0.0
    return min(requested_amount, budget.available_trade_value)
