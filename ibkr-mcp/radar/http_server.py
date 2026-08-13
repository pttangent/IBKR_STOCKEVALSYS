from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .engine import RadarEngine

UI_PATH = Path(__file__).with_name("ui") / "index.html"


class RadarHandler(BaseHTTPRequestHandler):
    engine: RadarEngine

    def log_message(self, *_: object) -> None:
        return

    def _json(self, payload: object, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            return json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            raise ValueError("invalid json")

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/radar"):
            body = UI_PATH.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if parsed.path in ("/health", "/api/v1/radar/health"):
            self._json(self.engine.connection_status())
            return
        if parsed.path == "/api/v1/radar/plan":
            self._json(self.engine.plan_status())
            return
        if parsed.path == "/api/v1/radar/snapshot":
            symbol = parse_qs(parsed.query).get("symbol", [None])[0]
            try:
                self._json(self.engine.snapshot(symbol))
            except KeyError:
                self._json({"error": "unknown symbol"}, 404)
            return
        if parsed.path == "/api/v1/radar/alerts":
            query = parse_qs(parsed.query)
            limit = int(query.get("limit", [40])[0])
            self._json(self.engine.alerts(limit))
            return
        self._json({"error": "not found"}, 404)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        try:
            payload = self._body()
        except ValueError as exc:
            self._json({"error": str(exc)}, 400)
            return
        if parsed.path == "/api/v1/radar/control":
            action = str(payload.get("action", "")).lower()
            if action == "pause":
                self._json({"action": action, "connection": self.engine.pause()})
                return
            if action == "resume":
                self._json({"action": action, "connection": self.engine.resume()})
                return
            if action == "stop":
                self._json({"action": action, "connection": self.engine.stop()})
                return
            self._json({"error": "action must be pause, resume, or stop"}, 400)
            return
        if parsed.path == "/api/v1/radar/config":
            try:
                result = self.engine.configure(symbols=payload.get("symbols"), mode=payload.get("mode"), market_data_lines=payload.get("marketDataLines"), flow_quote_source=payload.get("flowQuoteSource"))
                self._json(result)
            except (RuntimeError, ValueError) as exc:
                self._json({"error": str(exc)}, 409)
            return
        self._json({"error": "not found"}, 404)


def serve_http(engine: RadarEngine, host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
    handler = type("BoundRadarHandler", (RadarHandler,), {"engine": engine})
    return ThreadingHTTPServer((host, port), handler)
