from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agentguard.data import group_sequences, iter_sequence_windows, window_slices
from agentguard.schema import BehaviorEvent


class WindowingTests(unittest.TestCase):
    def events(self, count: int, entity_id: str = "agent-1") -> list[BehaviorEvent]:
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        return [
            BehaviorEvent(
                timestamp=(start + timedelta(seconds=index)).isoformat(),
                entity_id=entity_id,
                event_type="tool",
                action="read",
                object_type="file",
                object_name=str(index),
                label=int(index == count - 1 and count > 6),
                scenario="tail_anomaly" if index == count - 1 and count > 6 else "normal",
            )
            for index in range(count)
        ]

    @staticmethod
    def bounds(records):
        return [
            (int(record.events[0].object_name), int(record.events[-1].object_name))
            for record in records
        ]

    def test_offline_and_streaming_windows_match(self):
        for count in (5, 6, 10, 24, 25, 50):
            with self.subTest(count=count):
                events = self.events(count)
                offline = group_sequences(events, 24, 8, 6)
                streamed = list(iter_sequence_windows(events, 24, 8, 6))
                self.assertEqual(self.bounds(streamed), self.bounds(offline))

    def test_fifty_events_use_full_windows_and_one_aligned_tail(self):
        self.assertEqual(
            list(window_slices(50, 24, 8, 6)),
            [(0, 24), (8, 32), (16, 40), (24, 48), (26, 50)],
        )

    def test_invalid_window_parameters_are_rejected(self):
        for arguments in ((10, 0, 2, 4), (10, 8, 0, 4), (10, 8, 2, 0), (10, 4, 2, 5)):
            with self.subTest(arguments=arguments):
                with self.assertRaises(ValueError):
                    list(window_slices(*arguments))
        with self.assertRaisesRegex(ValueError, "max_entities"):
            list(iter_sequence_windows([], 24, 8, 6, 0))

    def test_streaming_entity_cache_can_be_bounded(self):
        events = []
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        for entity_index in range(4):
            for offset in range(7):
                events.append(BehaviorEvent(
                    timestamp=(start + timedelta(seconds=entity_index * 20 + offset)).isoformat(),
                    entity_id=f"agent-{entity_index}",
                    event_type="tool",
                    action="read",
                    object_type="file",
                    object_name=f"file-{offset}",
                ))
        records = list(iter_sequence_windows(events, 6, 2, 3, max_entities=2))
        self.assertEqual(
            {record.entity_id for record in records},
            {"agent-0", "agent-1", "agent-2", "agent-3"},
        )


if __name__ == "__main__":
    unittest.main()
