from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path

from _bootstrap import ROOT

os.environ.setdefault("MPLBACKEND", "Agg")
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / "artifacts" / ".matplotlib"))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from agentguard.baselines import score_hybrid_records
from agentguard.data import load_records
from agentguard.engine import AgentGuardDetector, benchmark_detector, save_json
from agentguard.metrics import calculate_metrics


plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Arial Unicode MS"]
plt.rcParams["axes.unicode_minus"] = False

SCENARIO_NAMES = {
    "credential_access": "凭据访问",
    "lateral_movement": "横向移动",
    "mass_file_tampering": "批量文件破坏",
    "persistence": "持久化",
    "prompt_injection_exfiltration": "提示注入与数据外传",
}


def make_plots(metrics: dict, scores: np.ndarray, labels: np.ndarray, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    plt.style.use("seaborn-v0_8-whitegrid")
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Arial Unicode MS"]
    plt.rcParams["axes.unicode_minus"] = False
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.hist(scores[labels == 0], bins=20, alpha=0.72, label="正常序列", color="#4f8bd6")
    ax.hist(scores[labels == 1], bins=20, alpha=0.72, label="异常序列", color="#e45b5b")
    ax.axvline(metrics["threshold"], color="#222", linestyle="--", label="告警阈值")
    ax.set(xlabel="异常分数", ylabel="序列数量", title="AgentGuard 异常分数分布")
    ax.legend()
    fig.tight_layout()
    fig.savefig(output_dir / "score_distribution.png", dpi=180)
    plt.close(fig)

    scenarios = metrics.get("by_scenario", {})
    if scenarios:
        names = list(scenarios)
        labels_zh = [SCENARIO_NAMES.get(name, name) for name in names]
        values = [scenarios[name]["detection_rate"] * 100 for name in names]
        fig, ax = plt.subplots(figsize=(9, 4.8))
        bars = ax.barh(labels_zh, values, color="#36a178")
        ax.set_xlim(0, 100)
        ax.set_xlabel("检出率（%）")
        ax.set_title("各异常场景检出覆盖率")
        for bar, value in zip(bars, values):
            ax.text(value + 1, bar.get_y() + bar.get_height() / 2, f"{value:.1f}%", va="center")
        fig.tight_layout()
        fig.savefig(output_dir / "scenario_detection_rate.png", dpi=180)
        plt.close(fig)


def scenario_metrics(records, scores: np.ndarray, threshold: float) -> dict:
    result = {}
    for scenario in sorted({record.scenario for record in records if record.label}):
        indices = [index for index, record in enumerate(records) if record.scenario == scenario]
        if indices:
            scenario_scores = scores[indices]
            result[scenario] = {
                "count": len(indices),
                "detection_rate": float((scenario_scores >= threshold).mean()),
                "mean_score": float(scenario_scores.mean()),
            }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate AgentGuard and export evidence")
    parser.add_argument("--checkpoint", default=str(ROOT / "artifacts" / "agentguard.pt"))
    parser.add_argument("--input", default=str(ROOT / "data" / "demo" / "test.jsonl"))
    parser.add_argument("--output-dir", default=str(ROOT / "artifacts" / "evaluation"))
    args = parser.parse_args()
    detector = AgentGuardDetector(args.checkpoint)
    config = detector.config
    _, records = load_records(
        args.input, config["window_size"], config["stride"], config["min_events"]
    )
    labels, hybrid_scores, model_scores, rule_scores, _ = score_hybrid_records(
        detector, records
    )
    performance = benchmark_detector(detector, records)
    transformer_metrics = calculate_metrics(
        labels, model_scores, detector.threshold
    ).to_dict()
    rule_metrics = calculate_metrics(labels, rule_scores, detector.threshold).to_dict()
    metrics = calculate_metrics(labels, hybrid_scores, detector.threshold).to_dict()
    for key in (
        "sequence_count",
        "elapsed_seconds",
        "mean_latency_ms",
        "throughput_sequences_per_second",
        "process_rss_mb_after",
        "rss_delta_mb",
    ):
        metrics[key] = performance[key]
    metrics["transformer_only"] = transformer_metrics
    metrics["ordered_rule_only"] = rule_metrics
    metrics["fusion_method"] = "max(transformer_score, ordered_rule_score)"
    metrics["by_scenario"] = scenario_metrics(records, hybrid_scores, detector.threshold)
    checkpoint_size = Path(args.checkpoint).stat().st_size / (1024 * 1024)
    metrics["checkpoint_size_mb"] = checkpoint_size
    metrics["dataset_disclosure"] = (
        "Self-built reproducible hard-negative engineering benchmark. "
        "It validates the software pipeline and does not represent production deployment."
    )
    output_dir = Path(args.output_dir)
    save_json(metrics, output_dir / "metrics.json")
    alerts = []
    for record, score, model_score, rule_score in zip(
        records, hybrid_scores, model_scores, rule_scores
    ):
        if score >= detector.threshold:
            alerts.append(detector.explain_record(
                record,
                float(score),
                model_score=float(model_score),
                rule_score=float(rule_score),
            ))
    with (output_dir / "alerts.jsonl").open("w", encoding="utf-8") as handle:
        for alert in alerts:
            handle.write(json.dumps(alert, ensure_ascii=False) + "\n")
    with (output_dir / "alerts.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "entity_id", "score", "model_score", "rule_score", "threshold",
                "severity", "explanation", "mapped_tactics",
            ],
        )
        writer.writeheader()
        for alert in alerts:
            writer.writerow({
                **{
                    key: alert[key]
                    for key in [
                        "entity_id", "score", "model_score", "rule_score", "threshold",
                        "severity", "explanation",
                    ]
                },
                "mapped_tactics": "; ".join(alert["mapped_tactics"]),
            })
    make_plots(metrics, hybrid_scores, labels, output_dir)
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
