"""Trino execution pipeline for rule execution and artifact persistence."""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from datetime import timezone
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dq_plan_execution_contract import build_execution_metadata
from dq_plan_execution_contract import build_observability_summary
from dq_plan_execution_persistence import persist_execution_payload
from dq_plan_lowerers import _infer_rule_family
from trino_adapter import AGGREGATE_RULE_TYPES
from trino_adapter import QUERY_RULE_TYPES
from trino_adapter import ROW_RULE_TYPES
from trino_adapter import lower_aggregate_rule_to_trino
from trino_adapter import lower_query_rule_to_trino
from trino_adapter import lower_row_rule_to_trino
from trino_adapter import validate_trino_compatibility
from trino_executor import TrinoExecutionError
from trino_executor import TrinoQueryResult
from trino_executor import TrinoExecutor

logger = logging.getLogger(__name__)


def _build_trino_failed_check(plan: dict[str, Any], failure_message: str, *, failure_stage: str) -> dict[str, Any]:
    rule_type = plan["rule_type"]
    params = dict(plan.get("params") or {})
    return {
        "rule_id": plan.get("rule_id"),
        "engine_type": "trino",
        "engine_target": "trino_sql",
        "check_name": rule_type or "unknown",
        "rule_type": rule_type or "unknown",
        "rule_family": _infer_rule_family(rule_type),
        "table": plan.get("table"),
        "column": plan.get("column"),
        "params": params,
        "query": plan.get("query"),
        "reason": failure_message,
        "failure_stage": failure_stage,
    }


def _build_trino_failure_metrics(
    plan: dict[str, Any],
    *,
    duration_ms: float,
    failure_stage: str,
    error_code: str | None,
    result_row_count: int,
) -> dict[str, Any]:
    rule_type = plan["rule_type"]
    return {
        "engine_type": "trino",
        "engine_target": "trino_sql",
        "rule_id": plan.get("rule_id"),
        "rule_type": rule_type,
        "rule_family": _infer_rule_family(rule_type),
        "failure_stage": failure_stage,
        "failure_code": error_code,
        "result": "failed",
        "passed_count": 0,
        "failed_count": 1,
        "duration_ms": duration_ms,
        "storage_kind": None,
        "storage_uri": None,
        "failure_count": 1,
        "failed_check_count": 1,
        "failed_row_count": int(result_row_count),
        "failed_rule_count": 1,
    }


def _build_trino_error_management(error_code: str | None, failure_message: str) -> dict[str, Any]:
    return {
        "storage_strategy": "inline",
        "total_error_count": 1,
        "chunk_count": 1,
        "overflowed": False,
        "sampled_error_rows": [
            {
                "engine_type": "trino",
                "error_code": error_code,
                "message": failure_message,
            }
        ],
    }


@dataclass
class ExecutionPlan:
    rule: dict[str, Any]
    executor: Any
    config: dict[str, Any] = field(default_factory=dict)
    plan: dict[str, Any] = field(init=False)

    def __post_init__(self) -> None:
        self.plan = self._build_plan()

    def _build_plan(self) -> dict[str, Any]:
        rule_type = str(self.rule.get("type") or "").strip().lower()
        unsupported = validate_trino_compatibility(self.rule)
        if unsupported:
            raise ValueError(f"Trino compatibility issues: {unsupported}")

        if rule_type in QUERY_RULE_TYPES:
            lowered = lower_query_rule_to_trino(self.rule)
        elif rule_type in ROW_RULE_TYPES:
            lowered = lower_row_rule_to_trino(self.rule)
        elif rule_type in AGGREGATE_RULE_TYPES:
            lowered = lower_aggregate_rule_to_trino(self.rule)
        else:
            raise ValueError(f"Unsupported rule type: {rule_type}")

        return {
            "rule_id": self.rule.get("id"),
            "rule_type": rule_type,
            "table": self.rule.get("table"),
            "column": self.rule.get("column"),
            "params": dict(self.rule.get("params") or {}),
            "lowered_rule": lowered,
            "query": lowered["query"],
            "expectation": lowered["expectation"],
        }

    def execute(self) -> dict[str, Any]:
        plan = self.plan
        rule_type = plan["rule_type"]
        started_at = time.perf_counter()
        started_at_iso = datetime.now(timezone.utc).isoformat()
        result_rows: Any = []
        client: Any = None

        try:
            client = self.executor.create_connection()
            timeout_ms = int(self.config.get("timeout_ms", 30000))
            result_rows = self.executor.execute_query(client, plan["query"], timeout=timeout_ms)
            validation = self._validate_result(result_rows, plan)
            row_summary = _summarize_result_rows(result_rows)
            metrics = self.executor.collect_query_metrics(plan["query"], started_at, row_summary["result_row_count"])
            completed_at_iso = datetime.now(timezone.utc).isoformat()
            passed_count = int(bool(validation.get("passed")))
            failed_count = int(not bool(validation.get("passed")))
            execution_metadata = build_execution_metadata(
                rule_id=plan["rule_id"],
                engine_type="trino",
                runtime="trino",
                started_at=started_at_iso,
                completed_at=completed_at_iso,
                duration_ms=float(metrics.get("duration_ms", 0)),
                source_row_count=int(row_summary["result_row_count"]),
                execution_name="dq-engine-trino",
                guardrails={"sample_limit": int(getattr(self.executor, "config", {}).get("max_result_sample_size", 1000))},
            )
            observability_summary = build_observability_summary(
                engine_type="trino",
                result="passed" if passed_count else "failed",
                passed_count=passed_count,
                failed_count=failed_count,
                rule_family=rule_type,
                duration_ms=float(metrics.get("duration_ms", 0)),
                storage_kind=None,
                storage_uri=None,
            )
            return {
                "ok": True,
                "engine_type": "trino",
                "rule_id": plan["rule_id"],
                "rule_type": rule_type,
                "result_status": "passed" if passed_count else "failed",
                "passed_count": passed_count,
                "failed_count": failed_count,
                "result": validation,
                "metrics": metrics,
                "execution_metadata": execution_metadata,
                "quarantine_artifact": {},
                "error_management": {},
                "observability_summary": observability_summary,
                **row_summary,
                "lowered_rule": plan["lowered_rule"],
                "compiled_artifact": {
                    "engine_type": "trino",
                    "engine_target": "trino_sql",
                    "rule": plan["lowered_rule"],
                    "error_management": {},
                },
            }
        except (TrinoExecutionError, ValueError) as exc:
            metrics = self.executor.collect_query_metrics(plan["query"], started_at, len(result_rows))
            duration_ms = float(metrics.get("duration_ms", 0))
            completed_at_iso = datetime.now(timezone.utc).isoformat()
            failure_message = str(exc)
            failure_code = getattr(exc, "error_code", None) or (
                "DQ_TRINO_VALIDATION_ERROR" if isinstance(exc, ValueError) else "DQ_TRINO_EXECUTION_ERROR"
            )
            query_id = getattr(exc, "query_id", None)
            failed_check = _build_trino_failed_check(plan, failure_message, failure_stage="execute")
            failure_metrics = _build_trino_failure_metrics(
                plan,
                duration_ms=duration_ms,
                failure_stage="execute",
                error_code=failure_code,
                result_row_count=len(result_rows),
            )
            error_management = _build_trino_error_management(failure_code, failure_message)
            execution_metadata = build_execution_metadata(
                rule_id=plan["rule_id"],
                engine_type="trino",
                runtime="trino",
                started_at=started_at_iso,
                completed_at=completed_at_iso,
                duration_ms=duration_ms,
                source_row_count=int(len(result_rows)),
                execution_name="dq-engine-trino",
                guardrails={"sample_limit": int(getattr(self.executor, "config", {}).get("max_result_sample_size", 1000))},
            )
            observability_summary = build_observability_summary(
                engine_type="trino",
                result="failed",
                passed_count=0,
                failed_count=1,
                rule_family=rule_type,
                duration_ms=duration_ms,
                storage_kind=None,
                storage_uri=None,
            )
            return {
                "ok": False,
                "engine_type": "trino",
                "rule_id": plan["rule_id"],
                "rule_type": rule_type,
                "result_status": "failed",
                "passed_count": 0,
                "failed_count": 1,
                "failure_code": failure_code,
                "failure_message": failure_message,
                "failed_check": failed_check,
                "failure_metrics": failure_metrics,
                "trace": {
                    "exception_type": exc.__class__.__name__,
                    "message": failure_message,
                    "query_id": query_id,
                },
                "result": {
                    "passed": False,
                    "error": failure_message,
                    "error_code": failure_code,
                    "query_id": query_id,
                },
                "metrics": metrics,
                "execution_metadata": execution_metadata,
                "quarantine_artifact": {},
                "error_management": error_management,
                "observability_summary": observability_summary,
                **_summarize_result_rows(result_rows),
                "lowered_rule": plan["lowered_rule"],
            }
        finally:
            if client is not None:
                close_connection = getattr(self.executor, "close_connection", None)
                if close_connection is not None:
                    close_connection(client)

    def _validate_result(self, result_rows: Any, plan: dict[str, Any]) -> dict[str, Any]:
        rule_type = plan["rule_type"]
        params = plan["params"]

        def _treat_as_scalar_result(rows: Any) -> bool:
            query_text = str(plan.get("query") or "").lower()
            aggregate_markers = ("count(", "sum(", "avg(", "min(", "max(", "stddev(", "distinct(")
            query_looks_scalar = any(marker in query_text for marker in aggregate_markers)
            if not query_looks_scalar:
                return False

            if isinstance(rows, TrinoQueryResult):
                return rows.row_count == 1 and len(rows.sample_rows) == 1

            sample_rows = list(rows or [])
            if len(sample_rows) != 1:
                return False

            first_row = sample_rows[0]
            if isinstance(first_row, dict):
                return len(first_row) == 1
            if isinstance(first_row, (list, tuple)):
                return len(first_row) == 1
            return True

        if rule_type == "query":
            expected_count = params.get("expected_count")
            if expected_count is None:
                raise ValueError("query DQ rule requires expected_count")
            validation_options = {
                "expected_count": expected_count,
                "treat_first_cell_as_count": _treat_as_scalar_result(result_rows),
            }
            return self.executor.validate_query_result(
                result_rows,
                validation_options,
            )

        if rule_type in {"count", "sum", "avg", "min", "max", "distinct_count"}:
            expected_value = params.get("expected_value", params.get("expected_count"))
            if expected_value is None:
                raise ValueError(f"aggregate DQ rule '{plan['rule_id']}' requires an expected value")
            validation_options = {
                "expected_count": expected_value,
                "treat_first_cell_as_count": _treat_as_scalar_result(result_rows),
            }
            return self.executor.validate_query_result(
                result_rows,
                validation_options,
            )

        return self.executor.validate_query_result(result_rows, {"expected_count": len(result_rows)})


def _summarize_result_rows(result_rows: Any) -> dict[str, Any]:
    if isinstance(result_rows, TrinoQueryResult):
        return {
            "result_row_count": result_rows.row_count,
            "result_rows_sample": list(result_rows.sample_rows),
            "result_rows_truncated": result_rows.truncated,
        }

    sample_rows = list(result_rows or [])
    return {
        "result_row_count": len(sample_rows),
        "result_rows_sample": sample_rows,
        "result_rows_truncated": False,
    }


def create_trino_execution_plan(
    rule: dict[str, Any],
    *,
    config: dict[str, Any] | None = None,
    executor: Any | None = None,
) -> ExecutionPlan:
    return ExecutionPlan(rule, executor or TrinoExecutor(config=config), config=config or {})


def execute_trino_pipeline(plan: ExecutionPlan, *, output_dir: str | None = None) -> dict[str, Any]:
    result = plan.execute()
    if output_dir:
        persist_trino_artifacts(result, output_dir)
    return result


def persist_trino_artifacts(result: dict[str, Any], output_dir: str) -> list[str]:
    artifact_paths = persist_execution_payload(output_dir, result, artifact_prefix="trino")

    output_path = Path(output_dir)

    rows_path = output_path / "trino_results.json"
    rows_payload = {
        "engine_type": result.get("engine_type", "trino"),
        "rule_id": result.get("rule_id"),
        "rule_type": result.get("rule_type"),
        "ok": result.get("ok"),
        "result": result.get("result", {}),
        "metrics": result.get("metrics", {}),
        "result_row_count": result.get("result_row_count", 0),
        "result_rows_truncated": result.get("result_rows_truncated", False),
        "result_rows_sample": result.get("result_rows_sample", []),
        "query": (result.get("lowered_rule") or {}).get("query"),
    }
    rows_path.write_text(json.dumps(rows_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    artifact_paths.append(str(rows_path))

    lowered_rule = result.get("lowered_rule") or {}
    query = lowered_rule.get("query")
    if query:
        query_path = output_path / "trino_query.sql"
        query_path.write_text(f"{query}\n", encoding="utf-8")
        artifact_paths.append(str(query_path))

    return artifact_paths
