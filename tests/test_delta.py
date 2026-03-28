from __future__ import annotations

import tempfile
import unittest

from arbiter.collectors.base import NormalizedEvent
from arbiter.delta.compute import annotate_deltas, build_snapshot
from arbiter.delta.state import DeltaState


def make_event(
    *,
    source: str = "gdelt",
    entities: list[str] | None = None,
    magnitude: float = 0.6,
    direction: str = "bullish",
) -> NormalizedEvent:
    return NormalizedEvent(
        id="evt-1",
        timestamp="2026-03-21T00:00:00+00:00",
        source=source,
        category="news",
        entities=entities or ["oil", "energy"],
        direction=direction,
        magnitude=magnitude,
        confidence=0.7,
        raw={},
    )


class DeltaTests(unittest.TestCase):
    def test_annotate_deltas_marks_new_and_repeated_events(self) -> None:
        previous = build_snapshot([make_event(magnitude=0.5)])
        annotated = annotate_deltas([make_event(magnitude=0.52)], previous)

        self.assertEqual(annotated[0].raw["delta_type"], "repeated")

    def test_annotate_deltas_marks_intensified_and_decayed(self) -> None:
        previous = build_snapshot([make_event(magnitude=0.2)])
        annotated = annotate_deltas([make_event(magnitude=0.6)], previous)
        self.assertEqual(annotated[0].raw["delta_type"], "intensified")

        decayed = annotate_deltas([], previous)
        self.assertEqual(decayed[0].raw["delta_type"], "decayed")

    def test_hot_memory_retains_recent_significant_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            state = DeltaState(storage_dir=tmpdir)
            annotated = annotate_deltas([make_event(magnitude=0.8)], {})
            memory = state.update_hot_memory(annotated, min_magnitude=0.4)

            self.assertEqual(len(memory), 1)
            reloaded = state.materialize_events(state.load_hot_memory())
            self.assertEqual(len(reloaded), 1)
            self.assertEqual(reloaded[0].source, "gdelt")


if __name__ == "__main__":
    unittest.main()
