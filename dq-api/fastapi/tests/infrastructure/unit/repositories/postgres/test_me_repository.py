"""Unit tests for current-user behavior in PostgresAdminRepository."""

from __future__ import annotations

from types import SimpleNamespace

import app.infrastructure.repositories.postgres_admin_repository as admin_mod
from app.infrastructure.repositories.postgres_admin_repository import PostgresAdminRepository


class _ExecResult:
    def __init__(self, rowcount=1):
        self.rowcount = rowcount

    def all(self):
        return []


class _Session:
    def __init__(self, rowcount=1):
        self.rowcount = rowcount
        self.committed = False

    def execute(self, stmt):
        return _ExecResult(self.rowcount)

    def commit(self):
        self.committed = True


class _Ctx:
    def __init__(self, session):
        self._session = session

    def __enter__(self):
        return self._session

    def __exit__(self, exc_type, exc, tb):
        return False


def test_get_current_user_none_when_missing(monkeypatch, me_lookup_claims: dict[str, object], clone_payload):
    repo = PostgresAdminRepository("postgresql://example")
    monkeypatch.setattr(repo, "_find_current_user", lambda user_id, claims: None)

    assert repo.get_current_user("u1", clone_payload(me_lookup_claims)) is None


def test_get_current_user_returns_serialized_entity(
    monkeypatch,
    me_current_user_row: dict[str, object],
    me_lookup_claims: dict[str, object],
    clone_payload,
):
    repo = PostgresAdminRepository("postgresql://example")
    monkeypatch.setattr(repo, "_build_exception_fact_access_workspace_roles", lambda user_id: [])
    monkeypatch.setattr(repo, "_get_active_exception_fact_access_scopes", lambda user_id, workspaces: [])

    monkeypatch.setattr(
        repo,
        "_find_current_user",
        lambda user_id, claims: clone_payload(me_current_user_row),
    )
    monkeypatch.setattr(
        repo,
        "_serialize_current_user",
        lambda user: repo._to_user_entity(
            {
                **user,
                "roles": ["admin"],
                "granted_scopes": ["dq:rules:read", "dq:rules:write"],
                "workspaces": ["w1"],
                "preferences": {"theme": "dark"},
            }
        ),
    )

    out = repo.get_current_user("u1", clone_payload(me_lookup_claims))

    assert out is not None
    assert out.id == "u1"
    assert out.roles == ["admin"]
    assert out.preferences["theme"] == "dark"


def test_update_current_user_returns_none_when_missing(
    monkeypatch,
    me_lookup_claims: dict[str, object],
    me_update_payload: dict[str, object],
    clone_payload,
):
    repo = PostgresAdminRepository("postgresql://example")
    monkeypatch.setattr(repo, "_find_current_user", lambda user_id, claims: None)

    assert repo.update_current_user("u1", clone_payload(me_lookup_claims), clone_payload(me_update_payload)) is None


def test_update_current_user_updates_and_returns_refreshed(
    monkeypatch,
    me_current_user_initial_row: dict[str, object],
    me_current_user_row: dict[str, object],
    me_lookup_claims: dict[str, object],
    me_update_payload: dict[str, object],
    clone_payload,
):
    repo = PostgresAdminRepository("postgresql://example")
    monkeypatch.setattr(repo, "_build_exception_fact_access_workspace_roles", lambda user_id: [])
    monkeypatch.setattr(repo, "_get_active_exception_fact_access_scopes", lambda user_id, workspaces: [])

    session = _Session(rowcount=1)
    monkeypatch.setattr(admin_mod, "session_scope", lambda db_url: _Ctx(session))

    calls = {"count": 0}

    def fake_find(user_id, claims):
        calls["count"] += 1
        if calls["count"] == 1:
            return clone_payload(me_current_user_initial_row)
        return clone_payload(me_current_user_row)

    monkeypatch.setattr(repo, "_find_current_user", fake_find)
    monkeypatch.setattr(
        repo,
        "_serialize_current_user",
        lambda user: repo._to_user_entity(
            {
                **user,
                "roles": ["viewer"],
                "granted_scopes": ["dq:rules:read"],
                "workspaces": ["w1"],
                "preferences": {"theme": "dark"},
            }
        ),
    )

    out = repo.update_current_user("u1", clone_payload(me_lookup_claims), clone_payload(me_update_payload))

    assert out is not None
    assert out.id == "u1"
    assert out.preferences["theme"] == "dark"
    assert session.committed is True


def test_update_current_user_raises_when_row_not_updated(
    monkeypatch,
    me_current_user_initial_row: dict[str, object],
    me_update_payload: dict[str, object],
    clone_payload,
):
    repo = PostgresAdminRepository("postgresql://example")

    session = _Session(rowcount=0)
    monkeypatch.setattr(admin_mod, "session_scope", lambda db_url: _Ctx(session))
    monkeypatch.setattr(
        repo,
        "_find_current_user",
        lambda user_id, claims: clone_payload(me_current_user_initial_row),
    )

    try:
        repo.update_current_user("u1", None, clone_payload(me_update_payload))
        assert False, "Expected RuntimeError"
    except RuntimeError as exc:
        assert "Unable to update current user" in str(exc)


def test_user_row_to_dict_maps_fields():
    row = SimpleNamespace(
        id="u1",
        first_name="Alice",
        last_name="Admin",
        email="a@example.com",
        workspaces="w1",
        preferences='{"theme":"dark"}',
        external_id="ext",
    )

    out = PostgresAdminRepository._user_row_to_dict(row)

    assert out["id"] == "u1"
    assert out["first_name"] == "Alice"
    assert out["last_name"] == "Admin"
    assert out["email"] == "a@example.com"
    assert out["external_id"] == "ext"
