from __future__ import annotations

import json

from sqlalchemy import select

from app.domain.entities.connector_audit import ConnectorAuditEntity
from app.domain.interfaces.v1.connector_audit_repository import ConnectorAuditRepository
from app.infrastructure.orm.models import AuditRow
from app.infrastructure.orm.session import session_scope


class PostgresConnectorAuditRepository(ConnectorAuditRepository):
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    async def record_event(self, event: ConnectorAuditEntity) -> ConnectorAuditEntity:
        payload = event.model_dump(mode="python", by_alias=False, exclude_none=True)
        approval_id = f"connector:{payload['provider']}"
        connector_instance_id = str(payload.get("connector_instance_id") or "").strip()
        if connector_instance_id:
            approval_id = f"{approval_id}:{connector_instance_id}"
        with session_scope(self.database_url) as session:
            session.add(
                AuditRow(
                    id=str(payload["id"]),
                    approval_id=approval_id,
                    action=str(payload.get("action") or "connector_event"),
                    actor_id=payload.get("actor_id"),
                    timestamp=str(payload.get("timestamp") or ""),
                    details=json.dumps(payload),
                )
            )
            session.commit()
        return ConnectorAuditEntity.model_validate(payload)

    async def list_events(
        self,
        *,
        provider: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ConnectorAuditEntity]:
        if limit < 0 or offset < 0:
            raise ValueError("limit and offset must be non-negative")

        normalized_provider = str(provider or "").strip().lower() or None
        approval_prefix = "connector:%"
        if normalized_provider is not None:
            approval_prefix = f"connector:{normalized_provider}%"

        with session_scope(self.database_url) as session:
            rows = (
                session.execute(
                    select(AuditRow)
                    .where(AuditRow.approval_id.like(approval_prefix))
                    .order_by(AuditRow.timestamp.desc(), AuditRow.id.desc())
                )
                .scalars()
                .all()
            )

        window = rows[offset : offset + limit]
        events: list[ConnectorAuditEntity] = []
        for row in window:
            parsed: dict | None = None
            approval_value = str(row.approval_id or "connector:unknown")
            approval_suffix = approval_value.split("connector:", 1)[-1]
            provider_value = approval_suffix.split(":", 1)[0]
            instance_value = approval_suffix.split(":", 1)[1] if ":" in approval_suffix else None
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
                    "request_id": f"connector-req-{row.id}",
                    "timestamp": str(row.timestamp or ""),
                    "action": str(row.action or "connector_event"),
                    "provider": provider_value,
                    "connector_instance_id": instance_value,
                    "endpoint": "",
                    "method": "",
                    "response_type": "unknown_response",
                    "status_code": 0,
                    "success": False,
                    "details": {},
                    "actor_id": row.actor_id,
                }
            elif instance_value and not str(parsed.get("connector_instance_id") or "").strip():
                parsed["connector_instance_id"] = instance_value
            events.append(ConnectorAuditEntity.model_validate(parsed))

        return events