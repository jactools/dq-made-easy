from fastapi.testclient import TestClient

from app.core.dependencies import get_approvals_repository
from app.core.dependencies import get_rules_repository
from app.domain.entities import build_rule_record_entity
from app.main import app


class _RulesRepository:
    async def list_rule_records(self, **kwargs):
        del kwargs
        return [
            build_rule_record_entity(
                {
                    "id": "rule-owned",
                    "name": "Owned rule",
                    "expression": "email IS NOT NULL",
                    "dimension": "Validity",
                    "workspace": "retail-banking",
                    "created_by": "alice@example.com",
                    "check_type": "REGEX",
                    "taxonomy": {
                        "owner": "alice@example.com",
                        "data_steward": "alice@example.com",
                        "domain_owner": "domain-owner@example.com",
                        "technical_owner": "tech-owner@example.com",
                    },
                    "dsl": {
                        "schema_version": "2.0.0",
                        "rule": {
                            "kind": "metric_threshold",
                            "scope": {"dataset": {"data_product_id": "odcs.retail.customer"}},
                            "measure": {"type": "metric", "metric": "missing_percent", "subject": {"column": "email"}},
                            "expectation": {"type": "threshold", "operator": "lte", "value": 0.0, "unit": "percent"},
                            "evidence": {
                                "failed_rows": {"mode": "sample", "limit": 10, "include_row_identifier": True, "include_primary_key": True},
                                "emit_compiled_artifact": True,
                                "emit_generated_sql": False,
                            },
                            "operations": {"severity": "critical", "preferred_engines": ["gx"], "fail_if_not_native": False},
                        },
                    },
                    "active": True,
                }
            ),
            build_rule_record_entity(
                {
                    "id": "rule-other",
                    "name": "Other rule",
                    "expression": "amount > 0",
                    "dimension": "Completeness",
                    "workspace": "retail-banking",
                    "created_by": "alice-team@example.com",
                    "active": True,
                }
            ),
        ]


class _ApprovalsRepository:
    def list_approvals(self, _workspace):
        return []


def test_rules_list_returns_taxonomy_and_owner_filter_is_exact(
    client: TestClient,
    auth_headers: callable,
) -> None:
    app.dependency_overrides[get_rules_repository] = lambda: _RulesRepository()
    app.dependency_overrides[get_approvals_repository] = lambda: _ApprovalsRepository()

    response = client.get(
        "/api/rulebuilder/v1/rules?owner=alice@example.com",
        headers=auth_headers("dq:rules:read"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert [row["id"] for row in payload["data"]] == ["rule-owned"]
    assert payload["data"][0]["taxonomy"] == {
        "type": "REGEX",
        "severity": "critical",
        "domain": "odcs.retail.customer",
        "owner": "alice@example.com",
        "data_steward": "alice@example.com",
        "domain_owner": "domain-owner@example.com",
        "technical_owner": "tech-owner@example.com",
        "sla_scope": "dataset",
        "execution_target": "gx",
    }