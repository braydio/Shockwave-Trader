"""Base collector class and utilities."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
import time
import hashlib


@dataclass
class NormalizedEvent:
    """Canonical event schema for all collectors."""

    id: str
    timestamp: str
    source: str
    category: str  # market | macro | news | social | commodity
    entities: list[str]
    direction: str  # bullish | bearish | neutral
    magnitude: float  # 0-1
    confidence: float  # 0-1
    raw: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "source": self.source,
            "category": self.category,
            "entities": self.entities,
            "direction": self.direction,
            "magnitude": self.magnitude,
            "confidence": self.confidence,
            "raw": self.raw,
        }


class BaseCollector(ABC):
    """Abstract base class for all collectors."""

    name: str = "base"
    priority: int = 10
    category: str = "unknown"

    def _generate_id(self, *parts) -> str:
        """Generate unique ID from parts."""
        hash_input = "_".join(str(p) for p in parts)
        hash_value = hashlib.md5(hash_input.encode()).hexdigest()[:12]
        return f"{self.name}_{hash_value}_{int(time.time())}"

    def _make_event(
        self,
        entities: list[str],
        direction: str,
        magnitude: float,
        confidence: float,
        raw: dict,
    ) -> NormalizedEvent:
        """Helper to create NormalizedEvent."""
        return NormalizedEvent(
            id=self._generate_id(*entities),
            timestamp=datetime.now(UTC).isoformat(),
            source=self.name,
            category=self.category,
            entities=entities,
            direction=direction,
            magnitude=min(max(magnitude, 0), 1),
            confidence=min(max(confidence, 0), 1),
            raw=raw,
        )

    @abstractmethod
    async def fetch(self) -> dict:
        """Fetch raw data from source."""
        pass

    @abstractmethod
    def transform(self, raw: dict) -> list[NormalizedEvent]:
        """Transform raw data into normalized events."""
        pass

    async def run(self) -> list[NormalizedEvent]:
        """Full fetch + transform pipeline."""
        raw = await self.fetch()
        return self.transform(raw)
