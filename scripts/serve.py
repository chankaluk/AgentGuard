from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from _bootstrap import ROOT
from agentguard.baselines import score_hybrid_records
from agentguard.data import group_sequences, load_records
from agentguard.engine import AgentGuardDetector
from agentguard.schema import BehaviorEvent


MAX_BODY_BYTES = 1024 * 1024
MAX_EVENTS = 5000


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
        raise RequestLimitError("请求体超过 1 MiB")
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
            return self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})

        def do_POST(self):
            if urlparse(self.path).path != "/api/analyze":
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
