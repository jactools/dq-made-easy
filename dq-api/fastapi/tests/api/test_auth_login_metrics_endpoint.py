from __future__ import annotations

import pytest

from app.api.v1.endpoints import auth as auth_endpoints
from app.core import dependencies
from app.core.auth_login_metrics import auth_login_metrics_store
from app.core.dependencies import get_admin_repository
from app.core.dependencies import get_app_config_repository
from app.core.dependencies import get_session_repository
from app.infrastructure.repositories.in_memory_admin_repository import InMemoryAdminRepository
from app.infrastructure.repositories.in_memory_app_config_repository import InMemoryAppConfigRepository
from app.infrastructure.repositories.in_memory_sessions_repository import InMemorySessionsRepository
from app.main import app


@pytest.fixture(autouse=True)
def isolated_auth_login_metrics_store() -> None:
    auth_login_metrics_store.clear()
    yield
    auth_login_metrics_store.clear()


@pytest.fixture(autouse=True)
def isolated_auth_dependencies(monkeypatch: pytest.MonkeyPatch) -> None:
    app_config_repository = InMemoryAppConfigRepository()
    admin_repository = InMemoryAdminRepository()
    session_repository = InMemorySessionsRepository()

    app.dependency_overrides[get_admin_repository] = lambda: admin_repository
    app.dependency_overrides[get_app_config_repository] = lambda: app_config_repository
    app.dependency_overrides[get_session_repository] = lambda: session_repository
    monkeypatch.setattr(dependencies, "get_app_config_repository", lambda: app_config_repository)

    yield

    app.dependency_overrides.pop(get_admin_repository, None)
    app.dependency_overrides.pop(get_app_config_repository, None)
    app.dependency_overrides.pop(get_session_repository, None)


def test_login_records_role_bucket(client, monkeypatch) -> None:
    captured: dict[str, list[str]] = {}

    def fake_record_login_event(role_sources: list[str]) -> str:
        captured["role_sources"] = list(role_sources)
        return "admin"

    monkeypatch.setattr(auth_endpoints, "record_login_event", fake_record_login_event)

    response = client.post("/api/auth/v1/login", json={"email": "admin@example.com"})

    assert response.status_code == 200
    assert any("admin" in role_source.lower() for role_source in captured["role_sources"])


def test_auth_login_metrics_endpoint_returns_role_counts(client, auth_headers) -> None:
    auth_login_metrics_store.record_login("admin")
    auth_login_metrics_store.record_login("auditor")

    response = client.get("/api/system/v1/auth-login-metrics", headers=auth_headers("dq:rules:read"))

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["total"] == 2
    assert len(payload["role_counts"]) == 4
    role_counts = {entry["role"]: entry["count"] for entry in payload["role_counts"]}
    assert role_counts["admin"] == 1
    assert role_counts["auditor"] == 1
    assert len(payload["trend_series"]) == 24
