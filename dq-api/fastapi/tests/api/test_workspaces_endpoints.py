from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app

client = TestClient(app)


def _jwt(payload: dict[str, object]) -> str:
    import base64
    import json

    header = {"alg": "none", "typ": "JWT"}

    def encode(value: dict[str, object]) -> str:
        return base64.urlsafe_b64encode(json.dumps(value).encode("utf-8")).decode("utf-8").rstrip("=")

    return f"{encode(header)}.{encode(payload)}.signature"


def _auth_headers(*scopes: str) -> dict[str, str]:
    token = _jwt(
        {
            "sub": "user-admin",
            "preferred_username": "admin",
            "iss": "http://keycloak.local:8080/realms/jaccloud",
            "aud": ["dq-rules-ui"],
            "scope": " ".join(scopes),
        }
    )
    return {"Authorization": f"Bearer {token}"}


def setup_module() -> None:
    get_settings.cache_clear()


def teardown_module() -> None:
    get_settings.cache_clear()


def test_workspaces_requires_auth(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.get("/api/rulebuilder/v1/workspaces")

    assert response.status_code == 401


def test_workspaces_returns_paginated_data(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.get(
        "/api/rulebuilder/v1/workspaces?page=1&limit=2",
        headers=_auth_headers("dq:rules:read"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["pagination"]["total"] >= 3
    assert payload["pagination"]["limit"] == 2
    assert len(payload["data"]) == 2


def test_workspaces_create_requires_manage_scope(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.post(
        "/api/rulebuilder/v1/workspaces",
        json={"id": "workspace-denied", "name": "Denied"},
        headers=_auth_headers("dq:rules:read"),
    )

    assert response.status_code == 403


def test_workspaces_create_and_update_and_delete_flow(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    created = client.post(
        "/api/rulebuilder/v1/workspaces",
        json={"id": "workspace-api-test", "name": "API Test Workspace", "description": "Created by test"},
        headers=_auth_headers("dq:workspace:manage"),
    )
    assert created.status_code == 200
    assert created.json() == {"ok": True}

    updated = client.put(
        "/api/rulebuilder/v1/workspaces/workspace-api-test",
        json={"name": "Workspace Renamed"},
        headers=_auth_headers("dq:workspace:manage"),
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Workspace Renamed"

    deleted = client.delete(
        "/api/rulebuilder/v1/workspaces/workspace-api-test",
        headers=_auth_headers("dq:workspace:manage"),
    )
    assert deleted.status_code == 200
    assert deleted.json() == {"ok": True}


def test_workspaces_update_and_delete_not_found(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    updated = client.put(
        "/api/rulebuilder/v1/workspaces/missing-workspace",
        json={"name": "Missing"},
        headers=_auth_headers("dq:workspace:manage"),
    )
    assert updated.status_code == 404

    deleted = client.delete(
        "/api/rulebuilder/v1/workspaces/missing-workspace",
        headers=_auth_headers("dq:workspace:manage"),
    )
    assert deleted.status_code == 404


def test_workspaces_delete_default_is_blocked(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.delete(
        "/api/rulebuilder/v1/workspaces/default",
        headers=_auth_headers("dq:workspace:manage"),
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Cannot delete default workspace"