from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.core.dependencies import get_app_config_repository
from app.core.dependencies import get_data_catalog_repository
from app.core.dependencies import get_join_consistency_contract_resolver
from app.core.dependencies import get_rules_repository
from app.main import app


def test_rule_create_rejects_ai_output_contract_before_persistence(
    client: TestClient,
    auth_headers: callable,
) -> None:
    class _RulesRepository:
        def __init__(self) -> None:
            self.create_calls: list[dict] = []
            self.list_calls: list[dict] = []

        async def list_rule_records(self, **kwargs):
            self.list_calls.append(kwargs)
            return []

        async def create_rule_record(self, **kwargs):
            self.create_calls.append(kwargs)
            raise AssertionError("AI output must not reach rule persistence")

    repository = _RulesRepository()
    app.dependency_overrides[get_rules_repository] = lambda: repository
    app.dependency_overrides[get_app_config_repository] = lambda: SimpleNamespace(
        get_app_config=lambda: SimpleNamespace(featureRuleDslV2=True)
    )
    app.dependency_overrides[get_data_catalog_repository] = lambda: object()
    app.dependency_overrides[get_join_consistency_contract_resolver] = lambda: object()

    response = client.post(
        "/api/rulebuilder/v1/rules",
        headers=auth_headers("dq:rules:create"),
        json={
            "name": "Assistant Draft Rule",
            "description": "AI output must remain read-only",
            "dimension": "completeness",
            "workspace": "default",
            "generated": False,
            "is_template": False,
            "ai_output": True,
            "dsl": {
                "schema_version": "1.0.0",
                "source": {
                    "kind": "filter_expression",
                    "expression": "email IS NOT NULL",
                },
            },
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"] == {
        "error": "ai_output_mutation_blocked",
        "message": "AI assistant output is read-only and cannot create, update, or persist rule contracts.",
        "field": "ai_output",
    }
    assert repository.list_calls == []
    assert repository.create_calls == []
