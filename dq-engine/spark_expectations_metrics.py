from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class _SparkExpectationsMetricsState:
    executions_total: int = 0
    passed_total: int = 0
    failed_total: int = 0
    failed_rows_total: int = 0
    quarantine_artifacts_total: int = 0
    execution_duration_ms_sum: float = 0.0
    execution_duration_ms_count: int = 0


class SparkExpectationsMetrics:
    def __init__(self) -> None:
        self._state = _SparkExpectationsMetricsState()

    def record_execution(
        self,
        *,
        result: str,
        duration_ms: float | None,
        failed_count: int | None,
        quarantine_artifact_written: bool,
    ) -> None:
        state = self._state
        state.executions_total += 1
        if str(result).strip().lower() == "passed":
            state.passed_total += 1
        else:
            state.failed_total += 1

        failed_count_value = int(failed_count or 0)
        state.failed_rows_total += failed_count_value
        if quarantine_artifact_written:
            state.quarantine_artifacts_total += 1

        if duration_ms is not None:
            state.execution_duration_ms_sum += float(duration_ms)
            state.execution_duration_ms_count += 1

    def snapshot(self) -> dict[str, Any]:
        return {
            "executions_total": self._state.executions_total,
            "passed_total": self._state.passed_total,
            "failed_total": self._state.failed_total,
            "failed_rows_total": self._state.failed_rows_total,
            "quarantine_artifacts_total": self._state.quarantine_artifacts_total,
            "execution_duration_ms_sum": self._state.execution_duration_ms_sum,
            "execution_duration_ms_count": self._state.execution_duration_ms_count,
        }


def build_metrics_summary(*, result: dict[str, Any], execution_metadata: dict[str, Any], quarantine_artifact: dict[str, Any] | None, rule_type: str) -> dict[str, Any]:
    return {
        "engine_type": "spark_expectations",
        "result": result.get("result", "passed"),
        "passed_count": result.get("passed_count", 0),
        "failed_count": result.get("failed_count", 0),
        "rule_family": _determine_rule_family(rule_type),
        "duration_ms": execution_metadata.get("duration_ms"),
        "storage_kind": (quarantine_artifact or {}).get("storage_kind"),
        "storage_uri": (quarantine_artifact or {}).get("storage_uri"),
    }


def _determine_rule_family(rule_type: str) -> str:
    normalized_rule_type = str(rule_type or "").strip().lower()
    if normalized_rule_type in {
        "not_null",
        "min",
        "max",
        "equals",
        "not_equal",
        "between",
        "in",
        "not_in",
        "is_null",
        "contains",
        "starts_with",
        "ends_with",
        "min_length",
        "max_length",
        "regex",
    }:
        return "row"
    if normalized_rule_type in {"count", "sum", "avg", "stddev", "unique", "missing_count", "duplicate_count", "row_count", "distinct_count"}:
        return "aggregate"
    if normalized_rule_type == "query":
        return "query"
    return "row"


def render_prometheus_metrics(metrics: SparkExpectationsMetrics | None = None) -> str:
    state = (metrics or spark_expectations_metrics).snapshot()
    lines = [
        "# HELP dq_spark_expectations_executions_total Total Spark Expectations executions",
        "# TYPE dq_spark_expectations_executions_total counter",
        f"dq_spark_expectations_executions_total {state['executions_total']}",
        "# HELP dq_spark_expectations_passed_total Number of Spark Expectations executions that passed",
        "# TYPE dq_spark_expectations_passed_total counter",
        f"dq_spark_expectations_passed_total {state['passed_total']}",
        "# HELP dq_spark_expectations_failed_total Number of Spark Expectations executions that failed",
        "# TYPE dq_spark_expectations_failed_total counter",
        f"dq_spark_expectations_failed_total {state['failed_total']}",
        "# HELP dq_spark_expectations_failed_rows_total Number of failed rows observed in Spark Expectations executions",
        "# TYPE dq_spark_expectations_failed_rows_total counter",
        f"dq_spark_expectations_failed_rows_total {state['failed_rows_total']}",
        "# HELP dq_spark_expectations_quarantine_artifacts_total Number of quarantine artifacts written by Spark Expectations executions",
        "# TYPE dq_spark_expectations_quarantine_artifacts_total counter",
        f"dq_spark_expectations_quarantine_artifacts_total {state['quarantine_artifacts_total']}",
        "# HELP dq_spark_expectations_execution_duration_ms_sum Total execution duration for Spark Expectations executions in milliseconds",
        "# TYPE dq_spark_expectations_execution_duration_ms_sum counter",
        f"dq_spark_expectations_execution_duration_ms_sum {state['execution_duration_ms_sum']}",
        "# HELP dq_spark_expectations_execution_duration_ms_count Number of Spark Expectations executions contributing to duration totals",
        "# TYPE dq_spark_expectations_execution_duration_ms_count counter",
        f"dq_spark_expectations_execution_duration_ms_count {state['execution_duration_ms_count']}",
        "",
    ]
    return "\n".join(lines)


spark_expectations_metrics = SparkExpectationsMetrics()
