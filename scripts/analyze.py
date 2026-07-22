from __future__ import annotations

import argparse
import json

from _bootstrap import ROOT
from agentguard.baselines import score_hybrid_records
from agentguard.data import load_records
from agentguard.engine import AgentGuardDetector


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze JSONL behavior logs")
    parser.add_argument("input", help="Input JSONL file")
    parser.add_argument("--checkpoint", default=str(ROOT / "artifacts" / "agentguard.pt"))
    parser.add_argument("--all", action="store_true", help="Include normal sequences")
    args = parser.parse_args()
    detector = AgentGuardDetector(args.checkpoint)
    config = detector.config
    _, records = load_records(
        args.input, config["window_size"], config["stride"], config["min_events"]
    )
    _, scores, model_scores, rule_scores, _ = score_hybrid_records(detector, records)
    for record, score, model_score, rule_score in zip(
        records, scores, model_scores, rule_scores
    ):
        if args.all or score >= detector.threshold:
            print(json.dumps(detector.explain_record(
                record,
                float(score),
                model_score=float(model_score),
                rule_score=float(rule_score),
            ), ensure_ascii=False))


if __name__ == "__main__":
    main()
