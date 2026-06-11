from __future__ import annotations

import json

from sqlalchemy import select

from app.domain.entities.agent_request_audit import AgentRequestAuditEntity
from app.domain.interfaces.v1.agent_request_audit_repository import AgentRequestAuditRepository
from app.infrastructure.orm.models import AuditRow
from app.infrastructure.orm.session import session_scope


class PostgresAgentRequestAuditRepository(AgentRequestAuditRepository):
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    async def record_event(self, event: AgentRequestAuditEntity) -> AgentRequestAuditEntity:
        payload = event.model_dump(mode="python", by_alias=False, exclude_none=True)
        with session_scope(self.database_url) as session:
            session.add(
                AuditRow(
                    id=str(payload["id"]),
                    approval_id=f"agent-request:{payload['request_id']}",
                    action=str(payload.get("action") or "agent_request"),
                    actor_id=payload.get("actor_id"),
                    timestamp=str(payload.get("timestamp") or ""),
                    details=json.dumps(payload),
                )
            )
            session.commit()
        return AgentRequestAuditEntity.model_validate(payload)

    async def list_events(self, *, limit: int = 100, offset: int = 0) -> list[AgentRequestAuditEntity]:
        if limit < 0 or offset < 0:
            raise ValueError("limit and offset must be non-negative")

        with session_scope(self.database_url) as session:
            rows = (
                session.execute(
                    select(AuditRow)
                    .where(AuditRow.approval_id.like("agent-request:%"))
                    .order_by(AuditRow.timestamp.desc(), AuditRow.id.desc())
                )
                .scalars()
                .all()
            )

        window = rows[offset : offset + limit]
        events: list[AgentRequestAuditEntity] = []
        for row in window:
            parsed: dict | None = None
            if row.details:
                try:
                    payload = json.loads(str(row.details))
                except Exception:
                    payload = None
                if isinstance(payload, dict):
                    parsed = payload
            if parsed is None:
                parsed = {
                    "id": row.id,
                    "request_id": str(row.approval_id or "agent-request:unknown").replace("agent-request:", "", 1),
                    "timestamp": str(row.timestamp or ""),
                    "action": str(row.action or "agent_request"),
                    "endpoint": "",
                    "method": "",
                    "response_type": "unknown_response",
                    "status_code": 0,
                    "success": False,
                    "actor_id": row.actor_id,
                }
            events.append(AgentRequestAuditEntity.model_validate(parsed))

        return events
