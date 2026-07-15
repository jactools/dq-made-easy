#!/usr/bin/env python3
"""Benchmark Trino Phase 1 lowerer and in-process execution pipeline paths.

Purpose:
- Measures Trino SQL lowering throughput for row, aggregate, and query rules.
- Measures Trino execution pipeline overhead with an injected in-memory executor.
- Verifies large-result guardrails keep persisted samples bounded while preserving full row counts.
- Writes JSON evidence suitable for milestone/test-proof records.

validate: groups=engine,performance
Version: 1.0
Last modified: 2026-06-30
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[2]
DQ_ENGINE_DIR = ROOT_DIR / "dq-engine"
if str(DQ_ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(DQ_ENGINE_DIR))

from dq_plan_lowerers_trino import lower_rule_to_trino  # noqa: E402
from trino_execution_adapter import create_trino_execution_plan  # noqa: E402
from trino_execution_adapter import execute_trino_pipeline  # noqa: E402
from trino_executor import TrinoQueryResult  # noqa: E402

APP_VERSION = os.environ.get("APP_VERSION", "0.11.5").strip() or "0.11.5"
WORKFLOW_LABEL = "dq-engine-trino-phase1-benchmark"


@dataclass(frozen=True)
class BenchmarkThresholds:
    min_lowering_rules_per_second: float
    min_pipeline_runs_per_second: float
    max_bounded_sample_rows: int


class BenchmarkExecutor:
    def __init__(self, result_rows: Any) -> None:
        self.result_rows = result_rows
        self.config = {"max_result_sample_size": 20}
        self.created_connections = 0
        self.closed_connections = 0

    def create_connection(self) -> object:
        self.created_connections += 1
        return object()

    def close_connection(self, client: object) -> None:
        self.closed_connections += 1

    def execute_query(self, client: object, query: str, timeout: int | None = None) -> Any:
        return self.result_rows

    def validate_query_result(self, result: Any, expected: dict[str, Any]) -> dict[str, Any]:
        expected_count = expected.get("expected_count")
        if expected.get("treat_first_cell_as_count"):
            sample_rows = result.sample_rows if isinstance(result, TrinoQueryResult) else list(result or [])
            if not sample_rows:
                actual_count = None
            else:
                first_row = sample_rows[0]
                if isinstance(first_row, dict):
                    actual_count = next(iter(first_row.values()), None)
                elif isinstance(first_row, (list, tuple)):
                    actual_count = first_row[0] if first_row else None
                else:
                    actual_count = first_row
        else:
            actual_count = len(result)
        passed = actual_count == expected_count
        return {
            "passed": passed,
            "actual_count": actual_count,
            "expected_count": expected_count,
            "failed_rows": [] if passed else [{"actual_count": actual_count, "expected_count": expected_count}],
            "details": {},
        }

    def collect_query_metrics(self, query: str, start_time: float, rows_returned: int) -> dict[str, Any]:
        return {
            "query_id": "benchmark-query",
            "duration_ms": int((time.perf_counter() - start_time) * 1000),
            "rows_returned": rows_returned,
            "warnings": [],
        }


def _positive_int_env(name: str, default: int) -> int:
    raw_value = os.environ.get(name, "").strip()
    if not raw_value:
        return default
    value = int(raw_value)
    if value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _positive_float_env(name: str, default: float) -> float:
    raw_value = os.environ.get(name, "").strip()
    if not raw_value:
        return default
    value = float(raw_value)
    if value <= 0:
        raise ValueError(f"{name} must be a positive number")
    return value


def _benchmark_rules() -> list[dict[str, Any]]:
    return [
        {"id": 1, "table": "customers", "column": "customer_id", "type": "not_null", "params": {}},
        {"id": 2, "table": "customers", "column": "status", "type": "equals", "params": {"expected": "active"}},
        {
            "id": 3,
            "table": "customers",
            "column": "amount",
            "type": "between",
            "params": {
                "min": 10,
                "max": 20,
                "where": {"column": "status", "operator": "=", "value": "active"},
            },
        },
        {"id": 4, "table": "customers", "type": "count", "params": {"expected_count": 100}},
        {
            "id": 5,
            "table": "customers",
            "column": "amount",
            "type": "sum",
            "params": {
                "expected_value": 1000,
                "where": {"column": "status", "operator": "=", "value": "active"},
                "having": {"operator": ">=", "value": 10},
            },
        },
        {"id": 6, "table": "customers", "column": "customer_id", "type": "distinct_count", "params": {"expected_count": 90}},
        {
            "id": 7,
            "table": "customers",
            "type": "query",
            "params": {"query": "SELECT COUNT(*) AS dq_count FROM customers", "expected_count": 100},
        },
    ]


def _pipeline_rule() -> dict[str, Any]:
    return {
        "id": 9001,
        "table": "customers",
        "type": "query",
        "params": {"query": "SELECT COUNT(*) AS dq_count FROM customers", "expected_count": 1},
    }


def _time_call(callable_obj: Any) -> float:
    started = time.perf_counter()
    callable_obj()
    return time.perf_counter() - started


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = int(round((len(ordered) - 1) * percentile))
    return ordered[index]


def _benchmark_lowering(iterations: int) -> dict[str, Any]:
    rules = _benchmark_rules()

    def run() -> None:
        for index in range(iterations):
            lower_rule_to_trino(rules[index % len(rules)])

    elapsed_seconds = _time_call(run)
    rules_per_second = iterations / elapsed_seconds if elapsed_seconds else float("inf")
    return {
        "iterations": iterations,
        "elapsed_seconds": elapsed_seconds,
        "rules_per_second": rules_per_second,
        "rule_count": len(rules),
    }


def _benchmark_pipeline(iterations: int) -> dict[str, Any]:
    rule = _pipeline_rule()
    durations: list[float] = []

    def run_once() -> None:
        executor = BenchmarkExecutor([[1]])
        plan = create_trino_execution_plan(rule, executor=executor, config={"timeout_ms": 1000})
        result = execute_trino_pipeline(plan)
        if not result.get("ok") or not result.get("result", {}).get("passed"):
            raise RuntimeError(f"Pipeline benchmark produced a failed result: {result}")

    started = time.perf_counter()
    for _ in range(iterations):
        iteration_started = time.perf_counter()
        run_once()
        durations.append(time.perf_counter() - iteration_started)
    elapsed_seconds = time.perf_counter() - started
    runs_per_second = iterations / elapsed_seconds if elapsed_seconds else float("inf")
    return {
        "iterations": iterations,
        "elapsed_seconds": elapsed_seconds,
        "runs_per_second": runs_per_second,
        "mean_ms": statistics.mean(durations) * 1000.0,
        "p95_ms": _percentile(durations, 0.95) * 1000.0,
    }


def _benchmark_large_result_guardrail() -> dict[str, Any]:
    executor = BenchmarkExecutor(TrinoQueryResult(rows=[(index,) for index in range(20)], row_count=2_500_000, truncated=True))
    rule = {
        "id": 9002,
        "table": "customers",
        "type": "query",
        "params": {"query": "SELECT customer_id FROM customers", "expected_count": 2_500_000},
    }
    with tempfile.TemporaryDirectory(prefix="trino-benchmark-") as temp_dir:
        plan = create_trino_execution_plan(rule, executor=executor, config={"timeout_ms": 1000})
        started = time.perf_counter()
        result = execute_trino_pipeline(plan, output_dir=temp_dir)
        elapsed_seconds = time.perf_counter() - started
        persisted = json.loads((Path(temp_dir) / "trino_results.json").read_text(encoding="utf-8"))

    return {
        "elapsed_seconds": elapsed_seconds,
        "result_row_count": result["result_row_count"],
        "result_rows_sample_count": len(result["result_rows_sample"]),
        "result_rows_truncated": result["result_rows_truncated"],
        "persisted_row_count": persisted["result_row_count"],
        "persisted_sample_count": len(persisted["result_rows_sample"]),
        "persisted_truncated": persisted["result_rows_truncated"],
    }


def _evaluate(results: dict[str, Any], thresholds: BenchmarkThresholds) -> dict[str, bool]:
    return {
        "lowering_throughput_within_bounds": results["lowering"]["rules_per_second"] >= thresholds.min_lowering_rules_per_second,
        "pipeline_throughput_within_bounds": results["pipeline"]["runs_per_second"] >= thresholds.min_pipeline_runs_per_second,
        "large_result_sample_within_bounds": results["large_result_guardrail"]["result_rows_sample_count"] <= thresholds.max_bounded_sample_rows,
        "large_result_persisted_sample_within_bounds": results["large_result_guardrail"]["persisted_sample_count"] <= thresholds.max_bounded_sample_rows,
        "large_result_row_count_preserved": results["large_result_guardrail"]["persisted_row_count"] == 2_500_000,
        "large_result_truncation_preserved": bool(results["large_result_guardrail"]["persisted_truncated"]),
    }


def _default_output_path() -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return ROOT_DIR / "test-results" / "evidence" / APP_VERSION / "api" / f"{timestamp}-dq-engine-trino-phase1-benchmark" / "benchmark.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark Trino Phase 1 lowerer and pipeline paths.")
    parser.add_argument("--output", type=Path, default=_default_output_path(), help="Path to write benchmark JSON evidence")
    parser.add_argument(
        "--lowering-iterations",
        type=int,
        default=_positive_int_env("DQ_TRINO_BENCHMARK_LOWERING_ITERATIONS", 10000),
        help="Number of lowering operations to benchmark",
    )
    parser.add_argument(
        "--pipeline-iterations",
        type=int,
        default=_positive_int_env("DQ_TRINO_BENCHMARK_PIPELINE_ITERATIONS", 1000),
        help="Number of in-process pipeline executions to benchmark",
    )
    parser.add_argument(
        "--min-lowering-rules-per-second",
        type=float,
        default=_positive_float_env("DQ_TRINO_BENCHMARK_MIN_LOWERING_RPS", 1000.0),
        help="Minimum accepted Trino lowering throughput",
    )
    parser.add_argument(
        "--min-pipeline-runs-per-second",
        type=float,
        default=_positive_float_env("DQ_TRINO_BENCHMARK_MIN_PIPELINE_RPS", 100.0),
        help="Minimum accepted in-process pipeline throughput",
    )
    parser.add_argument(
        "--max-bounded-sample-rows",
        type=int,
        default=_positive_int_env("DQ_TRINO_BENCHMARK_MAX_SAMPLE_ROWS", 20),
        help="Maximum expected sample row count for large-result guardrail benchmark",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    thresholds = BenchmarkThresholds(
        min_lowering_rules_per_second=args.min_lowering_rules_per_second,
        min_pipeline_runs_per_second=args.min_pipeline_runs_per_second,
        max_bounded_sample_rows=args.max_bounded_sample_rows,
    )

    results = {
        "lowering": _benchmark_lowering(args.lowering_iterations),
        "pipeline": _benchmark_pipeline(args.pipeline_iterations),
        "large_result_guardrail": _benchmark_large_result_guardrail(),
    }
    checks = _evaluate(results, thresholds)
    status = "passed" if all(checks.values()) else "failed"
    payload = {
        "validation": WORKFLOW_LABEL,
        "status": status,
        "executed_at_utc": datetime.now(UTC).isoformat(),
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "thresholds": thresholds.__dict__,
        "checks": checks,
        "results": results,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
