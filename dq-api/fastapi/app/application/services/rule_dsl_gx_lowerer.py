from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
import re
from typing import Any

from app.application.services.gx_expectations import GxExpectationBuildError
from app.application.services.gx_expectations import attach_gx_row_condition_to_expectations
from app.application.services.gx_expectations import build_gx_expectations_from_intermediate_model
from app.application.services.gx_rule_expectations import build_gx_expectations_for_rule
from app.application.services.rule_compiler import compile_rule_to_intermediate_model
from app.domain.entities import GxArtifactEnvelopeEntity
from app.domain.entities import build_gx_artifact_envelope_entity
from app.domain.entities import build_gx_execution_contract_entity
from app.domain.entities.rule_dsl_capability_registry import RULE_DSL_BACKEND_CAPABILITY_REGISTRY
from app.domain.entities.rule_dsl_ir import RuleDslIrDocument
from app.domain.entities.rule_dsl_ir import RuleDslIrMetricMeasure
from app.domain.entities.rule_dsl_ir import RuleDslIrQueryMeasure
from app.domain.entities.rule_dsl_ir import RuleDslIrSchemaContractExpectation
from app.domain.entities.rule_dsl_ir import RuleDslIrSchemaMeasure
from app.domain.entities.rule_dsl_ir import RuleDslIrRowPredicateMeasure
from app.domain.entities.rule_dsl_ir import RuleDslIrThresholdExpectation


@dataclass(frozen=True, slots=True)
class _SyntheticRule:
    id: str
    check_type: str
    check_type_params: dict[str, Any]


def _build_meta(*, rule_id: str | None, artifact_key: str | None) -> dict[str, Any]:
    meta: dict[str, Any] = {}
    if rule_id:
        meta["dq.rule_id"] = rule_id
    if artifact_key:
        meta["dq.artifact_key"] = artifact_key
    return meta


def _build_execution_hints(*, semantic_ir: RuleDslIrDocument) -> dict[str, Any]:
    return {
        "evidence": semantic_ir.rule.evidence.model_dump(mode="python", by_alias=True, exclude_none=True),
    }


_AGGREGATE_NUMERIC_METRICS = {
    "min",
    "max",
    "avg",
    "sum",
    "stddev",
}

_AGGREGATE_COUNT_METRICS = {"distinct_count"}


def _coerce_numeric_threshold_value(*, raw_value: Any, field_name: str) -> int | float:
    try:
        value = float(raw_value)
    except (TypeError, ValueError) as exc:
        raise GxExpectationBuildError(f"{field_name} must be numeric") from exc
    if value.is_integer():
        return int(value)
    return value


def _coerce_non_negative_count_value(*, raw_value: Any, field_name: str) -> int:
    value = _coerce_numeric_threshold_value(raw_value=raw_value, field_name=field_name)
    if isinstance(value, float):
        if not value.is_integer():
            raise GxExpectationBuildError(f"{field_name} must be a non-negative whole number")
        value = int(value)
    if value < 0:
        raise GxExpectationBuildError(f"{field_name} must be a non-negative whole number")
    return value


def _build_aggregate_metric_expectation(
    *,
    metric: str,
    subject_column: str,
    expectation: RuleDslIrThresholdExpectation,
    rule_id: str | None,
    artifact_key: str | None,
) -> dict[str, Any]:
    if metric in _AGGREGATE_NUMERIC_METRICS:
        expectation_type_by_metric = {
            "min": "expect_column_min_to_be_between",
            "max": "expect_column_max_to_be_between",
            "avg": "expect_column_mean_to_be_between",
            "sum": "expect_column_sum_to_be_between",
            "stddev": "expect_column_stdev_to_be_between",
        }
        expectation_type = expectation_type_by_metric[metric]
        coerce_value = _coerce_numeric_threshold_value
        allowed_units = {None, "raw"}
    elif metric in _AGGREGATE_COUNT_METRICS:
        expectation_type = "expect_column_unique_value_count_to_be_between"
        coerce_value = _coerce_non_negative_count_value
        allowed_units = {None, "count"}
    else:
        raise GxExpectationBuildError(f"GX lowerer does not yet support metric_threshold metric '{metric}'")

    if expectation.unit not in allowed_units:
        expected_units = ", ".join(repr(value) for value in sorted(unit for unit in allowed_units if unit is not None)) or "None"
        raise GxExpectationBuildError(
            f"metric_threshold metric '{metric}' currently supports expectation.unit values: {expected_units}"
        )

    kwargs: dict[str, Any] = {"column": subject_column}
    operator = str(expectation.operator or "").strip().lower()
    if operator == "between":
        min_value = coerce_value(
            raw_value=expectation.min_value,
            field_name="dsl.rule.expectation.min_value",
        )
        max_value = coerce_value(
            raw_value=expectation.max_value,
            field_name="dsl.rule.expectation.max_value",
        )
        if max_value < min_value:
            raise GxExpectationBuildError(
                f"metric_threshold metric '{metric}' requires expectation.max_value >= expectation.min_value"
            )
        kwargs.update({"min_value": min_value, "max_value": max_value})
    elif operator == "gt":
        kwargs.update({
            "min_value": coerce_value(raw_value=expectation.value, field_name="dsl.rule.expectation.value"),
            "strict_min": True,
        })
    elif operator == "gte":
        kwargs["min_value"] = coerce_value(raw_value=expectation.value, field_name="dsl.rule.expectation.value")
    elif operator == "lt":
        kwargs.update({
            "max_value": coerce_value(raw_value=expectation.value, field_name="dsl.rule.expectation.value"),
            "strict_max": True,
        })
    elif operator == "lte":
        kwargs["max_value"] = coerce_value(raw_value=expectation.value, field_name="dsl.rule.expectation.value")
    else:
        raise GxExpectationBuildError(
            f"metric_threshold metric '{metric}' currently supports operators gt, gte, lt, lte, and between"
        )

    return {
        "expectation_type": expectation_type,
        "kwargs": kwargs,
        "meta": _build_meta(rule_id=rule_id, artifact_key=artifact_key),
    }


def _build_row_count_metric_expectation(
    *,
    scope: Any,
    subject: Any,
    expectation: RuleDslIrThresholdExpectation,
    rule_id: str | None,
    artifact_key: str | None,
) -> dict[str, Any]:
    if subject is not None:
        raise GxExpectationBuildError("metric_threshold metric 'row_count' does not support a subject column")
    if getattr(scope, "dataset", None) is None:
        raise GxExpectationBuildError("metric_threshold metric 'row_count' requires dataset scope")
    if any(
        value is not None
        for value in (
            getattr(scope, "join", None),
            getattr(scope, "grouping", None),
            getattr(scope, "time_window", None),
            getattr(scope, "comparison", None),
        )
    ):
        raise GxExpectationBuildError("GX lowerer does not yet support non-dataset scope for metric_threshold metric 'row_count'")
    if expectation.unit not in {None, "count"}:
        raise GxExpectationBuildError("metric_threshold metric 'row_count' currently supports expectation.unit values: 'count'")

    operator = str(expectation.operator or "").strip().lower()
    if operator == "between":
        min_value = _coerce_non_negative_count_value(
            raw_value=expectation.min_value,
            field_name="dsl.rule.expectation.min_value",
        )
        max_value = _coerce_non_negative_count_value(
            raw_value=expectation.max_value,
            field_name="dsl.rule.expectation.max_value",
        )
        if max_value < min_value:
            raise GxExpectationBuildError(
                "metric_threshold metric 'row_count' requires expectation.max_value >= expectation.min_value"
            )
        kwargs: dict[str, Any] = {"min_value": min_value, "max_value": max_value}
    else:
        threshold = _coerce_non_negative_count_value(
            raw_value=expectation.value,
            field_name="dsl.rule.expectation.value",
        )
        if operator == "gte":
            kwargs = {"min_value": threshold}
        elif operator == "gt":
            kwargs = {"min_value": threshold + 1}
        elif operator == "lte":
            kwargs = {"max_value": threshold}
        elif operator == "lt":
            if threshold == 0:
                raise GxExpectationBuildError("metric_threshold metric 'row_count' cannot express operator 'lt' with threshold 0")
            kwargs = {"max_value": threshold - 1}
        else:
            raise GxExpectationBuildError(
                "metric_threshold metric 'row_count' currently supports operators gt, gte, lt, lte, and between"
            )

    return {
        "expectation_type": "expect_table_row_count_to_be_between",
        "kwargs": kwargs,
        "meta": _build_meta(rule_id=rule_id, artifact_key=artifact_key),
    }


def build_gx_expectations_from_rule_dsl_v2(
    *,
    semantic_ir: RuleDslIrDocument,
    rule_id: str | None = None,
    artifact_key: str | None = None,
) -> list[dict[str, Any]]:
    rule = semantic_ir.rule
    if not RULE_DSL_BACKEND_CAPABILITY_REGISTRY.supports(rule.kind, "gx"):
        raise GxExpectationBuildError(f"GX does not support semantic rule kind '{rule.kind}'")

    row_filter_intermediate_model = None
    if rule.scope.row_filter is not None:
        if rule.kind == "schema_assertion":
            raise GxExpectationBuildError("GX lowerer does not yet support row_filter for schema_assertion")
        if rule.kind == "custom_query_assertion":
            raise GxExpectationBuildError("GX lowerer does not yet support row_filter for custom_query_assertion")
        row_filter_intermediate_model = _compile_intermediate_model(
            expression=rule.scope.row_filter.expression,
            rule_id=rule_id,
            artifact_key=artifact_key,
        )

    if rule.kind == "row_assertion":
        expectations = _build_row_assertion_expectations(
            semantic_ir=semantic_ir,
            rule_id=rule_id,
            artifact_key=artifact_key,
        )
    elif rule.kind == "metric_threshold":
        expectations = _build_metric_threshold_expectations(
            semantic_ir=semantic_ir,
            rule_id=rule_id,
            artifact_key=artifact_key,
        )
    elif rule.kind == "freshness_assertion":
        expectations = _build_freshness_assertion_expectations(
            semantic_ir=semantic_ir,
            rule_id=rule_id,
            artifact_key=artifact_key,
        )
    elif rule.kind == "reference_assertion":
        expectations = _build_reference_assertion_expectations(
            semantic_ir=semantic_ir,
            rule_id=rule_id,
            artifact_key=artifact_key,
        )
    elif rule.kind == "schema_assertion":
        expectations = _build_schema_assertion_expectations(
            semantic_ir=semantic_ir,
            rule_id=rule_id,
            artifact_key=artifact_key,
        )
    elif rule.kind == "custom_query_assertion":
        expectations = _build_custom_query_assertion_expectations(
            semantic_ir=semantic_ir,
            rule_id=rule_id,
            artifact_key=artifact_key,
        )
    else:
        raise GxExpectationBuildError(f"GX lowerer does not yet support semantic rule kind '{rule.kind}'")

    if row_filter_intermediate_model is not None:
        expectations = attach_gx_row_condition_to_expectations(
            expectations,
            intermediate_model=row_filter_intermediate_model,
        )

    return expectations


def build_gx_suite_payload_from_rule_dsl_v2(
    *,
    semantic_ir: RuleDslIrDocument,
    suite_id: str,
    suite_version: int,
    rule_id: str | None = None,
    artifact_key: str | None = None,
) -> dict[str, Any]:
    expectations = build_gx_expectations_from_rule_dsl_v2(
        semantic_ir=semantic_ir,
        rule_id=rule_id,
        artifact_key=artifact_key,
    )

    meta: dict[str, Any] = {
        "dq.schema_version": semantic_ir.schema_version,
        "dq.rule_kind": semantic_ir.rule.kind,
    }
    if rule_id:
        meta["dq.rule_id"] = rule_id
    if artifact_key:
        meta["dq.artifact_key"] = artifact_key

    return {
        "expectation_suite_name": f"{suite_id}_v{suite_version}",
        "expectations": expectations,
        "meta": meta,
    }


def build_gx_artifact_envelope_from_rule_dsl_v2(
    *,
    semantic_ir: RuleDslIrDocument,
    suite_id: str,
    suite_version: int,
    assignment_scope: Mapping[str, Any],
    resolved_data_object_version_ids: list[str],
    execution_contract: Mapping[str, Any] | None = None,
    rule_id: str | None = None,
    artifact_key: str | None = None,
    saved_by: str | None = None,
    source_pipeline: str = "rule-dsl-v2-gx-lowerer",
    status: str | None = None,
    artifact_hash: str | None = None,
    compiler_version: str = "dq-7.3.0",
) -> GxArtifactEnvelopeEntity:
    suite_payload = build_gx_suite_payload_from_rule_dsl_v2(
        semantic_ir=semantic_ir,
        suite_id=suite_id,
        suite_version=suite_version,
        rule_id=rule_id,
        artifact_key=artifact_key,
    )
    now_iso = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    normalized_rule_id = str(rule_id or artifact_key or "rule-dsl-v2").strip() or "rule-dsl-v2"
    normalized_version_ids = [str(value).strip() for value in resolved_data_object_version_ids if str(value).strip()]
    if not normalized_version_ids:
        raise GxExpectationBuildError("GX artifact envelope requires at least one resolved data object version id")

    return build_gx_artifact_envelope_entity(
        {
            "suiteId": suite_id,
            "suiteVersion": suite_version,
            "artifactVersion": "v1",
            "assignmentScope": dict(assignment_scope),
            "resolvedExecutionScope": {
                "dataObjectVersionIds": normalized_version_ids,
            },
            "gxSuite": suite_payload,
            "compiledFrom": {
                "ruleIds": [normalized_rule_id],
                "compilerVersion": compiler_version,
                "generatedAt": now_iso,
            },
            "executionHints": _build_execution_hints(semantic_ir=semantic_ir),
            "executionContract": build_gx_execution_contract_entity(execution_contract) if execution_contract is not None else None,
            "savedBy": saved_by,
            "sourcePipeline": source_pipeline,
            "status": status,
            "artifactHash": artifact_hash,
        }
    )


def _build_row_assertion_expectations(
    *,
    semantic_ir: RuleDslIrDocument,
    rule_id: str | None,
    artifact_key: str | None,
) -> list[dict[str, Any]]:
    rule = semantic_ir.rule
    if not isinstance(rule.measure, RuleDslIrRowPredicateMeasure):
        raise GxExpectationBuildError("row_assertion requires a row_predicate measure")
    _require_percent_threshold_100(rule.expectation)

    predicate_intermediate_model = _compile_intermediate_model(
        expression=rule.measure.predicate.expression,
        rule_id=rule_id,
        artifact_key=artifact_key,
    )
    return build_gx_expectations_from_intermediate_model(
        dict(predicate_intermediate_model),
        rule_id=rule_id,
        artifact_key=artifact_key,
    )


def _build_metric_threshold_expectations(
    *,
    semantic_ir: RuleDslIrDocument,
    rule_id: str | None,
    artifact_key: str | None,
) -> list[dict[str, Any]]:
    rule = semantic_ir.rule
    if not isinstance(rule.measure, RuleDslIrMetricMeasure):
        raise GxExpectationBuildError("metric_threshold requires a metric measure")

    if rule.measure.metric == "row_count":
        return [
            _build_row_count_metric_expectation(
                scope=rule.scope,
                subject=rule.measure.subject,
                expectation=rule.expectation,
                rule_id=rule_id,
                artifact_key=artifact_key,
            )
        ]

    subject_column = _require_subject_column(rule.measure.subject)
    expectation = rule.expectation
    metric = rule.measure.metric

    if metric == "missing_percent":
        normalized_rule = _SyntheticRule(
            id=str(rule_id or artifact_key or "rule-dsl-v2"),
            check_type="THRESHOLD",
            check_type_params={
                "attribute": subject_column,
                "metric": "null_pct",
                "operator": _invert_threshold_operator(expectation.operator),
                "threshold": _missing_percent_to_success_threshold(expectation),
            },
        )
    elif metric == "missing_count":
        _require_zero_count_threshold(expectation, metric=metric)
        normalized_rule = _SyntheticRule(
            id=str(rule_id or artifact_key or "rule-dsl-v2"),
            check_type="THRESHOLD",
            check_type_params={
                "attribute": subject_column,
                "metric": "null_pct",
                "operator": "gte",
                "threshold": 100,
            },
        )
    elif metric in {"duplicate_count", "duplicate_percent"}:
        _require_zero_count_threshold(expectation, metric=metric)
        normalized_rule = _SyntheticRule(
            id=str(rule_id or artifact_key or "rule-dsl-v2"),
            check_type="UNIQUENESS",
            check_type_params={
                "attributes": _require_subject_columns(rule.measure.subject),
            },
        )
    elif metric in _AGGREGATE_NUMERIC_METRICS or metric in _AGGREGATE_COUNT_METRICS:
        return [
            _build_aggregate_metric_expectation(
                metric=metric,
                subject_column=subject_column,
                expectation=expectation,
                rule_id=rule_id,
                artifact_key=artifact_key,
            )
        ]
    elif metric == "quantile":
        raise GxExpectationBuildError(
            "GX lowerer does not yet support metric_threshold metric 'quantile' because the canonical DSL does not expose a quantile target"
        )
    else:
        raise GxExpectationBuildError(
            f"GX lowerer does not yet support metric_threshold metric '{metric}'"
        )

    return build_gx_expectations_for_rule(
        rule=normalized_rule,
        rule_id=rule_id,
        artifact_key=artifact_key,
    )


def _build_freshness_assertion_expectations(
    *,
    semantic_ir: RuleDslIrDocument,
    rule_id: str | None,
    artifact_key: str | None,
) -> list[dict[str, Any]]:
    rule = semantic_ir.rule
    if not isinstance(rule.measure, RuleDslIrMetricMeasure):
        raise GxExpectationBuildError("freshness_assertion requires a metric measure")
    if rule.measure.metric != "freshness_age":
        raise GxExpectationBuildError("freshness_assertion requires metric 'freshness_age'")
    _require_duration_threshold(rule.expectation)
    subject_column = _require_subject_column(rule.measure.subject)

    normalized_rule = _SyntheticRule(
        id=str(rule_id or artifact_key or "rule-dsl-v2"),
        check_type="FRESHNESS",
        check_type_params={
            "attribute": subject_column,
            "maxDaysOld": _duration_to_days(rule.expectation),
            "anchor": "now",
        },
    )
    return build_gx_expectations_for_rule(
        rule=normalized_rule,
        rule_id=rule_id,
        artifact_key=artifact_key,
    )


def _build_reference_assertion_expectations(
    *,
    semantic_ir: RuleDslIrDocument,
    rule_id: str | None,
    artifact_key: str | None,
) -> list[dict[str, Any]]:
    rule = semantic_ir.rule
    if not isinstance(rule.measure, RuleDslIrMetricMeasure):
        raise GxExpectationBuildError("reference_assertion requires a metric measure")
    if rule.measure.metric != "match_percent":
        raise GxExpectationBuildError("reference_assertion requires metric 'match_percent'")
    _require_percent_threshold_100(rule.expectation)

    comparison = rule.scope.comparison
    if comparison is None:
        raise GxExpectationBuildError("reference_assertion requires comparison scope")
    if len(comparison.join_keys) != 1:
        raise GxExpectationBuildError("reference_assertion requires exactly one join key")

    join_key = comparison.join_keys[0]
    subject_column = _require_subject_column(rule.measure.subject)
    if subject_column != join_key.left_column:
        raise GxExpectationBuildError(
            "reference_assertion subject.column must match the left comparison join key"
        )

    right_data_object_id = str(comparison.right.data_object_id or "").strip()
    right_data_object_version_id = str(comparison.right.data_object_version_id or "").strip()
    if not right_data_object_id or not right_data_object_version_id:
        raise GxExpectationBuildError(
            "reference_assertion requires the right comparison data object id and version id"
        )

    normalized_rule = _SyntheticRule(
        id=str(rule_id or artifact_key or "rule-dsl-v2"),
        check_type="REFERENTIAL_INTEGRITY",
        check_type_params={
            "attribute": subject_column,
            "refDataObjectId": right_data_object_id,
            "refDataObjectVersionId": right_data_object_version_id,
            "refAttribute": join_key.right_column,
        },
    )
    return build_gx_expectations_for_rule(
        rule=normalized_rule,
        rule_id=rule_id,
        artifact_key=artifact_key,
    )


def _build_schema_assertion_expectations(
    *,
    semantic_ir: RuleDslIrDocument,
    rule_id: str | None,
    artifact_key: str | None,
) -> list[dict[str, Any]]:
    rule = semantic_ir.rule
    if not isinstance(rule.measure, RuleDslIrSchemaMeasure):
        raise GxExpectationBuildError("schema_assertion requires a schema measure")
    if not isinstance(rule.expectation, RuleDslIrSchemaContractExpectation):
        raise GxExpectationBuildError("schema_assertion requires a schema_contract expectation")
    if rule.scope.dataset is None:
        raise GxExpectationBuildError("schema_assertion requires dataset scope")
    if rule.scope.row_filter is not None:
        raise GxExpectationBuildError("GX lowerer does not yet support row_filter for schema_assertion")
    if any(
        value is not None
        for value in (
            rule.scope.join,
            rule.scope.grouping,
            rule.scope.time_window,
            rule.scope.comparison,
        )
    ):
        raise GxExpectationBuildError("GX lowerer does not yet support non-dataset scope for schema_assertion")

    expectations: list[dict[str, Any]] = []
    meta = _build_meta(rule_id=rule_id, artifact_key=artifact_key)
    schema_assertion = rule.measure.schema_assertion

    if rule.expectation.min_column_count is not None or rule.expectation.max_column_count is not None:
        expectations.append(
            {
                "expectation_type": "expect_table_column_count_to_be_between",
                "kwargs": {
                    **({"min_value": rule.expectation.min_column_count} if rule.expectation.min_column_count is not None else {}),
                    **({"max_value": rule.expectation.max_column_count} if rule.expectation.max_column_count is not None else {}),
                },
                "meta": dict(meta),
            }
        )

    if schema_assertion == "column_count_between":
        if rule.expectation.min_column_count is None and rule.expectation.max_column_count is None:
            raise GxExpectationBuildError("schema_assertion column_count_between requires min_column_count or max_column_count")
        return expectations

    if schema_assertion == "column_order_matches":
        ordered_columns = [str(value).strip() for value in list(rule.expectation.ordered_columns or []) if str(value).strip()]
        if not ordered_columns:
            raise GxExpectationBuildError("schema_assertion column_order_matches requires ordered_columns")
        expectations.append(
            {
                "expectation_type": "expect_table_columns_to_match_ordered_list",
                "kwargs": {"column_list": ordered_columns},
                "meta": dict(meta),
            }
        )
        return expectations

    if schema_assertion == "column_types_match":
        expected_types = rule.expectation.expected_types or {}
        if not expected_types:
            raise GxExpectationBuildError("schema_assertion column_types_match requires expected_types")
        for column, type_name in expected_types.items():
            normalized_column = str(column).strip()
            normalized_type = str(type_name).strip()
            if not normalized_column or not normalized_type:
                raise GxExpectationBuildError("schema_assertion column_types_match requires non-empty column/type entries")
            expectations.append(
                {
                    "expectation_type": "expect_column_values_to_be_of_type",
                    "kwargs": {"column": normalized_column, "type_": normalized_type},
                    "meta": dict(meta),
                }
            )
        return expectations

    if schema_assertion == "required_columns_present":
        required_columns = [
            str(value).strip()
            for value in list(rule.expectation.required_columns or [])
            if str(value).strip()
        ]
        if not required_columns:
            raise GxExpectationBuildError("schema_assertion required_columns_present requires required_columns")
        expectations.append(
            {
                "expectation_type": "expect_table_columns_to_match_set",
                "kwargs": {
                    "column_set": required_columns,
                    "exact_match": False,
                },
                "meta": dict(meta),
            }
        )
        return expectations

    if schema_assertion == "forbidden_columns_absent":
        forbidden_columns = [
            str(value).strip()
            for value in list(rule.expectation.forbidden_columns or [])
            if str(value).strip()
        ]
        if not forbidden_columns:
            raise GxExpectationBuildError("schema_assertion forbidden_columns_absent requires forbidden_columns")
        expectations.append(
            {
                "expectation_type": "expect_table_columns_to_not_contain_set",
                "kwargs": {
                    "column_set": forbidden_columns,
                },
                "meta": dict(meta),
            }
        )
        return expectations

    raise GxExpectationBuildError(f"GX lowerer does not yet support schema_assertion measure '{schema_assertion}'")


def _build_custom_query_assertion_expectations(
    *,
    semantic_ir: RuleDslIrDocument,
    rule_id: str | None,
    artifact_key: str | None,
) -> list[dict[str, Any]]:
    rule = semantic_ir.rule
    if not isinstance(rule.measure, RuleDslIrQueryMeasure):
        raise GxExpectationBuildError("custom_query_assertion requires a query measure")
    if rule.scope.dataset is None:
        raise GxExpectationBuildError("custom_query_assertion requires dataset scope")
    if any(
        value is not None
        for value in (
            rule.scope.row_filter,
            rule.scope.join,
            rule.scope.grouping,
            rule.scope.time_window,
            rule.scope.comparison,
        )
    ):
        raise GxExpectationBuildError("GX lowerer does not yet support non-dataset scope for custom_query_assertion")

    if not rule.measure.comparison_query or not rule.measure.comparison_data_source_name:
        raise GxExpectationBuildError(
            "custom_query_assertion requires comparison_data_source_name and comparison_query"
        )
    if not isinstance(rule.expectation, RuleDslIrThresholdExpectation):
        raise GxExpectationBuildError("custom_query_assertion requires a threshold expectation")
    if rule.expectation.unit not in {None, "percent"}:
        raise GxExpectationBuildError("custom_query_assertion only supports percent thresholds")
    if rule.expectation.operator != "gte":
        raise GxExpectationBuildError("custom_query_assertion only supports operator 'gte'")
    try:
        mostly_threshold = float(rule.expectation.value)
    except (TypeError, ValueError) as exc:
        raise GxExpectationBuildError("dsl.rule.expectation.value must be numeric for custom_query_assertion") from exc
    if mostly_threshold < 0.0 or mostly_threshold > 100.0:
        raise GxExpectationBuildError("dsl.rule.expectation.value must be between 0 and 100 for custom_query_assertion")

    mostly = mostly_threshold / 100.0
    return [
        {
            "expectation_type": "expect_query_results_to_match_comparison",
            "kwargs": {
                "base_query": rule.measure.query,
                "comparison_data_source_name": rule.measure.comparison_data_source_name,
                "comparison_query": rule.measure.comparison_query,
                "mostly": mostly,
            },
            "meta": _build_meta(rule_id=rule_id, artifact_key=artifact_key),
        }
    ]


def _compile_intermediate_model(*, expression: str, rule_id: str | None, artifact_key: str | None) -> dict[str, Any]:
    compiled = compile_rule_to_intermediate_model(
        rule_id=str(rule_id or artifact_key or "rule-dsl-v2"),
        rule_version_id=str(artifact_key or rule_id or "rule-dsl-v2"),
        filter_expression=expression,
        join_definition=None,
    )
    if bool(compiled.get("compilable", True)):
        return compiled

    diagnostics = [
        str(item.get("message") or "DQ DSL compilation failed")
        for item in (compiled.get("diagnostics") or [])
        if isinstance(item, Mapping)
    ]
    detail = diagnostics[0] if diagnostics else "DQ DSL compilation failed"
    raise GxExpectationBuildError(detail)


def _require_percent_threshold_100(expectation: RuleDslIrThresholdExpectation) -> None:
    if expectation.operator != "gte" or expectation.unit != "percent":
        raise GxExpectationBuildError("row_assertion requires threshold operator 'gte' and unit 'percent'")
    if expectation.value != 100:
        raise GxExpectationBuildError("row_assertion requires a 100 percent threshold")


def _require_duration_threshold(expectation: RuleDslIrThresholdExpectation) -> None:
    if expectation.operator != "lte" or expectation.unit != "duration":
        raise GxExpectationBuildError("freshness_assertion requires threshold operator 'lte' and unit 'duration'")


def _require_subject_column(subject: Any) -> str:
    column = str(getattr(subject, "column", None) or "").strip()
    if not column:
        raise GxExpectationBuildError("GX lowering requires a single subject column")
    return column


def _require_subject_columns(subject: Any) -> list[str]:
    columns = [str(value).strip() for value in list(getattr(subject, "columns", None) or []) if str(value).strip()]
    if columns:
        return columns
    column = str(getattr(subject, "column", None) or "").strip()
    if column:
        return [column]
    raise GxExpectationBuildError("GX lowering requires at least one subject column")


def _require_zero_count_threshold(expectation: RuleDslIrThresholdExpectation, *, metric: str) -> None:
    if expectation.operator != "lte" or expectation.unit != "count" or expectation.value != 0:
        raise GxExpectationBuildError(
            f"{metric} lowering only preserves an exact zero-threshold count bound"
        )


def _missing_percent_to_success_threshold(expectation: RuleDslIrThresholdExpectation) -> float:
    if expectation.value is None:
        raise GxExpectationBuildError("missing_percent lowering requires a threshold value")
    try:
        failure_rate = float(expectation.value)
    except Exception as exc:
        raise GxExpectationBuildError("missing_percent lowering requires a numeric threshold") from exc
    if failure_rate < 0.0 or failure_rate > 100.0:
        raise GxExpectationBuildError("missing_percent threshold must be between 0 and 100")
    return 100.0 - failure_rate


def _invert_threshold_operator(operator: str) -> str:
    normalized = str(operator or "").strip().lower()
    if normalized == "lte":
        return "gte"
    if normalized == "lt":
        return "gt"
    if normalized == "gte":
        return "lte"
    if normalized == "gt":
        return "lt"
    if normalized == "between":
        raise GxExpectationBuildError("missing_percent lowering does not support 'between' thresholds")
    raise GxExpectationBuildError(f"Unsupported threshold operator '{operator}'")


def _duration_to_days(expectation: RuleDslIrThresholdExpectation) -> int:
    raw_value = str(expectation.value or "").strip().upper()
    match = re.fullmatch(r"P(?P<days>\d+)D", raw_value)
    if match is None:
        raise GxExpectationBuildError("freshness_assertion requires whole-day ISO-8601 durations such as P3D")
    return int(match.group("days"))
