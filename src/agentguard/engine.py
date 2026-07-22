from __future__ import annotations

import json
import random
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader

try:
    import psutil
except ImportError:  # optional during minimal inference
    psutil = None

from .data import BehaviorSequenceDataset, BehaviorVocabulary, SequenceRecord
from .metrics import calculate_metrics, choose_threshold
from .model import AgentBehaviorTransformer


CHECKPOINT_VERSION = 2
CHECKPOINT_FIELDS = {
    "version",
    "model_state",
    "model_config",
    "runtime_config",
    "vocabulary",
    "threshold",
    "nll_bounds",
    "validation_metrics",
    "best_epoch",
}


def seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.set_num_threads(max(1, min(4, torch.get_num_threads())))


def clone_state_dict(model: nn.Module) -> dict[str, torch.Tensor]:
    """创建与训练参数存储完全独立的 CPU 快照。"""

    return {
        name: value.detach().cpu().clone()
        for name, value in model.state_dict().items()
    }


def validate_checkpoint_payload(payload: Any) -> dict[str, Any]:
    """验证安全加载后的 checkpoint 结构，拒绝未知格式。"""

    if not isinstance(payload, dict):
        raise ValueError("checkpoint 顶层必须是字典")
    unknown = set(payload) - CHECKPOINT_FIELDS
    missing = CHECKPOINT_FIELDS - set(payload)
    if unknown:
        raise ValueError(f"checkpoint 包含未知字段：{sorted(unknown)}")
    if missing:
        raise ValueError(f"checkpoint 缺少字段：{sorted(missing)}")
    if payload["version"] != CHECKPOINT_VERSION:
        raise ValueError(
            f"不支持的 checkpoint 版本：{payload['version']}，"
            f"需要版本 {CHECKPOINT_VERSION}"
        )
    if not isinstance(payload["model_state"], dict) or not payload["model_state"]:
        raise ValueError("checkpoint model_state 必须是非空字典")
    if not all(
        isinstance(name, str) and isinstance(value, torch.Tensor)
        for name, value in payload["model_state"].items()
    ):
        raise ValueError("checkpoint model_state 只能包含命名张量")
    if not isinstance(payload["model_config"], dict):
        raise ValueError("checkpoint model_config 必须是字典")
    if not isinstance(payload["runtime_config"], dict):
        raise ValueError("checkpoint runtime_config 必须是字典")
    vocabulary = payload["vocabulary"]
    if not isinstance(vocabulary, dict) or not all(
        isinstance(token, str) and isinstance(index, int)
        for token, index in vocabulary.items()
    ):
        raise ValueError("checkpoint vocabulary 必须是字符串到整数的字典")
    threshold = payload["threshold"]
    if not isinstance(threshold, (int, float)) or not 0.0 <= float(threshold) <= 1.0:
        raise ValueError("checkpoint threshold 必须位于 0 到 1")
    bounds = payload["nll_bounds"]
    if not isinstance(bounds, (tuple, list)) or len(bounds) != 2:
        raise ValueError("checkpoint nll_bounds 必须包含两个数值")
    low, high = (float(bounds[0]), float(bounds[1]))
    if low > high:
        raise ValueError("checkpoint nll_bounds 下界不能大于上界")
    if not isinstance(payload["validation_metrics"], dict):
        raise ValueError("checkpoint validation_metrics 必须是字典")
    if not isinstance(payload["best_epoch"], int) or payload["best_epoch"] < 1:
        raise ValueError("checkpoint best_epoch 必须是正整数")
    return payload


def _next_event_loss(outputs, tokens, pad_id: int) -> torch.Tensor:
    predictions = outputs["next_event_logits"][:, :-1, :].contiguous()
    targets = tokens[:, 1:].contiguous()
    return nn.functional.cross_entropy(
        predictions.view(-1, predictions.shape[-1]),
        targets.view(-1),
        ignore_index=pad_id,
    )


@dataclass(slots=True)
class TrainingResult:
    best_epoch: int
    threshold: float
    validation_metrics: dict[str, Any]
    history: list[dict[str, float]]
    model_parameters: int


def predict_scores(
    model: AgentBehaviorTransformer,
    loader: DataLoader,
    device: torch.device,
    pad_id: int,
    nll_bounds: tuple[float, float] | None = None,
    classifier_weight: float = 0.8,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    model.eval()
    classifier_scores: list[np.ndarray] = []
    nll_scores: list[np.ndarray] = []
    labels: list[np.ndarray] = []
    with torch.inference_mode():
        for batch in loader:
            tokens = batch["tokens"].to(device)
            features = batch["features"].to(device)
            mask = batch["mask"].to(device)
            outputs = model(tokens, features, mask)
            classifier_scores.append(torch.sigmoid(outputs["logits"]).cpu().numpy())
            predictions = outputs["next_event_logits"][:, :-1, :]
            targets = tokens[:, 1:]
            losses = nn.functional.cross_entropy(
                predictions.transpose(1, 2), targets, ignore_index=pad_id, reduction="none"
            )
            valid = targets != pad_id
            mean_losses = (losses * valid).sum(1) / valid.sum(1).clamp_min(1)
            nll_scores.append(mean_losses.cpu().numpy())
            labels.append(batch["label"].numpy())
    cls = np.concatenate(classifier_scores) if classifier_scores else np.array([])
    nll = np.concatenate(nll_scores) if nll_scores else np.array([])
    y = np.concatenate(labels).astype(int) if labels else np.array([], dtype=int)
    if nll_bounds is None:
        normal_nll = nll[y == 0] if np.any(y == 0) else nll
        low = float(np.quantile(normal_nll, 0.50))
        high = float(np.quantile(normal_nll, 0.99))
    else:
        low, high = nll_bounds
    normalized_nll = np.clip((nll - low) / max(1e-6, high - low), 0.0, 1.0)
    combined = classifier_weight * cls + (1.0 - classifier_weight) * normalized_nll
    return y, combined, nll


def train_model(
    train_records: Sequence[SequenceRecord],
    validation_records: Sequence[SequenceRecord],
    vocabulary: BehaviorVocabulary,
    config: dict[str, Any],
    output_path: str | Path,
) -> TrainingResult:
    seed = int(config["seed"])
    seed_everything(seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    window_size = int(config["window_size"])
    train_dataset = BehaviorSequenceDataset(train_records, vocabulary, window_size)
    validation_dataset = BehaviorSequenceDataset(validation_records, vocabulary, window_size)
    train_loader = DataLoader(
        train_dataset,
        batch_size=int(config["training"]["batch_size"]),
        shuffle=True,
        num_workers=0,
    )
    validation_loader = DataLoader(
        validation_dataset,
        batch_size=int(config["training"]["batch_size"]),
        shuffle=False,
        num_workers=0,
    )
    model = AgentBehaviorTransformer(
        vocab_size=len(vocabulary), window_size=window_size, **config["model"]
    ).to(device)
    positives = sum(record.label for record in train_records)
    negatives = len(train_records) - positives
    pos_weight = torch.tensor([negatives / max(1, positives)], device=device)
    classification_loss = nn.BCEWithLogitsLoss(pos_weight=pos_weight)
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=float(config["training"]["learning_rate"]),
        weight_decay=float(config["training"]["weight_decay"]),
    )
    history: list[dict[str, float]] = []
    best_state = None
    best_key = (-1.0, -1.0)
    best_epoch = 0
    stale_epochs = 0
    loss_weight = float(config["training"]["next_event_loss_weight"])
    target_fpr = float(config["training"]["target_fpr"])

    for epoch in range(1, int(config["training"]["epochs"]) + 1):
        model.train()
        running_loss = 0.0
        for batch in train_loader:
            tokens = batch["tokens"].to(device)
            features = batch["features"].to(device)
            mask = batch["mask"].to(device)
            labels = batch["label"].to(device)
            optimizer.zero_grad(set_to_none=True)
            outputs = model(tokens, features, mask)
            cls_loss = classification_loss(outputs["logits"], labels)
            sequence_loss = _next_event_loss(outputs, tokens, vocabulary.pad_id)
            loss = cls_loss + loss_weight * sequence_loss
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            running_loss += float(loss.detach()) * len(labels)
        y, scores, _ = predict_scores(
            model,
            validation_loader,
            device,
            vocabulary.pad_id,
            classifier_weight=float(config["scoring"]["classifier_weight"]),
        )
        threshold, metrics = choose_threshold(y, scores, target_fpr)
        row = {
            "epoch": float(epoch),
            "train_loss": running_loss / max(1, len(train_dataset)),
            "validation_recall": metrics.detection_rate,
            "validation_fpr": metrics.false_positive_rate,
            "validation_f1": metrics.f1,
            "threshold": threshold,
        }
        history.append(row)
        key = (metrics.detection_rate, metrics.f1)
        if key > best_key:
            best_key = key
            best_epoch = epoch
            best_state = clone_state_dict(model)
            stale_epochs = 0
        else:
            stale_epochs += 1
            if stale_epochs >= int(config["training"]["early_stopping_patience"]):
                break

    if best_state is None:
        raise RuntimeError("Training produced no checkpoint")
    model.load_state_dict(best_state)
    y, provisional_scores, nll = predict_scores(
        model,
        validation_loader,
        device,
        vocabulary.pad_id,
        classifier_weight=float(config["scoring"]["classifier_weight"]),
    )
    normal_nll = nll[y == 0] if np.any(y == 0) else nll
    nll_bounds = (
        float(np.quantile(normal_nll, 0.50)),
        float(np.quantile(normal_nll, 0.99)),
    )
    y, scores, _ = predict_scores(
        model,
        validation_loader,
        device,
        vocabulary.pad_id,
        nll_bounds=nll_bounds,
        classifier_weight=float(config["scoring"]["classifier_weight"]),
    )
    threshold, metrics = choose_threshold(y, scores, target_fpr)
    payload = {
        "version": CHECKPOINT_VERSION,
        "model_state": best_state,
        "model_config": config["model"],
        "runtime_config": config,
        "vocabulary": vocabulary.token_to_id,
        "threshold": threshold,
        "nll_bounds": nll_bounds,
        "validation_metrics": metrics.to_dict(),
        "best_epoch": best_epoch,
    }
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    torch.save(payload, output)
    return TrainingResult(
        best_epoch=best_epoch,
        threshold=threshold,
        validation_metrics=metrics.to_dict(),
        history=history,
        model_parameters=sum(parameter.numel() for parameter in model.parameters()),
    )


class AgentGuardDetector:
    def __init__(self, checkpoint_path: str | Path, device: str = "cpu"):
        self.device = torch.device(device)
        payload = validate_checkpoint_payload(
            torch.load(checkpoint_path, map_location=self.device, weights_only=True)
        )
        self.config = payload["runtime_config"]
        self.vocabulary = BehaviorVocabulary(payload["vocabulary"])
        self.threshold = float(payload["threshold"])
        self.nll_bounds = tuple(payload["nll_bounds"])
        self.model = AgentBehaviorTransformer(
            vocab_size=len(self.vocabulary),
            window_size=int(self.config["window_size"]),
            **payload["model_config"],
        ).to(self.device)
        self.model.load_state_dict(payload["model_state"])
        self.model.eval()

    def score_records(self, records: Sequence[SequenceRecord], batch_size: int = 128):
        dataset = BehaviorSequenceDataset(records, self.vocabulary, int(self.config["window_size"]))
        loader = DataLoader(dataset, batch_size=batch_size, shuffle=False, num_workers=0)
        labels, scores, nll = predict_scores(
            self.model,
            loader,
            self.device,
            self.vocabulary.pad_id,
            self.nll_bounds,
            float(self.config["scoring"]["classifier_weight"]),
        )
        return labels, scores, nll

    def explain_record(
        self,
        record: SequenceRecord,
        score: float,
        *,
        model_score: float | None = None,
        rule_score: float | None = None,
    ) -> dict[str, Any]:
        dataset = BehaviorSequenceDataset([record], self.vocabulary, int(self.config["window_size"]))
        sample = dataset[0]
        tokens = sample["tokens"].unsqueeze(0).to(self.device)
        features = sample["features"].unsqueeze(0).to(self.device)
        mask = sample["mask"].unsqueeze(0).to(self.device)
        with torch.inference_mode():
            outputs = self.model(tokens, features, mask, return_attention=True)
            attention = torch.stack(outputs["attentions"]).mean(dim=(0, 2))[0, 0, 1:]
            predictions = outputs["next_event_logits"][0, :-1]
            targets = tokens[0, 1:]
            surprise = nn.functional.cross_entropy(predictions, targets, reduction="none")
        event_count = min(len(record.events), len(attention))
        attention = attention[:event_count].cpu().numpy()
        surprise_values = np.zeros(event_count, dtype=float)
        usable = min(event_count - 1, len(surprise))
        if usable > 0:
            surprise_values[1 : usable + 1] = surprise[:usable].cpu().numpy()
        def normalize(values):
            values = np.asarray(values, dtype=float)
            span = float(values.max() - values.min()) if len(values) else 0.0
            return np.zeros_like(values) if span < 1e-9 else (values - values.min()) / span
        contributions = 0.45 * normalize(attention) + 0.55 * normalize(surprise_values)
        top_indices = np.argsort(contributions)[::-1][: min(5, event_count)]
        evidence = []
        for index in top_indices:
            event = record.events[int(index)]
            evidence.append(
                {
                    "rank": len(evidence) + 1,
                    "timestamp": event.timestamp,
                    "event": event.token(),
                    "object_name": event.object_name,
                    "contribution": round(float(contributions[index]), 4),
                    "raw_log": event.to_dict(),
                }
            )
        explanation, tactics = _natural_language_explanation(record)
        return {
            "entity_id": record.entity_id,
            "score": round(float(score), 6),
            "model_score": round(float(model_score), 6) if model_score is not None else None,
            "rule_score": round(float(rule_score), 6) if rule_score is not None else None,
            "threshold": round(self.threshold, 6),
            "is_anomaly": bool(score >= self.threshold),
            "severity": _severity(score, self.threshold),
            "explanation": explanation,
            "mapped_tactics": tactics,
            "evidence": evidence,
            "event_timeline": [
                {
                    "index": index + 1,
                    "timestamp": event.timestamp,
                    "event": event.token(),
                    "source": event.source,
                    "event_type": event.event_type,
                    "action": event.action,
                    "object_type": event.object_type,
                    "object_name": event.object_name,
                    "result": event.result,
                    "risk_hint": event.risk_hint,
                    "label": event.label,
                    "scenario": event.scenario,
                    "raw_log": event.to_dict(),
                }
                for index, event in enumerate(record.events)
            ],
            "ground_truth_for_evaluation_only": {
                "label": record.label,
                "scenario": record.scenario,
            },
        }


def _severity(score: float, threshold: float) -> str:
    if score < threshold:
        return "low"
    margin = (score - threshold) / max(1e-6, 1.0 - threshold)
    if margin > 0.65:
        return "critical"
    if margin > 0.30:
        return "high"
    return "medium"


def _natural_language_explanation(record: SequenceRecord) -> tuple[str, list[str]]:
    terms = " ".join(
        f"{event.source} {event.event_type} {event.action} {event.object_type} {event.object_name} {event.result}".lower()
        for event in record.events
    )
    findings = []
    tactics = []
    rules = [
        (("secret", "upload"), "敏感凭据读取后紧接外传动作，呈现数据窃取链路", "Credential Access / Exfiltration"),
        (("registry", "run_key"), "出现启动项注册表写入，具有持久化特征", "Persistence"),
        (("write_many", "shadow_copy"), "短序列内发生批量文件改写与备份删除", "Impact"),
        (("scan", "remote_start"), "先进行内网探测，随后远程启动未知进程", "Discovery / Lateral Movement"),
        (("browser_login_data", "credential_process"), "访问浏览器凭据并尝试读取凭据进程内存", "Credential Access"),
        (("untrusted_web_content", "elevate"), "不可信内容输入后发生权限提升，疑似提示注入导致工具劫持", "Prompt Injection / Privilege Escalation"),
        (("public_loghub", "failure"), "公开系统日志中连续出现失败或致命事件，呈现系统异常波动", "Public Log Anomaly"),
    ]
    for needles, message, tactic in rules:
        if all(needle in terms for needle in needles):
            findings.append(message)
            tactics.append(tactic)
    if not findings:
        findings.append("该行为序列相对训练基线具有较高上下文偏离，关键事件见证据列表")
        tactics.append("Behavioral Anomaly")
    return "；".join(findings) + "。", tactics


def benchmark_detector(
    detector: AgentGuardDetector,
    records: Sequence[SequenceRecord],
) -> dict[str, Any]:
    process = psutil.Process() if psutil is not None else None
    rss_before = process.memory_info().rss if process else 0
    started = time.perf_counter()
    labels, scores, _ = detector.score_records(records)
    elapsed = time.perf_counter() - started
    rss_after = process.memory_info().rss if process else 0
    metrics = calculate_metrics(labels, scores, detector.threshold).to_dict()
    metrics.update(
        {
            "sequence_count": len(records),
            "elapsed_seconds": elapsed,
            "mean_latency_ms": elapsed * 1000.0 / max(1, len(records)),
            "throughput_sequences_per_second": len(records) / max(elapsed, 1e-9),
            "process_rss_mb_after": rss_after / (1024 * 1024) if process else None,
            "rss_delta_mb": (rss_after - rss_before) / (1024 * 1024) if process else None,
        }
    )
    by_scenario = {}
    for scenario in sorted({record.scenario for record in records if record.label}):
        indices = [i for i, record in enumerate(records) if record.scenario == scenario]
        if indices:
            by_scenario[scenario] = {
                "count": len(indices),
                "detection_rate": float((scores[indices] >= detector.threshold).mean()),
                "mean_score": float(scores[indices].mean()),
            }
    metrics["by_scenario"] = by_scenario
    return metrics


def save_json(data: Any, path: str | Path) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
