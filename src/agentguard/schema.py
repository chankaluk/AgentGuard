from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import math
from typing import Any


MAX_TEXT_LENGTH = 2048


@dataclass(slots=True)
class BehaviorEvent:
    timestamp: str
    entity_id: str
    event_type: str
    action: str
    object_type: str
    object_name: str
    result: str = "success"
    source: str = "agent"
    risk_hint: float = 0.0
    label: int = 0
    scenario: str = "normal"
    raw: dict[str, Any] | None = None

    @classmethod
    def from_dict(cls, record: dict[str, Any]) -> "BehaviorEvent":
        if not isinstance(record, dict):
            raise ValueError("事件必须是 JSON 对象")
        required = {"timestamp", "entity_id", "event_type", "action"}
        missing = required - record.keys()
        if missing:
            raise ValueError(f"Missing required fields: {sorted(missing)}")
        text_fields = {
            "timestamp": record["timestamp"],
            "entity_id": record["entity_id"],
            "event_type": record["event_type"],
            "action": record["action"],
            "object_type": record.get("object_type", "unknown"),
            "object_name": record.get("object_name", "unknown"),
            "result": record.get("result", "success"),
            "source": record.get("source", "agent"),
            "scenario": record.get("scenario", "normal"),
        }
        normalized = {}
        for field, value in text_fields.items():
            text = str(value).strip()
            if field in required and not text:
                raise ValueError(f"必填字段不能为空：{field}")
            if len(text) > MAX_TEXT_LENGTH:
                raise ValueError(f"字段过长：{field}")
            normalized[field] = text
        try:
            label = int(record.get("label", 0))
        except (TypeError, ValueError) as exc:
            raise ValueError("label 必须是 0 或 1") from exc
        if label not in {0, 1}:
            raise ValueError("label 必须是 0 或 1")
        try:
            risk_hint = float(record.get("risk_hint", 0.0))
        except (TypeError, ValueError) as exc:
            raise ValueError("risk_hint 必须是有限数值") from exc
        if not math.isfinite(risk_hint):
            raise ValueError("risk_hint 必须是有限数值")
        raw = record.get("raw")
        if raw is not None and not isinstance(raw, dict):
            raise ValueError("raw 必须是 JSON 对象或 null")
        event = cls(
            timestamp=normalized["timestamp"],
            entity_id=normalized["entity_id"],
            event_type=normalized["event_type"],
            action=normalized["action"],
            object_type=normalized["object_type"],
            object_name=normalized["object_name"],
            result=normalized["result"],
            source=normalized["source"],
            risk_hint=risk_hint,
            label=label,
            scenario=normalized["scenario"],
            raw=raw,
        )
        try:
            event.parsed_time()
        except (TypeError, ValueError) as exc:
            raise ValueError(f"无效 timestamp：{event.timestamp}") from exc
        return event

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def parsed_time(self) -> datetime:
        text = self.timestamp.replace("Z", "+00:00")
        value = datetime.fromisoformat(text)
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value

    def token(self) -> str:
        return "|".join(
            [self.source, self.event_type, self.action, self.object_type, self.result]
        ).lower()
