from __future__ import annotations

import traceback
from typing import Any

SUPPORTED_RUNTIME_ENGINES = {"gx", "soda", "spark_expectations", "trino"}
SUPPORTED_RUNTIME_CAPABILITIES = {
    "gx": {"row_dq", "aggregate_dq", "query_dq", "expectation_dq"},
    "soda": {"row_dq", "aggregate_dq", "query_dq"},
    "spark_expectations": {"row_dq", "aggregate_dq", "query_dq"},
    "trino": {"row_dq", "aggregate_dq", "query_dq"},
}
ENGINE_TYPE_ALIASES = {
    "great_expectations": "gx",
    "great-expectations": "gx",
    "pyspark": "spark_expectations",
    "pyspark_native": "spark_expectations",
    "spark": "spark_expectations",
    "sodacl": "soda",
}
ENGINE_TARGETS = {
    "gx": "pyspark",
    "soda": "pyspark",
    "spark_expectations": "pyspark",
    "trino": "trino_sql",
}
ROW_RULE_TYPES = {"not_null", "min", "max", "equals", "not_equal", "between", "in", "not_in", "is_null"}
AGGREGATE_RULE_TYPES = {"count", "sum", "avg", "stddev", "row_count", "unique", "missing_count", "duplicate_count", "distinct_count"}


def normalize_engine_type(engine_type: str | None) -> str:
    normalized_engine = (engine_type or "").strip().lower()
    return ENGINE_TYPE_ALIASES.get(normalized_engine, normalized_engine)


def _resolve_engine_target(engine_type: str | None) -> str | None:
    normalized_engine = normalize_engine_type(engine_type)
    return ENGINE_TARGETS.get(normalized_engine)


def _infer_rule_family(rule_type: str | None) -> str:
    normalized_rule_type = (rule_type or "").strip().lower()
    if normalized_rule_type in ROW_RULE_TYPES:
        return "row"
    if normalized_rule_type in AGGREGATE_RULE_TYPES:
        return "aggregate"
    if normalized_rule_type == "query":
        return "query"
    return "unknown"


def _build_failure_metrics(*, rule: dict[str, Any], engine_type: str | None, failure_stage: str) -> dict[str, Any]:
    normalized_engine = normalize_engine_type(engine_type)
    rule_type = str(rule.get("type") or "").strip().lower()
    return {
        "engine_type": normalized_engine or engine_type,
        "engine_target": _resolve_engine_target(normalized_engine),
        "rule_id": rule.get("id"),
        "rule_type": rule_type,
        "rule_family": _infer_rule_family(rule_type),
        "failure_stage": failure_stage,
        "result": "failed",
        "passed_count": 0,
        "failed_count": 0,
        "duration_ms": None,
        "storage_kind": None,
        "storage_uri": None,
        "failure_count": 1,
        "failed_check_count": 1,
        "failed_row_count": 0,
        "failed_rule_count": 1,
    }


def build_failure_envelope(
    rule: dict[str, Any],
    *,
    engine_type: str | None,
    failure_code: str,
    failure_message: str,
    failure_stage: str = "compile",
    exception: Exception | None = None,
    compiled_artifact: dict[str, Any] | None = None,
    failure_metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_engine = normalize_engine_type(engine_type)
    rule_type = str(rule.get("type") or "").strip()
    metrics = dict(failure_metrics or _build_failure_metrics(rule=rule, engine_type=normalized_engine, failure_stage=failure_stage))
    trace = {
        "exception_type": exception.__class__.__name__ if exception else None,
        "message": failure_message,
        "traceback": "".join(traceback.TracebackException.from_exception(exception).format()) if exception else None,
    }
    failed_check = {
        "rule_id": rule.get("id"),
        "engine_type": normalized_engine or engine_type,
        "engine_target": _resolve_engine_target(normalized_engine),
        "check_name": rule_type or "unknown",
        "rule_type": rule_type or "unknown",
        "rule_family": _infer_rule_family(rule_type),
        "table": rule.get("table"),
        "column": rule.get("column"),
        "params": rule.get("params") or {},
        "reason": failure_message,
        "failure_stage": failure_stage,
    }
    return {
        "ok": False,
        "engine_type": normalized_engine or engine_type,
        "engine_target": _resolve_engine_target(normalized_engine),
        "rule_id": rule.get("id"),
        "result": "failed",
        "failed_check": failed_check,
        "failure_code": failure_code,
        "failure_message": failure_message,
        "failure_metrics": metrics,
        "metrics": metrics,
        "observability_summary": metrics,
        "error_management": {},
        "execution_metadata": {},
        "quarantine_artifact": {},
        "compiled_artifact": compiled_artifact or {},
        "trace": trace,
    }


def _format_expectation_literal(value: Any) -> str:
    if isinstance(value, str):
        return repr(value)
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if value is None:
        return "NULL"
    return str(value)


def get_runtime_capabilities(engine_type: str | None) -> set[str]:
    normalized_engine = normalize_engine_type(engine_type)
    if normalized_engine not in SUPPORTED_RUNTIME_ENGINES:
        raise ValueError(f"unsupported runtime engine: {engine_type!r}")
    return set(SUPPORTED_RUNTIME_CAPABILITIES[normalized_engine])


def get_runtime_lowerer(engine_type: str | None) -> Any:
    normalized_engine = normalize_engine_type(engine_type)
    if normalized_engine == "gx":
        return lower_rule_to_gx
    if normalized_engine == "soda":
        return lower_rule_to_soda
    if normalized_engine == "spark_expectations":
        from spark_expectations_adapter import lower_rule_to_spark_expectations

        return lower_rule_to_spark_expectations
    if normalized_engine == "trino":
        return lower_rule_to_trino
    raise ValueError(f"unsupported runtime engine: {engine_type!r}")


def lower_rule_to_gx(rule: dict[str, Any]) -> dict[str, Any]:
    from rule_translator import translate

    expectation = translate(rule)
    return {
        "engine_type": "gx",
        "engine_target": "pyspark",
        "expectation": type(expectation).__name__,
        "kwargs": expectation.to_json_dict() if hasattr(expectation, "to_json_dict") else {},
    }


def lower_rule_to_soda(rule: dict[str, Any]) -> dict[str, Any]:
    raise ValueError(f"Soda lowering is not implemented for rule {rule.get('id')!r}")


def lower_rule_to_trino(rule: dict[str, Any]) -> dict[str, Any]:
    rule_type = str(rule.get("type") or "").strip()
    column = str(rule.get("column") or "").strip()
    table = str(rule.get("table") or "source").strip() or "source"
    params = rule.get("params") or {}

    if params.get("expression") is not None:
        raise ValueError("unsupported trino construct: custom expression")
    if params.get("sql_predicate") is not None:
        raise ValueError("unsupported trino construct: SQL predicate")
    if params.get("window") is not None:
        raise ValueError("unsupported trino construct: window/analytic operation")
    if isinstance(params.get("columns"), list) and len(params.get("columns")) > 1:
        raise ValueError("unsupported trino construct: multi-column predicate")

    if rule_type in {"not_null", "min", "max", "equals", "not_equal", "between", "in", "not_in", "is_null"}:
        if rule_type == "not_null":
            expectation = f"{column} IS NOT NULL"
        elif rule_type == "min":
            expectation = f"{column} >= {params.get('min')}"
        elif rule_type == "max":
            expectation = f"{column} <= {params.get('max')}"
        elif rule_type == "equals":
            expectation = f"{column} == {_format_expectation_literal(params.get('expected'))}"
        elif rule_type == "not_equal":
            expectation = f"{column} != {_format_expectation_literal(params.get('expected'))}"
        elif rule_type == "between":
            expectation = f"{column} BETWEEN {_format_expectation_literal(params.get('min'))} AND {_format_expectation_literal(params.get('max'))}"
        elif rule_type == "in":
            values = params.get("values") or []
            formatted_values = ", ".join(_format_expectation_literal(value) for value in values)
            expectation = f"{column} IN ({formatted_values})"
        elif rule_type == "not_in":
            values = params.get("values") or []
            formatted_values = ", ".join(_format_expectation_literal(value) for value in values)
            expectation = f"{column} NOT IN ({formatted_values})"
        else:
            expectation = f"{column} IS NULL"
        return {
            "engine_type": "trino",
            "engine_target": "trino_sql",
            "rule_type": "row_dq",
            "expectation": expectation,
            "action_if_failed": "quarantine",
            "query": f"SELECT * FROM {table} WHERE {expectation}",
        }

    if rule_type == "count":
        expected_count = params.get("expected_count")
        return {
            "engine_type": "trino",
            "engine_target": "trino_sql",
            "rule_type": "aggregate_dq",
            "expectation": f"COUNT(*) == {_format_expectation_literal(expected_count)}",
            "action_if_failed": "quarantine",
            "query": f"SELECT COUNT(*) AS dq_count FROM {table}",
        }

    if rule_type == "sum":
        expected_value = params.get("expected_value")
        return {
            "engine_type": "trino",
            "engine_target": "trino_sql",
            "rule_type": "aggregate_dq",
            "expectation": f"SUM({column}) == {_format_expectation_literal(expected_value)}",
            "action_if_failed": "quarantine",
            "query": f"SELECT SUM({column}) AS dq_sum FROM {table}",
        }

    if rule_type == "query":
        query_text = str(params.get("query") or "").strip()
        if not query_text:
            raise ValueError("unsupported trino construct: query without text")
        return {
            "engine_type": "trino",
            "engine_target": "trino_sql",
            "rule_type": "query_dq",
            "expectation": "query result count == expected_count",
            "action_if_failed": "quarantine",
            "query": query_text,
        }

    raise ValueError(f"unsupported rule type for Trino adapter: {rule_type!r}")


def build_compiled_artifact_for_engine(rule: dict[str, Any], *, engine_type: str | None) -> dict[str, Any]:
    normalized_engine = normalize_engine_type(engine_type)
    try:
        if normalized_engine == "gx":
            lowered_rule = get_runtime_lowerer(normalized_engine)(rule)
            return {
                "ok": True,
                "rule_id": rule.get("id"),
                "engine_type": "gx",
                "expectation": lowered_rule["expectation"],
                "kwargs": lowered_rule["kwargs"],
            }

        if normalized_engine == "soda":
            raise ValueError(f"unsupported runtime engine: {engine_type!r}")

        if normalized_engine == "spark_expectations":
            from spark_expectations_adapter import build_error_management_plan

            lowered_rule = get_runtime_lowerer(normalized_engine)(rule)
            error_plan = build_error_management_plan(
                (
                    {"row_id": row_id, "reason": f"synthetic-failure-{row_id}"}
                    for row_id in range(int(rule.get("params", {}).get("synthetic_error_count", 0)))
                ),
                chunk_size=int(rule.get("params", {}).get("error_chunk_size", 10_000)),
                max_samples=int(rule.get("params", {}).get("error_sample_size", 20)),
            )
            return {
                "ok": True,
                "rule_id": rule.get("id"),
                "engine_type": "spark_expectations",
                "lowered_rule": lowered_rule,
                "compiled_artifact": {
                    "engine_type": "spark_expectations",
                    "engine_target": "pyspark",
                    "rule": lowered_rule,
                    "error_management": error_plan,
                },
            }

        if normalized_engine == "trino":
            lowered_rule = lower_rule_to_trino(rule)
            return {
                "ok": True,
                "rule_id": rule.get("id"),
                "engine_type": "trino",
                "lowered_rule": lowered_rule,
                "compiled_artifact": {
                    "engine_type": "trino",
                    "engine_target": "trino_sql",
                    "rule": lowered_rule,
                    "error_management": {},
                },
            }

        raise ValueError(f"unsupported runtime engine: {engine_type!r}")
    except Exception as exc:
        failure_message = str(exc)
        if "unsupported runtime engine" in failure_message.lower():
            failure_code = "DQ_UNSUPPORTED_RUNTIME_ENGINE"
        elif "not implemented" in failure_message.lower():
            failure_code = "DQ_LOWERER_NOT_IMPLEMENTED"
        elif "unsupported" in failure_message.lower():
            failure_code = "DQ_LOWERER_UNSUPPORTED_CONSTRUCT"
        else:
            failure_code = "DQ_LOWERER_FAILURE"
        return build_failure_envelope(
            rule,
            engine_type=normalized_engine or engine_type,
            failure_code=failure_code,
            failure_message=failure_message,
            failure_stage="compile",
            exception=exc,
        )
