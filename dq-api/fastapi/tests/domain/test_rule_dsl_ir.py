from __future__ import annotations

import pytest

from app.domain.entities.rule_dsl_ir import RuleDslIrDocument
from app.domain.entities.rule_dsl_ir import build_rule_dsl_v2_semantic_ir
from app.domain.entities.rule_dsl_v2 import RuleDslV2Document


def test_build_rule_dsl_v2_semantic_ir_normalizes_snake_case_payload() -> None:
    semantic_model = RuleDslV2Document.model_validate(
        {
            "schema_version": "2.0.0",
            "rule": {
                "kind": "metric_threshold",
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
                    "type": "metric",
                    "metric": "row_count",
                },
                "expectation": {
                    "type": "threshold",
                    "operator": "gte",
                    "value": 25,
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
    )

    semantic_ir = build_rule_dsl_v2_semantic_ir(semantic_model=semantic_model)

    assert isinstance(semantic_ir, RuleDslIrDocument)
    assert semantic_ir.model_dump(mode="python", exclude_none=True) == {
        "schema_version": "2.0.0",
        "rule": {
            "kind": "metric_threshold",
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
                "type": "metric",
                "metric": "row_count",
            },
            "expectation": {
                "type": "threshold",
                "operator": "gte",
                "value": 25,
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


def test_build_rule_dsl_v2_semantic_ir_preserves_schema_contract_ordering_fields() -> None:
    semantic_model = RuleDslV2Document.model_validate(
        {
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
                    "schema_assertion": "column_order_matches",
                },
                "expectation": {
                    "type": "schema_contract",
                    "ordered_columns": ["customer_id", "email", "status"],
                    "min_column_count": 3,
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
    )

    semantic_ir = build_rule_dsl_v2_semantic_ir(semantic_model=semantic_model)

    assert semantic_ir.model_dump(mode="python", exclude_none=True)["rule"]["expectation"] == {
        "type": "schema_contract",
        "ordered_columns": ["customer_id", "email", "status"],
        "min_column_count": 3,
    }


def test_build_rule_dsl_v2_semantic_ir_preserves_query_comparison_fields() -> None:
    semantic_model = RuleDslV2Document.model_validate(
        {
            "schema_version": "2.0.0",
            "rule": {
                "kind": "custom_query_assertion",
                "scope": {
                    "dataset": {
                        "data_object_id": "do-customer",
                    },
                },
                "measure": {
                    "type": "query",
                    "query_language": "sql",
                    "query": "SELECT customer_id FROM customers",
                    "comparison_data_source_name": "warehouse_reporting",
                    "comparison_query": "SELECT customer_id FROM reporting_customers",
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
    )

    semantic_ir = build_rule_dsl_v2_semantic_ir(semantic_model=semantic_model)

    assert semantic_ir.model_dump(mode="python", exclude_none=True)["rule"]["measure"] == {
        "type": "query",
        "query_language": "sql",
        "query": "SELECT customer_id FROM customers",
        "comparison_data_source_name": "warehouse_reporting",
        "comparison_query": "SELECT customer_id FROM reporting_customers",
    }


def test_build_rule_dsl_v2_semantic_ir_rejects_one_sided_query_comparison_fields() -> None:
    with pytest.raises(ValueError, match="comparisonDataSourceName and comparisonQuery together"):
        RuleDslV2Document.model_validate(
            {
                "schema_version": "2.0.0",
                "rule": {
                    "kind": "custom_query_assertion",
                    "scope": {
                        "dataset": {
                            "data_object_id": "do-customer",
                        },
                    },
                    "measure": {
                        "type": "query",
                        "query_language": "sql",
                        "query": "SELECT customer_id FROM customers",
                        "comparison_data_source_name": "warehouse_reporting",
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
        )