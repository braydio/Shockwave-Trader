"""Delta computation for Arbiter normalized events."""

from __future__ import annotations

import copy

from arbiter.collectors.base import NormalizedEvent


def event_fingerprint(event: NormalizedEvent) -> str:
    """Stable key for comparing the same event narrative across cycles."""
    entities = ",".join(sorted(entity.lower() for entity in event.entities))
    return f"{event.source}|{event.category}|{entities}|{event.direction}"


def compute_delta(current: dict, previous: dict | None) -> str:
    """Classify the change between current and prior event states."""
    if not previous:
        return "new"

    current_mag = float(current.get("magnitude", 0.0) or 0.0)
    previous_mag = float(previous.get("magnitude", 0.0) or 0.0)

    if current_mag > previous_mag + 0.2:
        return "intensified"
    if current_mag < previous_mag - 0.2:
        return "weakened"
    return "repeated"


def annotate_deltas(
    events: list[NormalizedEvent],
    previous_snapshot: dict[str, dict],
) -> list[NormalizedEvent]:
    """Return copied events with delta metadata embedded in ``raw``."""
    annotated: list[NormalizedEvent] = []
    seen_keys = set()

    for event in events:
        key = event_fingerprint(event)
        seen_keys.add(key)
        previous = previous_snapshot.get(key)
        event_copy = copy.deepcopy(event)
        event_copy.raw["event_key"] = key
        event_copy.raw["delta_type"] = compute_delta(event_copy.to_dict(), previous)
        event_copy.raw["previous_magnitude"] = (
            float(previous.get("magnitude", 0.0)) if previous else None
        )
        annotated.append(event_copy)

    for key, previous in previous_snapshot.items():
        if key in seen_keys:
            continue
        previous_copy = NormalizedEvent(
            id=previous["id"],
            timestamp=previous["timestamp"],
            source=previous["source"],
            category=previous["category"],
            entities=list(previous["entities"]),
            direction=previous["direction"],
            magnitude=float(previous["magnitude"]),
            confidence=float(previous["confidence"]),
            raw=dict(previous.get("raw", {})),
        )
        previous_copy.raw["event_key"] = key
        previous_copy.raw["delta_type"] = "decayed"
        previous_copy.raw["previous_magnitude"] = float(previous.get("magnitude", 0.0))
        annotated.append(previous_copy)

    return annotated


def build_snapshot(events: list[NormalizedEvent]) -> dict[str, dict]:
    """Serialize events by fingerprint for persistence between cycles."""
    return {
        event_fingerprint(event): event.to_dict()
        for event in events
    }
