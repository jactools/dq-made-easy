from typing import Any, Protocol

from app.domain.entities.sla_slo import SlaSloDefinitionEntity


class SlaSloRepository(Protocol):
    async def list_sla_slo_definitions(
        self,
        *,
        workspace_id: str | None = None,
        status: str | None = None,
        scope_kind: str | None = None,
        metric_kind: str | None = None,
    ) -> list[SlaSloDefinitionEntity]:
        ...

    async def get_sla_slo_definition(self, definition_id: str) -> SlaSloDefinitionEntity | None:
        ...

    async def create_sla_slo_definition(self, payload: dict[str, Any], actor_id: str | None = None) -> SlaSloDefinitionEntity:
        ...

    async def update_sla_slo_definition(
        self,
        definition_id: str,
        payload: dict[str, Any],
        actor_id: str | None = None,
    ) -> SlaSloDefinitionEntity | None:
        ...

    async def approve_sla_slo_definition(
        self,
        definition_id: str,
        payload: dict[str, Any],
        actor_id: str | None = None,
    ) -> SlaSloDefinitionEntity | None:
        ...
