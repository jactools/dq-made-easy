import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app

client = TestClient(app)


PUBLIC_PATHS = [
    "/",
    "/health",
    "/auth/v1/login",
    "/auth/v1/callback",
    "/api/system/v1/health",
    "/api/system/v1/live",
    "/api/system/v1/readiness",
    "/api/system/v1/ready",
    "/api/system/v1/system-info",
    "/api/system/v1/api-metrics",
]


PROTECTED_PATHS = [
    "/api/rulebuilder/v1/rules",
    "/api/rulebuilder/v1/approvals",
    "/api/rulebuilder/v1/approvals/audit",
    "/api/rulebuilder/v1/workspaces",
    "/api/admin/v1/users",
    "/api/admin/v1/roles",
    "/api/admin/v1/me",
    "/api/user/v1/me",
    "/api/rulebuilder/v1/rules/rule-email-format",
    "/api/rulebuilder/v1/rules/rule-email-format/versions",
    "/api/rulebuilder/v1/rules/rule-email-format/versions/rollback-history",
    "/api/rulebuilder/v1/rules/rule-email-format/versions/stats",
    "/api/rulebuilder/v1/rules/rule-email-format/versions/rv-000/compare/rv-001",
    "/api/rulebuilder/v1/rules/rule-email-format/versions/rv-001",
    "/api/data-catalog/v1/data-products",
    "/api/data-catalog/v1/data-objects",
    "/api/data-catalog/v1/data-sets",
    "/api/data-catalog/v1/rule-attributes",
    "/api/data-catalog/v1/data-objects-catalog",
    "/api/data-catalog/v1/data-object-versions",
    "/api/data-catalog/v1/attributes-catalog",
    "/api/data-catalog/v1/data-deliveries",
    "/api/data-catalog/v1/attribute-rule-counts",
    "/api/system/v1/app-config",
    "/api/rulebuilder/v1/batch-test-requests",
    "/api/rulebuilder/v1/batch-test-requests/test-123",
    "/api/rulebuilder/v1/test-proofs/rule-email-format",
]


def setup_module() -> None:
    get_settings.cache_clear()


def teardown_module() -> None:
    get_settings.cache_clear()


@pytest.mark.parametrize("path", PUBLIC_PATHS)
def test_public_routes_not_blocked_by_auth_without_token(monkeypatch, path: str) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.get(path)

    # These paths may be unimplemented, but auth middleware must not force 401.
    assert response.status_code != 401


@pytest.mark.parametrize("path", PROTECTED_PATHS)
def test_protected_routes_require_token(monkeypatch, path: str) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.get(path)

    assert response.status_code == 401
    payload = response.json()
    if path in {"/api/admin/v1/me", "/api/user/v1/me"}:
        assert payload["detail"] == "Not authenticated"
    else:
        assert payload["detail"] == "Bearer token is required for this endpoint"


def test_protected_mutation_route_requires_token(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.post(
        "/api/rulebuilder/v1/rules/rule-email-format/rollback",
        json={"to_version_id": "rv-000", "reason": "Regression rollback"},
    )

    assert response.status_code == 401
    payload = response.json()
    assert payload["detail"] == "Not authenticated"


def test_public_logout_route_not_blocked_by_auth_without_token(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.post("/api/auth/v1/logout")

    assert response.status_code != 401


def test_public_auth_redirect_route_not_blocked_by_auth_without_token(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.get("/api/auth/v1/redirect", follow_redirects=False)

    assert response.status_code != 401


def test_protected_batch_test_create_route_requires_token(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.post(
        "/api/rulebuilder/v1/batch-test-requests",
        json={"ruleIds": ["rule-email-format"]},
    )

    assert response.status_code == 401
    payload = response.json()
    assert payload["detail"] == "Bearer token is required for this endpoint"


def test_protected_batch_test_run_route_requires_token(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.post("/api/rulebuilder/v1/batch-test-requests/test-123/run")

    assert response.status_code == 401
    payload = response.json()
    assert payload["detail"] == "Bearer token is required for this endpoint"


def test_protected_generate_test_data_route_requires_token(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.post(
        "/api/v1/data-object-versions/dov-23/generate-test-data",
        json={"sampleCount": 2},
    )

    assert response.status_code == 401
    payload = response.json()
    assert payload["detail"] == "Bearer token is required for this endpoint"


def test_protected_test_data_request_create_route_requires_token(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.post(
        "/api/rulebuilder/v1/test-data/requests",
        json={
            "targetType": "data_object_version",
            "targetId": "dov-23",
            "sampleCount": 2,
        },
    )

    assert response.status_code == 401
    payload = response.json()
    assert payload["detail"] == "Bearer token is required for this endpoint"


def test_protected_test_with_data_route_requires_token(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.post(
        "/api/rulebuilder/v1/rules/rule-email-format/test-with-data",
        json={"testData": [{"email": "valid@example.com"}]},
    )

    assert response.status_code == 401
    payload = response.json()
    assert payload["detail"] == "Bearer token is required for this endpoint"


def test_protected_log_test_action_route_requires_token(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.post(
        "/api/rulebuilder/v1/rules/rule-email-format/test",
        json={
            "coverage": 0.95,
            "passed": True,
            "recordsTestedCount": 100,
            "failuresFound": 5,
        },
    )

    assert response.status_code == 401
    payload = response.json()
    assert payload["detail"] == "Bearer token is required for this endpoint"


def test_protected_test_with_generated_data_route_requires_token(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.post(
        "/api/rulebuilder/v1/rules/rule-email-format/test-with-generated-data",
        json={"versionId": "dov-23", "sampleCount": 3},
    )

    assert response.status_code == 401
    payload = response.json()
    assert payload["detail"] == "Bearer token is required for this endpoint"


def test_protected_version_tags_mutation_route_requires_token(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.patch(
        "/api/rulebuilder/v1/rules/rule-email-format/versions/rv-001/tags",
        json={"tags": ["stable"]},
    )

    assert response.status_code == 401
    payload = response.json()
    assert payload["detail"] == "Bearer token is required for this endpoint"


def test_protected_mark_for_rollback_route_requires_token(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.patch(
        "/api/rulebuilder/v1/rules/rule-email-format/versions/rv-001/mark-for-rollback",
        json={"marked": True},
    )

    assert response.status_code == 401
    payload = response.json()
    assert payload["detail"] == "Bearer token is required for this endpoint"


def test_protected_rule_attributes_mutation_route_requires_token(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.post(
        "/api/data-catalog/v1/rule-attributes",
        json={"entries": [{"ruleId": "1", "attributeId": "attr-999"}]},
    )

    assert response.status_code == 401
    payload = response.json()
    assert payload["detail"] == "Bearer token is required for this endpoint"


def test_protected_app_config_mutation_route_requires_token(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.put(
        "/api/system/v1/app-config",
        json={"maintenanceMode": True},
    )

    assert response.status_code == 401
    payload = response.json()
    assert payload["detail"] == "Bearer token is required for this endpoint"


def test_protected_user_update_route_requires_token(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.put(
        "/api/admin/v1/users/user-analyst",
        json={"email": "updated@example.com"},
    )

    assert response.status_code == 401
    payload = response.json()
    assert payload["detail"] == "Bearer token is required for this endpoint"


def test_protected_user_reset_profile_route_requires_token(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.post("/api/admin/v1/users/user-admin/reset-profile")

    assert response.status_code == 401
    payload = response.json()
    assert payload["detail"] == "Bearer token is required for this endpoint"


def test_protected_user_reset_settings_route_requires_token(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.post("/api/admin/v1/users/user-admin/reset-settings")

    assert response.status_code == 401
    payload = response.json()
    assert payload["detail"] == "Bearer token is required for this endpoint"


def test_protected_me_update_route_requires_token(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.put(
        "/api/admin/v1/me",
        json={"preferences": {"display": {"theme": "light"}}},
    )

    assert response.status_code == 401
    payload = response.json()
    assert payload["detail"] == "Bearer token is required for this endpoint"
