from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

import app.infrastructure.repositories.postgres_profiling_repository as postgres_profiling_repository
from app.domain.entities.profiling_request import ProfilingRequest
from app.infrastructure.repositories.postgres_profiling_repository import PostgresProfilingRepository


class _FakeSession:
    def __init__(self, existing: object | None = None) -> None:
        self.existing = existing
        self.added: list[object] = []
        self.committed = False
        self.get_calls: list[tuple[object, str]] = []

    def get(self, model: object, row_id: str) -> object | None:
        self.get_calls.append((model, row_id))
        return self.existing

    def add(self, row: object) -> None:
        self.added.append(row)

    def commit(self) -> None:
        self.committed = True


def _install_session_scope(monkeypatch: pytest.MonkeyPatch, session: _FakeSession) -> None:
    class _SessionScope:
        def __enter__(self) -> _FakeSession:
            return session

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

    monkeypatch.setattr(
        "app.infrastructure.repositories.postgres_profiling_repository.session_scope",
        lambda database_url: _SessionScope(),
    )


def test_create_request_uses_supplied_identifier_and_persists_row(monkeypatch: pytest.MonkeyPatch) -> None:
    repository = PostgresProfilingRepository("postgresql://example")
    session = _FakeSession()
    _install_session_scope(monkeypatch, session)

    request = ProfilingRequest(
        id=None,
        profiling_request_id="pr-123",
        data_source_id="ds-1",
        requested_by_user_id="user-1",
        requested_at=datetime(2024, 5, 1, 10, 0, tzinfo=timezone.utc),
        started_at=None,
        completed_at=None,
        status="pending",
        error_message=None,
        job_id="job-1",
    )

    created = repository.create_request(request)

    assert session.committed is True
    assert len(session.added) == 1
    assert session.added[0].id == "pr-123"
    assert session.added[0].status == "pending"
    assert created.profiling_request_id == "pr-123"
    assert created.status == "pending"
    assert created.job_id == "job-1"


def test_create_request_generates_identifier_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    repository = PostgresProfilingRepository("postgresql://example")
    session = _FakeSession()
    _install_session_scope(monkeypatch, session)
    monkeypatch.setattr(postgres_profiling_repository, "uuid4", lambda: "generated-id")

    request = ProfilingRequest(
        id=None,
        profiling_request_id="",
        data_source_id=None,
        requested_by_user_id=None,
        requested_at=datetime(2024, 5, 1, 10, 0, tzinfo=timezone.utc),
        started_at=None,
        completed_at=None,
        status="",
        error_message=None,
        job_id=None,
    )

    created = repository.create_request(request)

    assert session.committed is True
    assert session.added[0].id == "generated-id"
    assert session.added[0].data_source_id == ""
    assert session.added[0].requested_by_user_id == ""
    assert session.added[0].status == "pending"
    assert created.profiling_request_id == "generated-id"
    assert created.status == "pending"


def test_set_started_updates_existing_row(monkeypatch: pytest.MonkeyPatch) -> None:
    repository = PostgresProfilingRepository("postgresql://example")
    existing = SimpleNamespace(started_at=None, job_id=None, status=None)
    session = _FakeSession(existing=existing)
    _install_session_scope(monkeypatch, session)

    repository.set_started("pr-123", "job-1")

    assert session.committed is True
    assert existing.job_id == "job-1"
    assert existing.status == "started"
    assert existing.started_at is not None


def test_set_started_raises_for_missing_row(monkeypatch: pytest.MonkeyPatch) -> None:
    repository = PostgresProfilingRepository("postgresql://example")
    session = _FakeSession(existing=None)
    _install_session_scope(monkeypatch, session)

    with pytest.raises(KeyError, match="profiling_request pr-123 not found"):
        repository.set_started("pr-123", "job-1")


def test_set_completed_updates_status_and_error_message(monkeypatch: pytest.MonkeyPatch) -> None:
    repository = PostgresProfilingRepository("postgresql://example")
    existing = SimpleNamespace(completed_at=None, status=None, error_message=None)
    session = _FakeSession(existing=existing)
    _install_session_scope(monkeypatch, session)

    repository.set_completed("pr-123", success=False, error_message="boom")

    assert session.committed is True
    assert existing.status == "failed"
    assert existing.error_message == "boom"
    assert existing.completed_at is not None


def test_set_completed_marks_success_without_error_message(monkeypatch: pytest.MonkeyPatch) -> None:
    repository = PostgresProfilingRepository("postgresql://example")
    existing = SimpleNamespace(completed_at=None, status=None, error_message=None)
    session = _FakeSession(existing=existing)
    _install_session_scope(monkeypatch, session)

    repository.set_completed("pr-123", success=True)

    assert session.committed is True
    assert existing.status == "completed"
    assert existing.error_message is None
    assert existing.completed_at is not None


def test_set_completed_raises_for_missing_row(monkeypatch: pytest.MonkeyPatch) -> None:
    repository = PostgresProfilingRepository("postgresql://example")
    session = _FakeSession(existing=None)
    _install_session_scope(monkeypatch, session)

    with pytest.raises(KeyError, match="profiling_request pr-123 not found"):
        repository.set_completed("pr-123", success=True)
