from __future__ import annotations

import argparse
import json

from _bootstrap import ROOT
from agentguard.baselines import score_hybrid_records
from agentguard.data import iter_sequence_windows
from agentguard.engine import AgentGuardDetector
from agentguard.synthetic import iter_jsonl


def main() -> None:
    parser = argparse.ArgumentParser(description="Per-entity bounded streaming analysis for chronological JSONL")
    parser.add_argument("input")
    parser.add_argument("--checkpoint", default=str(ROOT / "artifacts" / "agentguard.pt"))
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--max-active-entities", type=int, default=10000)
    parser.add_argument("--output", default="-")
    args = parser.parse_args()
    detector = AgentGuardDetector(args.checkpoint)
    config = detector.config
    window = int(config["window_size"]); stride = int(config["stride"]); minimum = int(config["min_events"])
    batch=[]
    output = None if args.output == "-" else open(args.output, "w", encoding="utf-8")

    def emit(records):
        if not records: return
        _, scores, model_scores, rule_scores, _ = score_hybrid_records(
            detector, records, args.batch_size
        )
        for record, score, model_score, rule_score in zip(
            records, scores, model_scores, rule_scores
        ):
            if score >= detector.threshold:
                line=json.dumps(detector.explain_record(
                    record,
                    float(score),
                    model_score=float(model_score),
                    rule_score=float(rule_score),
                ),ensure_ascii=False)
                (output.write(line+"\n") if output else print(line))

    try:
        for record in iter_sequence_windows(
            iter_jsonl(args.input), window, stride, minimum, args.max_active_entities
        ):
            batch.append(record)
            if len(batch)>=args.batch_size: emit(batch); batch=[]
        emit(batch)
    finally:
        if output: output.close()


if __name__ == "__main__":
    main()
