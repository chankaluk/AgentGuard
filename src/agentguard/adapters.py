from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from .schema import BehaviorEvent


DEFAULT_MAPPING = {
    "timestamp": "timestamp",
    "entity_id": "entity_id",
    "source": "source",
    "event_type": "event_type",
    "action": "action",
    "object_type": "object_type",
    "object_name": "object_name",
    "result": "result",
    "label": "label",
    "scenario": "scenario",
}


def _value(row: dict[str, str], mapping: dict[str, str], field: str, default: Any):
    source_name = mapping.get(field)
    if not source_name:
        return default
    value = row.get(source_name, default)
    return default if value is None or value == "" else value


def pseudonymize(value: str, salt: str) -> str:
    digest = hashlib.sha256((salt + value).encode("utf-8")).hexdigest()[:16]
    return f"entity-{digest}"


def iter_csv_events(
    path: str | Path,
    mapping: dict[str, str] | None = None,
    anonymize_entities: bool = False,
    salt: str | None = None,
) -> Iterable[BehaviorEvent]:
    if anonymize_entities and not salt:
        raise ValueError("启用实体匿名化时必须显式提供非空匿名化盐")
    fields = {**DEFAULT_MAPPING, **(mapping or {})}
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for line_number, row in enumerate(reader, 2):
            try:
                entity_id = str(_value(row, fields, "entity_id", "unknown-entity"))
                if anonymize_entities:
                    entity_id = pseudonymize(entity_id, str(salt))
                yield BehaviorEvent(
                    timestamp=str(_value(row, fields, "timestamp", "")),
                    entity_id=entity_id,
                    source=str(_value(row, fields, "source", "host")),
                    event_type=str(_value(row, fields, "event_type", "unknown")),
                    action=str(_value(row, fields, "action", "unknown")),
                    object_type=str(_value(row, fields, "object_type", "unknown")),
                    object_name=str(_value(row, fields, "object_name", "unknown")),
                    result=str(_value(row, fields, "result", "success")),
                    label=int(float(_value(row, fields, "label", 0))),
                    scenario=str(_value(row, fields, "scenario", "normal")),
                    raw={"csv_line": line_number, "source_file": Path(path).name},
                )
            except Exception as exc:
                raise ValueError(f"CSV conversion failed at line {line_number}: {exc}") from exc


def write_jsonl(events: Iterable[BehaviorEvent], output: str | Path) -> int:
    count = 0
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")
            count += 1
    return count
