from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import Field

from app.domain.entities.base import EntityModel


class AgentRequestAuditEntity(EntityModel):
    id: str
    request_id: str
    timestamp: str
    action: str
    endpoint: str
    method: str
    actor_id: str | None = None
    correlation_id: str | None = None
    agent_type: str | None = None
    agent_source: str | None = None
    agent_instance_id: str | None = None
    request_origin: str | None = None
    user_agent: str | None = None
    response_type: str
    status_code: int
    success: bool
    details: dict[str, Any] = Field(default_factory=dict)


def build_agent_request_audit_entity(
    *,
    action: str,
    endpoint: str,
    method: str,
    response_type: str,
    status_code: int,
    success: bool,
    request_id: str | None = None,
    actor_id: str | None = None,
    correlation_id: str | None = None,
    agent_type: str | None = None,
    agent_source: str | None = None,
    agent_instance_id: str | None = None,
    request_origin: str | None = None,
    user_agent: str | None = None,
    details: dict[str, Any] | None = None,
) -> AgentRequestAuditEntity:
    normalized_request_id = str(request_id or "").strip() or f"agent-req-{uuid4().hex}"
    now = datetime.now(UTC).isoformat()
    return AgentRequestAuditEntity(
        id=f"agent-audit-{uuid4().hex}",
        request_id=normalized_request_id,
        timestamp=now,
        action=str(action or "agent_request"),
        endpoint=str(endpoint or ""),
        method=str(method or "GET"),
        actor_id=(str(actor_id).strip() or None) if actor_id is not None else None,
        correlation_id=(str(correlation_id).strip() or None) if correlation_id is not None else None,
        agent_type=(str(agent_type).strip() or None) if agent_type is not None else None,
        agent_source=(str(agent_source).strip() or None) if agent_source is not None else None,
        agent_instance_id=(str(agent_instance_id).strip() or None) if agent_instance_id is not None else None,
        request_origin=(str(request_origin).strip() or None) if request_origin is not None else None,
        user_agent=(str(user_agent).strip() or None) if user_agent is not None else None,
        response_type=str(response_type or "unknown_response"),
        status_code=int(status_code),
        success=bool(success),
        details=dict(details or {}),
    )
