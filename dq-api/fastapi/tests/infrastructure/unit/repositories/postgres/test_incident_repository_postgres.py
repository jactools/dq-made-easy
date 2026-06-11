from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from types import SimpleNamespace

import app.infrastructure.repositories.postgres_incident_repository as incident_mod
from app.domain.entities.incident import IncidentRootCauseSuggestionEntity
from app.infrastructure.repositories.postgres_incident_repository import PostgresIncidentRepository


def test_postgres_incident_repository_maps_root_cause_suggestion_row() -> None:
    row = SimpleNamespace(
        id="suggestion-1",
        workspace_id="ws-1",
        incident_ids=["inc-1", "inc-2"],
        incident_count=2,
        suggested_root_cause={
            "kind": "shared_source_correlation",
            "title": "Shared source correlation chain",
            "summary": "Both incidents share the same correlation id.",
        },
        status="accepted",
        events_json=[{"event_type": "created"}],
        created_by="user-1",
        created_at=datetime(2026, 6, 1, tzinfo=UTC),
        updated_by="user-2",
        updated_at=datetime(2026, 6, 2, tzinfo=UTC),
        accepted_at=datetime(2026, 6, 2, tzinfo=UTC),
        rejected_at=None,
        assistance_requested_at=datetime(2026, 6, 3, tzinfo=UTC),
        assistance_request_reference_id="SUP-1",
        assistance_request_ticket_id=None,
        assistance_request_ticket_number="ZAM-4321",
        assistance_request_ticket_url="https://zammad.example/tickets/4321",
        assistance_request_ticket_system="Zammad",
        assistance_request_delivery_modes=["itsm"],
        assistance_request_payload_json={"title": "Incident root cause assistance"},
    )

    entity = incident_mod._root_cause_suggestion_row_to_entity(row)

    assert entity.id == "suggestion-1"
    assert entity.workspace_id == "ws-1"
    assert entity.incident_ids == ["inc-1", "inc-2"]
    assert entity.incident_count == 2
    assert entity.suggested_root_cause["kind"] == "shared_source_correlation"
    assert entity.status == "accepted"
    assert entity.events == [{"event_type": "created"}]
    assert entity.assistance_request_reference_id == "SUP-1"
    assert entity.assistance_request_ticket_number == "ZAM-4321"
    assert entity.assistance_request_delivery_modes == ["itsm"]
    assert entity.assistance_request_payload == {"title": "Incident root cause assistance"}


def test_postgres_incident_repository_persists_root_cause_suggestion(monkeypatch) -> None:
    repo = PostgresIncidentRepository("postgresql://example")
    storage: dict[str, object] = {}

    class _Result:
        def __init__(self, row):
            self._row = row

        def scalar_one_or_none(self):
            return self._row

        def scalars(self):
            return SimpleNamespace(all=lambda: list(storage.values()))

    class _Session:
        def add(self, row):
            storage[row.id] = row

        def commit(self):
            return None

        def refresh(self, row):
            storage[row.id] = row

        def execute(self, _stmt):
            return _Result(next(iter(storage.values())) if storage else None)

    @contextmanager
    def _scope(_dsn: str):
        yield _Session()

    monkeypatch.setattr(incident_mod, "session_scope", _scope)

    created = repo.create_root_cause_suggestion(
        IncidentRootCauseSuggestionEntity(
            id="suggestion-1",
            workspace_id="ws-1",
            incident_ids=["inc-1", "inc-2"],
            incident_count=2,
            suggested_root_cause={"kind": "shared_run_failure", "title": "Shared failing run"},
            status="pending",
            events=[{"event_type": "created"}],
            created_by="user-1",
        )
    )

    assert created.id == "suggestion-1"
    assert created.workspace_id == "ws-1"
    assert created.incident_count == 2
    assert storage["suggestion-1"].incident_ids == ["inc-1", "inc-2"]

    updated = repo.update_root_cause_suggestion(
        IncidentRootCauseSuggestionEntity(
            **{
                **created.model_dump(),
                "status": "accepted",
                "accepted_at": "2026-06-02T00:00:00+00:00",
                "updated_by": "user-2",
            }
        )
    )
    assert updated.status == "accepted"
    assert storage["suggestion-1"].status == "accepted"

    listed = repo.list_root_cause_suggestions(workspace_id="ws-1")
    assert len(listed) == 1
    assert listed[0].id == "suggestion-1"