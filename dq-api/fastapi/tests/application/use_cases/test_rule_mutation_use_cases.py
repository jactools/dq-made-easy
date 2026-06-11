import json
import asyncio
import importlib
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import HTTPException

from app.application.use_cases.create_rule import create_rule
from app.application.use_cases.rule_mutation import resolve_rule_mutation_payload, RuleMutationCommand
from app.application.use_cases.update_rule import update_rule
from app.domain.entities import build_rule_record_entity


create_rule_module = importlib.import_module("app.application.use_cases.create_rule")
update_rule_module = importlib.import_module("app.application.use_cases.update_rule")
rule_mutation_module = importlib.import_module("app.application.use_cases.rule_mutation")


pytestmark = pytest.mark.usefixtures("clone_payload")

SUPPORTED_CASES_FILE = (
    Path(__file__).resolve().parents[5]
    / "validation-data"
    / "validate_rule_lifecycle_gx_supported_cases.json"
)


def _run(coro):
    return asyncio.run(coro)


def _app_config_repository(*, rule_dsl_v2_enabled: bool = True):
    return SimpleNamespace(
        get_app_config=lambda: SimpleNamespace(
            featureRuleDslV2=rule_dsl_v2_enabled,
            defaultRuleThresholdPct=0.0,
            openMetadataContractCacheTtlSeconds=300,
        )
    )


def _filter_expression_dsl(expression: str = "email IS NOT NULL") -> dict:
    return {
        "schemaVersion": "1.0.0",
        "source": {
            "kind": "filter_expression",
            "expression": expression,
        },
    }


def _semantic_v2_metric_threshold_dsl(
    *,
    include_row_filter: bool = False,
    operator: str = "lte",
    value: float = 0.1,
    reusable_join_id: str | None = None,
    reusable_filter_ids: list[str] | None = None,
    preferred_engines: list[str] | None = None,
) -> dict:
    scope: dict[str, object] = {
        "dataset": {
            "data_object_id": "do-customer",
        }
    }
    if include_row_filter:
        scope["row_filter"] = {
            "kind": "row_predicate",
            "language": "dq_predicate",
            "expression": "country = 'NL'",
        }

    return {
        "schema_version": "2.0.0",
        "rule": {
            "kind": "metric_threshold",
            "scope": scope,
            "measure": {
                "type": "metric",
                "metric": "missing_percent",
                "subject": {
                    "column": "email",
                },
            },
            "expectation": {
                "type": "threshold",
                "operator": operator,
                "value": value,
                "unit": "percent",
            },
            "evidence": {
                "failed_rows": {
                    "mode": "sample",
                    "limit": 25,
                    "include_row_identifier": True,
                    "include_primary_key": True,
                },
                "emit_compiled_artifact": True,
                "emit_generated_sql": False,
            },
            "operations": {
                "severity": "critical",
                "preferred_engines": preferred_engines or ["gx", "sql"],
                "fail_if_not_native": False,
            },
            "reusable_join_id": reusable_join_id,
            "reusable_filter_ids": reusable_filter_ids or [],
        },
    }


def _semantic_v2_aggregate_metric_threshold_dsl(
    *,
    metric: str,
    operator: str = "gte",
    value: float | int | None = 1,
    min_value: float | int | None = None,
    max_value: float | int | None = None,
) -> dict:
    expectation: dict[str, object] = {
        "type": "threshold",
        "operator": operator,
    }
    if operator == "between":
        expectation["min_value"] = min_value
        expectation["max_value"] = max_value
        expectation["unit"] = "raw" if metric != "distinct_count" else "count"
    else:
        expectation["value"] = value
        expectation["unit"] = "raw" if metric != "distinct_count" else "count"

    return {
        "schema_version": "2.0.0",
        "rule": {
            "kind": "metric_threshold",
            "scope": {
                "dataset": {
                    "data_object_id": "do-customer",
                },
            },
            "measure": {
                "type": "metric",
                "metric": metric,
                "subject": {
                    "column": "amount",
                },
            },
            "expectation": expectation,
            "evidence": {
                "failed_rows": {
                    "mode": "sample",
                    "limit": 25,
                    "include_row_identifier": True,
                    "include_primary_key": True,
                },
                "emit_compiled_artifact": True,
                "emit_generated_sql": False,
            },
            "operations": {
                "severity": "critical",
                "preferred_engines": ["gx", "sql"],
                "fail_if_not_native": False,
            },
        },
    }


def _semantic_v2_row_assertion_dsl() -> dict:
    return {
        "schema_version": "2.0.0",
        "rule": {
            "kind": "row_assertion",
            "scope": {
                "dataset": {
                    "data_object_id": "do-customer",
                },
                "row_filter": {
                    "kind": "row_predicate",
                    "language": "dq_predicate",
                    "expression": "country = 'NL'",
                },
            },
            "measure": {
                "type": "row_predicate",
                "predicate": {
                    "kind": "row_predicate",
                    "language": "dq_predicate",
                    "expression": "email IS NOT NULL",
                },
            },
            "expectation": {
                "type": "threshold",
                "operator": "gte",
                "value": 100,
                "unit": "percent",
            },
            "evidence": {
                "failed_rows": {
                    "mode": "sample",
                    "limit": 25,
                    "include_row_identifier": True,
                    "include_primary_key": True,
                },
                "emit_compiled_artifact": True,
                "emit_generated_sql": False,
            },
            "operations": {
                "severity": "critical",
                "preferred_engines": ["gx", "sql"],
                "fail_if_not_native": False,
            },
        },
    }


def _semantic_v2_required_columns_schema_assertion_dsl(*, fail_if_not_native: bool = False) -> dict:
    return {
        "schema_version": "2.0.0",
        "rule": {
            "kind": "schema_assertion",
            "scope": {
                "dataset": {
                    "data_object_id": "do-customer",
                },
            },
            "measure": {
                "type": "schema",
                "schema_assertion": "required_columns_present",
            },
            "expectation": {
                "type": "schema_contract",
                "required_columns": ["customer_id", "email"],
            },
            "evidence": {
                "failed_rows": {
                    "mode": "sample",
                    "limit": 25,
                    "include_row_identifier": True,
                    "include_primary_key": True,
                },
                "emit_compiled_artifact": True,
                "emit_generated_sql": False,
            },
            "operations": {
                "severity": "critical",
                "preferred_engines": ["gx", "sql"],
                "fail_if_not_native": fail_if_not_native,
            },
        },
    }


def _semantic_v2_freshness_assertion_dsl(*, value: str = "P3D", operator: str = "lte") -> dict:
    return {
        "schema_version": "2.0.0",
        "rule": {
            "kind": "freshness_assertion",
            "scope": {
                "dataset": {
                    "data_object_id": "do-customer",
                }
            },
            "measure": {
                "type": "metric",
                "metric": "freshness_age",
                "subject": {
                    "column": "published_at",
                },
            },
            "expectation": {
                "type": "threshold",
                "operator": operator,
                "value": value,
                "unit": "duration",
            },
            "evidence": {
                "failed_rows": {
                    "mode": "sample",
                    "limit": 25,
                    "include_row_identifier": True,
                    "include_primary_key": True,
                },
                "emit_compiled_artifact": True,
                "emit_generated_sql": False,
            },
            "operations": {
                "severity": "critical",
                "preferred_engines": ["gx", "sql"],
                "fail_if_not_native": False,
            },
        },
    }


def _semantic_v2_reference_assertion_dsl() -> dict:
    return {
        "schema_version": "2.0.0",
        "rule": {
            "kind": "reference_assertion",
            "scope": {
                "comparison": {
                    "left": {
                        "data_object_version_id": "dov-customer-v5",
                    },
                    "right": {
                        "data_object_id": "do-reference-customer",
                        "data_object_version_id": "dov-reference-customer-v2",
                    },
                    "join_keys": [
                        {
                            "left_column": "customer_id",
                            "right_column": "customer_id",
                        }
                    ],
                }
            },
            "measure": {
                "type": "metric",
                "metric": "match_percent",
                "subject": {
                    "column": "customer_id",
                },
            },
            "expectation": {
                "type": "threshold",
                "operator": "gte",
                "value": 100,
                "unit": "percent",
            },
            "evidence": {
                "failed_rows": {
                    "mode": "sample",
                    "limit": 25,
                    "include_row_identifier": True,
                    "include_primary_key": True,
                },
                "emit_compiled_artifact": True,
                "emit_generated_sql": False,
            },
            "operations": {
                "severity": "critical",
                "preferred_engines": ["gx", "sql"],
                "fail_if_not_native": False,
            },
        },
    }


def _semantic_v2_duplicate_percent_dsl(*, include_row_filter: bool = False) -> dict:
    scope: dict[str, object] = {
        "dataset": {
            "data_object_id": "do-customer",
        }
    }
    if include_row_filter:
        scope["row_filter"] = {
            "kind": "row_predicate",
            "language": "dq_predicate",
            "expression": "country = 'NL'",
        }

    return {
        "schema_version": "2.0.0",
        "rule": {
            "kind": "metric_threshold",
            "scope": scope,
            "measure": {
                "type": "metric",
                "metric": "duplicate_percent",
                "subject": {
                    "columns": ["customer_id", "order_date"],
                },
            },
            "expectation": {
                "type": "threshold",
                "operator": "lte",
                "value": 0,
                "unit": "percent",
            },
            "evidence": {
                "failed_rows": {
                    "mode": "sample",
                    "limit": 25,
                    "include_row_identifier": True,
                    "include_primary_key": True,
                },
                "emit_compiled_artifact": True,
                "emit_generated_sql": False,
            },
            "operations": {
                "severity": "critical",
                "preferred_engines": ["gx", "sql"],
                "fail_if_not_native": False,
            },
        },
    }


def _semantic_v2_missing_count_dsl(*, value: float = 0, operator: str = "lte") -> dict:
    return {
        "schema_version": "2.0.0",
        "rule": {
            "kind": "metric_threshold",
            "scope": {
                "dataset": {
                    "data_object_id": "do-customer",
                }
            },
            "measure": {
                "type": "metric",
                "metric": "missing_count",
                "subject": {
                    "column": "email",
                },
            },
            "expectation": {
                "type": "threshold",
                "operator": operator,
                "value": value,
                "unit": "count",
            },
            "evidence": {
                "failed_rows": {
                    "mode": "sample",
                    "limit": 25,
                    "include_row_identifier": True,
                    "include_primary_key": True,
                },
                "emit_compiled_artifact": True,
                "emit_generated_sql": False,
            },
            "operations": {
                "severity": "critical",
                "preferred_engines": ["gx", "sql"],
                "fail_if_not_native": False,
            },
        },
    }


def _semantic_v2_duplicate_count_dsl(*, value: float = 0, operator: str = "lte") -> dict:
    return {
        "schema_version": "2.0.0",
        "rule": {
            "kind": "metric_threshold",
            "scope": {
                "dataset": {
                    "data_object_id": "do-customer",
                }
            },
            "measure": {
                "type": "metric",
                "metric": "duplicate_count",
                "subject": {
                    "columns": ["customer_id", "order_date"],
                },
            },
            "expectation": {
                "type": "threshold",
                "operator": operator,
                "value": value,
                "unit": "count",
            },
            "evidence": {
                "failed_rows": {
                    "mode": "sample",
                    "limit": 25,
                    "include_row_identifier": True,
                    "include_primary_key": True,
                },
                "emit_compiled_artifact": True,
                "emit_generated_sql": False,
            },
            "operations": {
                "severity": "critical",
                "preferred_engines": ["gx", "sql"],
                "fail_if_not_native": False,
            },
        },
    }


def _semantic_v2_row_count_dsl(*, include_row_filter: bool = False, operator: str = "gte", value: int = 25) -> dict:
    scope: dict[str, object] = {
        "dataset": {
            "data_object_id": "do-customer",
        }
    }
    if include_row_filter:
        scope["row_filter"] = {
            "kind": "row_predicate",
            "language": "dq_predicate",
            "expression": "country = 'NL'",
        }

    expectation: dict[str, object] = {
        "type": "threshold",
        "operator": operator,
        "unit": "count",
    }
    if operator == "between":
        expectation["minValue"] = value
        expectation["maxValue"] = value + 10
    else:
        expectation["value"] = value

    return {
        "schema_version": "2.0.0",
        "rule": {
            "kind": "metric_threshold",
            "scope": scope,
            "measure": {
                "type": "metric",
                "metric": "row_count",
            },
            "expectation": expectation,
            "evidence": {
                "failed_rows": {
                    "mode": "sample",
                    "limit": 25,
                    "include_row_identifier": True,
                    "include_primary_key": True,
                },
                "emit_compiled_artifact": True,
                "emit_generated_sql": False,
            },
            "operations": {
                "severity": "critical",
                "preferred_engines": ["gx", "sql"],
                "fail_if_not_native": False,
            },
        },
    }


@pytest.fixture
def mutation_command() -> RuleMutationCommand:
    return RuleMutationCommand(
        name="Email Rule",
        description="Checks email presence",
        dimension="completeness",
        workspace="default",
        generated=False,
        is_template=False,
        dsl=_filter_expression_dsl(),
    )


@pytest.fixture
def mutation_repository():
    class _Repository:
        def __init__(self) -> None:
            self.create_calls: list[dict] = []
            self.update_calls: list[dict] = []
            self.list_calls: list[dict] = []
            self.create_result = {"id": "rule-1", "workspace": "default"}
            self.update_result = {"id": "rule-1", "updated": True}
            self.create_error: Exception | None = None
            self.existing_rule: dict | None = {
                "id": "rule-1",
                "workspace": "default",
                "created_by": "user-admin",
                "taxonomy": {
                    "owner": "user-admin",
                },
                "last_approval_status": "draft",
                "active": False,
            }

        async def create_rule_record(self, **kwargs):
            self.create_calls.append(kwargs)
            if self.create_error is not None:
                raise self.create_error
            return build_rule_record_entity(self.create_result)

        async def list_rule_records(self, **kwargs):
            self.list_calls.append(kwargs)
            if self.existing_rule is None:
                return []
            return [build_rule_record_entity(self.existing_rule)]

        async def update_rule_record(self, **kwargs):
            self.update_calls.append(kwargs)
            return build_rule_record_entity(self.update_result)

    return _Repository()


@pytest.fixture(scope="module")
def gx_supported_case_catalog() -> dict[str, dict[str, Any]]:
    cases = json.loads(SUPPORTED_CASES_FILE.read_text(encoding="utf-8"))
    return {str(case["case_id"]): case for case in cases}


def test_create_rule_delegates_resolved_payload_and_actor(
    monkeypatch,
    mutation_command,
    mutation_repository,
) -> None:
    async def fake_resolve_rule_mutation_payload(**kwargs):
        assert kwargs["workspace_id"] == "default"
        assert kwargs["actor_id"] == "user-1"
        return {
            "name": kwargs["command"].name,
            "description": kwargs["command"].description,
            "expression": "compiled expression",
            "dimension": kwargs["command"].dimension,
            "active": False,
            "dsl": _filter_expression_dsl("compiled expression"),
            "join_conditions": [],
            "alias_mappings": {},
            "reusable_join_id": None,
            "reusable_filter_ids": [],
            "manual_override_by": None,
            "manual_override_at": None,
            "check_type": None,
            "check_type_params": None,
            "taxonomy": {
                "type": "filter_expression",
                "severity": None,
                "domain": "default",
                "owner": "user-1",
                "sla_scope": None,
                "execution_target": None,
            },
        }

    monkeypatch.setattr(create_rule_module, "resolve_rule_mutation_payload", fake_resolve_rule_mutation_payload)

    payload = _run(
        create_rule(
            mutation_command,
            mutation_repository,
            config_repository=object(),
            catalog_repository=object(),
            contract_resolver=object(),
            actor_id="user-1",
        )
    )

    assert payload["id"] == "rule-1"
    assert payload["workspace"] == "default"
    assert mutation_repository.create_calls == [
        {
            "name": "Email Rule",
            "description": "Checks email presence",
            "expression": "compiled expression",
            "dimension": "completeness",
            "active": False,
            "dsl": _filter_expression_dsl("compiled expression"),
            "join_conditions": [],
            "alias_mappings": {},
            "reusable_join_id": None,
            "reusable_filter_ids": [],
            "manual_override_by": None,
            "manual_override_at": None,
            "check_type": None,
            "check_type_params": None,
            "taxonomy": {
                "type": "filter_expression",
                "severity": None,
                "domain": "default",
                "owner": "user-1",
                "sla_scope": None,
                "execution_target": None,
            },
            "workspace": "default",
            "created_by": "user-1",
            "generated": False,
            "is_template": False,
            "template_id": None,
            "suggestion_id": None,
        }
    ]


@pytest.mark.parametrize(
    ("error", "status_code", "message_fragment"),
    [
        (ValueError("duplicate rule"), 409, "duplicate rule"),
        (RuntimeError("database unavailable"), 500, "database unavailable"),
    ],
)
def test_create_rule_maps_repository_failures_to_http_errors(
    monkeypatch,
    mutation_command,
    mutation_repository,
    error,
    status_code,
    message_fragment,
) -> None:
    async def fake_resolve_rule_mutation_payload(**kwargs):
        del kwargs
        return {
            "name": "Email Rule",
            "description": "Checks email presence",
            "expression": "compiled expression",
            "dimension": "completeness",
            "active": False,
            "dsl": _filter_expression_dsl("compiled expression"),
            "join_conditions": [],
            "alias_mappings": {},
            "reusable_join_id": None,
            "reusable_filter_ids": [],
            "manual_override_by": None,
            "manual_override_at": None,
            "check_type": None,
            "check_type_params": None,
        }

    monkeypatch.setattr(create_rule_module, "resolve_rule_mutation_payload", fake_resolve_rule_mutation_payload)
    mutation_repository.create_error = error

    with pytest.raises(HTTPException) as exc_info:
        _run(
            create_rule(
                mutation_command,
                mutation_repository,
                config_repository=object(),
                catalog_repository=object(),
                contract_resolver=object(),
                actor_id="user-1",
            )
        )

    assert exc_info.value.status_code == status_code
    assert message_fragment in str(exc_info.value.detail)


def test_create_rule_persists_v2_when_explicitly_opted_in(mutation_repository) -> None:
    command = RuleMutationCommand(
        name="Semantic Email Rule",
        description="Checks missing percent for email",
        dimension="completeness",
        workspace="default",
        generated=False,
        is_template=False,
        dsl=_semantic_v2_metric_threshold_dsl(reusable_join_id="rj-1", reusable_filter_ids=["rf-1", "rf-2"]),
    )

    payload = _run(
        create_rule(
            command,
            mutation_repository,
            config_repository=_app_config_repository(rule_dsl_v2_enabled=True),
            catalog_repository=object(),
            contract_resolver=object(),
            actor_id="user-1",
        )
    )

    assert payload["id"] == "rule-1"
    assert mutation_repository.create_calls[0]["workspace"] == "default"
    assert mutation_repository.create_calls[0]["created_by"] == "user-1"
    assert mutation_repository.create_calls[0]["dsl"]["schema_version"] == "2.0.0"
    assert mutation_repository.create_calls[0]["dsl"]["rule"]["kind"] == "metric_threshold"
    assert mutation_repository.create_calls[0]["reusable_join_id"] == "rj-1"
    assert mutation_repository.create_calls[0]["reusable_filter_ids"] == ["rf-1", "rf-2"]
    assert mutation_repository.create_calls[0]["check_type"] == "THRESHOLD"
    assert mutation_repository.create_calls[0]["taxonomy"] == {
        "type": "THRESHOLD",
        "severity": "critical",
        "domain": "default",
        "owner": "user-1",
        "data_steward": "user-1",
        "sla_scope": "dataset",
        "execution_target": "gx",
    }


def test_resolve_rule_mutation_payload_preserves_v2_reusable_assets(mutation_repository) -> None:
    command = RuleMutationCommand(
        name="Semantic Email Rule",
        description="Checks missing percent for email",
        dimension="completeness",
        workspace="default",
        generated=False,
        is_template=False,
        dsl=_semantic_v2_metric_threshold_dsl(reusable_join_id="rj-1", reusable_filter_ids=["rf-1", "rf-2"]),
    )

    payload = _run(
        resolve_rule_mutation_payload(
            command=command,
            repository=mutation_repository,
            config_repository=_app_config_repository(rule_dsl_v2_enabled=True),
            catalog_repository=object(),
            contract_resolver=object(),
            actor_id="user-1",
            workspace_id="default",
        )
    )

    assert payload["reusable_join_id"] == "rj-1"
    assert payload["reusable_filter_ids"] == ["rf-1", "rf-2"]
    assert payload["dsl"]["rule"]["reusable_join_id"] == "rj-1"
    assert payload["dsl"]["rule"]["reusable_filter_ids"] == ["rf-1", "rf-2"]


def test_resolve_rule_mutation_payload_merges_explicit_taxonomy_owner_with_derived_fields(mutation_repository) -> None:
    command = RuleMutationCommand(
        name="Semantic Email Rule",
        description="Checks missing percent for email",
        dimension="completeness",
        workspace="default",
        generated=False,
        is_template=False,
        taxonomy={"owner": "data-steward@example.com"},
        dsl=_semantic_v2_metric_threshold_dsl(),
    )

    payload = _run(
        resolve_rule_mutation_payload(
            command=command,
            repository=mutation_repository,
            config_repository=_app_config_repository(rule_dsl_v2_enabled=True),
            catalog_repository=object(),
            contract_resolver=object(),
            actor_id="user-1",
            workspace_id="default",
            owner_fallback="creator@example.com",
        )
    )

    assert payload["taxonomy"] == {
        "type": "THRESHOLD",
        "severity": "critical",
        "domain": "default",
        "owner": "data-steward@example.com",
        "data_steward": "data-steward@example.com",
        "sla_scope": "dataset",
        "execution_target": "gx",
    }


def test_resolve_rule_mutation_payload_preserves_explicit_ownership_roles(mutation_repository) -> None:
    command = RuleMutationCommand(
        name="Semantic Email Rule",
        description="Checks missing percent for email",
        dimension="completeness",
        workspace="default",
        generated=False,
        is_template=False,
        taxonomy={
            "data_steward": "data-steward@example.com",
            "domain_owner": "domain-owner@example.com",
            "technical_owner": "tech-owner@example.com",
        },
        dsl=_semantic_v2_metric_threshold_dsl(),
    )

    payload = _run(
        resolve_rule_mutation_payload(
            command=command,
            repository=mutation_repository,
            config_repository=_app_config_repository(rule_dsl_v2_enabled=True),
            catalog_repository=object(),
            contract_resolver=object(),
            actor_id="user-1",
            workspace_id="default",
        )
    )

    assert payload["taxonomy"] == {
        "type": "THRESHOLD",
        "severity": "critical",
        "domain": "default",
        "owner": "data-steward@example.com",
        "data_steward": "data-steward@example.com",
        "domain_owner": "domain-owner@example.com",
        "technical_owner": "tech-owner@example.com",
        "sla_scope": "dataset",
        "execution_target": "gx",
    }


def test_create_rule_rejects_v2_without_opt_in_before_persistence(mutation_repository) -> None:
    command = RuleMutationCommand(
        name="Semantic Email Rule",
        description="Checks missing percent for email",
        dimension="completeness",
        workspace="default",
        generated=False,
        is_template=False,
        dsl=_semantic_v2_metric_threshold_dsl(),
    )

    with pytest.raises(HTTPException) as exc_info:
        _run(
            create_rule(
                command,
                mutation_repository,
                config_repository=_app_config_repository(rule_dsl_v2_enabled=False),
                catalog_repository=object(),
                contract_resolver=object(),
                actor_id="user-1",
            )
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["error"] == "rule_dsl_v2_not_enabled"
    assert mutation_repository.create_calls == []


def test_create_rule_rejects_ai_output_before_validation_or_persistence(mutation_repository) -> None:
    command = RuleMutationCommand(
        name="Assistant Draft Rule",
        description="AI output must remain read-only",
        dimension="completeness",
        workspace="default",
        generated=False,
        is_template=False,
        ai_output=True,
        dsl=_filter_expression_dsl(),
    )

    with pytest.raises(HTTPException) as exc_info:
        _run(
            create_rule(
                command,
                mutation_repository,
                config_repository=_app_config_repository(),
                catalog_repository=object(),
                contract_resolver=object(),
                actor_id="user-1",
            )
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == {
        "error": "ai_output_mutation_blocked",
        "message": "AI assistant output is read-only and cannot create, update, or persist rule contracts.",
        "field": "ai_output",
    }
    assert mutation_repository.list_calls == []
    assert mutation_repository.create_calls == []


def test_update_rule_rejects_approved_or_active_versions(mutation_command, mutation_repository) -> None:
    mutation_repository.existing_rule = {
        "id": "rule-1",
        "workspace": "default",
        "last_approval_status": "approved",
        "active": False,
    }

    with pytest.raises(HTTPException) as exc_info:
        _run(
            update_rule(
                "rule-1",
                mutation_command,
                mutation_repository,
                config_repository=object(),
                catalog_repository=object(),
                contract_resolver=object(),
                actor_id="user-1",
            )
        )

    assert exc_info.value.status_code == 409
    assert "can no longer be changed" in str(exc_info.value.detail)


def test_update_rule_uses_existing_workspace_and_exclude_rule_id(
    monkeypatch,
    mutation_command,
    mutation_repository,
) -> None:
    seen: dict[str, object] = {}
    command = RuleMutationCommand(
        name=mutation_command.name,
        description=mutation_command.description,
        dimension=mutation_command.dimension,
        generated=mutation_command.generated,
        dsl=mutation_command.dsl,
    )

    async def fake_resolve_rule_mutation_payload(**kwargs):
        seen.update({
            "workspace_id": kwargs["workspace_id"],
            "exclude_rule_id": kwargs["exclude_rule_id"],
            "actor_id": kwargs["actor_id"],
            "owner_fallback": kwargs["owner_fallback"],
            "existing_taxonomy": kwargs["existing_taxonomy"],
        })
        return {
            "name": kwargs["command"].name,
            "description": kwargs["command"].description,
            "expression": "compiled expression",
            "dimension": kwargs["command"].dimension,
            "active": False,
            "dsl": _filter_expression_dsl("compiled expression"),
            "join_conditions": [],
            "alias_mappings": {},
            "reusable_join_id": None,
            "reusable_filter_ids": [],
            "manual_override_by": None,
            "manual_override_at": None,
            "check_type": None,
            "check_type_params": None,
            "taxonomy": {
                "type": "filter_expression",
                "severity": None,
                "domain": "default",
                "owner": "user-admin",
                "sla_scope": None,
                "execution_target": None,
            },
        }

    monkeypatch.setattr(update_rule_module, "resolve_rule_mutation_payload", fake_resolve_rule_mutation_payload)

    payload = _run(
        update_rule(
            "rule-1",
            command,
            mutation_repository,
            config_repository=object(),
            catalog_repository=object(),
            contract_resolver=object(),
            actor_id="user-1",
        )
    )

    assert payload["id"] == "rule-1"
    assert seen == {
        "workspace_id": "default",
        "exclude_rule_id": "rule-1",
        "actor_id": "user-1",
        "owner_fallback": "user-admin",
        "existing_taxonomy": {
            "domain": "default",
            "owner": "user-admin",
            "data_steward": "user-admin",
        },
    }
    assert mutation_repository.update_calls == [
        {
            "rule_id": "rule-1",
            "name": "Email Rule",
            "description": "Checks email presence",
            "expression": "compiled expression",
            "dimension": "completeness",
            "active": False,
            "dsl": _filter_expression_dsl("compiled expression"),
            "join_conditions": [],
            "alias_mappings": {},
            "reusable_join_id": None,
            "reusable_filter_ids": [],
            "manual_override_by": None,
            "manual_override_at": None,
            "check_type": None,
            "check_type_params": None,
            "taxonomy": {
                "type": "filter_expression",
                "severity": None,
                "domain": "default",
                "owner": "user-admin",
                "sla_scope": None,
                "execution_target": None,
            },
        }
    ]


def test_update_rule_rejects_ai_output_before_persistence(mutation_repository, mutation_command) -> None:
    command = RuleMutationCommand(
        name=mutation_command.name,
        description=mutation_command.description,
        dimension=mutation_command.dimension,
        workspace=mutation_command.workspace,
        generated=mutation_command.generated,
        is_template=mutation_command.is_template,
        ai_output=True,
        dsl=mutation_command.dsl,
    )

    with pytest.raises(HTTPException) as exc_info:
        _run(
            update_rule(
                "rule-1",
                command,
                mutation_repository,
                config_repository=_app_config_repository(),
                catalog_repository=object(),
                contract_resolver=object(),
                actor_id="user-1",
            )
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["error"] == "ai_output_mutation_blocked"
    assert mutation_repository.update_calls == []


def test_resolve_rule_mutation_payload_rejects_v2_without_opt_in(mutation_repository) -> None:
    command = RuleMutationCommand(
        name="Semantic Email Rule",
        description="Checks missing percent for email",
        dimension="completeness",
        workspace="default",
        generated=False,
        is_template=False,
        dsl=_semantic_v2_metric_threshold_dsl(),
    )

    with pytest.raises(HTTPException) as exc_info:
        _run(
            resolve_rule_mutation_payload(
                command=command,
                repository=mutation_repository,
                config_repository=_app_config_repository(rule_dsl_v2_enabled=False),
                catalog_repository=object(),
                contract_resolver=object(),
                actor_id="user-1",
                workspace_id="default",
            )
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == {
        "error": "rule_dsl_v2_not_enabled",
        "message": "DQ DSL 2.0.0 payloads require explicit feature_rule_dsl_v2 opt-in.",
        "schema_version": "2.0.0",
        "config_key": "feature_rule_dsl_v2",
    }


def test_resolve_rule_mutation_payload_rejects_v2_with_legacy_source_before_opt_in(
    mutation_repository,
) -> None:
    mixed_dsl = _semantic_v2_metric_threshold_dsl()
    mixed_dsl["source"] = _filter_expression_dsl()["source"]
    command = RuleMutationCommand(
        name="Mixed Semantic Email Rule",
        description="Mixes semantic and source contracts",
        dimension="completeness",
        workspace="default",
        generated=False,
        is_template=False,
        dsl=mixed_dsl,
    )

    with pytest.raises(HTTPException) as exc_info:
        _run(
            resolve_rule_mutation_payload(
                command=command,
                repository=mutation_repository,
                config_repository=_app_config_repository(rule_dsl_v2_enabled=False),
                catalog_repository=object(),
                contract_resolver=object(),
                actor_id="user-1",
                workspace_id="default",
            )
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == {
        "error": "mixed_rule_dsl_contract",
        "message": "DQ DSL payload must use exactly one schema-version contract without embedded compatibility fields.",
        "schema_version": "2.0.0",
        "fields": ["dsl.source"],
    }


def test_resolve_rule_mutation_payload_rejects_v1_with_semantic_rule(mutation_repository) -> None:
    mixed_dsl = _filter_expression_dsl()
    mixed_dsl["rule"] = _semantic_v2_metric_threshold_dsl()["rule"]
    command = RuleMutationCommand(
        name="Mixed Source Email Rule",
        description="Mixes source and semantic contracts",
        dimension="completeness",
        workspace="default",
        generated=False,
        is_template=False,
        dsl=mixed_dsl,
    )

    with pytest.raises(HTTPException) as exc_info:
        _run(
            resolve_rule_mutation_payload(
                command=command,
                repository=mutation_repository,
                config_repository=object(),
                catalog_repository=object(),
                contract_resolver=object(),
                actor_id="user-1",
                workspace_id="default",
            )
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["error"] == "mixed_rule_dsl_contract"
    assert exc_info.value.detail["schema_version"] == "1.0.0"
    assert exc_info.value.detail["fields"] == ["dsl.rule"]


def test_resolve_rule_mutation_payload_rejects_top_level_runtime_fields(mutation_repository) -> None:
    mixed_dsl = _semantic_v2_metric_threshold_dsl()
    mixed_dsl["check_type"] = "THRESHOLD"
    mixed_dsl["filter_expression"] = "email IS NOT NULL"
    command = RuleMutationCommand(
        name="Runtime Field Semantic Rule",
        description="Embeds runtime fields in the DSL contract",
        dimension="completeness",
        workspace="default",
        generated=False,
        is_template=False,
        dsl=mixed_dsl,
    )

    with pytest.raises(HTTPException) as exc_info:
        _run(
            resolve_rule_mutation_payload(
                command=command,
                repository=mutation_repository,
                config_repository=_app_config_repository(),
                catalog_repository=object(),
                contract_resolver=object(),
                actor_id="user-1",
                workspace_id="default",
            )
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["error"] == "mixed_rule_dsl_contract"
    assert exc_info.value.detail["schema_version"] == "2.0.0"
    assert exc_info.value.detail["fields"] == ["dsl.check_type", "dsl.filter_expression"]


def test_resolve_rule_mutation_payload_lowers_v2_metric_threshold(mutation_repository) -> None:
    command = RuleMutationCommand(
        name="Semantic Email Rule",
        description="Checks missing percent for email",
        dimension="completeness",
        workspace="default",
        generated=False,
        is_template=False,
        dsl=_semantic_v2_metric_threshold_dsl(),
    )

    payload = _run(
        resolve_rule_mutation_payload(
            command=command,
            repository=mutation_repository,
            config_repository=_app_config_repository(),
            catalog_repository=object(),
            contract_resolver=object(),
            actor_id="user-1",
            workspace_id="default",
        )
    )

    assert payload["expression"] == "email IS NOT NULL"
    assert payload["check_type"] == "THRESHOLD"
    assert payload["check_type_params"] == {
        "checkType": "THRESHOLD",
        "attribute": "email",
        "metric": "null_pct",
        "operator": "gte",
        "quantile": None,
        "threshold": 99.9,
    }
    assert payload["dsl"]["schema_version"] == "2.0.0"
    assert payload["dsl"]["rule"]["kind"] == "metric_threshold"


def test_resolve_rule_mutation_payload_routes_v2_metric_threshold_through_sodacl_lowerer(
    mutation_repository,
    monkeypatch,
) -> None:
    lowerer_calls: list[str] = []

    def fake_build_sodacl_checks_from_rule_dsl_v2(*, semantic_ir, rule_id=None, artifact_key=None):
        del rule_id, artifact_key
        lowerer_calls.append(semantic_ir.rule.kind)
        return [{"check": "row_count"}]

    monkeypatch.setattr(rule_mutation_module, "build_sodacl_checks_from_rule_dsl_v2", fake_build_sodacl_checks_from_rule_dsl_v2)

    command = RuleMutationCommand(
        name="Semantic SodaCL Rule",
        description="Checks missing percent for email using SodaCL",
        dimension="completeness",
        workspace="default",
        generated=False,
        is_template=False,
        dsl=_semantic_v2_metric_threshold_dsl(preferred_engines=["sodacl", "gx"]),
    )

    payload = _run(
        resolve_rule_mutation_payload(
            command=command,
            repository=mutation_repository,
            config_repository=_app_config_repository(),
            catalog_repository=object(),
            contract_resolver=object(),
            actor_id="user-1",
            workspace_id="default",
        )
    )

    assert lowerer_calls == ["metric_threshold"]
    assert payload["expression"] == "email IS NOT NULL"
    assert payload["check_type"] == "THRESHOLD"
    assert payload["check_type_params"]["metric"] == "null_pct"


def test_resolve_rule_mutation_payload_lowers_v2_aggregate_metric_threshold(mutation_repository) -> None:
    command = RuleMutationCommand(
        name="Semantic Aggregate Metric Rule",
        description="Checks average amount",
        dimension="quality",
        workspace="default",
        generated=False,
        is_template=False,
        dsl=_semantic_v2_aggregate_metric_threshold_dsl(metric="avg", operator="gte", value=10.5),
    )

    payload = _run(
        resolve_rule_mutation_payload(
            command=command,
            repository=mutation_repository,
            config_repository=_app_config_repository(),
            catalog_repository=object(),
            contract_resolver=object(),
            actor_id="user-1",
            workspace_id="default",
        )
    )

    assert payload["expression"] == ""
    assert payload["check_type"] is None
    assert payload["check_type_params"] is None
    assert payload["dsl"]["rule"]["measure"]["metric"] == "avg"


@pytest.mark.parametrize(
    ("operator", "value", "expected_operator", "expected_threshold"),
    [
        ("lte", 0.1, "gte", 99.9),
        ("lt", 5.0, "gt", 95.0),
        ("gte", 40.0, "lte", 60.0),
        ("gt", 20.0, "lt", 80.0),
    ],
)
def test_resolve_rule_mutation_payload_metric_threshold_inverts_missing_percent_bounds(
    mutation_repository,
    operator,
    value,
    expected_operator,
    expected_threshold,
) -> None:
    command = RuleMutationCommand(
        name=f"Semantic Email Rule {operator}",
        description="Checks missing percent for email",
        dimension="completeness",
        workspace="default",
        generated=False,
        is_template=False,
        dsl=_semantic_v2_metric_threshold_dsl(operator=operator, value=value),
    )

    payload = _run(
        resolve_rule_mutation_payload(
            command=command,
            repository=mutation_repository,
            config_repository=_app_config_repository(),
            catalog_repository=object(),
            contract_resolver=object(),
            actor_id="user-1",
            workspace_id="default",
        )
    )

    assert payload["check_type"] == "THRESHOLD"
    assert payload["check_type_params"]["metric"] == "null_pct"
    assert payload["check_type_params"]["operator"] == expected_operator
    assert payload["check_type_params"]["threshold"] == expected_threshold


def test_resolve_rule_mutation_payload_lowers_v2_row_assertion(mutation_repository) -> None:
    command = RuleMutationCommand(
        name="Semantic Row Assertion",
        description="Checks NL rows have email",
        dimension="completeness",
        workspace="default",
        generated=False,
        is_template=False,
        dsl=_semantic_v2_row_assertion_dsl(),
    )

    payload = _run(
        resolve_rule_mutation_payload(
            command=command,
            repository=mutation_repository,
            config_repository=_app_config_repository(),
            catalog_repository=object(),
            contract_resolver=object(),
            actor_id="user-1",
            workspace_id="default",
        )
    )

    assert payload["expression"] == "NOT (country = 'NL') OR (email IS NOT NULL)"
    assert payload["check_type"] is None
    assert payload["check_type_params"] is None
    assert payload["dsl"]["schema_version"] == "2.0.0"
    assert payload["dsl"]["rule"]["kind"] == "row_assertion"


def test_resolve_rule_mutation_payload_rejects_v2_metric_threshold_with_row_filter(mutation_repository) -> None:
    command = RuleMutationCommand(
        name="Scoped Semantic Email Rule",
        description="Checks missing percent for NL email rows",
        dimension="completeness",
        workspace="default",
        generated=False,
        is_template=False,
        dsl=_semantic_v2_metric_threshold_dsl(include_row_filter=True),
    )

    with pytest.raises(HTTPException) as exc_info:
        _run(
            resolve_rule_mutation_payload(
                command=command,
                repository=mutation_repository,
                config_repository=_app_config_repository(),
                catalog_repository=object(),
                contract_resolver=object(),
                actor_id="user-1",
                workspace_id="default",
            )
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["error"] == "rule_dsl_lowering_unsupported"
    assert exc_info.value.detail["schema_version"] == "2.0.0"
    assert exc_info.value.detail["rule_kind"] == "metric_threshold"
    assert "scope.row_filter" in exc_info.value.detail["message"]


def test_resolve_rule_mutation_payload_rejects_v2_schema_assertion_when_native_required(mutation_repository) -> None:
    command = RuleMutationCommand(
        name="Semantic Schema Rule",
        description="Checks required columns",
        dimension="schema",
        workspace="default",
        generated=False,
        is_template=False,
        dsl=_semantic_v2_required_columns_schema_assertion_dsl(fail_if_not_native=True),
    )

    with pytest.raises(HTTPException) as exc_info:
        _run(
            resolve_rule_mutation_payload(
                command=command,
                repository=mutation_repository,
                config_repository=_app_config_repository(),
                catalog_repository=object(),
                contract_resolver=object(),
                actor_id="user-1",
                workspace_id="default",
            )
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["error"] == "rule_dsl_lowering_unsupported"
    assert exc_info.value.detail["rule_kind"] == "schema_assertion"
    assert "fail_if_not_native" in exc_info.value.detail["message"]


def test_resolve_rule_mutation_payload_lowers_v2_freshness_assertion(mutation_repository) -> None:
    command = RuleMutationCommand(
        name="Semantic Freshness Rule",
        description="Checks freshness for published_at",
        dimension="timeliness",
        workspace="default",
        generated=False,
        is_template=False,
        dsl=_semantic_v2_freshness_assertion_dsl(),
    )

    payload = _run(
        resolve_rule_mutation_payload(
            command=command,
            repository=mutation_repository,
            config_repository=_app_config_repository(),
            catalog_repository=object(),
            contract_resolver=object(),
            actor_id="user-1",
            workspace_id="default",
        )
    )

    assert payload["expression"] == "DATEDIFF(NOW(), published_at) <= 3"
    assert payload["check_type"] == "FRESHNESS"
    assert payload["check_type_params"] == {
        "checkType": "FRESHNESS",
        "attribute": "published_at",
        "maxDaysOld": 3,
        "anchor": "now",
        "condition": None,
    }
    assert payload["dsl"]["schema_version"] == "2.0.0"
    assert payload["dsl"]["rule"]["kind"] == "freshness_assertion"


def test_resolve_rule_mutation_payload_rejects_v2_freshness_assertion_non_day_duration(mutation_repository) -> None:
    command = RuleMutationCommand(
        name="Unsupported Semantic Freshness Rule",
        description="Checks freshness with unsupported duration",
        dimension="timeliness",
        workspace="default",
        generated=False,
        is_template=False,
        dsl=_semantic_v2_freshness_assertion_dsl(value="PT6H"),
    )

    with pytest.raises(HTTPException) as exc_info:
        _run(
            resolve_rule_mutation_payload(
                command=command,
                repository=mutation_repository,
                config_repository=_app_config_repository(),
                catalog_repository=object(),
                contract_resolver=object(),
                actor_id="user-1",
                workspace_id="default",
            )
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["error"] == "rule_dsl_lowering_unsupported"
    assert exc_info.value.detail["rule_kind"] == "freshness_assertion"
    assert "day durations" in exc_info.value.detail["message"]


def test_resolve_rule_mutation_payload_lowers_v2_reference_assertion(mutation_repository) -> None:
    class _CatalogRepository:
        class _Version:
            def __init__(self, version_id: str, data_object_id: str) -> None:
                self.id = version_id
                self.data_object_id = data_object_id

        class _Attribute:
            def __init__(self, name: str) -> None:
                self.name = name

        def list_data_object_versions(self):
            return [self._Version("dov-reference-customer-v2", "do-reference-customer")]

        def list_attributes_catalog(self, version_id: str):
            assert version_id == "dov-reference-customer-v2"
            return [self._Attribute("customer_id")]

    command = RuleMutationCommand(
        name="Semantic Reference Rule",
        description="Checks customer_id exists in the reference object",
        dimension="consistency",
        workspace="default",
        generated=False,
        is_template=False,
        dsl=_semantic_v2_reference_assertion_dsl(),
    )

    payload = _run(
        resolve_rule_mutation_payload(
            command=command,
            repository=mutation_repository,
            config_repository=_app_config_repository(),
            catalog_repository=_CatalogRepository(),
            contract_resolver=object(),
            actor_id="user-1",
            workspace_id="default",
        )
    )

    assert payload["expression"] == "customer_id IN (SELECT customer_id FROM do-reference-customer)"
    assert payload["check_type"] == "REFERENTIAL_INTEGRITY"
    assert payload["check_type_params"] == {
        "checkType": "REFERENTIAL_INTEGRITY",
        "attribute": "customer_id",
        "refDataObjectId": "do-reference-customer",
        "refDataObjectVersionId": "dov-reference-customer-v2",
        "refAttribute": "customer_id",
        "refWorkspaceId": None,
    }
    assert payload["dsl"]["schema_version"] == "2.0.0"
    assert payload["dsl"]["rule"]["kind"] == "reference_assertion"


def test_resolve_rule_mutation_payload_lowers_v2_duplicate_percent_zero_to_uniqueness(mutation_repository) -> None:
    command = RuleMutationCommand(
        name="Semantic Duplicate Rule",
        description="Checks duplicate percent is zero for the business key",
        dimension="uniqueness",
        workspace="default",
        generated=False,
        is_template=False,
        dsl=_semantic_v2_duplicate_percent_dsl(),
    )

    payload = _run(
        resolve_rule_mutation_payload(
            command=command,
            repository=mutation_repository,
            config_repository=_app_config_repository(),
            catalog_repository=object(),
            contract_resolver=object(),
            actor_id="user-1",
            workspace_id="default",
        )
    )

    assert payload["expression"] == "COUNT(*) OVER (PARTITION BY customer_id, order_date) = 1"
    assert payload["check_type"] == "UNIQUENESS"
    assert payload["check_type_params"] == {
        "checkType": "UNIQUENESS",
        "attributes": ["customer_id", "order_date"],
    }
    assert payload["dsl"]["schema_version"] == "2.0.0"
    assert payload["dsl"]["rule"]["kind"] == "metric_threshold"


def test_resolve_rule_mutation_payload_rejects_v2_duplicate_percent_with_row_filter(mutation_repository) -> None:
    command = RuleMutationCommand(
        name="Scoped Semantic Duplicate Rule",
        description="Checks duplicate percent is zero for NL rows",
        dimension="uniqueness",
        workspace="default",
        generated=False,
        is_template=False,
        dsl=_semantic_v2_duplicate_percent_dsl(include_row_filter=True),
    )

    with pytest.raises(HTTPException) as exc_info:
        _run(
            resolve_rule_mutation_payload(
                command=command,
                repository=mutation_repository,
                config_repository=_app_config_repository(),
                catalog_repository=object(),
                contract_resolver=object(),
                actor_id="user-1",
                workspace_id="default",
            )
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["error"] == "rule_dsl_lowering_unsupported"
    assert exc_info.value.detail["rule_kind"] == "metric_threshold"
    assert "scope.row_filter" in exc_info.value.detail["message"]


def test_resolve_rule_mutation_payload_lowers_v2_missing_count_zero_to_threshold(mutation_repository) -> None:
    command = RuleMutationCommand(
        name="Semantic Missing Count Rule",
        description="Checks there are no missing email values",
        dimension="completeness",
        workspace="default",
        generated=False,
        is_template=False,
        dsl=_semantic_v2_missing_count_dsl(),
    )

    payload = _run(
        resolve_rule_mutation_payload(
            command=command,
            repository=mutation_repository,
            config_repository=_app_config_repository(),
            catalog_repository=object(),
            contract_resolver=object(),
            actor_id="user-1",
            workspace_id="default",
        )
    )

    assert payload["expression"] == "email IS NOT NULL"
    assert payload["check_type"] == "THRESHOLD"
    assert payload["check_type_params"] == {
        "checkType": "THRESHOLD",
        "attribute": "email",
        "metric": "null_pct",
        "operator": "gte",
        "quantile": None,
        "threshold": 100.0,
    }


def test_resolve_rule_mutation_payload_rejects_v2_missing_count_non_zero(mutation_repository) -> None:
    command = RuleMutationCommand(
        name="Semantic Missing Count Rule",
        description="Checks there is at most one missing email value",
        dimension="completeness",
        workspace="default",
        generated=False,
        is_template=False,
        dsl=_semantic_v2_missing_count_dsl(value=1),
    )

    with pytest.raises(HTTPException) as exc_info:
        _run(
            resolve_rule_mutation_payload(
                command=command,
                repository=mutation_repository,
                config_repository=_app_config_repository(),
                catalog_repository=object(),
                contract_resolver=object(),
                actor_id="user-1",
                workspace_id="default",
            )
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["error"] == "rule_dsl_lowering_unsupported"
    assert exc_info.value.detail["rule_kind"] == "metric_threshold"
    assert "measure.metric = 'missing_count'" in exc_info.value.detail["message"]


def test_resolve_rule_mutation_payload_lowers_v2_duplicate_count_zero_to_uniqueness(mutation_repository) -> None:
    command = RuleMutationCommand(
        name="Semantic Duplicate Count Rule",
        description="Checks there are no duplicate business keys",
        dimension="uniqueness",
        workspace="default",
        generated=False,
        is_template=False,
        dsl=_semantic_v2_duplicate_count_dsl(),
    )

    payload = _run(
        resolve_rule_mutation_payload(
            command=command,
            repository=mutation_repository,
            config_repository=_app_config_repository(),
            catalog_repository=object(),
            contract_resolver=object(),
            actor_id="user-1",
            workspace_id="default",
        )
    )

    assert payload["expression"] == "COUNT(*) OVER (PARTITION BY customer_id, order_date) = 1"
    assert payload["check_type"] == "UNIQUENESS"
    assert payload["check_type_params"] == {
        "checkType": "UNIQUENESS",
        "attributes": ["customer_id", "order_date"],
    }


def test_resolve_rule_mutation_payload_rejects_v2_duplicate_count_non_zero(mutation_repository) -> None:
    command = RuleMutationCommand(
        name="Semantic Duplicate Count Rule",
        description="Checks there is at most one duplicate business key",
        dimension="uniqueness",
        workspace="default",
        generated=False,
        is_template=False,
        dsl=_semantic_v2_duplicate_count_dsl(value=1),
    )

    with pytest.raises(HTTPException) as exc_info:
        _run(
            resolve_rule_mutation_payload(
                command=command,
                repository=mutation_repository,
                config_repository=_app_config_repository(),
                catalog_repository=object(),
                contract_resolver=object(),
                actor_id="user-1",
                workspace_id="default",
            )
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["error"] == "rule_dsl_lowering_unsupported"
    assert exc_info.value.detail["rule_kind"] == "metric_threshold"
    assert "measure.metric = 'duplicate_count'" in exc_info.value.detail["message"]


def test_resolve_rule_mutation_payload_lowers_v2_row_count_with_row_filter(mutation_repository) -> None:
    command = RuleMutationCommand(
        name="Semantic Row Count Rule",
        description="Checks active Dutch rows stay over a threshold",
        dimension="completeness",
        workspace="default",
        generated=False,
        is_template=False,
        dsl=_semantic_v2_row_count_dsl(include_row_filter=True, operator="gte", value=25),
    )

    payload = _run(
        resolve_rule_mutation_payload(
            command=command,
            repository=mutation_repository,
            config_repository=_app_config_repository(),
            catalog_repository=object(),
            contract_resolver=object(),
            actor_id="user-1",
            workspace_id="default",
        )
    )

    assert payload["expression"] == "country = 'NL'"
    assert payload["check_type"] == "ROW_COUNT"
    assert payload["check_type_params"] == {
        "checkType": "ROW_COUNT",
        "operator": "gte",
        "threshold": 25,
    }


def test_resolve_rule_mutation_payload_lowers_v2_row_count_between(mutation_repository) -> None:
    command = RuleMutationCommand(
        name="Semantic Row Count Range Rule",
        description="Checks row count stays within a bounded range",
        dimension="completeness",
        workspace="default",
        generated=False,
        is_template=False,
        dsl=_semantic_v2_row_count_dsl(operator="between", value=25),
    )

    payload = _run(
        resolve_rule_mutation_payload(
            command=command,
            repository=mutation_repository,
            config_repository=_app_config_repository(),
            catalog_repository=object(),
            contract_resolver=object(),
            actor_id="user-1",
            workspace_id="default",
        )
    )

    assert payload["expression"] == "1 = 1"
    assert payload["check_type"] == "ROW_COUNT"
    assert payload["check_type_params"] == {
        "checkType": "ROW_COUNT",
        "operator": "between",
        "minValue": 25,
        "maxValue": 35,
    }


def test_resolve_rule_mutation_payload_lowers_supported_gx_case(
    gx_supported_case_catalog: dict[str, dict[str, Any]],
    mutation_repository,
) -> None:
    case = gx_supported_case_catalog["threshold_customer_email_not_null"]
    command = RuleMutationCommand(
        name="Canonical Threshold Customer Email",
        description="Checks missing email values for customer rows",
        dimension=str(case["dimension"]),
        workspace="default",
        generated=False,
        is_template=False,
        dsl=case["dsl"],
    )

    payload = _run(
        resolve_rule_mutation_payload(
            command=command,
            repository=mutation_repository,
            config_repository=_app_config_repository(),
            catalog_repository=object(),
            contract_resolver=object(),
            actor_id="user-1",
            workspace_id="default",
        )
    )

    assert payload["expression"] == case["expression"]
    assert payload["check_type"] is None
    assert payload["check_type_params"] is None
    assert payload["dsl"]["schema_version"] == "2.0.0"
    assert payload["dsl"]["rule"]["kind"] == "row_assertion"
    assert payload["dsl"]["rule"]["scope"]["dataset"]["data_object_id"] == case["data_object_id"]


def test_resolve_rule_mutation_payload_lowers_supported_custom_query_case(
    gx_supported_case_catalog: dict[str, dict[str, Any]],
    mutation_repository,
) -> None:
    case = gx_supported_case_catalog["correct_atm_cash_movement_matches_authoritative_transaction_total"]
    dsl = json.loads(json.dumps(case["dsl"]))
    dsl["rule"]["measure"]["query"] = "SELECT transaction_id, amount FROM teller_machine_left_reconcile"
    dsl["rule"]["measure"]["comparison_data_source_name"] = "Transaction Source"
    dsl["rule"]["measure"]["comparison_query"] = (
        "SELECT order_id AS transaction_id, total_amount AS amount FROM teller_machine_right_reconcile"
    )

    command = RuleMutationCommand(
        name="Canonical Custom Query Assertion",
        description="Checks a supported custom query comparison",
        dimension=str(case["dimension"]),
        workspace="default",
        generated=False,
        is_template=False,
        dsl=dsl,
    )

    payload = _run(
        resolve_rule_mutation_payload(
            command=command,
            repository=mutation_repository,
            config_repository=_app_config_repository(),
            catalog_repository=object(),
            contract_resolver=object(),
            actor_id="user-1",
            workspace_id="default",
        )
    )

    assert payload["expression"] == ""
    assert payload["check_type"] is None
    assert payload["check_type_params"] is None
    assert payload["dsl"]["rule"]["kind"] == "custom_query_assertion"
    assert payload["dsl"]["rule"]["measure"]["comparison_data_source_name"] == "Transaction Source"
    assert payload["dsl"]["rule"]["measure"]["comparison_query"] == (
        "SELECT order_id AS transaction_id, total_amount AS amount FROM teller_machine_right_reconcile"
    )


def test_resolve_rule_mutation_payload_rejects_unsupported_gx_lowering_path(
    mutation_repository,
) -> None:
    command = RuleMutationCommand(
        name="Scoped Semantic Email Rule",
        description="Checks missing percent for NL email rows",
        dimension="completeness",
        workspace="default",
        generated=False,
        is_template=False,
        dsl=_semantic_v2_metric_threshold_dsl(include_row_filter=True),
    )

    with pytest.raises(HTTPException) as exc_info:
        _run(
            resolve_rule_mutation_payload(
                command=command,
                repository=mutation_repository,
                config_repository=_app_config_repository(),
                catalog_repository=object(),
                contract_resolver=object(),
                actor_id="user-1",
                workspace_id="default",
            )
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["error"] == "rule_dsl_lowering_unsupported"
    assert exc_info.value.detail["schema_version"] == "2.0.0"
    assert exc_info.value.detail["rule_kind"] == "metric_threshold"
    assert "scope.row_filter" in exc_info.value.detail["message"]