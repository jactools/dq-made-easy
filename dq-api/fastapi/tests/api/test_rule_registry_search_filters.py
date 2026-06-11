from __future__ import annotations

from app.core.dependencies import get_approvals_repository
from app.core.dependencies import get_rules_repository
from app.domain.entities import build_rule_record_entity
from app.main import app


class _ApprovalsRepository:
    def list_approvals(self, _workspace):
        return []


class _RulesRepository:
    async def list_rule_records(self, **kwargs):
        del kwargs
        return [
            build_rule_record_entity(
                {
                    "id": "rule-matching",
                    "name": "Matching rule",
                    "expression": "email IS NOT NULL",
                    "dimension": "Validity",
                    "workspace": "retail-banking",
                    "created_by": "alice@example.com",
                    "lifecycle_status": "deprecated",
                    "check_type": "REGEX",
                    "taxonomy": {
                        "owner": "alice@example.com",
                        "data_steward": "alice@example.com",
                        "domain": "odcs.retail.customer",
                        "domain_owner": "domain-owner@example.com",
                        "severity": "critical",
                        "technical_owner": "tech-owner@example.com",
                        "execution_target": "gx",
                    },
                    "dsl": {
                        "schema_version": "2.0.0",
                        "rule": {
                            "kind": "metric_threshold",
                            "scope": {"dataset": {"data_product_id": "odcs.retail.customer"}},
                            "measure": {"type": "metric", "metric": "missing_percent", "subject": {"column": "email"}},
                            "expectation": {"type": "threshold", "operator": "lte", "value": 0.0, "unit": "percent"},
                            "operations": {"severity": "critical", "preferred_engines": ["gx"], "fail_if_not_native": False},
                        },
                    },
                    "active": False,
                }
            ),
            build_rule_record_entity(
                {
                    "id": "rule-decoy",
                    "name": "Decoy rule",
                    "expression": "amount > 0",
                    "dimension": "Completeness",
                    "workspace": "retail-banking",
                    "created_by": "bob@example.com",
                    "lifecycle_status": "active",
                    "check_type": "THRESHOLD",
                    "taxonomy": {
                        "owner": "bob@example.com",
                        "data_steward": "bob@example.com",
                        "domain": "odcs.retail.payments",
                        "domain_owner": "ops-owner@example.com",
                        "severity": "medium",
                        "technical_owner": "ops-tech@example.com",
                        "execution_target": "sql",
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


def test_rule_registry_filters_by_owner_domain_lifecycle_severity_and_execution_target(
    client,
    auth_headers,
) -> None:
    app.dependency_overrides[get_rules_repository] = lambda: _RulesRepository()
    app.dependency_overrides[get_approvals_repository] = lambda: _ApprovalsRepository()

    try:
        scenarios = [
            ("owner=alice@example.com", ["rule-matching"]),
            ("domain=odcs.retail.customer", ["rule-matching"]),
            ("lifecycle_status=deprecated", ["rule-matching"]),
            ("severity=critical", ["rule-matching"]),
            ("execution_target=gx", ["rule-matching"]),
            (
                "owner=alice@example.com&domain=odcs.retail.customer&lifecycle_status=deprecated&severity=critical&execution_target=gx",
                ["rule-matching"],
            ),
        ]

        for query_string, expected_ids in scenarios:
            response = client.get(
                f"/api/rulebuilder/v1/rules/registry?{query_string}",
                headers=auth_headers("dq:rules:read"),
            )

            assert response.status_code == 200, response.text
            payload = response.json()
            assert [row["id"] for row in payload["data"]] == expected_ids
    finally:
        app.dependency_overrides.clear()