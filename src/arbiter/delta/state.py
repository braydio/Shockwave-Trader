"""Persistent state for Arbiter delta and hot-memory tracking."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from arbiter.collectors.base import NormalizedEvent
from arbiter.config.settings import STORAGE_DIR


class DeltaState:
    """Persist last-event snapshots and recent hot memory."""

    def __init__(self, storage_dir: str = STORAGE_DIR):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.last_events_file = self.storage_dir / "last_events.json"
        self.hot_memory_file = self.storage_dir / "hot_memory.json"

    def load_last_events(self) -> dict[str, dict]:
        if not self.last_events_file.exists():
            return {}
        return json.loads(self.last_events_file.read_text(encoding="utf-8"))

    def save_last_events(self, snapshot: dict[str, dict]) -> None:
        self.last_events_file.write_text(
            json.dumps(snapshot, indent=2),
            encoding="utf-8",
        )

    def load_hot_memory(self) -> dict[str, dict]:
        if not self.hot_memory_file.exists():
            return {}
        return json.loads(self.hot_memory_file.read_text(encoding="utf-8"))

    def save_hot_memory(self, memory: dict[str, dict]) -> None:
        self.hot_memory_file.write_text(
            json.dumps(memory, indent=2),
            encoding="utf-8",
        )

    def update_hot_memory(
        self,
        events: list[NormalizedEvent],
        max_age_hours: int = 6,
        min_magnitude: float = 0.45,
    ) -> dict[str, dict]:
        """Refresh hot memory with recent significant non-repeated events."""
        memory = self.load_hot_memory()
        cutoff = datetime.now(UTC) - timedelta(hours=max_age_hours)
        retained: dict[str, dict] = {}

        for key, event in memory.items():
            try:
                updated_at = datetime.fromisoformat(event["memory_updated_at"])
            except (KeyError, ValueError):
                continue
            if updated_at >= cutoff:
                retained[key] = event

        for event in events:
            delta_type = event.raw.get("delta_type")
            if delta_type not in {"new", "intensified", "weakened"}:
                continue
            if event.magnitude < min_magnitude:
                continue

            key = event.raw.get("event_key")
            if not key:
                continue
            payload = event.to_dict()
            payload["memory_updated_at"] = datetime.now(UTC).isoformat()
            retained[key] = payload

        self.save_hot_memory(retained)
        return retained

    @staticmethod
    def materialize_events(memory: dict[str, dict]) -> list[NormalizedEvent]:
        """Convert stored event payloads back into ``NormalizedEvent`` objects."""
        events: list[NormalizedEvent] = []
        for event in memory.values():
            events.append(
                NormalizedEvent(
                    id=event["id"],
                    timestamp=event["timestamp"],
                    source=event["source"],
                    category=event["category"],
                    entities=list(event["entities"]),
                    direction=event["direction"],
                    magnitude=float(event["magnitude"]),
                    confidence=float(event["confidence"]),
                    raw=dict(event.get("raw", {})),
                )
            )
        return events
