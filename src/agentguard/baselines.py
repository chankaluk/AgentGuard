from __future__ import annotations

from collections import defaultdict
from typing import Iterable, Sequence

import numpy as np

from .data import SequenceRecord
from .metrics import calculate_metrics
from .schema import BehaviorEvent


def attack_only_tokens(events: Iterable[BehaviorEvent]) -> set[str]:
    """返回训练集中只在标注异常事件出现的行为词元。"""

    labels_by_token: dict[str, set[int]] = defaultdict(set)
    for event in events:
        labels_by_token[event.token()].add(int(event.label))
    return {
        token for token, labels in labels_by_token.items()
        if labels == {1}
    }


def evaluate_token_lookup(
    train_events: Iterable[BehaviorEvent],
    records: Sequence[SequenceRecord],
) -> dict[str, float | int]:
    """评估不含序列建模的异常专属词元查表基线。"""

    tokens = attack_only_tokens(train_events)
    labels = np.asarray([record.label for record in records], dtype=int)
    scores = np.asarray(
        [float(any(event.token() in tokens for event in record.events)) for record in records],
        dtype=float,
    )
    result = calculate_metrics(labels, scores, 0.5).to_dict()
    result["attack_only_token_count"] = len(tokens)
    result["baseline"] = "attack_only_token_lookup"
    return result


def _ordered(record: SequenceRecord, predicates) -> bool:
    cursor = -1
    for predicate in predicates:
        found = None
        for index in range(cursor + 1, len(record.events)):
            if predicate(record.events[index]):
                found = index
                break
        if found is None:
            return False
        cursor = found
    return True


def sequence_rule_score(record: SequenceRecord) -> float:
    """按事件顺序计算透明规则分数，用作非学习基线。"""

    score = 0.0
    if _ordered(record, (
        lambda event: event.action == "read" and event.object_type == "secret",
        lambda event: event.event_type == "network" and event.action == "connect",
        lambda event: event.action == "upload",
    )):
        score += 0.75
    if _ordered(record, (
        lambda event: event.event_type == "permission" and event.action == "elevate",
        lambda event: event.action == "read" and event.object_type == "secret",
    )):
        score += 0.25
    if _ordered(record, (
        lambda event: event.event_type == "registry" and event.action == "set",
        lambda event: event.event_type == "scheduler" and event.action == "create",
    )):
        score += 0.70
    if _ordered(record, (
        lambda event: event.event_type == "file" and event.action == "enumerate",
        lambda event: event.event_type == "file" and event.action == "write_many",
        lambda event: event.object_type == "backup" and event.action == "delete",
    )):
        score += 0.80
    if _ordered(record, (
        lambda event: event.event_type == "network" and event.action == "scan",
        lambda event: event.action == "remote_start",
    )):
        score += 0.75
    public_failures = [
        event for event in record.events
        if event.source == "public_loghub"
        and (
            event.result.lower() == "failure"
            or event.action in {"fail", "interrupt"}
        )
    ]
    if len(public_failures) >= 3:
        score += 0.72
    return min(1.0, score)


def evaluate_rule_baseline(
    records: Sequence[SequenceRecord], threshold: float = 0.5
) -> dict[str, float | int | str]:
    labels = np.asarray([record.label for record in records], dtype=int)
    scores = np.asarray([sequence_rule_score(record) for record in records], dtype=float)
    result = calculate_metrics(labels, scores, threshold).to_dict()
    result["baseline"] = "ordered_transparent_rules"
    return result


def fuse_model_and_rule_scores(
    model_scores: Sequence[float] | np.ndarray,
    records: Sequence[SequenceRecord],
) -> tuple[np.ndarray, np.ndarray]:
    """按最大值融合模型分数与透明顺序规则分数。"""

    model_array = np.asarray(model_scores, dtype=float)
    if model_array.ndim != 1:
        raise ValueError("模型分数必须是一维数组")
    if len(model_array) != len(records):
        raise ValueError("模型分数数量必须与序列数量一致")

    rule_scores = np.asarray(
        [sequence_rule_score(record) for record in records],
        dtype=float,
    )
    return np.maximum(model_array, rule_scores), rule_scores


def score_hybrid_records(detector, records: Sequence[SequenceRecord], batch_size: int = 256):
    """共享的混合推理入口，同时保留模型与规则分数。"""

    labels, model_scores, auxiliary = detector.score_records(records, batch_size)
    hybrid_scores, rule_scores = fuse_model_and_rule_scores(model_scores, records)
    return labels, hybrid_scores, model_scores, rule_scores, auxiliary
