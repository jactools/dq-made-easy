from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from app.domain.entities.incident import IncidentEntity
from app.domain.entities.incident import IncidentRootCauseSuggestionEntity
from app.domain.interfaces.v1.incident_repository import IncidentRepository


class InMemoryIncidentRepository(IncidentRepository):
    """In-memory repository for unit tests."""

    def __init__(self) -> None:
        self._store: dict[str, IncidentEntity] = {}
        self._root_cause_suggestions: dict[str, IncidentRootCauseSuggestionEntity] = {}

    def create_incident(self, entity: IncidentEntity) -> IncidentEntity:
        now = datetime.now(tz=timezone.utc).isoformat()
        saved = IncidentEntity(
            **{
                **entity.model_dump(),
                "id": entity.id or str(uuid4()),
                "created_at": now,
                "updated_at": now,
            }
        )
        self._store[saved.id] = saved
        return saved

    def get_incident(self, incident_id: str) -> IncidentEntity | None:
        return self._store.get(incident_id)

    def update_incident(self, entity: IncidentEntity) -> IncidentEntity:
        now = datetime.now(tz=timezone.utc).isoformat()
        updated = IncidentEntity(
            **{
                **entity.model_dump(),
                "updated_at": now,
            }
        )
        self._store[updated.id] = updated
        return updated

    def list_incidents(
        self,
        *,
        workspace_id: str | None = None,
        incident_kind: str | None = None,
        status: str | None = None,
        run_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[IncidentEntity]:
        rows = list(self._store.values())
        if workspace_id:
            rows = [r for r in rows if r.workspace_id == workspace_id]
        if incident_kind:
            rows = [r for r in rows if r.incident_kind == incident_kind]
        if status:
            rows = [r for r in rows if r.status == status]
        if run_id:
            rows = [r for r in rows if r.run_id == run_id]
        # Sort by created_at descending for stable ordering
        rows.sort(key=lambda r: r.created_at or "", reverse=True)
        return rows[offset : offset + limit]

    def create_root_cause_suggestion(self, entity: IncidentRootCauseSuggestionEntity) -> IncidentRootCauseSuggestionEntity:
        now = datetime.now(tz=timezone.utc).isoformat()
        saved = IncidentRootCauseSuggestionEntity(
            **{
                **entity.model_dump(),
                "id": entity.id or str(uuid4()),
                "created_at": entity.created_at or now,
                "updated_at": entity.updated_at or now,
            }
        )
        self._root_cause_suggestions[saved.id] = saved
        return saved

    def get_root_cause_suggestion(self, suggestion_id: str) -> IncidentRootCauseSuggestionEntity | None:
        return self._root_cause_suggestions.get(suggestion_id)

    def update_root_cause_suggestion(self, entity: IncidentRootCauseSuggestionEntity) -> IncidentRootCauseSuggestionEntity:
        now = datetime.now(tz=timezone.utc).isoformat()
        updated = IncidentRootCauseSuggestionEntity(
            **{
                **entity.model_dump(),
                "updated_at": now,
            }
        )
        self._root_cause_suggestions[updated.id] = updated
        return updated

    def list_root_cause_suggestions(
        self,
        *,
        workspace_id: str | None = None,
        incident_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[IncidentRootCauseSuggestionEntity]:
        rows = list(self._root_cause_suggestions.values())
        if workspace_id:
            rows = [row for row in rows if row.workspace_id == workspace_id]
        if status:
            rows = [row for row in rows if row.status == status]
        if incident_id:
            rows = [row for row in rows if incident_id in row.incident_ids]
        rows.sort(key=lambda row: row.created_at or "", reverse=True)
        return rows[offset : offset + limit]
