from __future__ import annotations

import argparse
import json
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from _bootstrap import ROOT
from agentguard.baselines import score_hybrid_records
from agentguard.data import group_sequences, load_records
from agentguard.engine import AgentGuardDetector
from agentguard.schema import BehaviorEvent
from collect_local_normal import collect_events
from convert_loghub_bgl import convert_text as convert_bgl_text
from convert_loghub_hdfs import convert_text as convert_hdfs_text
from generate_controlled_security_logs import generate as generate_controlled_security_events


MAX_BODY_BYTES = 8 * 1024 * 1024
MAX_EVENTS = 5000
DEFAULT_LOCAL_PROCESS_LIMIT = 120
DEFAULT_LOCAL_CONNECTION_LIMIT = 80


class RequestLimitError(ValueError):
    """表示请求超过本地演示服务的资源边界。"""


def checked_content_length(value: str) -> int:
    try:
        length = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Content-Length 无效") from exc
    if length < 0:
        raise ValueError("Content-Length 不能为负数")
    if length > MAX_BODY_BYTES:
        raise RequestLimitError("请求体超过 8 MiB")
    return length


def parse_events_payload(payload) -> list[BehaviorEvent]:
    if not isinstance(payload, dict):
        raise ValueError("请求体必须是 JSON 对象")
    items = payload.get("events", [])
    if not isinstance(items, list):
        raise ValueError("events 必须是数组")
    if len(items) > MAX_EVENTS:
        raise RequestLimitError(f"事件数量超过上限 {MAX_EVENTS}")
    return [BehaviorEvent.from_dict(item) for item in items]


def bounded_int(values, default: int, minimum: int, maximum: int) -> int:
    if not values:
        return default
    try:
        value = int(values[0])
    except (TypeError, ValueError) as exc:
        raise ValueError("query parameter must be an integer") from exc
    return max(minimum, min(maximum, value))


def explain_records(detector: AgentGuardDetector, records):
    if not records:
        return []
    _, scores, model_scores, rule_scores, _ = score_hybrid_records(detector, records)
    return [
        detector.explain_record(
            record,
            float(score),
            model_score=float(model_score),
            rule_score=float(rule_score),
        )
        for record, score, model_score, rule_score in zip(records, scores, model_scores, rule_scores)
    ]


def looks_like_bgl(filename: str, text: str) -> bool:
    if "bgl" in filename.lower():
        return True
    first = next((line.strip() for line in text.splitlines() if line.strip()), "")
    parts = first.split(maxsplit=9)
    return len(parts) >= 10 and "." in parts[2] and "-" in parts[4]


def looks_like_hdfs(filename: str, text: str) -> bool:
    if "hdfs" in filename.lower():
        return True
    first = next((line.strip() for line in text.splitlines() if line.strip()), "")
    return bool(first[:6].isdigit() and " dfs." in first.lower())


def parse_uploaded_log(filename: str, text: str, limit: int) -> tuple[str, list[BehaviorEvent]]:
    stripped = text.lstrip("\ufeff\r\n\t ")
    if looks_like_bgl(filename, text):
        return "loghub_bgl", convert_bgl_text(text, limit=limit)
    if looks_like_hdfs(filename, text):
        return "loghub_hdfs", convert_hdfs_text(text, limit=limit)
    if stripped.startswith("{"):
        events = [
            BehaviorEvent.from_dict(json.loads(line))
            for line in stripped.splitlines()
            if line.strip()
        ][:limit]
        return "agentguard_jsonl", events
    raise ValueError("unsupported log format")


def build_handler(detector: AgentGuardDetector, demo_records):
    dashboard = (ROOT / "web" / "index.html").read_bytes()

    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, body: bytes, content_type: str):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: int, payload):
            self._send(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def do_GET(self):
            path = urlparse(self.path).path
            if path == "/":
                return self._send(HTTPStatus.OK, dashboard, "text/html; charset=utf-8")
            if path == "/api/health":
                return self._json(HTTPStatus.OK, {"status": "ok", "threshold": detector.threshold, "model": "AgentGuard-Hybrid"})
            if path == "/api/demo":
                _, scores, model_scores, rule_scores, _ = score_hybrid_records(
                    detector, demo_records
                )
                ranked = sorted(
                    zip(demo_records, scores, model_scores, rule_scores),
                    key=lambda item: item[1],
                    reverse=True,
                )[:12]
                return self._json(HTTPStatus.OK, [
                    detector.explain_record(
                        record,
                        float(score),
                        model_score=float(model_score),
                        rule_score=float(rule_score),
                    )
                    for record, score, model_score, rule_score in ranked
                ])
            if path == "/api/local-snapshot":
                try:
                    query = parse_qs(urlparse(self.path).query)
                    process_limit = bounded_int(
                        query.get("process_limit"),
                        DEFAULT_LOCAL_PROCESS_LIMIT,
                        10,
                        500,
                    )
                    connection_limit = bounded_int(
                        query.get("connection_limit"),
                        DEFAULT_LOCAL_CONNECTION_LIMIT,
                        0,
                        500,
                    )
                    salt = os.environ.get("AGENTGUARD_LOCAL_SALT", "agentguard-local-dashboard")
                    events = collect_events(salt, process_limit, connection_limit)
                    config = detector.config
                    records = group_sequences(events, config["window_size"], config["stride"], config["min_events"])
                    results = explain_records(detector, records)
                    return self._json(HTTPStatus.OK, {
                        "mode": "local_snapshot",
                        "summary": {
                            "event_count": len(events),
                            "sequence_count": len(records),
                            "alert_count": sum(1 for item in results if item["is_anomaly"]),
                            "privacy": "process names and remote port buckets only; command lines, usernames, hostnames, paths and remote IPs are not returned",
                        },
                        "results": results,
                    })
                except Exception:
                    return self._json(HTTPStatus.BAD_REQUEST, {"error": "本机快照采集或分析失败"})
            if path == "/api/controlled-security":
                events = generate_controlled_security_events()
                config = detector.config
                records = group_sequences(events, config["window_size"], config["stride"], config["min_events"])
                results = sorted(explain_records(detector, records), key=lambda item: item["score"], reverse=True)
                return self._json(HTTPStatus.OK, {
                    "mode": "controlled_security_test",
                    "summary": {
                        "event_count": len(events),
                        "sequence_count": len(records),
                        "alert_count": sum(1 for item in results if item["is_anomaly"]),
                        "safety": "simulated logs only; no credential access, exploit, network scan or upload is executed",
                        "expected_rule_hit": "untrusted prompt -> privilege elevation -> secret read -> external connect -> upload",
                    },
                    "results": results,
                })
            return self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})

        def do_POST(self):
            path = urlparse(self.path).path
            if path == "/api/upload-log":
                try:
                    length = checked_content_length(self.headers.get("Content-Length", "0"))
                    payload = json.loads(self.rfile.read(length) or b"{}")
                    if not isinstance(payload, dict):
                        raise ValueError("payload must be an object")
                    filename = str(payload.get("filename", "uploaded.log"))[:160]
                    content = str(payload.get("content", ""))
                    if not content.strip():
                        raise ValueError("empty upload")
                    limit = bounded_int([payload.get("limit", 800)], 800, 1, MAX_EVENTS)
                    parser_name, events = parse_uploaded_log(filename, content, limit)
                    config = detector.config
                    records = group_sequences(events, config["window_size"], config["stride"], config["min_events"])
                    results = sorted(explain_records(detector, records), key=lambda item: item["score"], reverse=True)
                    return self._json(HTTPStatus.OK, {
                        "mode": "uploaded_log",
                        "summary": {
                            "filename": filename,
                            "parser": parser_name,
                            "event_count": len(events),
                            "sequence_count": len(records),
                            "agentguard_alert_count": sum(1 for item in results if item["is_anomaly"]),
                            "public_label_event_count": sum(event.label for event in events),
                            "public_label_window_count": sum(record.label for record in records),
                            "privacy": "uploaded content is parsed in this local server process and is not sent outside this machine",
                        },
                        "results": results,
                    })
                except RequestLimitError:
                    return self._json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "上传日志超过 8 MiB"})
                except Exception as exc:
                    return self._json(HTTPStatus.BAD_REQUEST, {"error": f"无法自动解析日志：{exc}"})
            if path != "/api/analyze":
                return self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            try:
                length = checked_content_length(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length) or b"{}")
                events = parse_events_payload(payload)
                config = detector.config
                records = group_sequences(events, config["window_size"], config["stride"], config["min_events"])
                _, scores, model_scores, rule_scores, _ = score_hybrid_records(
                    detector, records
                )
                return self._json(HTTPStatus.OK, [
                    detector.explain_record(
                        record,
                        float(score),
                        model_score=float(model_score),
                        rule_score=float(rule_score),
                    )
                    for record, score, model_score, rule_score in zip(
                        records, scores, model_scores, rule_scores
                    )
                ])
            except RequestLimitError:
                return self._json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "请求超过资源限制"})
            except Exception:
                return self._json(HTTPStatus.BAD_REQUEST, {"error": "请求格式无效"})

        def log_message(self, format, *args):
            print(f"[web] {self.address_string()} - {format % args}")

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local AgentGuard dashboard")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--checkpoint", default=str(ROOT / "artifacts" / "agentguard.pt"))
    parser.add_argument("--demo", default=str(ROOT / "data" / "demo" / "test.jsonl"))
    args = parser.parse_args()
    detector = AgentGuardDetector(args.checkpoint)
    config = detector.config
    _, demo_records = load_records(args.demo, config["window_size"], config["stride"], config["min_events"])
    server = ThreadingHTTPServer((args.host, args.port), build_handler(detector, demo_records))
    print(f"AgentGuard dashboard: http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
