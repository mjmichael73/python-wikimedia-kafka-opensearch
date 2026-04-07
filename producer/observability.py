import json
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable

from prometheus_client import CONTENT_TYPE_LATEST, Counter, generate_latest, REGISTRY

KNOWN_LOGRECORD_KEYS = frozenset(
    {
        "name",
        "msg",
        "args",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
        "message",
        "taskName",
    },
)

producer_events_total = Counter(
    "wikimedia_producer_events_total",
    "Wikimedia SSE messages successfully produced to Kafka",
    ("topic",),
)

producer_errors_total = Counter(
    "wikimedia_producer_errors_total",
    "Producer errors",
    ("phase",),
)


class _ServiceFilter(logging.Filter):
    def __init__(self, service: str) -> None:
        super().__init__()
        self._service = service

    def filter(self, record: logging.LogRecord) -> bool:
        if record.name == self._service or record.name.startswith(f"{self._service}."):
            record.service = self._service  # type: ignore[attr-defined]
        return True


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": getattr(record, "service", None),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        for key, value in record.__dict__.items():
            if key in KNOWN_LOGRECORD_KEYS or key.startswith("_"):
                continue
            if key == "service":
                continue
            payload[key] = value
        return json.dumps({k: v for k, v in payload.items() if v is not None}, default=str)


def configure_logging(service: str) -> logging.Logger:
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler()
    handler.setFormatter(JsonLogFormatter())
    handler.addFilter(_ServiceFilter(service))
    root.addHandler(handler)
    root.setLevel(level)
    return logging.getLogger(service)


def start_observability_http(
    service: str,
    port: int,
    *,
    ready_fn: Callable[[], bool] | None = None,
) -> None:
    class _Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args) -> None:  # noqa: A003
            return

        def _json(self, code: int, body: dict) -> None:
            raw = json.dumps(body).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self) -> None:
            path = self.path.split("?", 1)[0]
            if path in ("/healthz", "/health"):
                self._json(200, {"status": "ok", "service": service})
            elif path in ("/ready", "/readiness"):
                ok = ready_fn is None or ready_fn()
                self._json(
                    200 if ok else 503,
                    {"status": "ready" if ok else "not_ready", "service": service},
                )
            elif path == "/metrics":
                data = generate_latest(REGISTRY)
                self.send_response(200)
                self.send_header("Content-Type", CONTENT_TYPE_LATEST)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            else:
                self.send_error(404, "Not Found")

    server = ThreadingHTTPServer(("0.0.0.0", port), _Handler)
    threading.Thread(target=server.serve_forever, name="obs-http", daemon=True).start()
