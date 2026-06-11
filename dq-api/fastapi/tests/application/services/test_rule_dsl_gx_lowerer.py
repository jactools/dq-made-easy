from __future__ import annotations

import pytest

from app.application.services import GxExpectationBuildError
from app.application.services import build_gx_artifact_envelope_from_rule_dsl_v2
from app.application.services import build_gx_expectations_from_rule_dsl_v2
from app.application.services import build_gx_suite_payload_from_rule_dsl_v2
from app.domain.entities.rule_dsl_ir import RuleDslIrDocument


def _base_rule_payload(*, kind: str, scope: dict, measure: dict, expectation: dict) -> dict:
    return {
        "schema_version": "2.0.0",
        "rule": {
            "kind": kind,
            "scope": scope,
            "measure": measure,
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


def test_build_gx_expectations_from_rule_dsl_v2_lower_row_assertion_with_row_filter() -> None:
    semantic_ir = RuleDslIrDocument.model_validate(
        _base_rule_payload(
            kind="row_assertion",
            scope={
                "dataset": {"data_object_id": "do-customer"},
                "row_filter": {
                    "kind": "row_predicate",
                    "language": "dq_predicate",
                    "expression": "country = 'NL'",
                },
            },
            measure={
                "type": "row_predicate",
                "predicate": {
                    "kind": "row_predicate",
                    "language": "dq_predicate",
                    "expression": "email IS NOT NULL",
                },
            },
            expectation={"type": "threshold", "operator": "gte", "value": 100, "unit": "percent"},
        )
    )

    expectations = build_gx_expectations_from_rule_dsl_v2(semantic_ir=semantic_ir)

    assert expectations == [
        {
            "expectation_type": "expect_column_values_to_not_be_null",
            "kwargs": {
                "column": "email",
                "row_condition": {
                    "type": "comparison",
                    "column": {"name": "country"},
                    "operator": "==",
                    "parameter": "NL",
                },
            },
            "meta": {},
        }
    ]


def test_build_gx_expectations_from_rule_dsl_v2_lower_missing_percent_metric() -> None:
    semantic_ir = RuleDslIrDocument.model_validate(
        _base_rule_payload(
            kind="metric_threshold",
            scope={"dataset": {"data_object_id": "do-customer"}},
            measure={
                "type": "metric",
                "metric": "missing_percent",
                "subject": {"column": "email"},
            },
            expectation={"type": "threshold", "operator": "lte", "value": 10, "unit": "percent"},
        )
    )

    expectations = build_gx_expectations_from_rule_dsl_v2(semantic_ir=semantic_ir)

    assert expectations == [
        {
            "expectation_type": "expect_column_proportion_of_non_null_values_to_be_between",
            "kwargs": {"column": "email", "min_value": 0.9},
            "meta": {},
        }
    ]


@pytest.mark.parametrize(
    ("expectation", "expected"),
    [
        (
            {"type": "threshold", "operator": "between", "min_value": 1000, "max_value": 2000, "unit": "count"},
            {
                "expectation_type": "expect_table_row_count_to_be_between",
                "kwargs": {"min_value": 1000, "max_value": 2000},
                "meta": {},
            },
        ),
        (
            {"type": "threshold", "operator": "gte", "value": 1000, "unit": "count"},
            {
                "expectation_type": "expect_table_row_count_to_be_between",
                "kwargs": {"min_value": 1000},
                "meta": {},
            },
        ),
        (
            {"type": "threshold", "operator": "gt", "value": 1000, "unit": "count"},
            {
                "expectation_type": "expect_table_row_count_to_be_between",
                "kwargs": {"min_value": 1001},
                "meta": {},
            },
        ),
        (
            {"type": "threshold", "operator": "lte", "value": 1000, "unit": "count"},
            {
                "expectation_type": "expect_table_row_count_to_be_between",
                "kwargs": {"max_value": 1000},
                "meta": {},
            },
        ),
        (
            {"type": "threshold", "operator": "lt", "value": 1000, "unit": "count"},
            {
                "expectation_type": "expect_table_row_count_to_be_between",
                "kwargs": {"max_value": 999},
                "meta": {},
            },
        ),
    ],
)
def test_build_gx_expectations_from_rule_dsl_v2_lower_row_count_metric(
    expectation: dict,
    expected: dict,
) -> None:
    semantic_ir = RuleDslIrDocument.model_validate(
        _base_rule_payload(
            kind="metric_threshold",
            scope={"dataset": {"data_object_id": "do-customer"}},
            measure={
                "type": "metric",
                "metric": "row_count",
            },
            expectation=expectation,
        )
    )

    expectations = build_gx_expectations_from_rule_dsl_v2(semantic_ir=semantic_ir)

    assert expectations == [expected]


def test_build_gx_expectations_from_rule_dsl_v2_rejects_row_count_subject_column() -> None:
    semantic_ir = RuleDslIrDocument.model_validate(
        _base_rule_payload(
            kind="metric_threshold",
            scope={"dataset": {"data_object_id": "do-customer"}},
            measure={
                "type": "metric",
                "metric": "row_count",
                "subject": {"column": "amount"},
            },
            expectation={"type": "threshold", "operator": "gte", "value": 100, "unit": "count"},
        )
    )

    with pytest.raises(GxExpectationBuildError, match="row_count' does not support a subject column"):
        build_gx_expectations_from_rule_dsl_v2(semantic_ir=semantic_ir)


def test_build_gx_expectations_from_rule_dsl_v2_rejects_row_count_non_dataset_scope() -> None:
    semantic_ir = RuleDslIrDocument.model_validate(
        _base_rule_payload(
            kind="metric_threshold",
            scope={
                "join": {
                    "join_type": "inner",
                    "conditions": [
                        {
                            "left_column": "customer_id",
                            "operator": "=",
                            "right_column": "customer_id",
                        }
                    ],
                }
            },
            measure={
                "type": "metric",
                "metric": "row_count",
            },
            expectation={"type": "threshold", "operator": "gte", "value": 100, "unit": "count"},
        )
    )

    with pytest.raises(GxExpectationBuildError, match="metric_threshold metric 'row_count' requires dataset scope"):
        build_gx_expectations_from_rule_dsl_v2(semantic_ir=semantic_ir)


@pytest.mark.parametrize(
    ("metric", "operator", "value", "extra_expectation", "expected"),
    [
        (
            "min",
            "gte",
            3,
            {"unit": "raw"},
            {
                "expectation_type": "expect_column_min_to_be_between",
                "kwargs": {"column": "amount", "min_value": 3},
                "meta": {},
            },
        ),
        (
            "max",
            "lt",
            10,
            {"unit": "raw"},
            {
                "expectation_type": "expect_column_max_to_be_between",
                "kwargs": {"column": "amount", "max_value": 10, "strict_max": True},
                "meta": {},
            },
        ),
        (
            "avg",
            "lte",
            42.5,
            {},
            {
                "expectation_type": "expect_column_mean_to_be_between",
                "kwargs": {"column": "amount", "max_value": 42.5},
                "meta": {},
            },
        ),
        (
            "sum",
            "between",
            None,
            {"min_value": 10, "max_value": 20, "unit": "raw"},
            {
                "expectation_type": "expect_column_sum_to_be_between",
                "kwargs": {"column": "amount", "min_value": 10, "max_value": 20},
                "meta": {},
            },
        ),
        (
            "stddev",
            "gt",
            1.5,
            {},
            {
                "expectation_type": "expect_column_stdev_to_be_between",
                "kwargs": {"column": "amount", "min_value": 1.5, "strict_min": True},
                "meta": {},
            },
        ),
        (
            "distinct_count",
            "gte",
            4,
            {"unit": "count"},
            {
                "expectation_type": "expect_column_unique_value_count_to_be_between",
                "kwargs": {"column": "amount", "min_value": 4},
                "meta": {},
            },
        ),
    ],
)
def test_build_gx_expectations_from_rule_dsl_v2_lower_aggregate_metrics(
    metric: str,
    operator: str,
    value: float | int | None,
    extra_expectation: dict,
    expected: dict,
) -> None:
    expectation = {"type": "threshold", "operator": operator}
    if operator == "between":
        expectation.update(extra_expectation)
    else:
        expectation["value"] = value
        expectation.update(extra_expectation)

    semantic_ir = RuleDslIrDocument.model_validate(
        _base_rule_payload(
            kind="metric_threshold",
            scope={"dataset": {"data_object_id": "do-customer"}},
            measure={
                "type": "metric",
                "metric": metric,
                "subject": {"column": "amount"},
            },
            expectation=expectation,
        )
    )

    expectations = build_gx_expectations_from_rule_dsl_v2(semantic_ir=semantic_ir)

    assert expectations == [expected]


def test_build_gx_suite_payload_from_rule_dsl_v2_wraps_the_lowered_expectations() -> None:
    semantic_ir = RuleDslIrDocument.model_validate(
        _base_rule_payload(
            kind="metric_threshold",
            scope={"dataset": {"data_object_id": "do-customer"}},
            measure={
                "type": "metric",
                "metric": "duplicate_count",
                "subject": {"column": "customer_id"},
            },
            expectation={"type": "threshold", "operator": "lte", "value": 0, "unit": "count"},
        )
    )

    suite_payload = build_gx_suite_payload_from_rule_dsl_v2(
        semantic_ir=semantic_ir,
        suite_id="gx-suite-1",
        suite_version=3,
        rule_id="rule-1",
        artifact_key="artifact-1",
    )

    assert suite_payload == {
        "expectation_suite_name": "gx-suite-1_v3",
        "expectations": [
            {
                "expectation_type": "expect_column_values_to_be_unique",
                "kwargs": {"column": "customer_id"},
                "meta": {"dq.rule_id": "rule-1", "dq.artifact_key": "artifact-1"},
            }
        ],
        "meta": {
            "dq.schema_version": "2.0.0",
            "dq.rule_kind": "metric_threshold",
            "dq.rule_id": "rule-1",
            "dq.artifact_key": "artifact-1",
        },
    }


def test_build_gx_artifact_envelope_from_rule_dsl_v2_preserves_evidence_policy() -> None:
    semantic_ir = RuleDslIrDocument.model_validate(
        _base_rule_payload(
            kind="metric_threshold",
            scope={"dataset": {"data_object_id": "do-customer"}},
            measure={
                "type": "metric",
                "metric": "duplicate_count",
                "subject": {"column": "customer_id"},
            },
            expectation={"type": "threshold", "operator": "lte", "value": 0, "unit": "count"},
        )
    )

    artifact_envelope = build_gx_artifact_envelope_from_rule_dsl_v2(
        semantic_ir=semantic_ir,
        suite_id="gx-suite-1",
        suite_version=3,
        assignment_scope={"dataObjectId": "do-customer"},
        resolved_data_object_version_ids=["dov-1"],
    )

    assert artifact_envelope.executionHints.evidence is not None
    assert artifact_envelope.executionHints.evidence.failedRows is not None
    assert artifact_envelope.executionHints.evidence.failedRows.mode == "sample"
    assert artifact_envelope.executionHints.evidence.failedRows.limit == 25
    assert artifact_envelope.executionHints.evidence.failedRows.includeRowIdentifier is True
    assert artifact_envelope.executionHints.evidence.failedRows.includePrimaryKey is True
    assert artifact_envelope.executionHints.evidence.emitCompiledArtifact is True
    assert artifact_envelope.executionHints.evidence.emitGeneratedSql is False

    payload = artifact_envelope.model_dump(mode="python", by_alias=True, exclude_none=True)
    assert payload["executionHints"]["evidence"]["failed_rows"]["mode"] == "sample"
    assert payload["executionHints"]["evidence"]["failed_rows"]["limit"] == 25


def test_build_gx_expectations_from_rule_dsl_v2_lower_freshness_assertion() -> None:
    semantic_ir = RuleDslIrDocument.model_validate(
        _base_rule_payload(
            kind="freshness_assertion",
            scope={"dataset": {"data_object_id": "do-customer"}},
            measure={
                "type": "metric",
                "metric": "freshness_age",
                "subject": {"column": "published_at"},
            },
            expectation={"type": "threshold", "operator": "lte", "value": "P3D", "unit": "duration"},
        )
    )

    expectations = build_gx_expectations_from_rule_dsl_v2(semantic_ir=semantic_ir)

    assert expectations == [
        {
            "expectation_type": "expect_column_values_to_be_within_past_days",
            "kwargs": {"column": "published_at", "max_days_old": 3, "anchor": "now"},
            "meta": {},
        }
    ]


def test_build_gx_expectations_from_rule_dsl_v2_lower_reference_assertion() -> None:
    semantic_ir = RuleDslIrDocument.model_validate(
        _base_rule_payload(
            kind="reference_assertion",
            scope={
                "comparison": {
                    "left": {"data_object_version_id": "dov-customer-v5"},
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
            measure={
                "type": "metric",
                "metric": "match_percent",
                "subject": {"column": "customer_id"},
            },
            expectation={"type": "threshold", "operator": "gte", "value": 100, "unit": "percent"},
        )
    )

    expectations = build_gx_expectations_from_rule_dsl_v2(semantic_ir=semantic_ir)

    assert expectations == [
        {
            "expectation_type": "expect_column_values_to_not_be_null",
            "kwargs": {"column": "rhs.customer_id"},
            "meta": {},
        }
    ]


def test_build_gx_expectations_from_rule_dsl_v2_lower_row_count_metric_with_row_filter() -> None:
    semantic_ir = RuleDslIrDocument.model_validate(
        _base_rule_payload(
            kind="metric_threshold",
            scope={
                "dataset": {"data_object_id": "do-customer"},
                "row_filter": {
                    "kind": "row_predicate",
                    "language": "dq_predicate",
                    "expression": "age >= 18",
                },
            },
            measure={
                "type": "metric",
                "metric": "row_count",
            },
            expectation={"type": "threshold", "operator": "gte", "value": 5, "unit": "count"},
        )
    )

    expectations = build_gx_expectations_from_rule_dsl_v2(semantic_ir=semantic_ir)

    assert expectations == [
        {
            "expectation_type": "expect_table_row_count_to_be_between",
            "kwargs": {
                "min_value": 5,
                "row_condition": {
                    "type": "comparison",
                    "column": {"name": "age"},
                    "operator": ">=",
                    "parameter": 18,
                },
            },
            "meta": {},
        }
    ]


def test_build_gx_expectations_from_rule_dsl_v2_lower_schema_assertion_required_columns_present() -> None:
    semantic_ir = RuleDslIrDocument.model_validate(
        _base_rule_payload(
            kind="schema_assertion",
            scope={"dataset": {"data_object_id": "do-customer"}},
            measure={"type": "schema", "schema_assertion": "required_columns_present"},
            expectation={
                "type": "schema_contract",
                "required_columns": ["customer_id", "email"],
            },
        )
    )

    expectations = build_gx_expectations_from_rule_dsl_v2(semantic_ir=semantic_ir)

    assert expectations == [
        {
            "expectation_type": "expect_table_columns_to_match_set",
            "kwargs": {
                "column_set": ["customer_id", "email"],
                "exact_match": False,
            },
            "meta": {},
        }
    ]


def test_build_gx_expectations_from_rule_dsl_v2_lower_schema_assertion_forbidden_columns_absent() -> None:
    semantic_ir = RuleDslIrDocument.model_validate(
        _base_rule_payload(
            kind="schema_assertion",
            scope={"dataset": {"data_object_id": "do-customer"}},
            measure={"type": "schema", "schema_assertion": "forbidden_columns_absent"},
            expectation={
                "type": "schema_contract",
                "forbidden_columns": ["legacy_status"],
            },
        )
    )

    expectations = build_gx_expectations_from_rule_dsl_v2(semantic_ir=semantic_ir)

    assert expectations == [
        {
            "expectation_type": "expect_table_columns_to_not_contain_set",
            "kwargs": {
                "column_set": ["legacy_status"],
            },
            "meta": {},
        }
    ]


def test_build_gx_expectations_from_rule_dsl_v2_lower_custom_query_assertion() -> None:
    semantic_ir = RuleDslIrDocument.model_validate(
        _base_rule_payload(
            kind="custom_query_assertion",
            scope={"dataset": {"data_object_id": "do-customer"}},
            measure={
                "type": "query",
                "query_language": "sql",
                "query": "SELECT customer_id, email FROM customers WHERE active = TRUE",
                "comparison_data_source_name": "warehouse_reporting",
                "comparison_query": "SELECT customer_id, email FROM reporting_customers WHERE active = TRUE",
            },
            expectation={"type": "threshold", "operator": "gte", "value": 100, "unit": "percent"},
        )
    )

    expectations = build_gx_expectations_from_rule_dsl_v2(semantic_ir=semantic_ir)

    assert expectations == [
        {
            "expectation_type": "expect_query_results_to_match_comparison",
            "kwargs": {
                "base_query": "SELECT customer_id, email FROM customers WHERE active = TRUE",
                "comparison_data_source_name": "warehouse_reporting",
                "comparison_query": "SELECT customer_id, email FROM reporting_customers WHERE active = TRUE",
                "mostly": 1.0,
            },
            "meta": {},
        }
    ]


def test_build_gx_expectations_from_rule_dsl_v2_rejects_custom_query_assertion_with_row_filter() -> None:
    semantic_ir = RuleDslIrDocument.model_validate(
        _base_rule_payload(
            kind="custom_query_assertion",
            scope={
                "dataset": {"data_object_id": "do-customer"},
                "row_filter": {
                    "kind": "row_predicate",
                    "language": "dq_predicate",
                    "expression": "country = 'NL'",
                },
            },
            measure={
                "type": "query",
                "query_language": "sql",
                "query": "SELECT 1",
                "comparison_data_source_name": "warehouse_reporting",
                "comparison_query": "SELECT 1",
            },
            expectation={"type": "threshold", "operator": "gte", "value": 100, "unit": "percent"},
        )
    )

    with pytest.raises(GxExpectationBuildError, match="row_filter for custom_query_assertion"):
        build_gx_expectations_from_rule_dsl_v2(semantic_ir=semantic_ir)


def test_build_gx_expectations_from_rule_dsl_v2_lower_schema_assertion_column_order_matches() -> None:
    semantic_ir = RuleDslIrDocument.model_validate(
        _base_rule_payload(
            kind="schema_assertion",
            scope={"dataset": {"data_object_id": "do-customer"}},
            measure={"type": "schema", "schema_assertion": "column_order_matches"},
            expectation={
                "type": "schema_contract",
                "ordered_columns": ["customer_id", "email", "status"],
            },
        )
    )

    expectations = build_gx_expectations_from_rule_dsl_v2(semantic_ir=semantic_ir)

    assert expectations == [
        {
            "expectation_type": "expect_table_columns_to_match_ordered_list",
            "kwargs": {"column_list": ["customer_id", "email", "status"]},
            "meta": {},
        }
    ]


def test_build_gx_expectations_from_rule_dsl_v2_lower_schema_assertion_column_types_match() -> None:
    semantic_ir = RuleDslIrDocument.model_validate(
        _base_rule_payload(
            kind="schema_assertion",
            scope={"dataset": {"data_object_id": "do-customer"}},
            measure={"type": "schema", "schema_assertion": "column_types_match"},
            expectation={
                "type": "schema_contract",
                "expected_types": {"customer_id": "INT64", "email": "STRING"},
                "min_column_count": 2,
            },
        )
    )

    expectations = build_gx_expectations_from_rule_dsl_v2(semantic_ir=semantic_ir)

    assert expectations == [
        {
            "expectation_type": "expect_table_column_count_to_be_between",
            "kwargs": {"min_value": 2},
            "meta": {},
        },
        {
            "expectation_type": "expect_column_values_to_be_of_type",
            "kwargs": {"column": "customer_id", "type_": "INT64"},
            "meta": {},
        },
        {
            "expectation_type": "expect_column_values_to_be_of_type",
            "kwargs": {"column": "email", "type_": "STRING"},
            "meta": {},
        },
    ]
