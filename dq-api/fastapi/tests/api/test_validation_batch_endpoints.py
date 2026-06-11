"""API tests for POST /rules/validate/batch — DQ-1.2."""
from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from app.core.config import get_settings
from app.core.dependencies import get_app_config_repository
from app.core.dependencies import get_rules_repository
from app.core.dependencies import get_validation_run_repository
from app.infrastructure.repositories.in_memory_app_config_repository import InMemoryAppConfigRepository
from app.infrastructure.repositories.in_memory_rules_repository import InMemoryRulesRepository
from app.infrastructure.repositories.in_memory_validation_run_repository import InMemoryValidationRunRepository
from app.main import app

client = TestClient(app)


def _jwt(payload: dict) -> str:
    import base64
    import json

    header = {"alg": "none", "typ": "JWT"}

    def encode(value: dict) -> str:
        return (
            base64.urlsafe_b64encode(json.dumps(value).encode()).decode().rstrip("=")
        )

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
    return {
        "Authorization": f"Bearer {token}",
        "X-Kong-Request-Id": "test-request-id",
    }


def setup_module() -> None:
    get_settings.cache_clear()


def teardown_module() -> None:
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def isolated_batch_validation_dependencies() -> None:
    rules_repository = InMemoryRulesRepository()
    app_config_repository = InMemoryAppConfigRepository()
    validation_run_repository = InMemoryValidationRunRepository()

    app.dependency_overrides[get_rules_repository] = lambda: rules_repository
    app.dependency_overrides[get_app_config_repository] = lambda: app_config_repository
    app.dependency_overrides[get_validation_run_repository] = lambda: validation_run_repository

    yield

    app.dependency_overrides.pop(get_rules_repository, None)
    app.dependency_overrides.pop(get_app_config_repository, None)
    app.dependency_overrides.pop(get_validation_run_repository, None)


def _sso_env(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()


# ── Auth guard ────────────────────────────────────────────────────────────────

def test_batch_validate_requires_bearer_token(monkeypatch) -> None:
    _sso_env(monkeypatch)
    response = client.post("/api/rulebuilder/v1/rules/validate/batch", json={"rule_ids": ["rule-email-format"]})
    assert response.status_code == 401


def test_batch_validate_requires_write_scope(monkeypatch) -> None:
    _sso_env(monkeypatch)
    response = client.post(
        "/api/rulebuilder/v1/rules/validate/batch",
        json={"rule_ids": ["rule-email-format"]},
        headers=_auth_headers("dq:rules:read"),   # read-only scope
    )
    assert response.status_code == 403


# ── Input validation ──────────────────────────────────────────────────────────

def test_batch_validate_rejects_empty_rule_ids(monkeypatch) -> None:
    _sso_env(monkeypatch)
    response = client.post(
        "/api/rulebuilder/v1/rules/validate/batch",
        json={"rule_ids": []},
        headers=_auth_headers("dq:rules:write"),
    )
    assert response.status_code == 422


def test_batch_validate_rejects_more_than_100_rules(monkeypatch) -> None:
    _sso_env(monkeypatch)
    rule_ids = [f"rule-{i}" for i in range(101)]
    response = client.post(
        "/api/rulebuilder/v1/rules/validate/batch",
        json={"rule_ids": rule_ids},
        headers=_auth_headers("dq:rules:write"),
    )
    assert response.status_code == 422


# ── Happy path ────────────────────────────────────────────────────────────────

def test_batch_validate_returns_expected_shape(monkeypatch) -> None:
    _sso_env(monkeypatch)
    response = client.post(
        "/api/rulebuilder/v1/rules/validate/batch",
        json={"rule_ids": ["rule-email-format"]},
        headers=_auth_headers("dq:rules:write"),
    )
    assert response.status_code == 200
    payload = response.json()

    assert "run_id" in payload
    assert isinstance(payload["run_id"], str)
    assert len(payload["run_id"]) > 0

    assert "results" in payload
    assert len(payload["results"]) == 1
    result = payload["results"][0]
    assert result["rule_id"] == "rule-email-format"
    assert isinstance(result["valid"], bool)
    assert isinstance(result["errors"], int)
    assert isinstance(result["warnings"], int)
    assert isinstance(result["diagnostics"], list)

    assert "conflicts" in payload
    assert isinstance(payload["conflicts"], list)

    assert "summary" in payload
    s = payload["summary"]
    assert s["total"] == 1
    assert s["valid"] + s["invalid"] == s["total"]


def test_batch_validate_valid_rule_reports_no_errors(monkeypatch) -> None:
    _sso_env(monkeypatch)
    response = client.post(
        "/api/rulebuilder/v1/rules/validate/batch",
        json={"rule_ids": ["rule-email-format"]},
        headers=_auth_headers("dq:rules:write"),
    )
    assert response.status_code == 200
    result = response.json()["results"][0]
    assert result["valid"] is True
    assert result["errors"] == 0


def test_batch_validate_warning_only_rule_preserves_compiler_diagnostics(monkeypatch) -> None:
    _sso_env(monkeypatch)
    repository = app.dependency_overrides[get_rules_repository]()
    repository._rules["rule-email-format"].expression = "email ILIKE '%@example.com'"

    response = client.post(
        "/api/rulebuilder/v1/rules/validate/batch",
        json={"rule_ids": ["rule-email-format"]},
        headers=_auth_headers("dq:rules:write"),
    )

    assert response.status_code == 200
    result = response.json()["results"][0]
    assert result["rule_id"] == "rule-email-format"
    assert result["valid"] is True
    assert result["errors"] == 0
    assert result["warnings"] == 1
    assert result["artifact_key"]
    assert result["compiler_version"] == "dq-7.3.0"
    assert any(
        diagnostic["code"] == "DQ7_AST_PARSE"
        and diagnostic["severity"] == "warning"
        and "ILIKE" in diagnostic["message"]
        for diagnostic in result["diagnostics"]
    )


def test_batch_validate_not_found_rule_returns_error_result(monkeypatch) -> None:
    """Missing rules produce an error result row rather than a 404 response."""
    _sso_env(monkeypatch)
    response = client.post(
        "/api/rulebuilder/v1/rules/validate/batch",
        json={"rule_ids": ["non-existent-rule-id"]},
        headers=_auth_headers("dq:rules:write"),
    )
    assert response.status_code == 200
    result = response.json()["results"][0]
    assert result["rule_id"] == "non-existent-rule-id"
    assert result["valid"] is False
    assert result["errors"] >= 1
    assert any(d["code"] == "DQ1_RULE_NOT_FOUND" for d in result["diagnostics"])


def test_batch_validate_run_id_is_unique_per_call(monkeypatch) -> None:
    _sso_env(monkeypatch)
    r1 = client.post(
        "/api/rulebuilder/v1/rules/validate/batch",
        json={"rule_ids": ["rule-email-format"]},
        headers=_auth_headers("dq:rules:write"),
    )
    r2 = client.post(
        "/api/rulebuilder/v1/rules/validate/batch",
        json={"rule_ids": ["rule-email-format"]},
        headers=_auth_headers("dq:rules:write"),
    )
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["run_id"] != r2.json()["run_id"]
