from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agentguard.baselines import (
    attack_only_tokens,
    evaluate_token_lookup,
    fuse_model_and_rule_scores,
    score_hybrid_records,
    sequence_rule_score,
)
from agentguard.data import SequenceRecord, group_sequences
from agentguard.schema import BehaviorEvent
from agentguard.synthetic import generate_dataset, iter_jsonl


class BenchmarkQualityTests(unittest.TestCase):
    def test_shared_hybrid_inference_returns_separate_score_sources(self):
        class FakeDetector:
            def score_records(self, records, batch_size=256):
                return np.asarray([0]), np.asarray([0.2]), {"batch_size": batch_size}

        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        events = [
            BehaviorEvent(start.isoformat(), "agent-1", "tool", "read", "secret", "x", source="agent"),
            BehaviorEvent((start + timedelta(seconds=1)).isoformat(), "agent-1", "network", "connect", "domain", "x", source="host"),
            BehaviorEvent((start + timedelta(seconds=2)).isoformat(), "agent-1", "tool", "upload", "archive", "x", source="agent"),
        ]
        record = SequenceRecord("agent-1", events, 0, "normal")
        labels, hybrid, model, rules, auxiliary = score_hybrid_records(
            FakeDetector(), [record], batch_size=32
        )
        self.assertEqual(labels.tolist(), [0])
        self.assertEqual(model.tolist(), [0.2])
        self.assertEqual(rules.tolist(), [0.75])
        self.assertEqual(hybrid.tolist(), [0.75])
        self.assertEqual(auxiliary["batch_size"], 32)

    def test_hybrid_fusion_keeps_stronger_model_or_rule_evidence(self):
        records = []
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        for index, order in enumerate(((0, 1, 2), (2, 1, 0))):
            specifications = [
                ("agent", "tool", "read", "secret", "test_secret"),
                ("host", "network", "connect", "domain", "external.example"),
                ("agent", "tool", "upload", "archive", "audit_bundle"),
            ]
            events = []
            for offset, source_index in enumerate(order):
                source, event_type, action, object_type, object_name = specifications[source_index]
                events.append(BehaviorEvent(
                    timestamp=(start + timedelta(seconds=index * 10 + offset)).isoformat(),
                    entity_id=f"agent-{index}",
                    source=source,
                    event_type=event_type,
                    action=action,
                    object_type=object_type,
                    object_name=object_name,
                ))
            records.append(SequenceRecord(f"agent-{index}", events, 0, "normal"))

        hybrid, rule_scores = fuse_model_and_rule_scores([0.2, 0.9], records)
        self.assertEqual(rule_scores.tolist(), [0.75, 0.0])
        self.assertEqual(hybrid.tolist(), [0.75, 0.9])

    def test_baseline_cli_writes_auditable_json(self):
        with tempfile.TemporaryDirectory() as directory:
            data_dir = Path(directory, "data")
            output = Path(directory, "baselines.json")
            generate_dataset(
                data_dir,
                seed=23,
                train_sessions=80,
                validation_sessions=40,
                test_sessions=60,
            )
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "evaluate_baselines.py"),
                    "--data-dir",
                    str(data_dir),
                    "--output",
                    str(output),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertIn("attack_only_token_lookup", payload)
            self.assertIn("ordered_transparent_rules", payload)
            self.assertEqual(payload["data_scope"], "自建可复现增强工程基准")

    def test_sequence_rule_depends_on_order_not_only_token_presence(self):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        specifications = [
            ("agent", "tool", "read", "secret", "test_secret"),
            ("host", "network", "connect", "domain", "external.example"),
            ("agent", "tool", "upload", "archive", "audit_bundle"),
        ]

        def record(order):
            events = []
            for index, source_index in enumerate(order):
                source, event_type, action, object_type, object_name = specifications[source_index]
                events.append(BehaviorEvent(
                    timestamp=(start + timedelta(seconds=index)).isoformat(),
                    entity_id="agent-1",
                    source=source,
                    event_type=event_type,
                    action=action,
                    object_type=object_type,
                    object_name=object_name,
                ))
            return SequenceRecord("agent-1", events, 0, "normal")

        dangerous = record((0, 1, 2))
        reordered = record((2, 1, 0))
        self.assertGreater(sequence_rule_score(dangerous), sequence_rule_score(reordered))

    def test_lookup_baseline_is_not_perfect_and_metadata_is_auditable(self):
        with tempfile.TemporaryDirectory() as directory:
            generate_dataset(
                directory,
                seed=19,
                train_sessions=120,
                validation_sessions=60,
                test_sessions=80,
            )
            root = Path(directory)
            train_events = list(iter_jsonl(root / "train.jsonl"))
            test_events = list(iter_jsonl(root / "test.jsonl"))
            test_records = group_sequences(test_events, 24, 8, 6)
            baseline = evaluate_token_lookup(train_events, test_records)

            perfect = (
                baseline["detection_rate"] == 1.0
                and baseline["false_positive_rate"] == 0.0
            )
            self.assertFalse(perfect, "异常专属词元查表仍能取得完美成绩")
            self.assertLess(len(attack_only_tokens(train_events)), 5)

            metadata = json.loads((root / "metadata.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["split_strategy"], "实体隔离+场景留出")
            self.assertIn("lateral_movement", metadata["holdout_scenarios"])
            self.assertGreater(metadata["hard_negative_sessions"]["train"], 0)
            self.assertEqual(set(metadata["file_sha256"]), {
                "train.jsonl", "validation.jsonl", "test.jsonl"
            })

            test_attack_scenarios = {
                event.scenario for event in test_events if event.label
            }
            self.assertIn("lateral_movement", test_attack_scenarios)


if __name__ == "__main__":
    unittest.main()
