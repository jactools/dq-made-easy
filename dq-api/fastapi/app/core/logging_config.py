import os
import json
import logging
import time
from typing import Any

from app.core.request_context import get_correlation_id, get_user_id

# Standard LogRecord attribute names — excluded from the JSON extra payload
_STDLIB_LOG_RECORD_KEYS = frozenset(
    {
        "name", "msg", "args", "created", "relativeCreated", "levelname", "levelno",
        "pathname", "filename", "module", "funcName", "lineno", "thread", "threadName",
        "processName", "process", "msecs", "exc_info", "exc_text", "stack_info",
        "taskName", "message",
    }
)


class _JsonFormatter(logging.Formatter):
    """Emit each log record as a single-line JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key.startswith("_") or key in _STDLIB_LOG_RECORD_KEYS:
                continue
            payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def normalize_environment_label(environment: str | None) -> str:
    normalized = (environment or "dev").strip().lower()
    if normalized in {"development", "local"}:
        return "dev"
    if normalized in {"testing", "ci"}:
        return "test"
    if normalized in {"production"}:
        return "prod"
    return normalized or "dev"


def _current_trace_id() -> str | None:
    from app.core.telemetry import current_trace_id

    return current_trace_id()


def _current_span_id() -> str | None:
    from app.core.telemetry import current_span_id

    return current_span_id()


class _TelemetryContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        correlation_id = get_correlation_id()
        if correlation_id and not hasattr(record, "correlation_id"):
            record.correlation_id = correlation_id

        if correlation_id and not hasattr(record, "correlationId"):
            record.correlationId = correlation_id

        user_id = get_user_id() or "anonymous"
        if not hasattr(record, "user_id"):
            record.user_id = user_id

        trace_id = _current_trace_id()
        if trace_id and not hasattr(record, "trace_id"):
            record.trace_id = trace_id

        span_id = _current_span_id()
        if span_id and not hasattr(record, "span_id"):
            record.span_id = span_id

        if not hasattr(record, "environment"):
            record.environment = normalize_environment_label(os.getenv("ENVIRONMENT", "dev"))

        if not hasattr(record, "service_name"):
            record.service_name = os.getenv("OTEL_SERVICE_NAME", "dq-api")

        if not hasattr(record, "service_version"):
            record.service_version = os.getenv("OTEL_SERVICE_VERSION", "unknown")

        return True


def configure_logging(log_level: str = "INFO") -> None:
    """Configure the root logger to emit JSON-structured log lines to stderr."""
    formatter = _JsonFormatter()
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    handler.addFilter(_TelemetryContextFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Quiet down noisy third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
