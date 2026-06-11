"""API tests for validation run history endpoints — DQ-1.4."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.core.config import get_settings

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
    return {"Authorization": f"Bearer {token}"}


def setup_module() -> None:
    get_settings.cache_clear()


def teardown_module() -> None:
    get_settings.cache_clear()


def _sso_env(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()


# ── List runs ─────────────────────────────────────────────────────────────────

def test_list_validation_runs_requires_auth(monkeypatch) -> None:
    _sso_env(monkeypatch)
    response = client.get("/api/rulebuilder/v1/rules/validation-runs")
    assert response.status_code == 401


def test_list_validation_runs_returns_paginated_shape(monkeypatch) -> None:
    _sso_env(monkeypatch)
    response = client.get(
        "/api/rulebuilder/v1/rules/validation-runs",
        headers=_auth_headers("dq:rules:read"),
    )
    assert response.status_code == 200
    payload = response.json()
    assert "data" in payload
    assert "pagination" in payload
    assert isinstance(payload["data"], list)
    p = payload["pagination"]
    assert "total" in p
    assert "page" in p
    assert "limit" in p


def test_list_validation_runs_respects_limit_param(monkeypatch) -> None:
    _sso_env(monkeypatch)
    response = client.get(
        "/api/rulebuilder/v1/rules/validation-runs?limit=5&page=1",
        headers=_auth_headers("dq:rules:read"),
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["pagination"]["limit"] == 5
    assert len(payload["data"]) <= 5


# ── Get run detail ────────────────────────────────────────────────────────────

def test_get_validation_run_returns_404_for_unknown_id(monkeypatch) -> None:
    _sso_env(monkeypatch)
    response = client.get(
        "/api/rulebuilder/v1/rules/validation-runs/no-such-run",
        headers=_auth_headers("dq:rules:read"),
    )
    assert response.status_code == 404


# ── Create then inspect ───────────────────────────────────────────────────────

def _run_batch(monkeypatch) -> dict:
    _sso_env(monkeypatch)
    response = client.post(
        "/api/rulebuilder/v1/rules/validate/batch",
        json={"rule_ids": ["rule-email-format"]},
        headers=_auth_headers("dq:rules:write"),
    )
    assert response.status_code == 200
    return response.json()


def test_batch_run_appears_in_run_history(monkeypatch) -> None:
    batch = _run_batch(monkeypatch)
    run_id = batch["run_id"]

    response = client.get(
        "/api/rulebuilder/v1/rules/validation-runs",
        headers=_auth_headers("dq:rules:read"),
    )
    assert response.status_code == 200
    run_ids = [r["id"] for r in response.json()["data"]]
    assert run_id in run_ids


def test_get_run_by_id_returns_run_detail(monkeypatch) -> None:
    batch = _run_batch(monkeypatch)
    run_id = batch["run_id"]

    response = client.get(
        f"/api/rulebuilder/v1/rules/validation-runs/{run_id}",
        headers=_auth_headers("dq:rules:read"),
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == run_id
    assert isinstance(payload["total"], int)
    assert isinstance(payload["valid_count"], int)


# ── Export ────────────────────────────────────────────────────────────────────

def test_export_run_json_returns_json_file(monkeypatch) -> None:
    batch = _run_batch(monkeypatch)
    run_id = batch["run_id"]

    response = client.get(
        f"/api/rulebuilder/v1/rules/validation-runs/{run_id}/export?format=json",
        headers=_auth_headers("dq:rules:read"),
    )
    assert response.status_code == 200
    assert "application/json" in response.headers.get("content-type", "")


def test_export_run_csv_returns_csv_file(monkeypatch) -> None:
    batch = _run_batch(monkeypatch)
    run_id = batch["run_id"]

    response = client.get(
        f"/api/rulebuilder/v1/rules/validation-runs/{run_id}/export?format=csv",
        headers=_auth_headers("dq:rules:read"),
    )
    assert response.status_code == 200
    assert "text/csv" in response.headers.get("content-type", "")
    content = response.text
    assert "ruleId" in content


def test_export_unknown_run_returns_404(monkeypatch) -> None:
    _sso_env(monkeypatch)
    response = client.get(
        "/api/rulebuilder/v1/rules/validation-runs/ghost-run-id/export?format=json",
        headers=_auth_headers("dq:rules:read"),
    )
    assert response.status_code == 404


def test_export_rejects_invalid_format(monkeypatch) -> None:
    batch = _run_batch(monkeypatch)
    run_id = batch["run_id"]

    response = client.get(
        f"/api/rulebuilder/v1/rules/validation-runs/{run_id}/export?format=xml",
        headers=_auth_headers("dq:rules:read"),
    )
    assert response.status_code == 422
