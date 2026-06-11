import pytest
from fastapi.testclient import TestClient

from collections.abc import Iterator

from app.core.dependencies import get_app_config_repository, get_approvals_repository, get_rules_repository
from app.infrastructure.repositories.in_memory_app_config_repository import InMemoryAppConfigRepository
from app.infrastructure.repositories.in_memory_approvals_repository import InMemoryApprovalsRepository
from app.infrastructure.repositories.in_memory_rules_repository import InMemoryRulesRepository
from app.main import app


@pytest.fixture(autouse=True)
def isolated_dependencies() -> Iterator[None]:
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


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


def test_approvals_create_returns_effective_at(client: TestClient, auth_headers: callable) -> None:
    effective_at = "2026-04-07T13:15:00Z"

    response = client.post(
        "/api/rulebuilder/v1/approvals",
        json={
            "rule_id": "rule-new",
            "workspace_id": "default",
            "status": "pending",
            "effective_at": effective_at,
        },
        headers=auth_headers("dq:rules:approve"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["effective_at"] == effective_at


def test_approvals_create_rejects_naive_effective_at(client: TestClient, auth_headers: callable) -> None:
    response = client.post(
        "/api/rulebuilder/v1/approvals",
        json={
            "rule_id": "rule-new",
            "workspace_id": "default",
            "status": "pending",
            "effective_at": "2026-04-07T13:15:00",
        },
        headers=auth_headers("dq:rules:approve"),
    )

    assert response.status_code == 422
    assert "effective_at" in str(response.json().get("detail"))


def test_deactivation_approval_with_future_effective_at_fails_fast(
    client: TestClient,
    auth_headers: callable,
) -> None:
    created_rule = client.post(
        "/api/rulebuilder/v1/rules",
        headers=auth_headers("dq:rules:create", "dq:rules:write"),
        json={
            "name": "Rule for deactivation scheduling",
            "description": "fixture",
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
    assert created_rule.status_code == 200
    rule_id = created_rule.json()["id"]

    created_approval = client.post(
        "/api/rulebuilder/v1/approvals",
        json={
            "rule_id": rule_id,
            "workspace_id": "default",
            "status": "pending",
            "request_type": "deactivation",
            "effective_at": "2030-01-01T00:00:00Z",
        },
        headers=auth_headers("dq:rules:approve"),
    )
    assert created_approval.status_code == 200
    approval_id = created_approval.json()["id"]

    response = client.put(
        f"/api/rulebuilder/v1/approvals/{approval_id}",
        json={"status": "approved"},
        headers=auth_headers("dq:rules:approve", sub="user-analyst", preferred_username="analyst"),
    )

    assert response.status_code == 503
    payload = response.json()
    assert payload["detail"]["error"] == "downstream_unavailable"
    assert payload["detail"]["service"] == "lifecycle-scheduler"


def test_parse_effective_at_validates_timezone_aware_values() -> None:
    from app.api.presenters.approvals import parse_approval_effective_at

    normalized, parsed = parse_approval_effective_at({"effective_at": "2026-04-12T12:00:00Z"})
    assert normalized == "2026-04-12T12:00:00Z"
    assert parsed is not None
    assert parsed.tzinfo is not None

    with pytest.raises(Exception) as naive_error:
        parse_approval_effective_at({"effective_at": "2026-04-12T12:00:00"})
    assert "effective_at" in str(naive_error.value)

    with pytest.raises(Exception) as invalid_error:
        parse_approval_effective_at({"effective_at": "not-a-date"})
    assert "effective_at" in str(invalid_error.value)
