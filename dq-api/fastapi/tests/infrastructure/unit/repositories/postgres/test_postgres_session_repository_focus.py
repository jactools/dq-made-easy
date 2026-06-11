from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from app.domain.entities import SessionEntity
from app.infrastructure.repositories.postgres_session_repository import PostgresSessionRepository


class _FakeScalarResult:
    def __init__(self, row: object | None) -> None:
        self._row = row

    def first(self) -> object | None:
        return self._row


class _FakeExecuteResult:
    def __init__(self, row: object | None) -> None:
        self._row = row

    def scalars(self) -> _FakeScalarResult:
        return _FakeScalarResult(self._row)


class _FakeSession:
    def __init__(self, row: object | None = None) -> None:
        self.row = row
        self.merged: list[object] = []
        self.deleted: list[object] = []
        self.committed = False
        self.executed = 0

    def merge(self, row: object) -> None:
        self.merged.append(row)

    def commit(self) -> None:
        self.committed = True

    def execute(self, stmt: object) -> _FakeExecuteResult:
        self.executed += 1
        return _FakeExecuteResult(self.row)

    def delete(self, row: object) -> None:
        self.deleted.append(row)


def _install_session_scope(monkeypatch, session: _FakeSession) -> None:
    class _SessionScope:
        def __enter__(self) -> _FakeSession:
            return session

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

    monkeypatch.setattr(
        "app.infrastructure.repositories.postgres_session_repository.session_scope",
        lambda database_url: _SessionScope(),
    )


def test_create_session_merges_row_and_commits(monkeypatch) -> None:
    repository = PostgresSessionRepository("postgresql://example")
    session = _FakeSession()
    _install_session_scope(monkeypatch, session)

    repository.create_session(
        "session-1",
        "user-1",
        access_token="access",
        id_token="id",
        refresh_token="refresh",
        token_expires_at=datetime(2024, 5, 1, 10, 0, tzinfo=timezone.utc),
    )

    assert session.committed is True
    assert len(session.merged) == 1
    row = session.merged[0]
    assert row.id == "session-1"
    assert row.user_id == "user-1"
    assert row.access_token == "access"
    assert row.id_token == "id"
    assert row.refresh_token == "refresh"
    assert row.token_expires_at == datetime(2024, 5, 1, 10, 0, tzinfo=timezone.utc)
    assert row.last_activity.tzinfo is None


def test_touch_session_updates_existing_row(monkeypatch) -> None:
    existing = SimpleNamespace(last_activity=datetime(2024, 5, 1, 10, 0))
    repository = PostgresSessionRepository("postgresql://example")
    session = _FakeSession(row=existing)
    _install_session_scope(monkeypatch, session)

    repository.touch_session("session-1")

    assert session.committed is True
    assert existing.last_activity > datetime(2024, 5, 1, 10, 0)


def test_touch_session_noops_when_missing(monkeypatch) -> None:
    repository = PostgresSessionRepository("postgresql://example")
    session = _FakeSession(row=None)
    _install_session_scope(monkeypatch, session)

    repository.touch_session("session-1")

    assert session.committed is False


def test_get_session_returns_entity_for_existing_row(monkeypatch) -> None:
    existing = SimpleNamespace(
        id="session-1",
        user_id="user-1",
        last_activity=datetime(2024, 5, 1, 10, 0),
        access_token="access",
        id_token="id",
        refresh_token="refresh",
        token_expires_at=datetime(2024, 5, 1, 11, 0, tzinfo=timezone.utc),
    )
    repository = PostgresSessionRepository("postgresql://example")
    session = _FakeSession(row=existing)
    _install_session_scope(monkeypatch, session)

    result = repository.get_session("session-1")

    assert result == SessionEntity(
        id="session-1",
        user_id="user-1",
        last_activity=datetime(2024, 5, 1, 10, 0),
        access_token="access",
        id_token="id",
        refresh_token="refresh",
        token_expires_at=datetime(2024, 5, 1, 11, 0, tzinfo=timezone.utc),
    )


def test_get_session_returns_none_when_missing(monkeypatch) -> None:
    repository = PostgresSessionRepository("postgresql://example")
    session = _FakeSession(row=None)
    _install_session_scope(monkeypatch, session)

    assert repository.get_session("session-1") is None


def test_delete_session_deletes_existing_row(monkeypatch) -> None:
    existing = SimpleNamespace(id="session-1")
    repository = PostgresSessionRepository("postgresql://example")
    session = _FakeSession(row=existing)
    _install_session_scope(monkeypatch, session)

    repository.delete_session("session-1")

    assert session.deleted == [existing]
    assert session.committed is True


def test_delete_session_noops_when_missing(monkeypatch) -> None:
    repository = PostgresSessionRepository("postgresql://example")
    session = _FakeSession(row=None)
    _install_session_scope(monkeypatch, session)

    repository.delete_session("session-1")

    assert session.deleted == []
    assert session.committed is False
