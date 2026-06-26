from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DQ_UTILS_ROOT = ROOT.parent / "dq-utils" / "src"
if str(DQ_UTILS_ROOT) not in sys.path:
    sys.path.insert(0, str(DQ_UTILS_ROOT))

from gx_dispatch_worker import GxWorkerConfig
from gx_dispatch_worker import process_dispatch_message
from main import app
from main import compile_rule_payload
from spark_expectations_adapter import build_error_management_plan
from spark_expectations_adapter import lower_rule_to_spark_expectations


def test_lower_rule_to_spark_expectations_for_not_null_rule() -> None:
    rule = {
        "id": 42,
        "table": "customers",
        "column": "customer_id",
        "type": "not_null",
        "params": {},
    }

    lowered = lower_rule_to_spark_expectations(rule)

    assert lowered["engine_type"] == "spark_expectations"
    assert lowered["engine_target"] == "pyspark"
    assert lowered["rule_type"] == "row_dq"
    assert lowered["expectation"] == "customer_id IS NOT NULL"
    assert lowered["action_if_failed"] == "quarantine"


@pytest.mark.parametrize(
    ("rule_type", "params", "expected_expectation"),
    [
        ("min", {"min": 10}, "customer_id >= 10"),
        ("max", {"max": 100}, "customer_id <= 100"),
    ],
)
def test_lower_rule_to_spark_expectations_supports_row_level_bounds(
    rule_type: str, params: dict[str, object], expected_expectation: str
) -> None:
    rule = {
        "id": 44,
        "table": "customers",
        "column": "customer_id",
        "type": rule_type,
        "params": params,
    }

    lowered = lower_rule_to_spark_expectations(rule)

    assert lowered["engine_type"] == "spark_expectations"
    assert lowered["engine_target"] == "pyspark"
    assert lowered["rule_type"] == "row_dq"
    assert lowered["expectation"] == expected_expectation
    assert lowered["action_if_failed"] == "quarantine"


def test_lower_rule_to_spark_expectations_rejects_unsupported_rule() -> None:
    rule = {
        "id": 43,
        "table": "customers",
        "column": "email",
        "type": "unsupported",
        "params": {},
    }

    with pytest.raises(ValueError, match="unsupported"):
        lower_rule_to_spark_expectations(rule)


def test_build_error_management_plan_handles_large_error_batches() -> None:
    failed_rows = ({"row_id": row_id, "reason": f"bad-{row_id}"} for row_id in range(250_000))

    plan = build_error_management_plan(failed_rows, chunk_size=10_000, max_samples=20)

    assert plan["total_error_count"] == 250_000
    assert plan["chunk_count"] == 25
    assert plan["storage_strategy"] == "chunked"
    assert plan["overflowed"] is True
    assert len(plan["sampled_error_rows"]) == 20
    assert plan["sampled_error_rows"][0]["row_id"] == 0
    assert plan["sampled_error_rows"][-1]["row_id"] == 19


def test_compile_rule_payload_supports_spark_expectations_engine() -> None:
    rule = {
        "id": 99,
        "table": "customers",
        "column": "customer_id",
        "type": "not_null",
        "params": {},
    }

    compiled = compile_rule_payload(rule, engine_type="spark_expectations")

    assert compiled["ok"] is True
    assert compiled["rule_id"] == 99
    assert compiled["engine_type"] == "spark_expectations"
    assert compiled["lowered_rule"]["rule_type"] == "row_dq"
    assert compiled["lowered_rule"]["expectation"] == "customer_id IS NOT NULL"


def test_compile_rule_payload_emits_neutral_artifact_envelope_for_spark_expectations() -> None:
    rule = {
        "id": 100,
        "table": "customers",
        "column": "customer_id",
        "type": "not_null",
        "params": {},
    }

    compiled = compile_rule_payload(rule, engine_type="spark_expectations")

    assert compiled["compiled_artifact"]["engine_type"] == "spark_expectations"
    assert compiled["compiled_artifact"]["engine_target"] == "pyspark"
    assert compiled["compiled_artifact"]["rule"]["expectation"] == "customer_id IS NOT NULL"


def test_compile_rule_payload_includes_chunked_error_management_for_synthetic_batch() -> None:
    rule = {
        "id": 101,
        "table": "customers",
        "column": "customer_id",
        "type": "not_null",
        "params": {
            "synthetic_error_count": 25_000,
            "error_chunk_size": 5_000,
            "error_sample_size": 10,
        },
    }

    compiled = compile_rule_payload(rule, engine_type="spark_expectations")

    error_management = compiled["compiled_artifact"]["error_management"]
    assert error_management["total_error_count"] == 25_000
    assert error_management["chunk_count"] == 5
    assert error_management["storage_strategy"] == "chunked"
    assert error_management["overflowed"] is True
    assert len(error_management["sampled_error_rows"]) == 10


def test_execute_endpoint_persists_artifacts(tmp_path: Path) -> None:
    client = TestClient(app)

    response = client.post(
        "/execute",
        json={
            "id": 103,
            "table": "customers",
            "column": "customer_id",
            "type": "not_null",
            "params": {
                "synthetic_error_count": 8,
                "error_chunk_size": 4,
                "error_sample_size": 3,
                "synthetic_row_count": 20,
            },
            "output_dir": str(tmp_path),
            "engine_type": "spark_expectations",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["failed_count"] == 8
    assert payload["passed_count"] == 12
    assert (tmp_path / "spark_expectations_execution.json").exists()
    assert (tmp_path / "spark_expectations_errors.json").exists()


def test_process_dispatch_message_routes_spark_expectations_payload(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
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

    created_reports: list[dict[str, object]] = []

    def fake_report_run(*args: object, **kwargs: object) -> None:
        created_reports.append({"action": "report_run", **kwargs})

    def fake_report_progress(*args: object, **kwargs: object) -> None:
        created_reports.append({"action": "report_progress", **kwargs})

    class DummyTokenProvider:
        def get_token(self, *, correlation_id: str | None = None) -> str:
            return "token"

    monkeypatch.setattr("gx_dispatch_worker._api_report_run", fake_report_run)
    monkeypatch.setattr("gx_dispatch_worker._api_report_execution_progress", fake_report_progress)
    monkeypatch.setattr("gx_dispatch_worker._build_token_provider", lambda: DummyTokenProvider())

    payload = {
        "run_id": "run-123",
        "correlation_id": "corr-123",
        "requested_by": "tester",
        "engine_type": "spark_expectations",
        "rule_payload": {
            "id": 104,
            "table": "customers",
            "column": "customer_id",
            "type": "not_null",
            "params": {
                "synthetic_error_count": 6,
                "error_chunk_size": 3,
                "error_sample_size": 2,
                "synthetic_row_count": 10,
            },
        },
        "output_dir": str(tmp_path),
    }

    process_dispatch_message(config, raw_message=json.dumps(payload))

    assert (tmp_path / "spark_expectations_execution.json").exists()
    assert (tmp_path / "spark_expectations_errors.json").exists()
    assert any(item.get("action") == "report_run" for item in created_reports)
    assert any(item.get("new_status") == "succeeded" for item in created_reports)
