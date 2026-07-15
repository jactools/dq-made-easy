"""Runtime lowerer registry and shared lowering helpers (Layer 2).

This module owns the lowerer registry, normalization helpers, failure
envelope construction, and per-engine lowering dispatch. Per-engine
lowering logic lives in `dq_plan_lowerers_gx.py`, `dq_plan_lowerers_trino.py`,
and `dq_plan_lowerers_soda.py`.

All constants and shared utilities that support lowering are kept here so
per-engine modules stay small and focused.
"""

from __future__ import annotations

import traceback
from typing import Any

# ---------------------------------------------------------------------------
# Registry constants
# ---------------------------------------------------------------------------

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
ROW_RULE_TYPES = {
    "not_null",
    "min",
    "max",
    "equals",
    "not_equal",
    "between",
    "in",
    "not_in",
    "is_null",
}
AGGREGATE_RULE_TYPES = {
    "count",
    "sum",
    "avg",
    "stddev",
    "row_count",
    "unique",
    "missing_count",
    "duplicate_count",
    "distinct_count",
}

# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------


def normalize_engine_type(engine_type: str | None) -> str:
    """Normalize an engine type string to its canonical form."""
    normalized_engine = (engine_type or "").strip().lower()
    return ENGINE_TYPE_ALIASES.get(normalized_engine, normalized_engine)


def _resolve_engine_target(engine_type: str | None) -> str | None:
    """Resolve the runtime target for a normalized engine type."""
    normalized_engine = normalize_engine_type(engine_type)
    return ENGINE_TARGETS.get(normalized_engine)


def _infer_rule_family(rule_type: str | None) -> str:
    """Infer the rule family (row, aggregate, query) from a rule type string."""
    normalized_rule_type = (rule_type or "").strip().lower()
    if normalized_rule_type in ROW_RULE_TYPES:
        return "row"
    if normalized_rule_type in AGGREGATE_RULE_TYPES:
        return "aggregate"
    if normalized_rule_type == "query":
        return "query"
    return "unknown"


# ---------------------------------------------------------------------------
# Failure envelope helpers
# ---------------------------------------------------------------------------


def _build_failure_metrics(*, rule: dict[str, Any], engine_type: str | None, failure_stage: str) -> dict[str, Any]:
    """Build failure metrics for a failed lowering attempt."""
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
    """Build a complete failure envelope for a lowering/compilation error."""
    normalized_engine = normalize_engine_type(engine_type)
    rule_type = str(rule.get("type") or "").strip()
    metrics = dict(
        failure_metrics
        or _build_failure_metrics(
            rule=rule,
            engine_type=normalized_engine,
            failure_stage=failure_stage,
        )
    )
    trace = {
        "exception_type": exception.__class__.__name__ if exception else None,
        "message": failure_message,
        "traceback": (
            "".join(traceback.TracebackException.from_exception(exception).format())
            if exception
            else None
        ),
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


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


def _format_expectation_literal(value: Any) -> str:
    """Format an expectation parameter value as a literal string."""
    if isinstance(value, str):
        return repr(value)
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if value is None:
        return "NULL"
    return str(value)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def get_runtime_capabilities(engine_type: str | None) -> set[str]:
    """Return the set of supported capabilities for an engine type."""
    normalized_engine = normalize_engine_type(engine_type)
    if normalized_engine not in SUPPORTED_RUNTIME_ENGINES:
        raise ValueError(f"unsupported runtime engine: {engine_type!r}")
    return set(SUPPORTED_RUNTIME_CAPABILITIES[normalized_engine])


def get_runtime_lowerer(engine_type: str | None) -> Any:
    """Resolve and return the lowering function for a given engine type."""
    normalized_engine = normalize_engine_type(engine_type)
    if normalized_engine == "gx":
        from dq_plan_lowerers_gx import lower_rule_to_gx

        return lower_rule_to_gx
    if normalized_engine == "soda":
        from dq_plan_lowerers_soda import lower_rule_to_soda

        return lower_rule_to_soda
    if normalized_engine == "spark_expectations":
        from spark_expectations_execution_adapter import (
            lower_rule_to_spark_expectations,
        )

        return lower_rule_to_spark_expectations
    if normalized_engine == "trino":
        from dq_plan_lowerers_trino import lower_rule_to_trino

        return lower_rule_to_trino
    raise ValueError(f"unsupported runtime engine: {engine_type!r}")


# ---------------------------------------------------------------------------
# Compilation
# ---------------------------------------------------------------------------


def build_compiled_artifact_for_engine(
    rule: dict[str, Any],
    *,
    engine_type: str | None,
) -> dict[str, Any]:
    """Build a compiled artifact for a rule targeting a specific engine."""
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
            from spark_expectations_execution_adapter import (
                build_error_management_plan,
            )

            lowered_rule = get_runtime_lowerer(normalized_engine)(rule)
            error_plan = build_error_management_plan(
                (
                    {
                        "row_id": row_id,
                        "reason": f"synthetic-failure-{row_id}",
                    }
                    for row_id in range(
                        int(
                            rule.get("params", {}).get(
                                "synthetic_error_count", 0
                            )
                        )
                    )
                ),
                chunk_size=int(
                    rule.get("params", {}).get("error_chunk_size", 10_000)
                ),
                max_samples=int(
                    rule.get("params", {}).get("error_sample_size", 20)
                ),
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
            from dq_plan_lowerers_trino import lower_rule_to_trino

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
