from __future__ import annotations

import pytest

from app.infrastructure.repositories.in_memory_admin_repository import InMemoryAdminRepository

pytestmark = pytest.mark.usefixtures("clone_payload")


def _repo_with_users() -> InMemoryAdminRepository:
    repo = InMemoryAdminRepository()
    repo._users = [  # type: ignore[attr-defined]
        {
            "id": "u1",
            "name": "Alice",
            "email": "alice@example.com",
            "roles": ["admin"],
            "workspaces": ["default"],
            "preferences": {"profile": {"theme": "dark"}},
        },
        {
            "id": "u2",
            "name": "Bob",
            "email": "bob@example.com",
            "roles": ["viewer"],
            "workspaces": ["default", "w2"],
            "preferences": {"other": True},
        },
    ]
    repo._roles = [  # type: ignore[attr-defined]
        {"id": "admin", "name": "Admin", "workspace": "default", "permissions": ["dq:admin"]},
        {"id": "viewer", "name": "Viewer", "workspace": "default", "permissions": ["dq:rules:view"]},
    ]
    return repo


def test_list_users_roles_and_login_resolution_paths() -> None:
    repo = _repo_with_users()

    assert len(repo.list_users()) == 2
    assert [role.id for role in repo.list_roles()] == ["admin", "viewer"]
    assert repo.list_roles()[0].permissions == ["dq:admin"]

    assert repo.resolve_login_user({"email": "Alice@Example.com"}).id == "u1"
    assert repo.resolve_login_user({}, sso=True).id == "u1"
    assert repo.resolve_login_user({"email": "missing@example.com"}, sso=True) is None
    assert repo.resolve_login_user({"x": "y"}) is None


def test_find_or_create_user_from_oidc_paths() -> None:
    repo = _repo_with_users()

    existing = repo.find_or_create_user_from_oidc(
        {"email": "alice@example.com", "sub": "oidc-1"},
        allow_signup=True,
        default_role="viewer",
    )
    assert existing.id == "u1"
    assert existing.external_id == "oidc-1"

    created = repo.find_or_create_user_from_oidc(
        {
            "sub": "oidc-created",
            "email": "new@example.com",
            "name": "New User",
            "preferred_username": "newuser",
        },
        allow_signup=True,
        default_role="editor",
    )
    assert created.email == "new@example.com"
    assert created.roles == ["editor"]
    assert created.granted_scopes == []
    assert created.external_id == "oidc-created"

    with pytest.raises(PermissionError):
        repo.find_or_create_user_from_oidc(
            {"email": "denied@example.com", "sub": "oidc-denied"},
            allow_signup=False,
            default_role="viewer",
        )


def test_update_user_reset_and_current_user_paths() -> None:
    repo = _repo_with_users()

    assert repo.update_user("missing", {}, max_users_per_workspace=10) is None

    updated = repo.update_user(
        "u1",
        {"email": "a2@example.com", "roles": ["viewer"], "workspaces": ["w2"]},
        max_users_per_workspace=2,
    )
    assert updated is not None
    assert updated.email == "a2@example.com"
    assert updated.roles == ["viewer"]
    assert updated.workspaces == ["w2"]

    with pytest.raises(ValueError):
        repo.update_user(
            "u1",
            {"roles": ["viewer"], "workspaces": ["w2"], "permissions": ["dq:users:manage"]},
            max_users_per_workspace=2,
        )

    with pytest.raises(ValueError):
        repo.update_user("u1", {"workspaces": ["default"]}, max_users_per_workspace=1)

    profile_reset = repo.reset_user_preferences("u1", "profile")
    assert profile_reset is not None
    assert "profile" not in profile_reset.preferences

    full_reset = repo.reset_user_preferences("u2", "all")
    assert full_reset is not None
    assert full_reset.preferences == {}

    assert repo.reset_user_preferences("missing", "profile") is None

    me = repo.get_current_user(None, {"preferred_username": "bob"})
    assert me is not None
    assert me.id == "u2"

    changed = repo.update_current_user("u2", None, {"preferences": {"theme": "light"}})
    assert changed is not None
    assert changed.preferences == {"theme": "light"}

    cleared = repo.update_current_user("u2", None, {})
    assert cleared is not None
    assert cleared.preferences == {}

    assert repo.get_current_user("missing", None) is None
    assert repo.update_current_user("missing", None, {"preferences": {}}) is None
