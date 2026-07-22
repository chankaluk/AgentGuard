from __future__ import annotations

import argparse
import json
from pathlib import Path

from _bootstrap import ROOT
from agentguard.baselines import evaluate_rule_baseline, evaluate_token_lookup
from agentguard.data import group_sequences
from agentguard.synthetic import iter_jsonl


def main() -> None:
    parser = argparse.ArgumentParser(description="评估 AgentGuard 的透明非深度学习基线")
    parser.add_argument("--data-dir", default=str(ROOT / "data" / "demo"))
    parser.add_argument(
        "--output",
        default=str(ROOT / "artifacts" / "evaluation" / "baselines.json"),
    )
    parser.add_argument("--config", default=str(ROOT / "configs" / "default.json"))
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    train_events = list(iter_jsonl(data_dir / "train.jsonl"))
    test_events = list(iter_jsonl(data_dir / "test.jsonl"))
    test_records = group_sequences(
        test_events,
        int(config["window_size"]),
        int(config["stride"]),
        int(config["min_events"]),
    )
    lookup = evaluate_token_lookup(train_events, test_records)
    ordered_rules = evaluate_rule_baseline(test_records)
    payload = {
        "data_scope": "自建可复现增强工程基准",
        "sequence_count": len(test_records),
        "attack_only_token_lookup": lookup,
        "ordered_transparent_rules": ordered_rules,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
