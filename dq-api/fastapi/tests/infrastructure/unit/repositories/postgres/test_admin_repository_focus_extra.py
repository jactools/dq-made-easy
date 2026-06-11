from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

import pytest

import app.infrastructure.repositories.postgres_admin_repository as admin_mod
from app.infrastructure.repositories.postgres_admin_repository import PostgresAdminRepository
from app.infrastructure.orm.models import UserRow


class _ScalarResult:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return self

    def all(self):
        return self._values if isinstance(self._values, list) else [self._values]

    def first(self):
        if isinstance(self._values, list):
            return self._values[0] if self._values else None
        return self._values

    def scalar_one_or_none(self):
        if isinstance(self._values, list):
            return self._values[0] if self._values else None
        return self._values

    def all_rows(self):
        return self._values if isinstance(self._values, list) else [self._values]


class _Session:
    def __init__(self, scalar_values=None, gets=None):
        self.scalar_values = list(scalar_values or [])
        self.gets = dict(gets or {})
        self.added = []
        self.committed = False
        self.deleted = []

    def execute(self, _stmt):
        if self.scalar_values:
            value = self.scalar_values.pop(0)
            if isinstance(value, list):
                return _ScalarResult(value)
            return _ScalarResult(value)
        return _ScalarResult([])

    def get(self, _model, key):
        return self.gets.get(key)

    def add(self, value):
        self.added.append(value)

    def commit(self):
        self.committed = True

    def refresh(self, _value):
        return None


@contextmanager
def _scope(session):
    yield session


def test_list_roles_create_role_and_update_role_paths(monkeypatch) -> None:
    roles = [SimpleNamespace(id="viewer", name="Viewer", workspace="default", permissions='["dq:rules:read"]')]
    existing = SimpleNamespace(id="viewer", name="Viewer", workspace="default", permissions='["dq:rules:read"]')
    session = _Session(scalar_values=[roles], gets={"viewer": existing})
    monkeypatch.setattr(admin_mod, "session_scope", lambda _dsn: _scope(session))

    repo = PostgresAdminRepository("postgresql://example")

    listed = repo.list_roles()
    assert listed[0].id == "viewer"
    assert listed[0].permissions == ["dq:rules:read"]

    with pytest.raises(ValueError):
        repo.create_role({"id": "viewer", "permissions": ["dq:rules:read"]})

    updated = repo.update_role("viewer", {"name": "Read Only", "permissions": ["dq:rules:read", "dq:rules:test"]})
    assert updated is not None
    assert updated.name == "Read Only"
    assert "dq:rules:test" in updated.permissions


def test_create_role_success_and_decode_encode_permissions(monkeypatch) -> None:
    session = _Session(gets={})
    monkeypatch.setattr(admin_mod, "session_scope", lambda _dsn: _scope(session))

    repo = PostgresAdminRepository("postgresql://example")

    role = repo.create_role({"id": "qa", "name": "QA", "workspace": "w1", "permissions": ["dq:rules:read", "dq:rules:read"]})
    assert role.id == "qa"
    assert role.workspace == "w1"
    assert role.permissions == ["dq:rules:read"]
    assert len(session.added) == 1
    assert session.committed is True

    assert repo._decode_permissions("not-json") == []
    assert repo._encode_permissions(["dq:rules:read", "dq:rules:read"]).startswith("[")
    assert "dq:rules:activate" in repo._expand_permissions(["dq:rules:write"])


def test_resolve_login_user_paths_and_find_or_create_oidc(monkeypatch) -> None:
    session = _Session(
        scalar_values=[
            [("u1",)],
            [("u2",)],
            [SimpleNamespace(id="u3", first_name="Oidc", last_name="User", email="oidc@example.com")],
        ]
    )
    monkeypatch.setattr(admin_mod, "session_scope", lambda _dsn: _scope(session))

    repo = PostgresAdminRepository("postgresql://example")
    monkeypatch.setattr(repo, "_fetch_user", lambda user_id: SimpleNamespace(id=user_id))

    assert repo.resolve_login_user({"email": "a@example.com"}, sso=False).id == "u1"
    assert repo.resolve_login_user({"first_name": "alice", "last_name": "admin"}, sso=False).id == "u2"

    # Existing OIDC user path from lookup query.
    oidc = repo.find_or_create_user_from_oidc(
        {"email": "oidc@example.com", "preferred_username": "oidc", "sub": "sub-1"},
        allow_signup=True,
        default_role="viewer",
    )
    assert oidc.id == "u3"


def test_find_or_create_oidc_signup_blocked_and_update_user_paths(monkeypatch) -> None:
    session = _Session(scalar_values=[None])
    monkeypatch.setattr(admin_mod, "session_scope", lambda _dsn: _scope(session))

    repo = PostgresAdminRepository("postgresql://example")
    with pytest.raises(PermissionError):
        repo.find_or_create_user_from_oidc(
            {"email": "new@example.com", "preferred_username": "new"},
            allow_signup=False,
            default_role="viewer",
        )

    user_row = UserRow(
        id="u1",
        first_name="User",
        last_name="One",
        email="old@example.com",
        external_id=None,
        workspaces="w1",
        preferences=None,
    )
    role_rows = [("viewer",)]
    session2 = _Session(scalar_values=[role_rows], gets={"u1": user_row})
    monkeypatch.setattr(admin_mod, "session_scope", lambda _dsn: _scope(session2))
    monkeypatch.setattr(repo, "_assert_workspace_capacity", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(repo, "_fetch_user", lambda user_id: SimpleNamespace(id=user_id, workspaces=["w2"], roles=["viewer"]))

    updated = repo.update_user("u1", {"email": "new@example.com", "roles": ["viewer"], "workspaces": ["w2"]}, max_users_per_workspace=10)
    assert updated is not None
    assert updated.id == "u1"

    with pytest.raises(ValueError):
        repo.update_user(
            "u1",
            {"permissions": ["dq:users:manage"], "roles": ["viewer"], "workspaces": ["w2"]},
            max_users_per_workspace=10,
        )

    session3 = _Session(gets={"u1": user_row})
    monkeypatch.setattr(admin_mod, "session_scope", lambda _dsn: _scope(session3))
    reset = repo.reset_user_preferences("u1", scope="profile")
    assert reset is not None
    assert reset.id == "u1"
