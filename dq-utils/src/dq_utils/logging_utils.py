from __future__ import annotations

import json
import logging
import time
from typing import Any

_STD_KEYS = frozenset(
    {
        "name",
        "msg",
        "args",
        "created",
        "relativeCreated",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "funcName",
        "lineno",
        "thread",
        "threadName",
        "processName",
        "process",
        "msecs",
        "exc_info",
        "exc_text",
        "stack_info",
        "taskName",
        "message",
    }
)


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key.startswith("_") or key in _STD_KEYS:
                continue
            payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(_JsonFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))


def log_event(logger: logging.Logger, event: str, level: str = "info", **context: Any) -> None:
    raw_extra = {"event": event, **context}

    # Never allow callers to overwrite reserved LogRecord attributes.
    # Python's logging will raise KeyError (and can crash workers) if `extra`
    # contains any standard LogRecord keys such as `message`.
    safe_extra: dict[str, Any] = {}
    for key, value in raw_extra.items():
        if key in _STD_KEYS:
            safe_extra[f"ctx_{key}"] = value
        else:
            safe_extra[key] = value

    getattr(logger, level.lower())(event, extra=safe_extra)
