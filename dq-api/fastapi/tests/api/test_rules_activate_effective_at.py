from collections.abc import Iterator

import pytest

from app.core.dependencies import get_approvals_repository, get_app_config_repository, get_rules_repository
from app.infrastructure.repositories.in_memory_app_config_repository import InMemoryAppConfigRepository
from app.infrastructure.repositories.in_memory_approvals_repository import InMemoryApprovalsRepository
from app.infrastructure.repositories.in_memory_rules_repository import InMemoryRulesRepository
from app.main import app


@pytest.fixture(autouse=True)
def isolated_rule_activation_dependencies() -> Iterator[None]:
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


def _create_rule(client, auth_headers: callable) -> str:
    resp = client.post(
        "/api/rulebuilder/v1/rules",
        headers=auth_headers("dq:rules:create", "dq:rules:write"),
        json={
            "name": "Rule To Activate (effective_at)",
            "description": "fixture",
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
    assert resp.status_code == 200
    return resp.json()["id"]


def _approve_rule(client, auth_headers: callable, rule_id: str) -> None:
    created = client.post(
        "/api/rulebuilder/v1/approvals",
        json={"rule_id": rule_id, "workspace_id": "default", "status": "pending"},
        headers=auth_headers("dq:rules:approve", "dq:rules:write"),
    )
    assert created.status_code == 200
    approval_id = created.json()["id"]

    reviewed = client.put(
        f"/api/rulebuilder/v1/approvals/{approval_id}",
        json={"status": "approved"},
        headers=auth_headers("dq:rules:approve", sub="user-reviewer", preferred_username="reviewer"),
    )
    assert reviewed.status_code == 200


def test_activate_rule_rejects_naive_effective_at(client, auth_headers: callable) -> None:
    rule_id = _create_rule(client, auth_headers)
    _approve_rule(client, auth_headers, rule_id)

    resp = client.post(
        f"/api/rulebuilder/v1/rules/{rule_id}/activate?effective_at=2026-04-07T13:15:00",
        headers=auth_headers("dq:rules:activate", "dq:rules:write"),
    )

    assert resp.status_code == 422
    assert "effective_at" in str(resp.json().get("detail"))


def test_activate_rule_future_effective_at_fails_fast(client, auth_headers: callable) -> None:
    rule_id = _create_rule(client, auth_headers)
    _approve_rule(client, auth_headers, rule_id)

    resp = client.post(
        f"/api/rulebuilder/v1/rules/{rule_id}/activate?effective_at=2030-01-01T00:00:00Z",
        headers=auth_headers("dq:rules:activate", "dq:rules:write"),
    )

    assert resp.status_code == 503
    payload = resp.json()
    assert payload["detail"]["service"] == "lifecycle-scheduler"
