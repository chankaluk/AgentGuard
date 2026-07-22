from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from agentguard.synthetic import iter_jsonl
from convert_loghub_bgl import convert_text as convert_bgl_text
from convert_loghub_hdfs import convert
from generate_controlled_security_logs import generate


class SupplementalDataScriptTests(unittest.TestCase):
    def test_controlled_security_logs_have_normal_and_attack_entities(self):
        events = generate()
        labels = {event.label for event in events}
        scenarios = {event.scenario for event in events}
        self.assertEqual(labels, {0, 1})
        self.assertIn("controlled_prompt_injection_exfiltration", scenarios)

    def test_loghub_hdfs_converter_outputs_valid_events(self):
        sample = (
            "081109 203615 148 INFO dfs.DataNode$PacketResponder: "
            "PacketResponder 1 for block blk_38865049064139660 terminating\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "HDFS_2k.log")
            path.write_text(sample, encoding="utf-8")
            events = convert(path, limit=10)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].source, "public_loghub")
        self.assertEqual(events[0].event_type, "process")
        self.assertEqual(events[0].action, "terminate")

    def test_loghub_bgl_converter_preserves_public_anomaly_label(self):
        sample = (
            "- 1117838570 2005.06.03 R02-M1-N0-C:J12-U11 "
            "2005-06-03-15.42.50.675872 R02-M1-N0-C:J12-U11 RAS KERNEL INFO corrected\n"
            "KERNDTLB 1118536327 2005.06.11 R30-M0-N9-C:J16-U01 "
            "2005-06-11-17.32.07.581048 R30-M0-N9-C:J16-U01 RAS KERNEL FATAL data TLB error interrupt\n"
        )
        events = convert_bgl_text(sample)
        self.assertEqual([event.label for event in events], [0, 1])
        self.assertEqual(events[1].scenario, "public_loghub_bgl_anomaly")

    def test_supplemental_doc_is_present(self):
        text = (ROOT / "docs" / "12_三类真实补充数据输入输出说明.md").read_text(encoding="utf-8")
        for phrase in ("本机正常行为日志", "隔离环境可控安全测试日志", "公共安全数据样本"):
            self.assertIn(phrase, text)


if __name__ == "__main__":
    unittest.main()
