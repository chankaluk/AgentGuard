from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from _bootstrap import ROOT
from agentguard.schema import BehaviorEvent


DEFAULT_INPUTS = (
    ROOT / "data" / "local" / "normal_from_host.jsonl",
    ROOT / "data" / "local" / "controlled_security_test.jsonl",
    ROOT / "data" / "public" / "loghub_hdfs_sample.jsonl",
)


def load_events(path: Path) -> list[BehaviorEvent]:
    events = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                events.append(BehaviorEvent.from_dict(json.loads(line)))
            except Exception as exc:
                raise ValueError(f"{path} line {line_number}: {exc}") from exc
    return events


def ordered_rule_hit(events: list[BehaviorEvent]) -> bool:
    ordered = sorted(events, key=lambda event: event.parsed_time())
    cursor = -1
    predicates = (
        lambda event: event.action == "read" and event.object_type == "secret",
        lambda event: event.event_type == "network" and event.action == "connect",
        lambda event: event.action == "upload",
    )
    for predicate in predicates:
        for index in range(cursor + 1, len(ordered)):
            if predicate(ordered[index]):
                cursor = index
                break
        else:
            return False
    return True


def summarize(path: Path) -> dict:
    events = load_events(path)
    by_entity: dict[str, list[BehaviorEvent]] = defaultdict(list)
    for event in events:
        by_entity[event.entity_id].append(event)
    label_counts = Counter(str(event.label) for event in events)
    scenario_counts = Counter(event.scenario for event in events)
    event_type_counts = Counter(event.event_type for event in events)
    rule_hit_entities = [
        entity_id for entity_id, entity_events in sorted(by_entity.items())
        if ordered_rule_hit(entity_events)
    ]
    first_events = [
        {
            "timestamp": event.timestamp,
            "entity_id": event.entity_id,
            "source": event.source,
            "event_type": event.event_type,
            "action": event.action,
            "object_type": event.object_type,
            "object_name": event.object_name,
            "label": event.label,
            "scenario": event.scenario,
        }
        for event in events[:3]
    ]
    return {
        "path": display_path(path),
        "event_count": len(events),
        "entity_count": len(by_entity),
        "label_counts": dict(sorted(label_counts.items())),
        "scenario_counts": dict(sorted(scenario_counts.items())),
        "event_type_counts": dict(sorted(event_type_counts.items())),
        "transparent_rule_hit_entities": rule_hit_entities,
        "example_events": first_events,
    }


def display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.name


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize supplemental AgentGuard JSONL inputs without requiring PyTorch")
    parser.add_argument("--output", default=str(ROOT / "artifacts" / "supplemental_data_report.json"))
    parser.add_argument("inputs", nargs="*", default=[str(path) for path in DEFAULT_INPUTS])
    args = parser.parse_args()
    report = {
        "purpose": "input/output extraction summary for local normal, controlled security, and public Loghub samples",
        "model_inference_note": "Run scripts/analyze.py inside the project .venv to produce model_score/rule_score/final alerts.",
        "inputs": [summarize(Path(path)) for path in args.inputs],
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
