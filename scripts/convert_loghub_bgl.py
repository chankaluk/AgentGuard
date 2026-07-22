from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from _bootstrap import ROOT
from agentguard.adapters import write_jsonl
from agentguard.schema import BehaviorEvent


def parse_timestamp(value: str) -> str:
    parsed = datetime.strptime(value, "%Y-%m-%d-%H.%M.%S.%f").replace(tzinfo=timezone.utc)
    return parsed.isoformat().replace("+00:00", "Z")


def classify_event(level: str, message: str) -> tuple[str, str, str]:
    lower = message.lower()
    if "socket" in lower or "stream" in lower or "network" in lower:
        return "network", "connect", "service"
    if "interrupt" in lower or "exception" in lower:
        return "process", "interrupt", "kernel"
    if "failed" in lower or "failure" in lower or "fatal" in level.lower():
        return "process", "fail", "service"
    if "parity error corrected" in lower or "corrected" in lower:
        return "process", "correct", "kernel"
    return "log", "observe", "message"


def parse_line(line: str, line_number: int) -> BehaviorEvent | None:
    parts = line.strip().split(maxsplit=9)
    if len(parts) < 10:
        return None
    label_text, epoch, date_text, node, timestamp, repeated_node, category, component, level, message = parts
    is_anomaly = label_text != "-"
    entity_digest = hashlib.sha256(node.encode("utf-8")).hexdigest()[:16]
    event_type, action, object_type = classify_event(level, message)
    return BehaviorEvent(
        timestamp=parse_timestamp(timestamp),
        entity_id=f"bgl-node-{entity_digest}",
        source="public_loghub",
        event_type=event_type,
        action=action,
        object_type=object_type,
        object_name=f"{component.lower()}_{label_text.lower()}"[:80] if is_anomaly else component.lower()[:80],
        result="failure" if is_anomaly or level.lower() in {"error", "fatal", "warning"} else "success",
        label=1 if is_anomaly else 0,
        scenario="public_loghub_bgl_anomaly" if is_anomaly else "public_loghub_bgl_normal",
        raw={
            "dataset": "Loghub BGL_2k",
            "line_number": line_number,
            "original_label": label_text,
            "epoch": epoch,
            "date": date_text,
            "node": node,
            "repeated_node": repeated_node,
            "category": category,
            "component": component,
            "level": level,
            "message": message[:512],
            "source_url": "https://github.com/logpai/loghub/tree/master/BGL",
        },
    )


def convert_text(text: str, limit: int = 500) -> list[BehaviorEvent]:
    events: list[BehaviorEvent] = []
    for line_number, line in enumerate(text.splitlines(), 1):
        if limit and len(events) >= limit:
            break
        event = parse_line(line, line_number)
        if event is not None:
            events.append(event)
    return events


def convert(input_path: Path, limit: int = 500) -> list[BehaviorEvent]:
    return convert_text(input_path.read_text(encoding="utf-8", errors="replace"), limit)


def display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.name


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert a Loghub BGL raw log sample to AgentGuard JSONL")
    parser.add_argument("input", help="Path to BGL_2k.log or another Loghub BGL raw log")
    parser.add_argument("--output", default=str(ROOT / "data" / "public" / "loghub_bgl_sample.jsonl"))
    parser.add_argument("--summary", default=str(ROOT / "artifacts" / "public_loghub_bgl_summary.json"))
    parser.add_argument("--limit", type=int, default=500)
    args = parser.parse_args()

    events = convert(Path(args.input), args.limit)
    count = write_jsonl(events, args.output)
    anomaly_count = sum(event.label for event in events)
    summary = {
        "input_source": display_path(Path(args.input)),
        "output": display_path(Path(args.output)),
        "event_count": count,
        "public_label_anomaly_count": anomaly_count,
        "dataset": "Loghub BGL_2k public sample",
        "label_policy": "BGL first column is used as public ground-truth label: '-' normal, other values anomaly",
        "source_url": "https://github.com/logpai/loghub/tree/master/BGL",
    }
    Path(args.summary).parent.mkdir(parents=True, exist_ok=True)
    Path(args.summary).write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
