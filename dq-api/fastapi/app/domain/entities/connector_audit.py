from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import Field

from app.domain.entities.base import EntityModel


_SENSITIVE_KEY_PATTERN = re.compile(
    r"(password|passwd|secret|token|authorization|api[-_]?key|private[-_]?key|client[-_]?secret|connection_string|access[-_]?key)",
    re.IGNORECASE,
)
_REDACTED = "[REDACTED]"


def _sanitize(value: Any, key_hint: str | None = None) -> Any:
    if key_hint and _SENSITIVE_KEY_PATTERN.search(key_hint):
        return _REDACTED
    if isinstance(value, dict):
        return {str(key): _sanitize(item, str(key)) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize(item, key_hint) for item in value]
    if isinstance(value, tuple):
        return tuple(_sanitize(item, key_hint) for item in value)
    if isinstance(value, str):
        lowered = value.lower().strip()
        if lowered.startswith("bearer "):
            return _REDACTED
    return value


class ConnectorAuditEntity(EntityModel):
    id: str
    request_id: str
    timestamp: str
    action: str
    provider: str
    connector_instance_id: str | None = None
    endpoint: str
    method: str
    actor_id: str | None = None
    correlation_id: str | None = None
    response_type: str
    status_code: int
    success: bool
    details: dict[str, Any] = Field(default_factory=dict)


def build_connector_audit_entity(
    *,
    action: str,
    provider: str,
    endpoint: str,
    method: str,
    response_type: str,
    status_code: int,
    success: bool,
    request_id: str | None = None,
    actor_id: str | None = None,
    correlation_id: str | None = None,
    connector_instance_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> ConnectorAuditEntity:
    normalized_provider = str(provider or "").strip().lower()
    normalized_request_id = str(request_id or "").strip() or f"connector-req-{uuid4().hex}"
    now = datetime.now(UTC).isoformat()
    return ConnectorAuditEntity(
        id=f"connector-audit-{uuid4().hex}",
        request_id=normalized_request_id,
        timestamp=now,
        action=str(action or "connector_event"),
        provider=normalized_provider,
        connector_instance_id=(str(connector_instance_id).strip() or None) if connector_instance_id is not None else None,
        endpoint=str(endpoint or ""),
        method=str(method or "GET"),
        actor_id=(str(actor_id).strip() or None) if actor_id is not None else None,
        correlation_id=(str(correlation_id).strip() or None) if correlation_id is not None else None,
        response_type=str(response_type or "connector_response"),
        status_code=int(status_code),
        success=bool(success),
        details=_sanitize(dict(details or {})),
    )


__all__ = ["ConnectorAuditEntity", "build_connector_audit_entity"]