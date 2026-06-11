from fastapi.testclient import TestClient

import pytest

from app.core.dependencies import get_approvals_repository
from app.core.dependencies import get_app_config_repository
from app.core.dependencies import get_rules_repository
from app.core.config import get_settings
from app.infrastructure.repositories.in_memory_approvals_repository import InMemoryApprovalsRepository
from app.infrastructure.repositories.in_memory_app_config_repository import InMemoryAppConfigRepository
from app.infrastructure.repositories.in_memory_rules_repository import InMemoryRulesRepository
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


@pytest.fixture(autouse=True)
def isolated_approvals_dependencies() -> None:
    approvals_repository = InMemoryApprovalsRepository()
    rules_repository = InMemoryRulesRepository()
    app_config_repository = InMemoryAppConfigRepository()

    app.dependency_overrides[get_approvals_repository] = lambda: approvals_repository
    app.dependency_overrides[get_rules_repository] = lambda: rules_repository
    app.dependency_overrides[get_app_config_repository] = lambda: app_config_repository

    yield

    app.dependency_overrides.pop(get_approvals_repository, None)
    app.dependency_overrides.pop(get_rules_repository, None)
    app.dependency_overrides.pop(get_app_config_repository, None)


def test_approvals_requires_auth(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.get("/api/rulebuilder/v1/approvals")

    assert response.status_code == 401


def test_approvals_returns_paginated_data(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.get(
        "/api/rulebuilder/v1/approvals?page=1&limit=2",
        headers=_auth_headers("dq:rules:read"),
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["pagination"]["total"] >= 3
    assert payload["pagination"]["limit"] == 2
    assert len(payload["data"]) == 2


def test_approvals_filters_by_workspace(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.get(
        "/rulebuilder/v1/approvals?workspace=governance",
        headers=_auth_headers("dq:rules:read"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["pagination"]["total"] == 1
    assert payload["data"][0]["id"] == "approval-002"


def test_approvals_filters_by_business_key(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.get(
        "/api/rulebuilder/v1/approvals?businessKey=approval-002",
        headers=_auth_headers("dq:rules:read"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["pagination"]["total"] == 1
    assert payload["data"][0]["id"] == "approval-002"
    assert payload["data"][0]["business_key"] == "approval-002"


def test_approvals_filters_by_request_type(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.get(
        "/api/rulebuilder/v1/approvals?request_type=deactivation",
        headers=_auth_headers("dq:rules:read"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["pagination"]["total"] == 3
    assert all(item["request_type"] == "deactivation" for item in payload["data"])


def test_approvals_filters_by_requester_scope(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.get(
        "/api/rulebuilder/v1/approvals?workspace=retail-banking&exclude_requester_id=user-analyst",
        headers=_auth_headers("dq:rules:read"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["pagination"]["total"] == 0


def test_approvals_filters_by_query(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.get(
        "/api/rulebuilder/v1/approvals?query=controlled%20shutdown",
        headers=_auth_headers("dq:rules:read"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["pagination"]["total"] == 1
    assert payload["data"][0]["id"] == "approval-005"


def test_approvals_audit_returns_entries(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.get(
        "/api/rulebuilder/v1/approvals/audit",
        headers=_auth_headers("dq:rules:read"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["approval_id"] == "approval-001"
    assert payload[1]["action"] == "approved"


def test_approvals_requires_view_scope(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.get(
        "/api/rulebuilder/v1/approvals",
        headers=_auth_headers("dq:profiling:request"),
    )

    assert response.status_code == 403


def test_approvals_create_requires_approve_scope(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.post(
        "/api/rulebuilder/v1/approvals",
        json={"rule_id": "rule-new", "workspace_id": "default"},
        headers=_auth_headers("dq:rules:read"),
    )

    assert response.status_code == 403


def test_approvals_create_succeeds(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.post(
        "/api/rulebuilder/v1/approvals",
        json={"rule_id": "rule-new", "workspace_id": "default", "status": "pending"},
        headers=_auth_headers("dq:rules:approve"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["rule_id"] == "rule-new"
    assert payload["business_key"] == payload["id"]
    assert payload["status"] == "pending"
    assert payload["requester_id"] == "user-admin"


def test_approvals_create_supports_gx_run_plan_requests(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.post(
        "/api/rulebuilder/v1/approvals",
        json={
            "gx_run_plan_id": "run-plan-1",
            "gx_run_plan_version_id": "run-plan-version-1",
            "workspace_id": "default",
            "status": "pending",
        },
        headers=_auth_headers("dq:rules:approve"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["gx_run_plan_id"] == "run-plan-1"
    assert payload["gx_run_plan_version_id"] == "run-plan-version-1"
    assert payload["business_key"] == payload["id"]
    assert payload["status"] == "pending"


def test_approvals_comment_endpoint_persists_thread(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    created = client.post(
        "/api/rulebuilder/v1/approvals",
        json={
            "rule_id": "rule-threaded",
            "workspace_id": "default",
            "status": "pending",
            "comments": "Initial request note",
        },
        headers=_auth_headers("dq:rules:approve"),
    )

    assert created.status_code == 200
    approval_id = created.json()["id"]

    response = client.post(
        f"/api/rulebuilder/v1/approvals/{approval_id}/comments",
        json={
            "workspace_id": "default",
            "comment": "Please attach the contract snapshot.",
            "comment_type": "question",
        },
        headers=_auth_headers("dq:rules:approve"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["comment_thread"][0]["content"] == "Initial request note"
    assert payload["comment_thread"][0]["type"] == "note"
    assert payload["comment_thread"][1]["content"] == "Please attach the contract snapshot."
    assert payload["comment_thread"][1]["type"] == "question"
    assert payload["comment_thread"][1]["author_id"] == "user-admin"


def test_approvals_create_rejects_incomplete_gx_run_plan_requests(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.post(
        "/api/rulebuilder/v1/approvals",
        json={
            "gx_run_plan_id": "run-plan-1",
            "workspace_id": "default",
            "status": "pending",
        },
        headers=_auth_headers("dq:rules:approve"),
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "gx_run_plan_version_id is required when gx_run_plan_id is provided"


def test_approvals_update_blocks_self_approval(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    created_rule = client.post(
        "/api/rulebuilder/v1/rules",
        headers=_auth_headers("dq:rules:create", "dq:rules:write"),
        json={
            "name": "Self approval test rule",
            "description": "approval transition fixture",
            "dimension": "completeness",
            "active": False,
            "workspace": "default",
            "dsl": {
                "schemaVersion": "1.0.0",
                "source": {
                    "kind": "filter_expression",
                    "expression": "email IS NOT NULL",
                },
            },
        },
    )
    assert created_rule.status_code == 200
    rule_id = created_rule.json()["id"]

    created_approval = client.post(
        "/api/rulebuilder/v1/approvals",
        json={"rule_id": rule_id, "workspace_id": "default", "status": "pending"},
        headers=_auth_headers("dq:rules:approve", "dq:rules:write"),
    )
    assert created_approval.status_code == 200
    approval_id = created_approval.json()["id"]

    token = _jwt(
        {
            "sub": "user-admin",
            "preferred_username": "admin",
            "iss": "http://keycloak.local:8080/realms/jaccloud",
            "aud": ["dq-rules-ui"],
            "scope": "dq:rules:approve",
        }
    )
    response = client.put(
        f"/api/rulebuilder/v1/approvals/{approval_id}",
        json={"status": "approved"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Requester cannot approve their own request"


def test_approvals_update_and_delete_permission_paths(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    created = client.post(
        "/api/rulebuilder/v1/approvals",
        json={"rule_id": "rule-delete", "workspace_id": "default", "status": "pending"},
        headers=_auth_headers("dq:rules:approve"),
    )
    assert created.status_code == 200
    approval_id = created.json()["id"]

    updated = client.put(
        f"/api/rulebuilder/v1/approvals/{approval_id}",
        json={"status": "approved"},
        headers=_auth_headers("dq:rules:approve"),
    )
    assert updated.status_code == 403

    analyst_token = _jwt(
        {
            "sub": "user-analyst",
            "preferred_username": "analyst",
            "iss": "http://keycloak.local:8080/realms/jaccloud",
            "aud": ["dq-rules-ui"],
            "scope": "dq:rules:approve",
        }
    )
    updated_ok = client.put(
        f"/api/rulebuilder/v1/approvals/{approval_id}",
        json={"status": "approved"},
        headers={"Authorization": f"Bearer {analyst_token}"},
    )
    assert updated_ok.status_code == 200
    assert updated_ok.json()["status"] == "approved"

    deleted_forbidden = client.delete(
        f"/api/rulebuilder/v1/approvals/{approval_id}",
        headers={"Authorization": f"Bearer {analyst_token}"},
    )
    assert deleted_forbidden.status_code == 403
    assert deleted_forbidden.json()["detail"] == "Only requester can cancel"

    deleted_ok = client.delete(
        f"/api/rulebuilder/v1/approvals/{approval_id}",
        headers=_auth_headers("dq:rules:approve"),
    )
    assert deleted_ok.status_code == 200
    assert deleted_ok.json()["id"] == approval_id


def test_approvals_comment_governance_lock_and_lifecycle(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    created = client.post(
        "/api/rulebuilder/v1/approvals",
        json={"rule_id": "rule-governance", "workspace_id": "default", "status": "pending"},
        headers=_auth_headers("dq:rules:approve"),
    )
    assert created.status_code == 200
    approval_id = created.json()["id"]

    comment_response = client.post(
        f"/api/rulebuilder/v1/approvals/{approval_id}/comments",
        json={"workspace_id": "default", "comment": "Please review the evidence.", "comment_type": "question"},
        headers=_auth_headers("dq:rules:approve"),
    )
    assert comment_response.status_code == 200
    comment_id = comment_response.json()["comment_thread"][-1]["id"]

    edited = client.patch(
        f"/api/rulebuilder/v1/approvals/{approval_id}/comments/{comment_id}",
        json={"comment": "Please review the evidence packet."},
        headers=_auth_headers("dq:rules:approve"),
    )
    assert edited.status_code == 200
    edited_thread = edited.json()["comment_thread"]
    assert edited_thread[-1]["content"] == "Please review the evidence packet."
    assert edited_thread[-1]["edited"] is True

    resolved = client.post(
        f"/api/rulebuilder/v1/approvals/{approval_id}/comments/{comment_id}/resolve",
        headers=_auth_headers("dq:rules:approve"),
    )
    assert resolved.status_code == 200
    assert resolved.json()["comment_thread"][-1]["state"] == "resolved"

    lock_response = client.patch(
        f"/api/rulebuilder/v1/approvals/{approval_id}/comments-lock",
        json={"locked": True},
        headers=_auth_headers("dq:rules:approve"),
    )
    assert lock_response.status_code == 200
    assert lock_response.json()["comments_locked"] is True

    blocked = client.post(
        f"/api/rulebuilder/v1/approvals/{approval_id}/comments",
        json={"workspace_id": "default", "comment": "This should be blocked.", "comment_type": "general"},
        headers=_auth_headers("dq:rules:approve"),
    )
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["error"] == "comments_locked"

    deleted = client.delete(
        f"/api/rulebuilder/v1/approvals/{approval_id}/comments/{comment_id}",
        headers=_auth_headers("dq:rules:approve"),
    )
    assert deleted.status_code == 200
    assert deleted.json()["removed_comment_count"] == 1


def test_reject_rule_appears_in_audit_trail(monkeypatch) -> None:
    """Rejecting a pending approval for an existing rule leaves a 'declined' entry in the audit trail."""
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    created_rule = client.post(
        "/api/rulebuilder/v1/rules",
        headers=_auth_headers("dq:rules:create", "dq:rules:write"),
        json={
            "name": "Reject audit test rule",
            "description": "approval transition fixture",
            "dimension": "completeness",
            "active": False,
            "workspace": "default",
            "dsl": {
                "schemaVersion": "1.0.0",
                "source": {
                    "kind": "filter_expression",
                    "expression": "email IS NOT NULL",
                },
            },
        },
    )
    assert created_rule.status_code == 200
    rule_id = created_rule.json()["id"]

    # Create a fresh approval for an isolated rule so transition rules are deterministic.
    created = client.post(
        "/api/rulebuilder/v1/approvals",
        json={"rule_id": rule_id, "workspace_id": "default", "status": "pending"},
        headers=_auth_headers("dq:rules:approve", "dq:rules:write"),
    )
    assert created.status_code == 200
    approval_id = created.json()["id"]
    assert created.json()["rule_id"] == rule_id

    # Reject the approval as a different actor (reviewer, not the requester).
    reviewer_token = _jwt(
        {
            "sub": "user-reviewer",
            "preferred_username": "reviewer",
            "iss": "http://keycloak.local:8080/realms/jaccloud",
            "aud": ["dq-rules-ui"],
            "scope": "dq:rules:approve",
        }
    )
    rejected = client.put(
        f"/api/rulebuilder/v1/approvals/{approval_id}",
        json={"status": "declined"},
        headers={"Authorization": f"Bearer {reviewer_token}"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "declined"

    # Verify the rejection is recorded in the audit trail.
    audit_response = client.get(
        "/api/rulebuilder/v1/approvals/audit",
        headers=_auth_headers("dq:rules:read"),
    )
    assert audit_response.status_code == 200
    audit_entries = audit_response.json()

    rejected_entries = [
        entry for entry in audit_entries
        if entry["approval_id"] == approval_id and entry["action"] == "rejected"
    ]
    assert len(rejected_entries) == 1
    assert rejected_entries[0]["actor_id"] == "user-reviewer"


def test_removed_rule_cannot_reenter_approval_until_recovered(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    create_rule = client.post(
        "/api/rulebuilder/v1/rules",
        headers=_auth_headers("dq:rules:create"),
        json={
            "name": "Removed Rule Approval Guard",
            "description": "approval guard flow",
            "dimension": "completeness",
            "active": True,
            "workspace": "default",
            "dsl": {
                "schemaVersion": "1.0.0",
                "source": {
                    "kind": "filter_expression",
                    "expression": "email IS NOT NULL",
                },
            },
        },
    )
    assert create_rule.status_code == 200
    rule_id = create_rule.json()["id"]

    deactivation_request = client.post(
        "/api/rulebuilder/v1/approvals",
        headers=_auth_headers("dq:rules:approve", "dq:rules:write"),
        json={
            "rule_id": rule_id,
            "workspace_id": "default",
            "request_type": "deactivation",
            "status": "pending",
        },
    )
    assert deactivation_request.status_code == 200
    deactivation_approval_id = deactivation_request.json()["id"]

    reviewer_token = _jwt(
        {
            "sub": "user-reviewer",
            "preferred_username": "reviewer",
            "iss": "http://keycloak.local:8080/realms/jaccloud",
            "aud": ["dq-rules-ui"],
            "scope": "dq:rules:approve",
        }
    )
    approve_deactivation = client.put(
        f"/api/rulebuilder/v1/approvals/{deactivation_approval_id}",
        json={"status": "approved"},
        headers={"Authorization": f"Bearer {reviewer_token}"},
    )
    assert approve_deactivation.status_code == 200

    remove_rule = client.delete(
        f"/api/rulebuilder/v1/rules/{rule_id}",
        headers=_auth_headers("dq:rules:delete", "dq:rules:write"),
    )
    assert remove_rule.status_code == 200
    assert remove_rule.json()["removed"] is True

    blocked_approval = client.post(
        "/api/rulebuilder/v1/approvals",
        headers=_auth_headers("dq:rules:approve", "dq:rules:write"),
        json={"rule_id": rule_id, "workspace_id": "default", "status": "pending"},
    )
    assert blocked_approval.status_code == 409
    assert "removed" in blocked_approval.json()["detail"]

    recover_rule = client.post(
        f"/api/admin/v1/rules/{rule_id}/recover",
        headers=_auth_headers("dq:users:manage"),
    )
    assert recover_rule.status_code == 200
    assert recover_rule.json()["last_approval_status"] == "recovered"

    resubmitted_approval = client.post(
        "/api/rulebuilder/v1/approvals",
        headers=_auth_headers("dq:rules:approve", "dq:rules:write"),
        json={"rule_id": rule_id, "workspace_id": "default", "status": "pending"},
    )
    assert resubmitted_approval.status_code == 200