from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import platform
from datetime import datetime, timezone
from pathlib import Path

from _bootstrap import ROOT
from agentguard.adapters import write_jsonl
from agentguard.schema import BehaviorEvent

try:
    import psutil
except ImportError as exc:  # pragma: no cover - environment guard
    raise SystemExit("collect_local_normal.py requires psutil. Run setup_env.ps1 first.") from exc


def pseudonym(value: str, salt: str) -> str:
    digest = hashlib.sha256((salt + value).encode("utf-8")).hexdigest()[:16]
    return f"local-{digest}"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def safe_process_name(name: str | None) -> str:
    text = (name or "unknown_process").strip().lower()
    keep = []
    for char in text:
        keep.append(char if char.isalnum() or char in {"_", "-", "."} else "_")
    return "".join(keep)[:80] or "unknown_process"


def collect_events(salt: str, process_limit: int, connection_limit: int) -> list[BehaviorEvent]:
    entity = pseudonym(f"{platform.node()}:{getpass.getuser()}", salt)
    events: list[BehaviorEvent] = []
    timestamp = now_iso()

    processes = []
    for proc in psutil.process_iter(["pid", "name", "status"]):
        try:
            info = proc.info
        except (psutil.Error, OSError):
            continue
        processes.append((int(info.get("pid") or 0), safe_process_name(info.get("name")), str(info.get("status") or "unknown")))
    for _, name, status in sorted(processes)[:process_limit]:
        events.append(
            BehaviorEvent(
                timestamp=timestamp,
                entity_id=entity,
                source="host",
                event_type="process",
                action="observed",
                object_type="process",
                object_name=name,
                result="success" if status in {"running", "sleeping"} else status,
                label=0,
                scenario="local_normal_snapshot",
                raw={"collector": "collect_local_normal.py", "privacy": "process name only; no command line"},
            )
        )

    connections = []
    for conn in psutil.net_connections(kind="inet"):
        remote = conn.raddr
        if not remote:
            continue
        port = getattr(remote, "port", None)
        status = str(conn.status or "unknown").lower()
        connections.append((status, int(port or 0)))
    for status, port in connections[:connection_limit]:
        bucket = f"remote_port_{port}" if port else "remote_port_unknown"
        events.append(
            BehaviorEvent(
                timestamp=timestamp,
                entity_id=entity,
                source="host",
                event_type="network",
                action="connect",
                object_type="port",
                object_name=bucket,
                result="success" if status in {"established", "listen", "none"} else status,
                label=0,
                scenario="local_normal_snapshot",
                raw={"collector": "collect_local_normal.py", "privacy": "remote IP omitted"},
            )
        )
    return events


def display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.name


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect a privacy-preserving local normal telemetry snapshot")
    parser.add_argument("--output", default=str(ROOT / "data" / "local" / "normal_from_host.jsonl"))
    parser.add_argument("--summary", default=str(ROOT / "artifacts" / "local_normal_summary.json"))
    parser.add_argument("--salt", required=True, help="Secret salt for pseudonymizing the local entity id")
    parser.add_argument("--process-limit", type=int, default=80)
    parser.add_argument("--connection-limit", type=int, default=40)
    args = parser.parse_args()

    events = collect_events(args.salt, args.process_limit, args.connection_limit)
    output = Path(args.output)
    count = write_jsonl(events, output)
    summary = {
        "input": display_path(output),
        "event_count": count,
        "label": "normal only",
        "scenario": "local_normal_snapshot",
        "privacy": "entity_id salted; command lines, usernames, hostnames and remote IPs are not stored",
    }
    summary_path = Path(args.summary)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
