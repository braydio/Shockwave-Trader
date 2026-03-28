"""Portfolio and position helpers for Arbiter execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from arbiter.execution.public_client import Position, PublicClient


@dataclass
class PositionSnapshot:
    """Normalized position snapshot used by strategies and risk checks."""

    symbol: str
    qty: float
    market_value: float
    unrealized_pl: float
    current_price: float


class PositionService:
    """Convenience wrapper around Public positions."""

    def __init__(self, client: Optional[PublicClient] = None):
        self.client = client or PublicClient()

    def list_positions(self) -> list[PositionSnapshot]:
        return [self._snapshot(position) for position in self.client.get_positions()]

    def get_position(self, symbol: str) -> Optional[PositionSnapshot]:
        position = self.client.get_position(symbol)
        if not position:
            return None
        return self._snapshot(position)

    def has_position(self, symbol: str) -> bool:
        return self.get_position(symbol) is not None

    @staticmethod
    def _snapshot(position: Position) -> PositionSnapshot:
        return PositionSnapshot(
            symbol=position.symbol,
            qty=position.qty,
            market_value=position.market_value,
            unrealized_pl=position.unrealized_pl,
            current_price=position.current_price,
        )
