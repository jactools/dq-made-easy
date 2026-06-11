from __future__ import annotations

from copy import deepcopy

from app.domain.entities.connector_audit import ConnectorAuditEntity
from app.domain.interfaces.v1.connector_audit_repository import ConnectorAuditRepository


class InMemoryConnectorAuditRepository(ConnectorAuditRepository):
    def __init__(self) -> None:
        self._events: list[dict] = []

    async def record_event(self, event: ConnectorAuditEntity) -> ConnectorAuditEntity:
        payload = event.model_dump(mode="python", by_alias=False, exclude_none=True)
        self._events.append(deepcopy(payload))
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
        rows = self._events
        if normalized_provider is not None:
            rows = [row for row in rows if str(row.get("provider") or "").strip().lower() == normalized_provider]

        window = rows[offset : offset + limit]
        return [ConnectorAuditEntity.model_validate(item) for item in deepcopy(window)]