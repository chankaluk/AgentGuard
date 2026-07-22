from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from agentguard.adapters import iter_csv_events
from agentguard.schema import BehaviorEvent
from serve import MAX_BODY_BYTES, MAX_EVENTS, RequestLimitError, checked_content_length, parse_events_payload


def valid_event(**overrides):
    record = {
        "timestamp": "2026-01-01T00:00:00Z",
        "entity_id": "agent-1",
        "event_type": "tool",
        "action": "read",
        "object_type": "file",
        "object_name": "report.txt",
        "label": 0,
    }
    record.update(overrides)
    return record


class SecurityBoundaryTests(unittest.TestCase):
    def test_schema_rejects_invalid_timestamp_empty_fields_and_label(self):
        invalid_records = [
            valid_event(timestamp="not-a-time"),
            valid_event(entity_id="   "),
            valid_event(event_type=""),
            valid_event(action=""),
            valid_event(label=2),
            valid_event(object_name="x" * 2049),
        ]
        for record in invalid_records:
            with self.subTest(record=record):
                with self.assertRaises(ValueError):
                    BehaviorEvent.from_dict(record)

    def test_anonymization_requires_explicit_secret_salt(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "events.csv")
            path.write_text(
                "timestamp,entity_id,event_type,action\n"
                "2026-01-01T00:00:00Z,alice,file,read\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "匿名化盐"):
                list(iter_csv_events(path, anonymize_entities=True, salt=None))

    def test_request_limits_reject_large_body_and_event_count(self):
        self.assertEqual(checked_content_length(str(MAX_BODY_BYTES)), MAX_BODY_BYTES)
        with self.assertRaises(RequestLimitError):
            checked_content_length(str(MAX_BODY_BYTES + 1))
        with self.assertRaises(RequestLimitError):
            parse_events_payload({"events": [valid_event()] * (MAX_EVENTS + 1)})


if __name__ == "__main__":
    unittest.main()
