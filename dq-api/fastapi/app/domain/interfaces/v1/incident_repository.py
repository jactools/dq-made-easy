from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.domain.entities.incident import IncidentEntity
from app.domain.entities.incident import IncidentRootCauseSuggestionEntity


@runtime_checkable
class IncidentRepository(Protocol):
    def create_incident(self, entity: IncidentEntity) -> IncidentEntity: ...

    def get_incident(self, incident_id: str) -> IncidentEntity | None: ...

    def update_incident(self, entity: IncidentEntity) -> IncidentEntity: ...

    def list_incidents(
        self,
        *,
        workspace_id: str | None = None,
        incident_kind: str | None = None,
        status: str | None = None,
        run_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[IncidentEntity]: ...

    def create_root_cause_suggestion(self, entity: IncidentRootCauseSuggestionEntity) -> IncidentRootCauseSuggestionEntity: ...

    def get_root_cause_suggestion(self, suggestion_id: str) -> IncidentRootCauseSuggestionEntity | None: ...

    def update_root_cause_suggestion(self, entity: IncidentRootCauseSuggestionEntity) -> IncidentRootCauseSuggestionEntity: ...

    def list_root_cause_suggestions(
        self,
        *,
        workspace_id: str | None = None,
        incident_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[IncidentRootCauseSuggestionEntity]: ...
