from __future__ import annotations

import json
import hashlib
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

from .schema import BehaviorEvent


NORMAL_FLOWS = [
    [
        ("agent", "model", "receive_prompt", "text", "user_request"),
        ("agent", "reasoning", "plan", "task", "task_plan"),
        ("agent", "tool", "read", "file", "project_document"),
        ("host", "process", "start", "process", "python"),
        ("agent", "tool", "write", "file", "project_output"),
        ("agent", "model", "respond", "text", "assistant_response"),
    ],
    [
        ("agent", "model", "receive_prompt", "text", "analysis_request"),
        ("agent", "reasoning", "plan", "task", "analysis_plan"),
        ("agent", "tool", "query", "database", "analytics_db"),
        ("host", "network", "connect", "service", "internal_api"),
        ("agent", "tool", "read", "database", "query_result"),
        ("agent", "model", "respond", "text", "analysis_result"),
    ],
    [
        ("agent", "scheduler", "trigger", "job", "daily_summary"),
        ("agent", "memory", "read", "memory", "user_preferences"),
        ("agent", "tool", "list", "file", "workspace"),
        ("host", "file", "read", "file", "business_report"),
        ("agent", "tool", "write", "file", "summary_report"),
        ("agent", "model", "respond", "text", "summary"),
    ],
]


ATTACK_FLOWS = {
    "prompt_injection_exfiltration": [
        ("agent", "model", "receive_prompt", "text", "untrusted_web_content", 0.3),
        ("agent", "permission", "elevate", "privilege", "admin_scope", 0.7),
        ("agent", "tool", "read", "secret", "credential_store", 1.0),
        ("host", "file", "read", "file", "ssh_private_key", 1.0),
        ("host", "network", "connect", "domain", "newly_seen_external", 0.8),
        ("agent", "tool", "upload", "archive", "secrets_bundle", 1.0),
    ],
    "credential_access": [
        ("host", "process", "start", "process", "powershell_encoded", 0.8),
        ("host", "file", "read", "file", "browser_login_data", 1.0),
        ("host", "process", "dump", "memory", "credential_process", 1.0),
        ("host", "network", "connect", "ip", "rare_external_ip", 0.8),
    ],
    "persistence": [
        ("host", "scheduler", "create", "job", "hidden_task", 0.6),
        ("host", "registry", "set", "registry", "run_key", 1.0),
        ("host", "file", "write", "file", "startup_payload", 0.9),
        ("host", "scheduler", "create", "job", "hidden_task", 0.9),
    ],
    "mass_file_tampering": [
        ("host", "file", "enumerate", "directory", "user_documents", 0.5),
        ("host", "file", "write_many", "file", "encrypted_extension", 1.0),
        ("host", "process", "delete", "backup", "shadow_copy", 1.0),
        ("host", "file", "write", "file", "ransom_note", 1.0),
    ],
    "lateral_movement": [
        ("host", "network", "scan", "subnet", "internal_range", 0.8),
        ("host", "authentication", "fail_many", "account", "service_account", 0.8),
        ("host", "network", "connect", "service", "remote_admin", 0.8),
        ("host", "process", "remote_start", "process", "unknown_binary", 1.0),
    ],
}


HARD_NEGATIVE_FLOWS = {
    "approved_security_export": [
        ("agent", "model", "receive_prompt", "text", "approved_security_review"),
        ("host", "network", "connect", "domain", "approved_backup_endpoint"),
        ("agent", "tool", "read", "secret", "rotated_test_secret"),
        ("agent", "permission", "elevate", "privilege", "approved_admin_window"),
        ("host", "file", "read", "file", "public_test_key"),
        ("agent", "tool", "upload", "archive", "encrypted_audit_export"),
    ],
    "support_diagnostics": [
        ("host", "network", "connect", "ip", "approved_support_ip"),
        ("host", "process", "start", "process", "signed_diagnostics"),
        ("host", "process", "dump", "memory", "owned_test_process"),
        ("host", "file", "read", "file", "diagnostic_bundle"),
    ],
    "approved_software_install": [
        ("host", "scheduler", "create", "job", "signed_update_task"),
        ("host", "file", "write", "file", "approved_startup_helper"),
        ("host", "process", "start", "process", "signed_installer"),
        ("host", "registry", "set", "registry", "approved_run_key"),
    ],
    "backup_rehearsal": [
        ("host", "process", "delete", "backup", "expired_test_snapshot"),
        ("host", "file", "enumerate", "directory", "backup_scope"),
        ("host", "file", "write", "file", "restore_report"),
        ("host", "file", "write_many", "file", "restored_test_files"),
    ],
    "authorized_red_team_validation": [
        ("host", "network", "connect", "service", "isolated_test_service"),
        ("host", "process", "remote_start", "process", "signed_test_binary"),
        ("host", "network", "scan", "subnet", "isolated_test_range"),
        ("host", "authentication", "fail_many", "account", "synthetic_test_account"),
    ],
}


def _normal_noise(rng: random.Random):
    choices = [
        ("host", "file", "read", "file", "config_file"),
        ("host", "network", "resolve", "domain", "approved_domain"),
        ("agent", "memory", "write", "memory", "conversation_summary"),
        ("host", "process", "exit", "process", "python"),
        ("agent", "tool", "inspect", "metadata", "schema"),
    ]
    return rng.choice(choices)


def generate_session(
    rng: random.Random,
    entity_id: str,
    start: datetime,
    anomalous: bool,
    attack_scenarios: tuple[str, ...] | None = None,
    forced_scenario: str | None = None,
    hard_negative_name: str | None = None,
) -> list[BehaviorEvent]:
    flow = list(rng.choice(NORMAL_FLOWS))
    for _ in range(rng.randint(0, 4)):
        flow.insert(rng.randint(1, len(flow) - 1), _normal_noise(rng))
    scenario = "normal"
    if anomalous:
        candidates = attack_scenarios or tuple(ATTACK_FLOWS)
        scenario = forced_scenario or rng.choice(candidates)
        attack = ATTACK_FLOWS[scenario]
        insert_at = rng.randint(1, max(1, len(flow) - 2))
        flow[insert_at:insert_at] = attack
    elif hard_negative_name:
        hard_negative = HARD_NEGATIVE_FLOWS[hard_negative_name]
        insert_at = rng.randint(1, max(1, len(flow) - 2))
        flow[insert_at:insert_at] = hard_negative

    events: list[BehaviorEvent] = []
    current = start
    attack_keys = {
        (a, b, c, d, e) for a, b, c, d, e, *_ in ATTACK_FLOWS.get(scenario, [])
    }
    for item in flow:
        source, event_type, action, object_type, object_name, *risk = item
        current += timedelta(milliseconds=rng.randint(80, 3000))
        is_attack = (source, event_type, action, object_type, object_name) in attack_keys
        events.append(
            BehaviorEvent(
                timestamp=current.isoformat().replace("+00:00", "Z"),
                entity_id=entity_id,
                event_type=event_type,
                action=action,
                object_type=object_type,
                object_name=object_name,
                result="success",
                source=source,
                risk_hint=float(risk[0] if risk else 0.0),
                label=int(is_attack),
                scenario=scenario if is_attack else "normal",
                raw={"generator": "AgentGuard reproducible demo", "seeded": True},
            )
        )
    return events


def generate_dataset(
    output_dir: str | Path,
    seed: int = 2026,
    train_sessions: int = 1000,
    validation_sessions: int = 300,
    test_sessions: int = 400,
) -> dict[str, int]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    base = datetime(2026, 6, 1, tzinfo=timezone.utc)
    counts: dict[str, int] = {}
    specs = {
        "train": (train_sessions, 0.16),
        "validation": (validation_sessions, 0.25),
        "test": (test_sessions, 0.25),
    }
    holdout_scenarios = ("lateral_movement",)
    development_scenarios = tuple(
        scenario for scenario in ATTACK_FLOWS if scenario not in holdout_scenarios
    )
    hard_negative_names = tuple(HARD_NEGATIVE_FLOWS)
    hard_negative_counts: dict[str, int] = {}
    for split, (sessions, anomaly_rate) in specs.items():
        records: list[BehaviorEvent] = []
        hard_negative_count = 0
        for idx in range(sessions):
            anomalous = rng.random() < anomaly_rate
            scenario = "normal"
            forced_scenario = None
            hard_negative_name = None
            if anomalous:
                scenario = rng.choice(development_scenarios)
            elif rng.random() < 0.05:
                hard_negative_name = rng.choice(hard_negative_names)
                hard_negative_count += 1
            entity_id = f"entity_{split}_{idx:04d}"
            start = base + timedelta(days=idx)
            records.extend(
                generate_session(
                    rng,
                    entity_id,
                    start,
                    anomalous=anomalous,
                    attack_scenarios=development_scenarios,
                    forced_scenario=forced_scenario,
                    hard_negative_name=hard_negative_name,
                )
            )
        counts[split] = len(records)
        output_file = output / f"{split}_sessions.json"
        output_file.write_text(json.dumps([record.to_dict() for record in records], indent=2), encoding="utf-8")
    counts["hard_negative_count"] = hard_negative_count
    return counts


def dataset_hash(output_dir: str | Path) -> str:
    output = Path(output_dir)
    hasher = hashlib.sha256()
    for json_file in sorted(output.glob("*.json")):
        hasher.update(json_file.read_bytes())
    return hasher.hexdigest()
