from fastapi.testclient import TestClient

from app.core.dependencies import get_approvals_repository
from app.core.dependencies import get_rules_repository
from app.domain.entities import build_rule_record_entity
from app.main import app


class _RulesRepository:
    def __init__(self) -> None:
        self.rows = [
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
                    "created_by": "bob@example.com",
                    "check_type": "THRESHOLD",
                    "taxonomy": {
                        "owner": "bob@example.com",
                        "data_steward": "bob@example.com",
                        "domain_owner": "ops-owner@example.com",
                        "technical_owner": "tech-owner@example.com",
                    },
                    "dsl": {
                        "schema_version": "2.0.0",
                        "rule": {
                            "kind": "metric_threshold",
                            "scope": {"dataset": {"data_product_id": "odcs.retail.payments"}},
                            "measure": {"type": "metric", "metric": "row_count", "subject": {"column": "amount"}},
                            "expectation": {"type": "threshold", "operator": "gte", "value": 1, "unit": "count"},
                            "operations": {"severity": "medium", "preferred_engines": ["sql"], "fail_if_not_native": False},
                        },
                    },
                    "active": True,
                }
            ),
        ]

    async def list_rule_records(self, **kwargs):
        del kwargs
        return [row for row in self.rows if row is not None]


class _ApprovalsRepository:
    def list_approvals(self, _workspace):
        return []


def test_rule_registry_endpoint_returns_discovery_facets(
    client: TestClient,
    auth_headers,
) -> None:
    app.dependency_overrides[get_rules_repository] = lambda: _RulesRepository()
    app.dependency_overrides[get_approvals_repository] = lambda: _ApprovalsRepository()

    try:
        response = client.get(
            "/api/rulebuilder/v1/rules/registry?owner=alice@example.com&domain=odcs.retail.customer",
            headers=auth_headers("dq:rules:read"),
        )

        assert response.status_code == 200
        payload = response.json()
        assert [row["id"] for row in payload["data"]] == ["rule-owned"]
        assert payload["discovery"]["owners"] == ["alice@example.com"]
        assert payload["discovery"]["data_stewards"] == ["alice@example.com"]
        assert payload["discovery"]["domain_owners"] == ["domain-owner@example.com"]
        assert payload["discovery"]["technical_owners"] == ["tech-owner@example.com"]
        assert payload["discovery"]["domains"] == ["odcs.retail.customer"]
    finally:
        app.dependency_overrides.clear()