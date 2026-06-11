"""Unit tests for PostgresAdminRepository."""

from __future__ import annotations

from types import SimpleNamespace

import app.infrastructure.repositories.postgres_admin_repository as admin_mod
from app.infrastructure.repositories.postgres_admin_repository import PostgresAdminRepository
from app.infrastructure.orm.models import UserRow


class _FakeScalarResult:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return self

    def all(self):
        return self._values


class _FakeRowsResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, users=None, role_pairs=None, roles=None):
        self._users = users or []
        self._role_pairs = role_pairs or []
        self._roles = roles or []
        self.calls = 0

    def execute(self, stmt):
        self.calls += 1
        if self.calls == 1 and self._users:
            return _FakeScalarResult(self._users)
        if self.calls == 2 and self._role_pairs:
            return _FakeRowsResult(self._role_pairs)
        return _FakeScalarResult(self._roles)

    def get(self, model, user_id):
        return None


class _Ctx:
    def __init__(self, session):
        self._session = session

    def __enter__(self):
        return self._session

    def __exit__(self, exc_type, exc, tb):
        return False


def test_list_users_maps_rows(monkeypatch, admin_user_row: dict[str, object], clone_payload):
    user = UserRow(**clone_payload(admin_user_row))
    session = _FakeSession(users=[user], role_pairs=[("u1", "admin")])
    monkeypatch.setattr(admin_mod, "session_scope", lambda db_url: _Ctx(session))

    repo = PostgresAdminRepository("postgresql://example")

    users = repo.list_users()

    assert len(users) == 1
    assert users[0].id == "u1"
    assert users[0].first_name == "Alice"
    assert users[0].last_name == "Admin"
    assert users[0].roles == ["admin"]
    assert users[0].workspaces == ["w1", "w2"]


def test_list_roles_maps_rows(monkeypatch):
    role = SimpleNamespace(id="viewer", name="Viewer", workspace="default", permissions='["dq:rules:view"]')
    session = _FakeSession(roles=[role])
    monkeypatch.setattr(admin_mod, "session_scope", lambda db_url: _Ctx(session))

    repo = PostgresAdminRepository("postgresql://example")

    roles = repo.list_roles()

    assert len(roles) == 1
    assert roles[0].id == "viewer"
    assert roles[0].name == "Viewer"
    assert roles[0].workspace == "default"
    assert roles[0].permissions == ["dq:rules:view"]


def test_get_current_user_returns_none_when_not_found(monkeypatch, me_lookup_claims: dict[str, object], clone_payload):
    repo = PostgresAdminRepository("postgresql://example")
    monkeypatch.setattr(repo, "_find_current_user", lambda user_id, claims: None)

    assert repo.get_current_user("u1", clone_payload(me_lookup_claims)) is None


def test_get_current_user_serializes_found_user(
    monkeypatch,
    me_current_user_initial_row: dict[str, object],
    me_lookup_claims: dict[str, object],
    clone_payload,
):
    repo = PostgresAdminRepository("postgresql://example")
    monkeypatch.setattr(repo, "_build_exception_fact_access_workspace_roles", lambda user_id: [])
    monkeypatch.setattr(repo, "_get_active_exception_fact_access_scopes", lambda user_id, workspaces: [])

    monkeypatch.setattr(
        repo,
        "_find_current_user",
        lambda user_id, claims: clone_payload(me_current_user_initial_row),
    )
    monkeypatch.setattr(
        repo,
        "_serialize_current_user",
        lambda user: repo._to_user_entity(
            {
                **user,
                "roles": ["viewer"],
                "granted_scopes": ["dq:rules:read"],
                "workspaces": ["w1"],
                "preferences": {},
            }
        ),
    )

    out = repo.get_current_user("u1", clone_payload(me_lookup_claims))

    assert out is not None
    assert out.id == "u1"
    assert out.roles == ["viewer"]


def test_update_current_user_returns_none_when_user_missing(monkeypatch):
    repo = PostgresAdminRepository("postgresql://example")
    monkeypatch.setattr(repo, "_find_current_user", lambda user_id, claims: None)

    assert repo.update_current_user("u1", None, {"preferences": {"theme": "dark"}}) is None


def test_parse_workspaces_handles_dict_and_row_like():
    repo = PostgresAdminRepository("postgresql://example")

    assert repo._parse_workspaces({"workspaces": "w1;w2"}) == ["w1", "w2"]
    row_like = UserRow(id="u3", first_name="Carol", last_name="Clark", email="c@example.com", workspaces="w3;w4")
    assert repo._parse_workspaces(row_like) == ["w3", "w4"]


def test_payload_workspaces_prefers_payload():
    repo = PostgresAdminRepository("postgresql://example")

    existing = SimpleNamespace(workspaces="w1")
    assert repo._payload_workspaces({"workspaces": ["w2", "w3"]}, existing) == ["w2", "w3"]


def test_preferences_codec_roundtrip():
    repo = PostgresAdminRepository("postgresql://example")

    encoded = repo._encode_preferences({"theme": "dark"})
    decoded = repo._decode_preferences(encoded)

    assert isinstance(encoded, str)
    assert decoded == {"theme": "dark"}
