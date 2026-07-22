from __future__ import annotations

import argparse
import json
from pathlib import Path

from _bootstrap import ROOT
from agentguard.data import BehaviorVocabulary, load_records
from agentguard.engine import save_json, train_model


def main() -> None:
    parser = argparse.ArgumentParser(description="Train the AgentGuard Transformer")
    parser.add_argument("--config", default=str(ROOT / "configs" / "default.json"))
    parser.add_argument("--data-dir", default=str(ROOT / "data" / "demo"))
    parser.add_argument("--output", default=str(ROOT / "artifacts" / "agentguard.pt"))
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    data_dir = Path(args.data_dir)
    train_events, train_records = load_records(
        data_dir / "train.jsonl",
        config["window_size"], config["stride"], config["min_events"],
    )
    _, validation_records = load_records(
        data_dir / "validation.jsonl",
        config["window_size"], config["stride"], config["min_events"],
    )
    vocabulary = BehaviorVocabulary()
    vocabulary.fit(train_events, config["max_vocab_size"])
    vocabulary.save(ROOT / "artifacts" / "vocabulary.json")
    result = train_model(train_records, validation_records, vocabulary, config, args.output)
    save_json(
        {
            "best_epoch": result.best_epoch,
            "threshold": result.threshold,
            "validation_metrics": result.validation_metrics,
            "history": result.history,
            "model_parameters": result.model_parameters,
            "train_sequences": len(train_records),
            "validation_sequences": len(validation_records),
        },
        ROOT / "artifacts" / "training_result.json",
    )
    print(json.dumps(result.validation_metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

