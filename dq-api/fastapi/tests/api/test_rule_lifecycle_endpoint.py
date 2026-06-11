from __future__ import annotations

import pytest

from app.core.dependencies import get_approvals_repository
from app.core.dependencies import get_rules_repository
from app.domain.entities import build_rule_record_entity
from app.infrastructure.repositories import InMemoryRulesRepository
from app.main import app
import app.api.v1.endpoints.rules as rules_endpoints


class _ApprovalsRepository:
    def list_approvals(self, _workspace):
        return []


class _RulesListRepository:
    async def list_rule_records(self, **kwargs):
        del kwargs
        return [
            build_rule_record_entity(
                {
                    "id": "rule-active",
                    "name": "Active rule",
                    "expression": "value > 0",
                    "dimension": "validity",
                    "lifecycle_status": "active",
                    "active": False,
                }
            ),
            build_rule_record_entity(
                {
                    "id": "rule-deprecated",
                    "name": "Deprecated rule",
                    "expression": "value > 10",
                    "dimension": "validity",
                    "lifecycle_status": "deprecated",
                    "active": False,
                }
            ),
        ]


def test_rules_list_filters_by_lifecycle_status(client, auth_headers) -> None:
    app.dependency_overrides[get_rules_repository] = lambda: _RulesListRepository()
    app.dependency_overrides[get_approvals_repository] = lambda: _ApprovalsRepository()

    try:
        response = client.get(
            "/api/rulebuilder/v1/rules?lifecycle_status=deprecated",
            headers=auth_headers("dq:rules:read"),
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200, response.text
    payload = response.json()
    assert [row["id"] for row in payload["data"]] == ["rule-deprecated"]
    assert payload["data"][0]["lifecycle_status"] == "deprecated"


@pytest.mark.anyio
async def test_rule_lifecycle_endpoint_transitions_rule(monkeypatch: pytest.MonkeyPatch) -> None:
    repository = InMemoryRulesRepository()
    repository._rules["rule-email-format"] = repository._rules["rule-email-format"].model_copy(update={"active": False})

    monkeypatch.setattr(rules_endpoints, "get_scopes", lambda: ["dq:rules:write"])
    monkeypatch.setattr(rules_endpoints, "get_user_id", lambda: "user-admin")

    payload = await rules_endpoints.transition_rule_lifecycle(
        "rule-email-format",
        rules_endpoints.RuleLifecycleTransitionRequest(
            lifecycle_status="deprecated",
            reason="Superseded by a newer rule set",
        ),
        repository=repository,
    )

    assert payload["id"] == "rule-email-format"
    assert payload["lifecycle_status"] == "deprecated"