from __future__ import annotations

import sys
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trino_execution_pipeline import create_trino_execution_plan
from trino_execution_pipeline import execute_trino_pipeline
from trino_executor import TrinoQueryResult


class RecordingExecutor:
    def __init__(self, result_rows: list[object]) -> None:
        self.result_rows = result_rows
        self.created_connections = 0
        self.executed_queries: list[tuple[str, int | None]] = []
        self.validations: list[dict[str, object]] = []
        self.metric_calls: list[tuple[str, int]] = []
        self.closed_connections = 0

    def create_connection(self) -> object:
        self.created_connections += 1
        return object()

    def close_connection(self, client: object) -> None:
        self.closed_connections += 1

    def execute_query(self, client: object, query: str, timeout: int | None = None) -> list[object]:
        self.executed_queries.append((query, timeout))
        return self.result_rows

    def validate_query_result(self, result: list[object], expected: dict[str, object]) -> dict[str, object]:
        self.validations.append(expected)
        expected_count = expected.get("expected_count")
        if expected.get("treat_first_cell_as_count"):
            if not result:
                actual_count = None
            else:
                first_row = result[0]
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

    def collect_query_metrics(self, query: str, start_time: float, rows_returned: int) -> dict[str, object]:
        self.metric_calls.append((query, rows_returned))
        return {
            "query_id": "query-1",
            "duration_ms": 1,
            "rows_returned": rows_returned,
            "warnings": [],
        }


def test_query_rule_execution_uses_expected_count_and_scalar_result() -> None:
    executor = RecordingExecutor([[3]])
    rule = {
        "id": 501,
        "table": "customers",
        "type": "query",
        "params": {
            "query": "SELECT COUNT(*) AS dq_count FROM customers",
            "expected_count": 3,
        },
    }

    plan = create_trino_execution_plan(rule, executor=executor, config={"timeout_ms": 1234})
    result = execute_trino_pipeline(plan)

    assert result["ok"] is True
    assert result["engine_type"] == "trino"
    assert result["rule_type"] == "query"
    assert executor.created_connections == 1
    assert executor.closed_connections == 1
    assert executor.executed_queries == [("SELECT COUNT(*) AS dq_count FROM customers", 1234)]
    assert executor.validations == [{"expected_count": 3, "treat_first_cell_as_count": True}]
    assert result["result"]["passed"] is True
    assert result["result"]["actual_count"] == 3
    assert result["metrics"]["rows_returned"] == 1


def test_query_rule_execution_reports_mismatch_when_scalar_result_differs() -> None:
    executor = RecordingExecutor([[2]])
    rule = {
        "id": 502,
        "table": "customers",
        "type": "query",
        "params": {
            "query": "SELECT COUNT(*) AS dq_count FROM customers",
            "expected_count": 3,
        },
    }

    plan = create_trino_execution_plan(rule, executor=executor, config={})
    result = execute_trino_pipeline(plan)

    assert result["ok"] is True
    assert result["result"]["passed"] is False
    assert result["result"]["actual_count"] == 2
    assert result["result"]["expected_count"] == 3


def test_query_rule_execution_persists_bounded_results_and_query_artifact(tmp_path: Path) -> None:
    executor = RecordingExecutor(TrinoQueryResult(rows=[(0,), (1,), (2,)], row_count=2_500_000, truncated=True))
    rule = {
        "id": 503,
        "table": "customers",
        "type": "query",
        "params": {
            "query": "SELECT customer_id FROM customers WHERE customer_id IS NOT NULL",
            "expected_count": 2_500_000,
        },
    }

    plan = create_trino_execution_plan(rule, executor=executor, config={"timeout_ms": 1500})
    result = execute_trino_pipeline(plan, output_dir=str(tmp_path))

    assert result["ok"] is True
    assert result["result_status"] == "passed"
    assert result["result_row_count"] == 2_500_000
    assert result["result_rows_truncated"] is True
    assert len(result["result_rows_sample"]) == 3
    assert result["execution_metadata"]["engine_type"] == "trino"
    assert result["observability_summary"]["engine_type"] == "trino"
    assert (tmp_path / "trino_execution.json").exists()
    assert (tmp_path / "trino_errors.json").exists()
    assert (tmp_path / "trino_results.json").exists()
    assert (tmp_path / "trino_query.sql").exists()

    persisted_execution = json.loads((tmp_path / "trino_execution.json").read_text(encoding="utf-8"))
    persisted_errors = json.loads((tmp_path / "trino_errors.json").read_text(encoding="utf-8"))
    persisted_results = json.loads((tmp_path / "trino_results.json").read_text(encoding="utf-8"))

    assert persisted_execution["result_row_count"] == 2_500_000
    assert persisted_execution["result_rows_truncated"] is True
    assert persisted_execution["result_rows_sample"] == [[0], [1], [2]]
    assert persisted_execution["result_status"] == "passed"
    assert persisted_execution["execution_metadata"]["engine_type"] == "trino"
    assert persisted_errors["execution_metadata"]["engine_type"] == "trino"
    assert persisted_results["result_row_count"] == 2_500_000
    assert persisted_results["result_rows_truncated"] is True
    assert persisted_results["result_rows_sample"] == [[0], [1], [2]]
    assert persisted_results["query"] == "SELECT customer_id FROM customers WHERE customer_id IS NOT NULL"
