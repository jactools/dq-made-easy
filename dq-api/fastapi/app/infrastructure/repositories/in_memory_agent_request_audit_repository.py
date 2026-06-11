from __future__ import annotations

from copy import deepcopy

from app.domain.entities.agent_request_audit import AgentRequestAuditEntity
from app.domain.interfaces.v1.agent_request_audit_repository import AgentRequestAuditRepository


class InMemoryAgentRequestAuditRepository(AgentRequestAuditRepository):
    def __init__(self) -> None:
        self._events: list[dict] = []

    async def record_event(self, event: AgentRequestAuditEntity) -> AgentRequestAuditEntity:
        payload = event.model_dump(mode="python", by_alias=False, exclude_none=True)
        self._events.append(deepcopy(payload))
        return AgentRequestAuditEntity.model_validate(payload)

    async def list_events(self, *, limit: int = 100, offset: int = 0) -> list[AgentRequestAuditEntity]:
        if limit < 0 or offset < 0:
            raise ValueError("limit and offset must be non-negative")
        window = self._events[offset : offset + limit]
        return [AgentRequestAuditEntity.model_validate(item) for item in deepcopy(window)]
