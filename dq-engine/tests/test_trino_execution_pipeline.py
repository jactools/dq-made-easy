from __future__ import annotations

import sys
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from execution_dispatch import process_engine_dispatch_message
from gx_dispatch_types import GxWorkerConfig
from trino_execution_pipeline import create_trino_execution_plan
from trino_execution_pipeline import execute_trino_pipeline
from trino_executor import TrinoExecutionError
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


class FailingExecutor(RecordingExecutor):
    def __init__(self) -> None:
        super().__init__([])

    def execute_query(self, client: object, query: str, timeout: int | None = None) -> list[object]:
        self.executed_queries.append((query, timeout))
        raise TrinoExecutionError(
            "Trino query error: line 1:15: Table 'system.runtime.missing_table' does not exist",
            query_id="query-missing-table",
            error_code="DQ_TRINO_QUERY_ERROR",
        )

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


def test_query_rule_execution_persists_structured_trino_error_payload(tmp_path: Path) -> None:
    executor = FailingExecutor()
    rule = {
        "id": 504,
        "table": "system.runtime.missing_table",
        "type": "query",
        "params": {
            "query": "SELECT count(*) AS dq_count FROM system.runtime.missing_table",
            "expected_count": 1,
        },
    }

    plan = create_trino_execution_plan(rule, executor=executor, config={"timeout_ms": 1500})
    result = execute_trino_pipeline(plan, output_dir=str(tmp_path))

    assert result["ok"] is False
    assert result["result_status"] == "failed"
    assert result["failure_code"] == "DQ_TRINO_QUERY_ERROR"
    assert "missing_table" in result["failure_message"]
    assert result["failed_check"]["engine_type"] == "trino"
    assert result["failed_check"]["engine_target"] == "trino_sql"
    assert result["failed_check"]["table"] == "system.runtime.missing_table"
    assert result["failed_check"]["failure_stage"] == "execute"
    assert result["failure_metrics"]["failure_code"] == "DQ_TRINO_QUERY_ERROR"
    assert result["trace"]["query_id"] == "query-missing-table"
    assert result["error_management"]["storage_strategy"] == "inline"
    assert result["error_management"]["total_error_count"] == 1
    assert executor.closed_connections == 1

    persisted_execution = json.loads((tmp_path / "trino_execution.json").read_text(encoding="utf-8"))
    persisted_errors = json.loads((tmp_path / "trino_errors.json").read_text(encoding="utf-8"))

    assert persisted_execution["failure_code"] == "DQ_TRINO_QUERY_ERROR"
    assert persisted_execution["failed_check"]["table"] == "system.runtime.missing_table"
    assert persisted_execution["trace"]["query_id"] == "query-missing-table"
    assert persisted_errors["failure_code"] == "DQ_TRINO_QUERY_ERROR"
    assert persisted_errors["failure_message"] == result["failure_message"]
    assert persisted_errors["failed_check"]["engine_target"] == "trino_sql"
    assert persisted_errors["failure_metrics"]["failure_stage"] == "execute"
    assert persisted_errors["trace"]["query_id"] == "query-missing-table"
    assert persisted_errors["sampled_error_rows"][0]["error_code"] == "DQ_TRINO_QUERY_ERROR"


def test_trino_structured_error_is_reported_through_generic_dispatch(tmp_path: Path) -> None:
    executor = FailingExecutor()
    rule = {
        "id": 505,
        "table": "system.runtime.missing_table",
        "type": "query",
        "params": {
            "query": "SELECT count(*) AS dq_count FROM system.runtime.missing_table",
            "expected_count": 1,
        },
    }
    failure_result = execute_trino_pipeline(create_trino_execution_plan(rule, executor=executor, config={}))
    reports: list[dict[str, object]] = []

    class DummyTokenProvider:
        def get_token(self, *, correlation_id: str | None = None) -> str:
            return "token"

    def fake_report_run(*args: object, **kwargs: object) -> None:
        reports.append({"action": "report_run", **kwargs})

    def fake_report_progress(*args: object, **kwargs: object) -> None:
        reports.append({"action": "report_progress", **kwargs})

    config = GxWorkerConfig(
        redis_url="redis://localhost:6379/0",
        queue_key="dq-gx:execution-dispatch",
        processing_queue_key="dq-gx:execution-dispatch:processing",
        heartbeat_key="dq-gx:execution-dispatch:heartbeat",
        heartbeat_ttl_seconds=30,
        heartbeat_interval_seconds=10,
        max_rows=1000,
        poll_timeout_seconds=5,
        api_url="http://localhost",
        spark_master="local[1]",
        spark_ui_port=4044,
        s3_endpoint=None,
        s3_access_key=None,
        s3_secret_key=None,
        s3_region=None,
        s3_path_style_access=False,
        s3_ssl_enabled=None,
    )

    process_engine_dispatch_message(
        config,
        payload={
            "engine_type": "trino",
            "rule_payload": rule,
            "output_dir": str(tmp_path),
        },
        run_id="run-trino-error",
        correlation_id="corr-trino-error",
        requested_by="tester",
        report_run_fn=fake_report_run,
        report_progress_fn=fake_report_progress,
        token_provider_factory=lambda: DummyTokenProvider(),
        execute_payload_fn=lambda **kwargs: failure_result,
    )

    failed_report = next(item for item in reports if item.get("new_status") == "failed")
    assert failed_report["failure_code"] == "DQ_TRINO_QUERY_ERROR"
    assert "missing_table" in str(failed_report["failure_message"])

    result_summary = failed_report.get("result_summary", {})
    assert result_summary.get("failure_code") == "DQ_TRINO_QUERY_ERROR"
    assert result_summary.get("failed_check", {}).get("engine_target") == "trino_sql"
    assert result_summary.get("failure_metrics", {}).get("failure_stage") == "execute"
    assert result_summary.get("trace", {}).get("query_id") == "query-missing-table"

    details = failed_report.get("details", {})
    assert details.get("failure_code") == "DQ_TRINO_QUERY_ERROR"
    assert details.get("failed_check", {}).get("table") == "system.runtime.missing_table"
    assert details.get("failure_metrics", {}).get("failure_code") == "DQ_TRINO_QUERY_ERROR"


def test_aggregate_rule_execution_uses_scalar_validation() -> None:
    executor = RecordingExecutor([{"dq_count": 4}])
    rule = {
        "id": 506,
        "table": "customers",
        "type": "count",
        "params": {"expected_count": 4},
    }

    result = execute_trino_pipeline(create_trino_execution_plan(rule, executor=executor, config={}))

    assert result["ok"] is True
    assert result["rule_type"] == "count"
    assert executor.validations == [{"expected_count": 4, "treat_first_cell_as_count": True}]
    assert result["result"]["passed"] is True


def test_aggregate_rule_missing_expected_value_returns_structured_validation_error(tmp_path: Path) -> None:
    executor = RecordingExecutor([[4]])
    rule = {
        "id": 507,
        "table": "customers",
        "column": "amount",
        "type": "sum",
        "params": {"expected_value": 4},
    }
    plan = create_trino_execution_plan(rule, executor=executor, config={})
    del plan.plan["params"]["expected_value"]

    result = execute_trino_pipeline(plan, output_dir=str(tmp_path))

    assert result["ok"] is False
    assert result["failure_code"] == "DQ_TRINO_VALIDATION_ERROR"
    assert "requires an expected value" in result["failure_message"]
    assert result["failed_check"]["rule_family"] == "aggregate"
    assert json.loads((tmp_path / "trino_errors.json").read_text(encoding="utf-8"))["failure_code"] == "DQ_TRINO_VALIDATION_ERROR"


def test_execute_trino_pipeline_without_output_dir_does_not_persist(tmp_path: Path) -> None:
    executor = RecordingExecutor([[1]])
    rule = {
        "id": 508,
        "table": "customers",
        "type": "query",
        "params": {"query": "SELECT 1", "expected_count": 1},
    }

    result = execute_trino_pipeline(create_trino_execution_plan(rule, executor=executor, config={}))

    assert result["ok"] is True
    assert list(tmp_path.iterdir()) == []
