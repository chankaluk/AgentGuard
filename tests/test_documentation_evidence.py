from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


class DocumentationEvidenceTests(unittest.TestCase):
    def test_forward_looking_docs_and_mappings_are_present(self):
        frontiers = ROOT / "docs" / "10_前沿方案对照与补强路线.md"
        plain = ROOT / "docs" / "11_评委通俗讲解稿.md"
        for path in (frontiers, plain):
            self.assertTrue(path.is_file(), f"缺少文档：{path.name}")

        text = frontiers.read_text(encoding="utf-8")
        for phrase in ("AgentDojo", "InjecAgent", "Langfuse", "osquery", "Loglizer"):
            self.assertIn(phrase, text)

        plain_text = plain.read_text(encoding="utf-8")
        for phrase in ("行车记录仪", "不是 Transformer 单模型", "原始 JSON 日志"):
            self.assertIn(phrase, plain_text)

    def test_external_mapping_templates_are_valid_json(self):
        for name in (
            "otel_span_mapping.example.json",
            "osquery_process_mapping.example.json",
            "wazuh_alert_mapping.example.json",
        ):
            path = ROOT / "configs" / name
            payload = json.loads(path.read_text(encoding="utf-8"))
            for field in ("timestamp", "entity_id", "source", "event_type", "action"):
                self.assertIn(field, payload)
            self.assertIn("description", payload)


if __name__ == "__main__":
    unittest.main()
