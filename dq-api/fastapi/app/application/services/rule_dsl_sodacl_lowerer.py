from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from app.domain.entities import ValidationArtifactEnvelopeEntity
from app.domain.entities import build_validation_artifact_envelope_entity
from app.domain.entities.rule_dsl_capability_registry import RULE_DSL_BACKEND_CAPABILITY_REGISTRY
from app.domain.entities.rule_dsl_ir import RuleDslIrDatasetScope
from app.domain.entities.rule_dsl_ir import RuleDslIrDocument
from app.domain.entities.rule_dsl_ir import RuleDslIrMetricMeasure
from app.domain.entities.rule_dsl_ir import RuleDslIrSchemaContractExpectation
from app.domain.entities.rule_dsl_ir import RuleDslIrSchemaMeasure
from app.domain.entities.rule_dsl_ir import RuleDslIrThresholdExpectation


class SodaclExpectationBuildError(ValueError):
    pass


def build_sodacl_checks_from_rule_dsl_v2(
    *,
    semantic_ir: RuleDslIrDocument,
    rule_id: str | None = None,
    artifact_key: str | None = None,
) -> list[dict[str, Any]]:
    rule = semantic_ir.rule
    if not RULE_DSL_BACKEND_CAPABILITY_REGISTRY.supports(rule.kind, "sodacl"):
        raise SodaclExpectationBuildError(f"SodaCL does not support semantic rule kind '{rule.kind}'")

    if rule.kind == "metric_threshold":
        return _build_metric_threshold_checks(semantic_ir=semantic_ir, rule_id=rule_id, artifact_key=artifact_key)
    if rule.kind == "schema_assertion":
        return _build_schema_assertion_checks(semantic_ir=semantic_ir, rule_id=rule_id, artifact_key=artifact_key)
    if rule.kind == "freshness_assertion":
        return _build_freshness_assertion_checks(semantic_ir=semantic_ir, rule_id=rule_id, artifact_key=artifact_key)

    raise SodaclExpectationBuildError(
        f"SodaCL lowerer does not yet support semantic rule kind '{rule.kind}'"
    )


def build_sodacl_scan_payload_from_rule_dsl_v2(
    *,
    semantic_ir: RuleDslIrDocument,
    rule_id: str | None = None,
    artifact_key: str | None = None,
) -> dict[str, Any]:
    rule = semantic_ir.rule
    checks = build_sodacl_checks_from_rule_dsl_v2(
        semantic_ir=semantic_ir,
        rule_id=rule_id,
        artifact_key=artifact_key,
    )
    scope = _normalize_assignment_scope(rule.scope.dataset)
    return {
        "scanName": str(artifact_key or rule_id or "rule-dsl-v2").strip() or "rule-dsl-v2",
        "checks": checks,
        "ruleId": str(rule_id or artifact_key or "rule-dsl-v2"),
        "ruleKind": rule.kind,
        "scope": scope,
    }


def build_sodacl_artifact_envelope_from_rule_dsl_v2(
    *,
    semantic_ir: RuleDslIrDocument,
    validation_artifact_id: str,
    validation_artifact_version: int,
    assignment_scope: Mapping[str, Any] | None = None,
    resolved_data_object_version_ids: list[str] | None = None,
    rule_id: str | None = None,
    artifact_key: str | None = None,
    saved_by: str | None = None,
    source_pipeline: str = "rule-dsl-v2-sodacl-lowerer",
    status: str | None = None,
    artifact_hash: str | None = None,
    compiler_version: str = "dq-7.3.0",
) -> ValidationArtifactEnvelopeEntity:
    rule = semantic_ir.rule
    normalized_rule_id = str(rule_id or artifact_key or validation_artifact_id or "rule-dsl-v2").strip() or "rule-dsl-v2"
    normalized_version_ids = [
        str(value).strip()
        for value in (resolved_data_object_version_ids or [])
        if str(value).strip()
    ]
    if not normalized_version_ids and rule.scope.dataset is not None:
        candidate = str(rule.scope.dataset.data_object_version_id or "").strip()
        if candidate:
            normalized_version_ids = [candidate]
    if not normalized_version_ids:
        raise SodaclExpectationBuildError("SodaCL artifact envelope requires at least one resolved data object version id")

    normalized_assignment_scope = _normalize_assignment_scope(rule.scope.dataset, assignment_scope)
    payload = build_sodacl_scan_payload_from_rule_dsl_v2(
        semantic_ir=semantic_ir,
        rule_id=normalized_rule_id,
        artifact_key=artifact_key,
    )
    now_iso = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    evidence = _build_evidence_payload(rule.evidence)

    return build_validation_artifact_envelope_entity(
        {
            "validationArtifactId": validation_artifact_id,
            "validationArtifactVersion": validation_artifact_version,
            "artifactContractVersion": "v1",
            "engineType": "soda",
            "assignmentScope": normalized_assignment_scope,
            "resolvedExecutionScope": {"dataObjectVersionIds": normalized_version_ids},
            "compiledFrom": {
                "ruleIds": [normalized_rule_id],
                "compilerVersion": compiler_version,
                "generatedAt": now_iso,
            },
            "executionHints": {
                "recommendedEngineTarget": "soda",
                "primaryKeyFields": [],
                "businessKeyFields": [],
                "supportedExecutionShapes": ["single_object"],
                "evidence": evidence,
            },
            "runPlanning": {
                "engineTarget": "soda",
                "executionShape": "single_object",
                "groupingKey": "data_object_version_id",
                "groupingValues": normalized_version_ids,
                "traceability": {
                    "ruleId": normalized_rule_id,
                    "validationArtifactId": validation_artifact_id,
                    "validationArtifactVersion": validation_artifact_version,
                    "dataObjectVersionId": normalized_version_ids[0],
                },
            },
            "engineArtifact": {
                "engineType": "soda",
                "artifactKind": "soda_scan",
                "artifactSchemaVersion": "soda-scan/v1",
                "payload": payload,
            },
            "savedBy": saved_by,
            "sourcePipeline": source_pipeline,
            "status": status,
            "artifactHash": artifact_hash,
        }
    )


def _build_metric_threshold_checks(
    *,
    semantic_ir: RuleDslIrDocument,
    rule_id: str | None,
    artifact_key: str | None,
) -> list[dict[str, Any]]:
    rule = semantic_ir.rule
    if not isinstance(rule.measure, RuleDslIrMetricMeasure):
        raise SodaclExpectationBuildError("metric_threshold requires a metric measure")
    if not isinstance(rule.expectation, RuleDslIrThresholdExpectation):
        raise SodaclExpectationBuildError("metric_threshold requires a threshold expectation")
    _require_dataset_scope(semantic_ir=semantic_ir)
    _require_simple_scope(semantic_ir=semantic_ir)

    metric = rule.measure.metric
    subject_columns = _subject_columns_for_metric(rule.measure)

    if metric == "row_count":
        if subject_columns:
            raise SodaclExpectationBuildError("row_count lowering does not accept a subject")
        threshold_text = _threshold_text(rule.expectation, field_name="dsl.rule.expectation", allowed_unit="count")
        return [
            _build_check_item(
                metric=metric,
                subject_columns=[],
                expectation=rule.expectation,
                threshold_text=threshold_text,
                rule_id=rule_id,
                artifact_key=artifact_key,
            )
        ]

    if metric == "missing_percent":
        threshold_text = _threshold_text(rule.expectation, field_name="dsl.rule.expectation", allowed_unit="percent")
        return [
            _build_check_item(
                metric=metric,
                subject_columns=subject_columns,
                expectation=rule.expectation,
                threshold_text=threshold_text,
                rule_id=rule_id,
                artifact_key=artifact_key,
            )
        ]

    if metric in {"missing_count", "duplicate_count", "distinct_count"}:
        threshold_text = _threshold_text(rule.expectation, field_name="dsl.rule.expectation", allowed_unit="count")
        return [
            _build_check_item(
                metric=metric,
                subject_columns=subject_columns,
                expectation=rule.expectation,
                threshold_text=threshold_text,
                rule_id=rule_id,
                artifact_key=artifact_key,
            )
        ]

    if metric == "duplicate_percent":
        threshold_text = _threshold_text(rule.expectation, field_name="dsl.rule.expectation", allowed_unit="percent")
        return [
            _build_check_item(
                metric=metric,
                subject_columns=subject_columns,
                expectation=rule.expectation,
                threshold_text=threshold_text,
                rule_id=rule_id,
                artifact_key=artifact_key,
            )
        ]

    if metric in {"min", "max", "avg", "sum", "stddev"}:
        threshold_text = _threshold_text(rule.expectation, field_name="dsl.rule.expectation", allowed_unit=None)
        return [
            _build_check_item(
                metric=metric,
                subject_columns=subject_columns,
                expectation=rule.expectation,
                threshold_text=threshold_text,
                rule_id=rule_id,
                artifact_key=artifact_key,
            )
        ]

    raise SodaclExpectationBuildError(f"SodaCL lowerer does not yet support metric_threshold metric '{metric}'")


def _build_schema_assertion_checks(
    *,
    semantic_ir: RuleDslIrDocument,
    rule_id: str | None,
    artifact_key: str | None,
) -> list[dict[str, Any]]:
    rule = semantic_ir.rule
    if not isinstance(rule.measure, RuleDslIrSchemaMeasure):
        raise SodaclExpectationBuildError("schema_assertion requires a schema measure")
    if not isinstance(rule.expectation, RuleDslIrSchemaContractExpectation):
        raise SodaclExpectationBuildError("schema_assertion requires a schema_contract expectation")
    _require_dataset_scope(semantic_ir=semantic_ir)
    _require_simple_scope(semantic_ir=semantic_ir)

    checks: list[dict[str, Any]] = []
    if rule.expectation.required_columns:
        required_columns = [str(value).strip() for value in rule.expectation.required_columns if str(value).strip()]
        if not required_columns:
            raise SodaclExpectationBuildError("schema_assertion required_columns_present requires required_columns")
        checks.append(
            _build_schema_check_item(
                check_name="required_columns_present",
                text=f"required_columns_present({', '.join(required_columns)})",
                details={"requiredColumns": required_columns},
                rule_id=rule_id,
                artifact_key=artifact_key,
            )
        )

    if rule.expectation.forbidden_columns:
        forbidden_columns = [str(value).strip() for value in rule.expectation.forbidden_columns if str(value).strip()]
        if not forbidden_columns:
            raise SodaclExpectationBuildError("schema_assertion forbidden_columns_absent requires forbidden_columns")
        checks.append(
            _build_schema_check_item(
                check_name="forbidden_columns_absent",
                text=f"forbidden_columns_absent({', '.join(forbidden_columns)})",
                details={"forbiddenColumns": forbidden_columns},
                rule_id=rule_id,
                artifact_key=artifact_key,
            )
        )

    if rule.expectation.expected_types:
        typed_entries = {
            str(column).strip(): str(type_name).strip()
            for column, type_name in rule.expectation.expected_types.items()
            if str(column).strip() and str(type_name).strip()
        }
        if not typed_entries:
            raise SodaclExpectationBuildError("schema_assertion column_types_match requires expected_types")
        for column, type_name in typed_entries.items():
            checks.append(
                _build_schema_check_item(
                    check_name="column_types_match",
                    text=f"column_types_match({column}: {type_name})",
                    details={"column": column, "type": type_name},
                    rule_id=rule_id,
                    artifact_key=artifact_key,
                )
            )

    if rule.expectation.min_column_count is not None or rule.expectation.max_column_count is not None:
        checks.append(
            _build_schema_check_item(
                check_name="column_count_between",
                text=(
                    f"column_count_between(min={rule.expectation.min_column_count}, max={rule.expectation.max_column_count})"
                ),
                details={
                    "minColumnCount": rule.expectation.min_column_count,
                    "maxColumnCount": rule.expectation.max_column_count,
                },
                rule_id=rule_id,
                artifact_key=artifact_key,
            )
        )

    if rule.expectation.ordered_columns:
        ordered_columns = [str(value).strip() for value in rule.expectation.ordered_columns if str(value).strip()]
        if not ordered_columns:
            raise SodaclExpectationBuildError("schema_assertion column_order_matches requires ordered_columns")
        checks.append(
            _build_schema_check_item(
                check_name="column_order_matches",
                text=f"column_order_matches({', '.join(ordered_columns)})",
                details={"orderedColumns": ordered_columns},
                rule_id=rule_id,
                artifact_key=artifact_key,
            )
        )

    if not checks:
        raise SodaclExpectationBuildError("schema_assertion requires at least one schema clause")

    return checks


def _build_freshness_assertion_checks(
    *,
    semantic_ir: RuleDslIrDocument,
    rule_id: str | None,
    artifact_key: str | None,
) -> list[dict[str, Any]]:
    rule = semantic_ir.rule
    if not isinstance(rule.measure, RuleDslIrMetricMeasure):
        raise SodaclExpectationBuildError("freshness_assertion requires a metric measure")
    if rule.measure.metric != "freshness_age":
        raise SodaclExpectationBuildError("freshness_assertion requires metric 'freshness_age'")
    if not isinstance(rule.expectation, RuleDslIrThresholdExpectation):
        raise SodaclExpectationBuildError("freshness_assertion requires a threshold expectation")
    _require_dataset_scope(semantic_ir=semantic_ir)
    _require_simple_scope(semantic_ir=semantic_ir)

    subject_columns = _subject_columns_for_metric(rule.measure)
    if len(subject_columns) != 1:
        raise SodaclExpectationBuildError("freshness_assertion requires exactly one subject column")
    if rule.expectation.operator != "lte" or rule.expectation.unit != "duration":
        raise SodaclExpectationBuildError("freshness_assertion requires threshold operator 'lte' and unit 'duration'")

    duration_text = _normalize_iso8601_day_duration(rule.expectation.value)
    return [
        _build_check_item(
            metric=rule.measure.metric,
            subject_columns=subject_columns,
            expectation=rule.expectation,
            threshold_text=duration_text,
            rule_id=rule_id,
            artifact_key=artifact_key,
        )
    ]


def _build_check_item(
    *,
    metric: str,
    subject_columns: list[str],
    expectation: RuleDslIrThresholdExpectation,
    threshold_text: str,
    rule_id: str | None,
    artifact_key: str | None,
) -> dict[str, Any]:
    return {
        "checkType": "metric_threshold",
        "metric": metric,
        "subjectColumns": subject_columns,
        "operator": expectation.operator,
        "threshold": threshold_text,
        "text": _build_metric_check_text(
            metric=metric,
            subject_columns=subject_columns,
            operator=expectation.operator,
            threshold_text=threshold_text,
        ),
        "ruleId": str(rule_id or artifact_key or "rule-dsl-v2"),
    }


def _build_schema_check_item(
    *,
    check_name: str,
    text: str,
    details: dict[str, Any],
    rule_id: str | None,
    artifact_key: str | None,
) -> dict[str, Any]:
    return {
        "checkType": "schema_assertion",
        "checkName": check_name,
        "details": details,
        "text": text,
        "ruleId": str(rule_id or artifact_key or "rule-dsl-v2"),
    }


def _build_metric_check_text(*, metric: str, subject_columns: list[str], operator: str, threshold_text: str) -> str:
    subject_text = ""
    if subject_columns:
        subject_text = f"({', '.join(subject_columns)})"
    operator_symbol = _threshold_operator_symbol(operator)
    return f"{metric}{subject_text} {operator_symbol} {threshold_text}"


def _threshold_operator_symbol(operator: str) -> str:
    normalized = str(operator or "").strip().lower()
    if normalized == "gt":
        return ">"
    if normalized == "gte":
        return ">="
    if normalized == "lt":
        return "<"
    if normalized == "lte":
        return "<="
    raise SodaclExpectationBuildError(f"Unsupported threshold operator '{operator}'")


def _threshold_text(
    expectation: RuleDslIrThresholdExpectation,
    *,
    field_name: str,
    allowed_unit: str | None,
) -> str:
    if expectation.operator == "between":
        raise SodaclExpectationBuildError(f"{field_name} does not support threshold operator 'between'")
    if allowed_unit is not None and expectation.unit != allowed_unit:
        raise SodaclExpectationBuildError(f"{field_name} requires threshold unit '{allowed_unit}'")
    if allowed_unit is None and expectation.unit not in {None, "raw"}:
        raise SodaclExpectationBuildError(f"{field_name} requires threshold unit 'raw' or no unit")
    return _format_numeric_value(expectation.value, field_name=field_name)


def _format_numeric_value(value: Any, *, field_name: str) -> str:
    if value is None:
        raise SodaclExpectationBuildError(f"{field_name} requires a threshold value")
    if isinstance(value, bool):
        raise SodaclExpectationBuildError(f"{field_name} requires a numeric threshold value")
    try:
        numeric_value = float(value)
    except (TypeError, ValueError) as exc:
        raise SodaclExpectationBuildError(f"{field_name} requires a numeric threshold value") from exc
    if numeric_value.is_integer():
        return str(int(numeric_value))
    return format(numeric_value, "g")


def _normalize_iso8601_day_duration(value: Any) -> str:
    duration_value = str(value or "").strip().upper()
    if not duration_value.startswith("P") or not duration_value.endswith("D"):
        raise SodaclExpectationBuildError("freshness_assertion requires whole-day ISO-8601 durations such as P3D")
    try:
        day_count = int(duration_value[1:-1])
    except (TypeError, ValueError) as exc:
        raise SodaclExpectationBuildError("freshness_assertion requires whole-day ISO-8601 durations such as P3D") from exc
    if day_count < 0:
        raise SodaclExpectationBuildError("freshness_assertion requires a non-negative day duration")
    return f"P{day_count}D"


def _subject_columns_for_metric(measure: RuleDslIrMetricMeasure) -> list[str]:
    subject = measure.subject
    if subject is None:
        return []
    columns = [str(value).strip() for value in list(subject.columns or []) if str(value).strip()]
    if not columns and subject.column is not None:
        normalized_column = str(subject.column).strip()
        if normalized_column:
            columns.append(normalized_column)
    return columns


def _normalize_assignment_scope(
    dataset_scope: RuleDslIrDatasetScope | None,
    override: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if isinstance(override, Mapping):
        normalized_override = {
            "dataObjectId": override.get("dataObjectId") or override.get("data_object_id"),
            "datasetId": override.get("datasetId") or override.get("dataset_id"),
            "dataProductId": override.get("dataProductId") or override.get("data_product_id"),
        }
        if any(value not in {None, ""} for value in normalized_override.values()):
            return normalized_override

    if dataset_scope is None:
        return {}

    return {
        "dataObjectId": dataset_scope.data_object_id,
        "datasetId": dataset_scope.dataset_id,
        "dataProductId": dataset_scope.data_product_id,
    }


def _require_dataset_scope(*, semantic_ir: RuleDslIrDocument) -> None:
    if semantic_ir.rule.scope.dataset is None:
        raise SodaclExpectationBuildError("SodaCL lowering requires dataset scope")


def _require_simple_scope(*, semantic_ir: RuleDslIrDocument) -> None:
    scope = semantic_ir.rule.scope
    if any(
        value is not None
        for value in (
            scope.row_filter,
            scope.join,
            scope.grouping,
            scope.time_window,
            scope.comparison,
        )
    ):
        raise SodaclExpectationBuildError(
            "SodaCL lowering does not yet support row_filter, join, grouping, time_window, or comparison scope"
        )


def _build_evidence_payload(evidence: Any) -> dict[str, Any]:
    failed_rows = getattr(evidence, "failed_rows", None)
    if failed_rows is None:
        return {}
    return {
        "failedRows": {
            "mode": getattr(failed_rows, "mode", None),
            "limit": getattr(failed_rows, "limit", None),
            "includeRowIdentifier": getattr(failed_rows, "include_row_identifier", None),
            "includePrimaryKey": getattr(failed_rows, "include_primary_key", None),
        },
        "emitCompiledArtifact": getattr(evidence, "emit_compiled_artifact", None),
        "emitGeneratedSql": getattr(evidence, "emit_generated_sql", None),
    }


__all__ = [
    "SodaclExpectationBuildError",
    "build_sodacl_artifact_envelope_from_rule_dsl_v2",
    "build_sodacl_checks_from_rule_dsl_v2",
    "build_sodacl_scan_payload_from_rule_dsl_v2",
]
