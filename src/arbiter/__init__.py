"""Arbiter - Ingestion → Signal → Execution Framework

Collects data, detects changes, generates signals, executes trades via Public API.
"""

from arbiter.collectors.base import BaseCollector, NormalizedEvent
from arbiter.execution.order_executor import OrderExecutor, TradeDecision, TradeResult
from arbiter.execution.public_client import (
    Account,
    BrokerageAccount,
    Order,
    OrderHistoryEntry,
    Position,
    PublicClient,
)

__version__ = "0.1.0"

__all__ = [
    "BaseCollector",
    "NormalizedEvent",
    "BrokerageAccount",
    "OrderExecutor",
    "PublicClient",
    "Account",
    "Position",
    "Order",
    "OrderHistoryEntry",
    "TradeDecision",
    "TradeResult",
]
