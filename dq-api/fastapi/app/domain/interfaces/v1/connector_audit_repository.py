from typing import Protocol

from app.domain.entities.connector_audit import ConnectorAuditEntity


class ConnectorAuditRepository(Protocol):
    async def record_event(self, event: ConnectorAuditEntity) -> ConnectorAuditEntity:
        ...

    async def list_events(
        self,
        *,
        provider: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ConnectorAuditEntity]:
        ...