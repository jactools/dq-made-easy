import asyncio

import pytest

from app.application.resolvers import resolve_rule_view
from app.application.use_cases import get_rule_details
from app.infrastructure.repositories import InMemoryRulesRepository

pytestmark = pytest.mark.usefixtures("clone_payload")


def test_resolve_rule_view_enriches_created_by_and_tags() -> None:
    repository = InMemoryRulesRepository()
    repository._rule_details["rule-email-format"]["reusable_join_id"] = "rj-1"
    repository._rule_details["rule-email-format"]["reusableFilterIds"] = ["rf-1", "rf-2"]
    repository._rule_details["rule-email-format"]["workspace"] = "retail-banking"
    repository._rule_details["rule-email-format"]["check_type"] = "REGEX"
    repository._rule_details["rule-email-format"]["taxonomy"] = {
        "owner": "user-admin",
        "data_steward": "user-admin",
        "domain_owner": "domain-owner@example.com",
        "technical_owner": "tech-owner@example.com",
    }
    repository._rule_details["rule-email-format"]["dsl"] = {
        "schema_version": "2.0.0",
        "rule": {
            "kind": "metric_threshold",
            "scope": {"dataset": {"data_product_id": "odcs.retail-banking.customer"}},
            "measure": {"type": "metric", "metric": "missing_percent", "subject": {"column": "email"}},
            "expectation": {"type": "threshold", "operator": "lte", "value": 0.0, "unit": "percent"},
            "evidence": {
                "failed_rows": {"mode": "sample", "limit": 10, "include_row_identifier": True, "include_primary_key": True},
                "emit_compiled_artifact": True,
                "emit_generated_sql": False,
            },
            "operations": {"severity": "critical", "preferred_engines": ["gx", "sql"], "fail_if_not_native": False},
        },
    }
    entity = asyncio.run(get_rule_details("rule-email-format", repository))

    view = asyncio.run(resolve_rule_view(entity, repository))

    assert view.id == "rule-email-format"
    assert view.created_by is not None
    assert view.created_by.username == "admin"
    assert [tag.name for tag in view.tags] == ["PII", "Contact"]
    assert view.reusableJoinId == "rj-1"
    assert view.reusableFilterIds == ["rf-1", "rf-2"]
    assert view.taxonomy.type == "REGEX"
    assert view.taxonomy.severity == "critical"
    assert view.taxonomy.domain == "odcs.retail-banking.customer"
    assert view.taxonomy.owner == "user-admin"
    assert view.taxonomy.dataSteward == "user-admin"
    assert view.taxonomy.domainOwner == "domain-owner@example.com"
    assert view.taxonomy.technicalOwner == "tech-owner@example.com"
    assert view.taxonomy.sla_scope == "dataset"
    assert view.taxonomy.execution_target == "gx"
