import asyncio
from types import SimpleNamespace

from app.application.use_cases.list_rules import list_rules, ListRulesQuery
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
                    "created_by": "alice-team@example.com",
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


def test_list_rules_exposes_taxonomy_and_uses_exact_owner_filter() -> None:
    payload = asyncio.run(
        list_rules(
            request=ListRulesQuery(page=1, limit=20, owner="alice@example.com"),
            repository=_RulesRepository(),
            approvals_repository=_ApprovalsRepository(),
        )
    )

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