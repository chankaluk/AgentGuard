from __future__ import annotations

import argparse
import json
from pathlib import Path

from _bootstrap import ROOT
from agentguard.adapters import iter_csv_events, write_jsonl


def main() -> None:
    parser = argparse.ArgumentParser(description="Stream-convert vendor CSV logs to AgentGuard JSONL")
    parser.add_argument("input")
    parser.add_argument("output")
    parser.add_argument("--mapping", help="JSON file: unified field -> CSV column")
    parser.add_argument("--anonymize-entities", action="store_true")
    parser.add_argument("--salt", help="实体匿名化秘密盐；启用匿名化时必填")
    args = parser.parse_args()
    if args.anonymize_entities and not args.salt:
        parser.error("--anonymize-entities 必须同时提供 --salt")
    mapping = json.loads(Path(args.mapping).read_text(encoding="utf-8")) if args.mapping else None
    count = write_jsonl(
        iter_csv_events(args.input, mapping, args.anonymize_entities, args.salt),
        args.output,
    )
    print(f"Converted {count} events -> {args.output}")


if __name__ == "__main__":
    main()
