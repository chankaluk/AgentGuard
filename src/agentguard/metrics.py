from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np


@dataclass(slots=True)
class DetectionMetrics:
    threshold: float
    true_positive: int
    false_positive: int
    true_negative: int
    false_negative: int
    detection_rate: float
    false_positive_rate: float
    precision: float
    f1: float
    accuracy: float
    roc_auc: float

    def to_dict(self):
        return asdict(self)


def roc_auc(labels: np.ndarray, scores: np.ndarray) -> float:
    labels = labels.astype(int)
    scores = np.asarray(scores, dtype=float)
    positive_count = int((labels == 1).sum())
    negative_count = int((labels == 0).sum())
    if not positive_count or not negative_count:
        return 0.5
    order = np.argsort(scores, kind="mergesort")
    sorted_scores = scores[order]
    ranks = np.empty(len(scores), dtype=float)
    start = 0
    while start < len(sorted_scores):
        end = start + 1
        while end < len(sorted_scores) and sorted_scores[end] == sorted_scores[start]:
            end += 1
        average_rank = (start + 1 + end) / 2.0
        ranks[order[start:end]] = average_rank
        start = end
    positive_rank_sum = float(ranks[labels == 1].sum())
    baseline = positive_count * (positive_count + 1) / 2.0
    return (positive_rank_sum - baseline) / (positive_count * negative_count)


def calculate_metrics(labels, scores, threshold: float) -> DetectionMetrics:
    labels = np.asarray(labels, dtype=int)
    scores = np.asarray(scores, dtype=float)
    predictions = (scores >= threshold).astype(int)
    tp = int(((predictions == 1) & (labels == 1)).sum())
    fp = int(((predictions == 1) & (labels == 0)).sum())
    tn = int(((predictions == 0) & (labels == 0)).sum())
    fn = int(((predictions == 0) & (labels == 1)).sum())
    recall = tp / max(1, tp + fn)
    fpr = fp / max(1, fp + tn)
    precision = tp / max(1, tp + fp)
    f1 = 2 * precision * recall / max(1e-12, precision + recall)
    accuracy = (tp + tn) / max(1, len(labels))
    return DetectionMetrics(
        threshold=float(threshold),
        true_positive=tp,
        false_positive=fp,
        true_negative=tn,
        false_negative=fn,
        detection_rate=float(recall),
        false_positive_rate=float(fpr),
        precision=float(precision),
        f1=float(f1),
        accuracy=float(accuracy),
        roc_auc=roc_auc(labels, scores),
    )


def choose_threshold(labels, scores, target_fpr: float = 0.15) -> tuple[float, DetectionMetrics]:
    labels = np.asarray(labels, dtype=int)
    scores = np.asarray(scores, dtype=float)
    candidates = np.unique(np.concatenate(([0.0], scores, [1.0])))
    best = None
    for threshold in candidates:
        current = calculate_metrics(labels, scores, float(threshold))
        feasible = current.false_positive_rate <= target_fpr
        key = (int(feasible), current.detection_rate, current.f1, -current.false_positive_rate)
        if best is None or key > best[0]:
            best = (key, float(threshold), current)
    assert best is not None
    return best[1], best[2]
