from fastapi.testclient import TestClient

import pytest

from app.core.dependencies import get_approvals_repository
from app.core.dependencies import get_app_config_repository
from app.core.dependencies import get_data_catalog_repository
from app.core.dependencies import get_gx_suite_repository
from app.core.dependencies import get_rules_repository
from app.core.dependencies import get_validation_run_repository
from app.core.config import get_settings
from app.infrastructure.repositories.in_memory_approvals_repository import InMemoryApprovalsRepository
from app.infrastructure.repositories.in_memory_app_config_repository import InMemoryAppConfigRepository
from app.infrastructure.repositories.in_memory_data_catalog_repository import InMemoryDataCatalogRepository
from app.infrastructure.repositories.in_memory_gx_suite_repository import InMemoryGxSuiteRepository
from app.infrastructure.repositories.in_memory_rules_repository import InMemoryRulesRepository
from app.infrastructure.repositories.in_memory_validation_run_repository import InMemoryValidationRunRepository
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


def teardown_module() -> None:
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def isolated_rule_version_dependencies() -> None:
    rules_repository = InMemoryRulesRepository()
    approvals_repository = InMemoryApprovalsRepository()
    app_config_repository = InMemoryAppConfigRepository()
    data_catalog_repository = InMemoryDataCatalogRepository()
    gx_suite_repository = InMemoryGxSuiteRepository()
    validation_run_repository = InMemoryValidationRunRepository()

    app.dependency_overrides[get_rules_repository] = lambda: rules_repository
    app.dependency_overrides[get_approvals_repository] = lambda: approvals_repository
    app.dependency_overrides[get_app_config_repository] = lambda: app_config_repository
    app.dependency_overrides[get_data_catalog_repository] = lambda: data_catalog_repository
    app.dependency_overrides[get_gx_suite_repository] = lambda: gx_suite_repository
    app.dependency_overrides[get_validation_run_repository] = lambda: validation_run_repository

    yield

    app.dependency_overrides.pop(get_rules_repository, None)
    app.dependency_overrides.pop(get_approvals_repository, None)
    app.dependency_overrides.pop(get_app_config_repository, None)
    app.dependency_overrides.pop(get_data_catalog_repository, None)
    app.dependency_overrides.pop(get_gx_suite_repository, None)
    app.dependency_overrides.pop(get_validation_run_repository, None)


def test_rule_versions_returns_paginated_history(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.get(
        "/api/rulebuilder/v1/rules/rule-email-format/versions?limit=1&offset=0",
        headers=_auth_headers("dq:rules:read"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["rule_id"] == "rule-email-format"
    assert payload["pagination"]["limit"] == 1
    assert payload["pagination"]["offset"] == 0
    assert payload["pagination"]["total"] >= 1
    assert len(payload["versions"]) == 1


def test_rule_versions_requires_rules_view_scope(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.get(
        "/api/rulebuilder/v1/rules/rule-email-format/versions",
        headers=_auth_headers("dq:profiling:request"),
    )

    assert response.status_code == 403
    payload = response.json()
    assert payload["title"] == "Forbidden"


def test_rule_versions_returns_not_found_for_missing_rule(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.get(
        "/api/rulebuilder/v1/rules/missing-rule/versions",
        headers=_auth_headers("dq:rules:read"),
    )

    assert response.status_code == 404
    payload = response.json()
    assert payload["status"] == 404


def test_rule_rollback_history_returns_paginated_data(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.get(
        "/api/rulebuilder/v1/rules/rule-email-format/versions/rollback-history?limit=1&offset=0",
        headers=_auth_headers("dq:rules:read"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["rule_id"] == "rule-email-format"
    assert payload["pagination"]["limit"] == 1
    assert len(payload["rollbacks"]) == 1


def test_rule_rollback_history_requires_read_scope(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.get(
        "/api/rulebuilder/v1/rules/rule-email-format/versions/rollback-history",
        headers=_auth_headers("dq:profiling:request"),
    )

    assert response.status_code == 403
    payload = response.json()
    assert payload["title"] == "Forbidden"


def test_rule_rollback_history_returns_not_found_for_missing_rule(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.get(
        "/api/rulebuilder/v1/rules/missing-rule/versions/rollback-history",
        headers=_auth_headers("dq:rules:read"),
    )

    assert response.status_code == 404
    payload = response.json()
    assert payload["status"] == 404


def test_rule_version_stats_returns_payload(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.get(
        "/api/rulebuilder/v1/rules/rule-email-format/versions/stats",
        headers=_auth_headers("dq:rules:read"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["versions"]["total"] >= 1
    assert "change_types" in payload["versions"]
    assert "rollbacks" in payload


def test_rule_version_stats_requires_read_scope(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.get(
        "/api/rulebuilder/v1/rules/rule-email-format/versions/stats",
        headers=_auth_headers("dq:profiling:request"),
    )

    assert response.status_code == 403
    payload = response.json()
    assert payload["title"] == "Forbidden"


def test_rule_version_stats_returns_not_found_for_missing_rule(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.get(
        "/api/rulebuilder/v1/rules/missing-rule/versions/stats",
        headers=_auth_headers("dq:rules:read"),
    )

    assert response.status_code == 404
    payload = response.json()
    assert payload["status"] == 404


def test_compare_rule_versions_returns_diff(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.get(
        "/api/rulebuilder/v1/rules/rule-email-format/versions/rv-000/compare/rv-001",
        headers=_auth_headers("dq:rules:read"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["from_version"]["id"] == "rv-000"
    assert payload["to_version"]["id"] == "rv-001"
    assert payload["changes"]["summary"]["fields_changed"] >= 1


def test_compare_rule_versions_requires_read_scope(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.get(
        "/api/rulebuilder/v1/rules/rule-email-format/versions/rv-000/compare/rv-001",
        headers=_auth_headers("dq:profiling:request"),
    )

    assert response.status_code == 403
    payload = response.json()
    assert payload["title"] == "Forbidden"


def test_compare_rule_versions_returns_not_found(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.get(
        "/api/rulebuilder/v1/rules/rule-email-format/versions/rv-missing/compare/rv-001",
        headers=_auth_headers("dq:rules:read"),
    )

    assert response.status_code == 404
    payload = response.json()
    assert payload["status"] == 404


def test_rule_version_details_returns_payload(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.get(
        "/api/rulebuilder/v1/rules/rule-email-format/versions/rv-001",
        headers=_auth_headers("dq:rules:read"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == "rv-001"
    assert payload["rule_id"] == "rule-email-format"
    assert payload["version_number"] == 2


def test_rule_version_details_not_found(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.get(
        "/api/rulebuilder/v1/rules/rule-email-format/versions/missing-version",
        headers=_auth_headers("dq:rules:read"),
    )

    assert response.status_code == 404
    payload = response.json()
    assert payload["status"] == 404


def test_rule_rollback_returns_accepted(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.post(
        "/api/rulebuilder/v1/rules/rule-email-format/rollback",
        headers=_auth_headers("dq:rules:write"),
        json={
            "to_version_id": "rv-000",
            "reason": "Regression rollback",
            "tags": ["maintenance"],
        },
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == "processing"
    assert payload["to_version"]["id"] == "rv-000"
    assert payload["new_version_created"]["id"].startswith("rv-")


def test_rule_rollback_requires_write_scope(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.post(
        "/api/rulebuilder/v1/rules/rule-email-format/rollback",
        headers=_auth_headers("dq:rules:read"),
        json={
            "to_version_id": "rv-000",
            "reason": "Regression rollback",
        },
    )

    assert response.status_code == 403
    payload = response.json()
    assert payload["title"] == "Forbidden"


def test_rule_rollback_rejects_current_version_target(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    current = client.get(
        "/api/rulebuilder/v1/rules/rule-email-format/versions?limit=1&offset=0",
        headers=_auth_headers("dq:rules:read"),
    )
    assert current.status_code == 200
    current_version_id = current.json()["versions"][0]["id"]

    response = client.post(
        "/api/rulebuilder/v1/rules/rule-email-format/rollback",
        headers=_auth_headers("dq:rules:write"),
        json={
            "to_version_id": current_version_id,
            "reason": "Invalid rollback",
        },
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["status"] == 400


def test_rule_rollback_returns_not_found_for_missing_version(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.post(
        "/api/rulebuilder/v1/rules/rule-email-format/rollback",
        headers=_auth_headers("dq:rules:write"),
        json={
            "to_version_id": "rv-missing",
            "reason": "Rollback target does not exist",
        },
    )

    assert response.status_code == 404
    payload = response.json()
    assert payload["status"] == 404


def test_update_rule_version_tags_returns_updated_payload(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.patch(
        "/api/rulebuilder/v1/rules/rule-email-format/versions/rv-001/tags",
        headers=_auth_headers("dq:rules:write"),
        json={"tags": ["production", "stable", "v2"]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == "rv-001"
    assert payload["tags"] == ["production", "stable", "v2"]
    assert payload["updated_by"]["id"] == "user-admin"


def test_update_rule_version_tags_requires_write_scope(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.patch(
        "/api/rulebuilder/v1/rules/rule-email-format/versions/rv-001/tags",
        headers=_auth_headers("dq:rules:read"),
        json={"tags": ["production"]},
    )

    assert response.status_code == 403
    payload = response.json()
    assert payload["title"] == "Forbidden"


def test_update_rule_version_tags_returns_not_found_for_missing_version(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.patch(
        "/api/rulebuilder/v1/rules/rule-email-format/versions/rv-missing/tags",
        headers=_auth_headers("dq:rules:write"),
        json={"tags": ["production"]},
    )

    assert response.status_code == 404
    payload = response.json()
    assert payload["status"] == 404


def test_mark_version_for_rollback_returns_updated_flag(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.patch(
        "/api/rulebuilder/v1/rules/rule-email-format/versions/rv-001/mark-for-rollback",
        headers=_auth_headers("dq:rules:write"),
        json={"marked": True},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == "rv-001"
    assert payload["marked"] is True


def test_mark_version_for_rollback_requires_write_scope(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.patch(
        "/api/rulebuilder/v1/rules/rule-email-format/versions/rv-001/mark-for-rollback",
        headers=_auth_headers("dq:rules:read"),
        json={"marked": True},
    )

    assert response.status_code == 403
    payload = response.json()
    assert payload["title"] == "Forbidden"


def test_mark_version_for_rollback_returns_not_found(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.patch(
        "/api/rulebuilder/v1/rules/rule-email-format/versions/rv-missing/mark-for-rollback",
        headers=_auth_headers("dq:rules:write"),
        json={"marked": True},
    )

    assert response.status_code == 404
    payload = response.json()
    assert payload["status"] == 404
