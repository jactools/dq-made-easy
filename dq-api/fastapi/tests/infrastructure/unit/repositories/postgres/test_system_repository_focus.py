from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from types import SimpleNamespace

import app.infrastructure.repositories.postgres_system_repository as sys_mod
from app.infrastructure.repositories.postgres_system_repository import (
    PostgresSystemRepository,
)


class _ScalarResult:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return self

    def all(self):
        return self._values


class _Session:
    def __init__(self, scalar_values=None):
        self.scalar_values = list(scalar_values or [])

    def execute(self, _stmt):
        if self.scalar_values:
            return _ScalarResult(self.scalar_values.pop(0))
        return _ScalarResult([])


@contextmanager
def _scope(session):
    yield session


def test_fetch_all_maps_system_info_rows(monkeypatch) -> None:
    rows = [
        SimpleNamespace(
            info_key="db_schema_version",
            info_value="2.1.0",
            description="schema",
            updated_at="2026-03-27T10:00:00Z",
        ),
        SimpleNamespace(
            info_key="db_git_commit",
            info_value="abc123",
            description="git",
            updated_at="2026-03-27T10:00:00Z",
        ),
    ]
    session = _Session(scalar_values=[rows])
    monkeypatch.setattr(sys_mod, "session_scope", lambda _dsn: _scope(session))

    repo = PostgresSystemRepository("postgresql://example")
    out = repo._fetch_all()

    assert len(out) == 2
    assert out[0]["info_key"] == "db_schema_version"
    assert out[1]["info_value"] == "abc123"


def test_get_system_info_defaults_for_missing_fields(monkeypatch) -> None:
    repo = PostgresSystemRepository("postgresql://example")
    monkeypatch.setattr(repo, "_fetch_all", lambda: [{"info_key": "db_git_commit", "info_value": "xyz"}])

    out = repo.get_system_info()

    assert out.db_schema_version == "unknown"
    assert out.db_schema_updated is None
    assert out.db_git_commit == "xyz"


def test_get_suggestions_metrics_summary_aggregates_actions(monkeypatch) -> None:
    interaction_rows = [
        SimpleNamespace(
            suggestion_id="sug-plain-1",
            action="accepted",
            created_at=datetime(2026, 3, 27, 10, 0, tzinfo=UTC),
        ),
        SimpleNamespace(
            suggestion_id="sug-preview-1",
            action="dismissed",
            created_at=datetime(2026, 3, 27, 10, 5, tzinfo=UTC),
        ),
        SimpleNamespace(
            suggestion_id="sug-plain-2",
            action=None,
            created_at=None,
        ),
    ]
    suggestion_rows = [
        SimpleNamespace(id="sug-plain-1", data_source_id="source-1"),
        SimpleNamespace(id="sug-preview-1", data_source_id="nl-preview:retail-banking"),
        SimpleNamespace(id="sug-plain-2", data_source_id="source-2"),
    ]
    preview_rows = [
        SimpleNamespace(
            action="preview_clicked",
            result="success",
            created_at=datetime(2026, 3, 27, 10, 1, tzinfo=UTC),
        ),
        SimpleNamespace(
            action="preview_error",
            result="failure",
            created_at=datetime(2026, 3, 27, 10, 2, tzinfo=UTC),
        ),
    ]
    session = _Session(scalar_values=[interaction_rows, suggestion_rows, preview_rows])
    monkeypatch.setattr(sys_mod, "session_scope", lambda _dsn: _scope(session))

    repo = PostgresSystemRepository("postgresql://example")
    out = repo.get_suggestions_metrics_summary()

    assert out.total == 5
    assert out.successful == 4
    assert out.failed == 1
    operations = {item.operation: item for item in out.operations}
    assert operations["suggestions.accepted"].count == 1
    assert operations["suggestions.natural_language.suggestion_rejected"].count == 1
    assert operations["suggestions.natural_language.preview_clicked"].count == 1
    assert operations["suggestions.natural_language.preview_error"].failure_count == 1
    assert operations["suggestions.unknown"].count == 1
