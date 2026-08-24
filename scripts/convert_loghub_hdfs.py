from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from _bootstrap import ROOT
from agentguard.adapters import write_jsonl
from agentguard.schema import BehaviorEvent


LINE_RE = re.compile(
    r"^(?P<date>\d{6})\s+(?P<time>\d{6})\s+(?P<pid>\d+)\s+(?P<level>\w+)\s+(?P<component>[^:]+):\s+(?P<message>.*)$"
)
BLOCK_RE = re.compile(r"blk_-?\d+")


def parse_timestamp(date_text: str, time_text: str) -> str:
    value = datetime.strptime(date_text + time_text, "%y%m%d%H%M%S").replace(tzinfo=timezone.utc)
    return value.isoformat().replace("+00:00", "Z")


def classify_action(message: str) -> tuple[str, str]:
    lower = message.lower()
    if "receiv" in lower:
        return "network", "receive"
    if "packetresponder" in lower:
        return "process", "terminate"
    if "addstoredblock" in lower or "blockmap updated" in lower:
        return "file", "write"
    if "verification succeeded" in lower:
        return "file", "verify"
    if "delete" in lower or "remov" in lower:
        return "file", "delete"
    return "log", "observe"


def convert_text(text: str, limit: int) -> list[BehaviorEvent]:
    events: list[BehaviorEvent] = []
    for line in text.splitlines():
        if limit and len(events) >= limit:
            break
        match = LINE_RE.match(line.strip())
        if not match:
            continue
        groups = match.groupdict()
        block = BLOCK_RE.search(groups["message"])
        block_id = block.group(0) if block else f"pid-{groups['pid']}"
        digest = hashlib.sha256(block_id.encode("utf-8")).hexdigest()[:16]
        event_type, action = classify_action(groups["message"])
        events.append(
            BehaviorEvent(
                timestamp=parse_timestamp(groups["date"], groups["time"]),
                entity_id=f"hdfs-block-{digest}",
                source="public_loghub",
                event_type=event_type,
                action=action,
                object_type="hdfs_block",
                object_name=groups["component"].split(".")[-1][:80],
                result="failure" if groups["level"].lower() in {"warn", "error", "fatal"} else "success",
                label=0,
                scenario="public_loghub_hdfs_unlabeled_sample",
                raw={
                    "dataset": "Loghub HDFS_2k",
                    "license_note": "public research sample; converted for format validation",
                    "log_level": groups["level"],
                },
            )
        )
    return events


def convert(input_path: Path, limit: int) -> list[BehaviorEvent]:
    return convert_text(input_path.read_text(encoding="utf-8", errors="replace"), limit)


def display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.name


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert a Loghub HDFS raw log sample to AgentGuard JSONL")
    parser.add_argument("input", help="Path to HDFS_2k.log or another Loghub HDFS raw log")
    parser.add_argument("--output", default=str(ROOT / "data" / "public" / "loghub_hdfs_sample.jsonl"))
    parser.add_argument("--summary", default=str(ROOT / "artifacts" / "public_loghub_summary.json"))
    parser.add_argument("--limit", type=int, default=200)
    args = parser.parse_args()

    events = convert(Path(args.input), args.limit)
    output = Path(args.output)
    count = write_jsonl(events, output)
    summary = {
        "input_source": display_path(Path(args.input)),
        "output": display_path(output),
        "event_count": count,
        "dataset": "Loghub HDFS_2k public sample",
        "label_policy": "unlabeled format-validation sample; labels are set to 0 and must not be reported as detection accuracy",
        "source_url": "https://github.com/logpai/loghub/tree/master/HDFS",
    }
    summary_path = Path(args.summary)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
