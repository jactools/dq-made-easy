import asyncio

from app.application.use_cases.rule_registry import RuleRegistryQuery
from app.application.use_cases.rule_registry import list_rule_registry
from app.domain.entities import build_rule_record_entity


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


def test_rule_registry_filters_and_exposes_discovery_facets() -> None:
    payload = asyncio.run(
        list_rule_registry(
            request=RuleRegistryQuery(
                page=1,
                limit=20,
                owner="alice@example.com",
                domain="odcs.retail.customer",
                severity="critical",
                execution_target="gx",
                rule_type="REGEX",
            ),
            repository=_RulesRepository(),
            approvals_repository=_ApprovalsRepository(),
        )
    )

    assert [row["id"] for row in payload["data"]] == ["rule-owned"]
    assert payload["discovery"] == {
        "workspaces": ["retail-banking"],
        "statuses": [payload["data"][0]["status"]],
        "lifecycle_statuses": [payload["data"][0]["lifecycle_status"]],
        "owners": ["alice@example.com"],
        "data_stewards": ["alice@example.com"],
        "domain_owners": ["domain-owner@example.com"],
        "technical_owners": ["tech-owner@example.com"],
        "domains": ["odcs.retail.customer"],
        "execution_targets": ["gx"],
        "rule_types": ["REGEX"],
        "dimensions": ["Validity"],
    }