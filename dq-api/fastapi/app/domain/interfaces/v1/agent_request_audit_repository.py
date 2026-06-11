from typing import Protocol

from app.domain.entities.agent_request_audit import AgentRequestAuditEntity


class AgentRequestAuditRepository(Protocol):
    async def record_event(self, event: AgentRequestAuditEntity) -> AgentRequestAuditEntity:
        ...

    async def list_events(self, *, limit: int = 100, offset: int = 0) -> list[AgentRequestAuditEntity]:
        ...
