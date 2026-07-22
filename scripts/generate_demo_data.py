from __future__ import annotations

import argparse

from _bootstrap import ROOT
from agentguard.synthetic import generate_dataset


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the reproducible AgentGuard benchmark")
    parser.add_argument("--output", default=str(ROOT / "data" / "demo"))
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--train-sessions", type=int, default=1000)
    parser.add_argument("--validation-sessions", type=int, default=300)
    parser.add_argument("--test-sessions", type=int, default=400)
    args = parser.parse_args()
    counts = generate_dataset(
        args.output,
        seed=args.seed,
        train_sessions=args.train_sessions,
        validation_sessions=args.validation_sessions,
        test_sessions=args.test_sessions,
    )
    print("Generated:", counts)


if __name__ == "__main__":
    main()

