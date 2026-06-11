import pytest

from app.core import dependencies
from app.core.api_metrics import api_metrics_store
from app.core.config import get_settings
from app.core.dependencies import get_system_repository
from app.infrastructure.repositories.in_memory_app_config_repository import InMemoryAppConfigRepository
from app.infrastructure.repositories.in_memory_system_repository import InMemorySystemRepository
from app.main import app

pytestmark = pytest.mark.asyncio

def _reset_app_config_repository() -> None:
    dependencies._app_config_repository = InMemoryAppConfigRepository()


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
            "sub": "user-123",
            "preferred_username": "admin",
            "iss": "http://keycloak.local:8080/realms/jaccloud",
            "aud": ["dq-rules-ui"],
            "scope": " ".join(scopes),
        }
    )
    return {"Authorization": f"Bearer {token}"}


def setup_module() -> None:
    get_settings.cache_clear()
    _reset_app_config_repository()
    api_metrics_store.clear()


def teardown_module() -> None:
    get_settings.cache_clear()
    _reset_app_config_repository()
    api_metrics_store.clear()


@pytest.fixture(autouse=True)
def isolated_system_dependencies() -> None:
    system_repository = InMemorySystemRepository()

    app.dependency_overrides[get_system_repository] = lambda: system_repository

    yield

    app.dependency_overrides.pop(get_system_repository, None)


async def test_system_info_is_public(async_client, monkeypatch) -> None:
    _reset_app_config_repository()
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = await async_client.get("/api/system/v1/system-info")

    assert response.status_code == 200


async def test_system_info_returns_expected_shape(async_client, monkeypatch) -> None:
    _reset_app_config_repository()
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = await async_client.get("/system/v1/system-info")

    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload["api"]["version"], str)
    assert isinstance(payload["api"]["build_date"], str)
    assert payload["database"]["schema_version"] == "unknown"
    assert payload["database"]["schema_updated"] is None
    assert payload["database"]["schema_git_commit"] is None
    assert payload["deployment"]["deployment_verification_date"] is None
    assert payload["deployment"]["deployment_verified_by"] is None
    assert isinstance(payload["versions"], dict)
    assert isinstance(payload["versions"].get("apps"), dict)
    assert "ui" in payload["versions"]["apps"]
    assert "api" in payload["versions"]["apps"]
    assert isinstance(payload["versions"]["apps"]["ui"], str)
    assert isinstance(payload["versions"]["apps"]["api"], str)
    assert isinstance(payload["versions"].get("components", {}), dict)


async def test_version_catalog_is_public_and_returns_expected_shape(async_client, monkeypatch) -> None:
    _reset_app_config_repository()
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = await async_client.get("/api/system/v1/version-catalog")

    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload.get("apps"), dict)
    assert "ui" in payload["apps"]
    assert "api" in payload["apps"]
    assert isinstance(payload["apps"]["ui"], str)
    assert isinstance(payload["apps"]["api"], str)
    assert isinstance(payload.get("components", {}), dict)


async def test_suggestions_metrics_returns_expected_shape(async_client, monkeypatch) -> None:
    _reset_app_config_repository()
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = await async_client.get("/api/system/v1/suggestions/metrics", headers=_auth_headers("dq:rules:read"))

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert isinstance(payload["total"], int)
    assert isinstance(payload["successful"], int)
    assert isinstance(payload["failed"], int)
    assert isinstance(payload["success_rate"], (int, float))
    assert isinstance(payload["operations"], list)


async def test_api_metrics_applies_query_filters(async_client, monkeypatch) -> None:
    _reset_app_config_repository()
    api_metrics_store.clear()
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    api_metrics_store.record("GET", "/system/v1/health", 200, 5.0)
    api_metrics_store.record("GET", "/api/rulebuilder/v1/rules", 200, 40.0)
    api_metrics_store.record("GET", "/api/rulebuilder/v1/rules", 404, 60.0)
    api_metrics_store.record("POST", "/api/rulebuilder/v1/rules", 500, 120.0)

    response = await async_client.get(
        "/api/system/v1/api-metrics"
        "?excludeHealthEndpoints=true"
        "&apiEndpointFilter=/api/rulebuilder/v1/rules"
        "&apiMethodFilter=GET"
        "&apiMinRequests=2"
        "&recentErrorStatusFilter=4xx"
        "&recentErrorPathFilter=/api/rulebuilder/v1/rules",
        headers=_auth_headers("dq:rules:read"),
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["success"] is True
    assert payload["total"] == 2
    assert payload["errors"] == 1
    assert payload["error_rate"] == 0.5
    assert len(payload["endpoints"]) == 1
    assert payload["endpoints"][0]["endpoint"] == "GET /api/rulebuilder/v1/rules"
    assert payload["endpoints"][0]["count"] == 2
    assert len(payload["recent_errors"]) == 1
    assert payload["recent_errors"][0]["status_code"] == 404
    assert payload["recent_errors"][0]["path"] == "/api/rulebuilder/v1/rules"