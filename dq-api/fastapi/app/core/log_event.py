import logging
import re
from typing import Any

from app.core.request_context import get_correlation_id


_SENSITIVE_KEY_PATTERN = re.compile(
    r"(password|passwd|secret|token|authorization|api[-_]?key|private[-_]?key)",
    re.IGNORECASE,
)
_RAW_ROW_KEY_PATTERN = re.compile(r"(^|_|-)(row|rows|record|records)(_|-|$)", re.IGNORECASE)
_REDACTED = "[REDACTED]"


def _is_sensitive_key(key: str) -> bool:
    return bool(_SENSITIVE_KEY_PATTERN.search(key))


def _is_raw_row_key(key: str) -> bool:
    return bool(_RAW_ROW_KEY_PATTERN.search(key))


def _sanitize(value: Any, key_hint: str | None = None) -> Any:
    if key_hint and _is_sensitive_key(key_hint):
        return _REDACTED
    if key_hint and _is_raw_row_key(key_hint) and isinstance(value, (dict, list, tuple)):
        return _REDACTED
    if isinstance(value, dict):
        return {str(k): _sanitize(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize(item, key_hint) for item in value]
    if isinstance(value, tuple):
        return tuple(_sanitize(item, key_hint) for item in value)
    if isinstance(value, str):
        lowered = value.lower().strip()
        if lowered.startswith("bearer "):
            return _REDACTED
    return value


def log_event(
    logger: logging.Logger,
    event: str,
    level: str = "info",
    **context: Any,
) -> None:
    """
    Emit a structured log record carrying the mandatory DQ-7.4 observability fields.

    Auto-injects ``correlationId`` from the active request ContextVar.
    All keyword arguments are forwarded as extra fields on the log record, so
    the JSON formatter picks them up alongside the standard log fields.

    Recognised context keys (all optional — include when available):
        suiteId, suiteVersion, ruleId, runId,
        dataObjectId, dataObjectVersionId, datasetId, dataProductId,
        component, sourcePipeline, status, reason, newStatus
    """
    safe_context = {k: _sanitize(v, k) for k, v in context.items()}
    extra: dict[str, Any] = {"event": event, **safe_context}
    correlation_id = get_correlation_id()
    if correlation_id is not None:
        extra["correlationId"] = correlation_id
    getattr(logger, level.lower())(event, extra=extra)
