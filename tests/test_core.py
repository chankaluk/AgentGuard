from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np
import torch

from agentguard.adapters import iter_csv_events, pseudonymize
from agentguard.data import BehaviorSequenceDataset, BehaviorVocabulary, group_sequences
from agentguard.metrics import calculate_metrics, choose_threshold
from agentguard.model import AgentBehaviorTransformer
from agentguard.schema import BehaviorEvent
from agentguard.synthetic import generate_dataset, iter_jsonl


class CoreTests(unittest.TestCase):
    def event(self, index: int, label: int = 0):
        return BehaviorEvent(
            timestamp=datetime(2026, 1, 1, 0, 0, index, tzinfo=timezone.utc).isoformat(),
            entity_id="agent-1", event_type="tool", action="read", object_type="file",
            object_name=f"file-{index}", label=label,
        )

    def test_schema_rejects_missing_fields(self):
        with self.assertRaises(ValueError):
            BehaviorEvent.from_dict({"timestamp": "2026-01-01T00:00:00Z"})

    def test_sequence_label_uses_any_event(self):
        records = group_sequences([self.event(i, int(i == 3)) for i in range(6)], 8, 2, 4)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].label, 1)

    def test_threshold_respects_fpr_when_feasible(self):
        labels = np.array([0, 0, 0, 0, 1, 1, 1])
        scores = np.array([0.05, 0.10, 0.15, 0.20, 0.70, 0.80, 0.95])
        threshold, metrics = choose_threshold(labels, scores, 0.20)
        self.assertLessEqual(metrics.false_positive_rate, 0.20)
        self.assertEqual(metrics.detection_rate, 1.0)
        self.assertGreaterEqual(threshold, 0.20)

    def test_transformer_forward_shapes(self):
        events = [self.event(i) for i in range(6)]
        vocabulary = BehaviorVocabulary(); vocabulary.fit(events)
        records = group_sequences(events, 8, 2, 4)
        batch = BehaviorSequenceDataset(records, vocabulary, 8)[0]
        model = AgentBehaviorTransformer(len(vocabulary), 8, d_model=32, n_heads=4, n_layers=1, dim_feedforward=64)
        outputs = model(batch["tokens"].unsqueeze(0), batch["features"].unsqueeze(0), batch["mask"].unsqueeze(0), True)
        self.assertEqual(tuple(outputs["logits"].shape), (1,))
        self.assertEqual(tuple(outputs["next_event_logits"].shape[:2]), (1, 8))
        self.assertEqual(len(outputs["attentions"]), 1)

    def test_generator_is_reproducible(self):
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            generate_dataset(first, seed=7, train_sessions=10, validation_sessions=5, test_sessions=5)
            generate_dataset(second, seed=7, train_sessions=10, validation_sessions=5, test_sessions=5)
            self.assertEqual(Path(first, "train.jsonl").read_bytes(), Path(second, "train.jsonl").read_bytes())

    def test_csv_adapter_and_pseudonymization(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "events.csv")
            path.write_text(
                "event_time,host_user,category,operation,target_type,target_name\n"
                "2026-01-01T00:00:00Z,alice,file,read,file,report.txt\n",
                encoding="utf-8",
            )
            mapping = {
                "timestamp": "event_time", "entity_id": "host_user",
                "event_type": "category", "action": "operation",
                "object_type": "target_type", "object_name": "target_name",
            }
            events = list(iter_csv_events(path, mapping, True, "test-salt"))
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0].entity_id, pseudonymize("alice", "test-salt"))
            self.assertNotIn("alice", events[0].entity_id)


if __name__ == "__main__":
    unittest.main()
