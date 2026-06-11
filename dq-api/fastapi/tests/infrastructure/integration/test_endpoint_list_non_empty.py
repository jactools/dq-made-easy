"""Integration policy: seeded list endpoints must return at least one row.

This test guards UI-facing list endpoints against regressions where API wiring,
filters, or repository behavior accidentally return empty collections despite
seeded data being present.
"""
from __future__ import annotations

import base64
import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app

pytestmark = pytest.mark.integration
client = TestClient(app)


def _jwt(payload: dict[str, object]) -> str:
    header = {"alg": "none", "typ": "JWT"}

    def encode(value: dict[str, object]) -> str:
        raw = json.dumps(value).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")

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
    return {
        "Authorization": f"Bearer {token}",
        "X-Kong-Request-Id": f"test-{uuid4().hex}",
    }


def _admin_headers() -> dict[str, str]:
    return _auth_headers(
        "dq:users:manage",
        "dq:rules:read",
        "dq:rules:view",
        "dq:rules:test",
        "dq:rules:create",
        "dq:rules:edit",
        "dq:rules:approve",
        "dq:workspace:manage",
    )


@pytest.fixture(autouse=True)
def _integration_auth_env(monkeypatch: pytest.MonkeyPatch, live_db_url: str) -> None:
    _ = live_db_url
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()


def _assert_non_empty_collection(payload: object, key: str | None) -> None:
    if key is None:
        assert isinstance(payload, list)
        assert len(payload) >= 1
        return

    assert isinstance(payload, dict)
    collection = payload.get(key)
    assert isinstance(collection, list)
    assert len(collection) >= 1


def _get_first_rule_id() -> str:
    response = client.get("/api/rulebuilder/v1/rules", headers=_admin_headers())
    assert response.status_code == 200
    payload = response.json()
    rows = payload.get("data") or []
    assert rows, "Expected at least one rule row"
    return str(rows[0]["id"])


def _ensure_batch_test_request(rule_id: str) -> None:
    response = client.get("/api/rulebuilder/v1/batch-test-requests", headers=_admin_headers())
    assert response.status_code == 200
    payload = response.json()
    existing = payload.get("data") or []
    if existing:
        return

    create_response = client.post(
        "/api/rulebuilder/v1/batch-test-requests",
        headers=_admin_headers(),
        json={"rule_ids": [rule_id], "requested_by": "user-admin", "workspace": "default"},
    )
    assert create_response.status_code == 200


def _ensure_reusable_assets() -> None:
    filters_response = client.get("/api/rulebuilder/v1/reusable-filters", headers=_admin_headers())
    assert filters_response.status_code == 200
    filters_payload = filters_response.json()
    if not filters_payload:
        create_filter = client.post(
            "/api/rulebuilder/v1/reusable-filters",
            headers=_admin_headers(),
            json={
                "name": f"Policy Filter {uuid4().hex[:8]}",
                "expression": "1 = 1",
                "workspace": "default",
                "active": True,
            },
        )
        assert create_filter.status_code == 200

    joins_response = client.get("/api/rulebuilder/v1/reusable-joins", headers=_admin_headers())
    assert joins_response.status_code == 200
    joins_payload = joins_response.json()
    if not joins_payload:
        create_join = client.post(
            "/api/rulebuilder/v1/reusable-joins",
            headers=_admin_headers(),
            json={
                "name": f"Policy Join {uuid4().hex[:8]}",
                "joinDefinition": [
                    {
                        "joinType": "inner",
                        "conditions": [
                            {
                                "leftDataObjectId": "orders",
                                "leftAttributeId": "customer_id",
                                "operator": "=",
                                "rightDataObjectId": "customers",
                                "rightAttributeId": "id",
                            }
                        ],
                    }
                ],
                "workspace": "default",
                "active": True,
            },
        )
        assert create_join.status_code == 200


def _ensure_test_proof(rule_id: str) -> None:
    response = client.get(f"/api/rulebuilder/v1/test-proofs/{rule_id}", headers=_admin_headers())
    assert response.status_code == 200
    payload = response.json()
    if payload:
        return

    create_response = client.post(
        f"/api/rulebuilder/v1/rules/{rule_id}/test",
        headers=_admin_headers(),
        json={
            "coverage": 1.0,
            "passed": True,
            "records_tested_count": 1,
            "failures_found": 0,
            "proof_data": {"source": "policy-test"},
        },
    )
    assert create_response.status_code == 200


@pytest.mark.parametrize(
    ("path", "collection_key", "scopes"),
    [
        ("/api/admin/v1/users", "data", ("dq:admin:read",)),
        ("/api/admin/v1/roles", None, ("dq:admin:read",)),
        ("/api/rulebuilder/v1/approvals", "data", ("dq:rules:read",)),
        ("/api/rulebuilder/v1/approvals/audit", None, ("dq:rules:read",)),
        ("/api/rulebuilder/v1/workspaces", "data", ("dq:rules:view", "dq:rules:read")),
        ("/api/rulebuilder/v1/rules", "data", ("dq:rules:read",)),
        ("/api/data-catalog/v1/data-products", "data", ("dq:rules:read",)),
        ("/api/data-catalog/v1/data-objects", None, ("dq:rules:read",)),
        ("/api/data-catalog/v1/data-sets", "data", ("dq:rules:read",)),
        ("/api/data-catalog/v1/rule-attributes", None, ("dq:rules:read",)),
        ("/api/data-catalog/v1/data-objects-catalog", "data", ("dq:rules:read",)),
        ("/api/data-catalog/v1/data-object-versions", "data", ("dq:rules:read",)),
        ("/api/data-catalog/v1/attributes-catalog", "data", ("dq:rules:read",)),
        ("/api/data-catalog/v1/data-deliveries", "data", ("dq:rules:read",)),
        ("/api/rulebuilder/v1/catalog/terms", "terms", ("dq:rules:read",)),
        ("/api/rulebuilder/v1/reusable-filters", None, ("dq:rules:read",)),
        ("/api/rulebuilder/v1/reusable-joins", None, ("dq:rules:read",)),
        ("/api/rulebuilder/v1/batch-test-requests", "data", ("dq:rules:test",)),
    ],
)
def test_seeded_list_endpoints_return_at_least_one_entry_integration(
    path: str,
    collection_key: str | None,
    scopes: tuple[str, ...],
    live_db_url: str,
) -> None:
    _ = live_db_url

    if path in {"/api/rulebuilder/v1/reusable-filters", "/api/rulebuilder/v1/reusable-joins"}:
        _ensure_reusable_assets()

    if path == "/api/rulebuilder/v1/batch-test-requests":
        _ensure_batch_test_request(_get_first_rule_id())

    response = client.get(path, headers=_auth_headers(*scopes))
    assert response.status_code == 200, f"{path} returned {response.status_code}: {response.text}"

    payload = response.json()
    _assert_non_empty_collection(payload, collection_key)


def test_rule_versions_list_returns_at_least_one_version_integration(live_db_url: str) -> None:
    _ = live_db_url
    first_rule_id = _get_first_rule_id()
    versions_response = client.get(
        f"/api/rulebuilder/v1/rules/{first_rule_id}/versions",
        headers=_admin_headers(),
    )
    assert versions_response.status_code == 200
    versions_payload = versions_response.json()
    versions = versions_payload.get("versions")
    assert isinstance(versions, list)
    assert len(versions) >= 1


def test_rule_versions_and_test_proofs_lists_return_at_least_one_entry_integration(
    live_db_url: str,
) -> None:
    _ = live_db_url
    first_rule_id = _get_first_rule_id()

    versions_response = client.get(f"/api/rulebuilder/v1/rules/{first_rule_id}/versions", headers=_admin_headers())
    assert versions_response.status_code == 200
    versions_payload = versions_response.json()
    versions = versions_payload.get("versions")
    assert isinstance(versions, list)
    assert len(versions) >= 1

    _ensure_test_proof(first_rule_id)
    proofs_response = client.get(f"/api/rulebuilder/v1/test-proofs/{first_rule_id}", headers=_admin_headers())
    assert proofs_response.status_code == 200
    proofs_payload = proofs_response.json()
    assert isinstance(proofs_payload, list)
    assert len(proofs_payload) >= 1
