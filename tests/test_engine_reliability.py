from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path

import numpy as np
import torch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agentguard.engine import clone_state_dict, validate_checkpoint_payload
from agentguard.metrics import roc_auc


class EngineReliabilityTests(unittest.TestCase):
    def test_state_snapshot_is_independent_on_cpu(self):
        model = torch.nn.Linear(2, 1)
        snapshot = clone_state_dict(model)
        original = snapshot["weight"].clone()
        with torch.no_grad():
            model.weight.add_(10.0)
        self.assertTrue(torch.equal(snapshot["weight"], original))
        self.assertFalse(torch.equal(snapshot["weight"], model.weight))

    def test_checkpoint_payload_rejects_unknown_version(self):
        payload = {
            "version": 1,
            "model_state": {"weight": torch.zeros(1)},
            "model_config": {},
            "runtime_config": {"window_size": 8},
            "vocabulary": {"[PAD]": 0, "[UNK]": 1, "[CLS]": 2},
            "threshold": 0.5,
            "nll_bounds": (0.1, 1.0),
            "validation_metrics": {},
            "best_epoch": 1,
        }
        with self.assertRaisesRegex(ValueError, "checkpoint 版本"):
            validate_checkpoint_payload(payload)

    def test_roc_auc_uses_rank_algorithm_and_handles_ties(self):
        labels = np.array([0, 1, 0, 1])
        scores = np.array([0.1, 0.8, 0.8, 0.9])
        self.assertAlmostEqual(roc_auc(labels, scores), 0.875)
        source = inspect.getsource(roc_auc)
        self.assertNotIn("[:, None]", source)
        self.assertNotIn("[None, :]", source)


if __name__ == "__main__":
    unittest.main()
