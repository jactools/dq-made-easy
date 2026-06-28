from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

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
from spark_expectations_adapter import execute_spark_expectations_rule
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


@pytest.mark.parametrize(
    ("rule_type", "params", "expected_expectation"),
    [
        ("equals", {"expected": "ok"}, "status == 'ok'"),
        ("not_equal", {"expected": "unknown"}, "status != 'unknown'"),
        ("between", {"min": 10, "max": 20}, "status BETWEEN 10 AND 20"),
        ("in", {"values": ["a", "b"]}, "status IN ('a', 'b')"),
    ],
)
def test_lower_rule_to_spark_expectations_supports_extended_row_level_checks(
    rule_type: str, params: dict[str, object], expected_expectation: str
) -> None:
    rule = {
        "id": 45,
        "table": "customers",
        "column": "status",
        "type": rule_type,
        "params": params,
    }

    lowered = lower_rule_to_spark_expectations(rule)

    assert lowered["engine_type"] == "spark_expectations"
    assert lowered["engine_target"] == "pyspark"
    assert lowered["rule_type"] == "row_dq"
    assert lowered["expectation"] == expected_expectation
    assert lowered["action_if_failed"] == "quarantine"


@pytest.mark.parametrize(
    ("rule_type", "params", "expected_rule_type", "expected_expectation"),
    [
        ("count", {"expected_count": 3}, "aggregate_dq", "COUNT(*) == 3"),
        ("sum", {"expected_value": 10}, "aggregate_dq", "SUM(amount) == 10"),
        ("query", {"query": "SELECT COUNT(*) AS c FROM source", "expected_count": 2}, "query_dq", "query result count == 2"),
    ],
)
def test_lower_rule_to_spark_expectations_supports_aggregate_and_query_checks(
    rule_type: str, params: dict[str, object], expected_rule_type: str, expected_expectation: str
) -> None:
    rule = {
        "id": 46,
        "table": "customers",
        "column": "amount",
        "type": rule_type,
        "params": params,
    }

    lowered = lower_rule_to_spark_expectations(rule)

    assert lowered["engine_type"] == "spark_expectations"
    assert lowered["engine_target"] == "pyspark"
    assert lowered["rule_type"] == expected_rule_type
    assert lowered["expectation"] == expected_expectation
    assert lowered["action_if_failed"] == "quarantine"


@pytest.mark.parametrize(
    ("rule_type", "params", "expected_expectation"),
    [
        ("unique", {}, "duplicate_count(customer_id) == 0"),
        ("max_length", {"max": 10}, "length(customer_id) <= 10"),
        ("regex", {"pattern": "^A.*"}, "customer_id RLIKE '^A.*'"),
        ("row_count", {"expected_count": 5}, "COUNT(*) == 5"),
        ("avg", {"expected_value": 2.5}, "AVG(amount) == 2.5"),
        ("stddev", {"expected_value": 1.2}, "STDDEV(amount) == 1.2"),
        ("missing_count", {"expected_count": 1}, "missing_count(amount) == 1"),
        ("duplicate_count", {"expected_count": 2}, "duplicate_count(amount) == 2"),
        ("distinct_count", {"expected_count": 3}, "COUNT(DISTINCT amount) == 3"),
    ],
)
def test_lower_rule_to_spark_expectations_supports_extended_constructs(
    rule_type: str, params: dict[str, object], expected_expectation: str
) -> None:
    rule = {
        "id": 47,
        "table": "customers",
        "column": "customer_id" if rule_type in {"unique", "max_length", "regex", "row_count"} else "amount",
        "type": rule_type,
        "params": params,
    }

    lowered = lower_rule_to_spark_expectations(rule)

    assert lowered["engine_type"] == "spark_expectations"
    assert lowered["engine_target"] == "pyspark"
    assert lowered["action_if_failed"] == "quarantine"
    assert lowered["expectation"] == expected_expectation


@pytest.mark.parametrize(
    ("rule_type", "params", "expected_expectation"),
    [
        ("is_null", {}, "customer_id IS NULL"),
        ("not_in", {"values": ["a", "b"]}, "status NOT IN ('a', 'b')"),
        ("contains", {"value": "foo"}, "status CONTAINS 'foo'"),
        ("starts_with", {"value": "foo"}, "status STARTS WITH 'foo'"),
        ("ends_with", {"value": "foo"}, "status ENDS WITH 'foo'"),
        ("min_length", {"min": 3}, "status LENGTH >= 3"),
    ],
)
def test_lower_rule_to_spark_expectations_supports_additional_text_and_null_checks(
    rule_type: str, params: dict[str, object], expected_expectation: str
) -> None:
    rule = {
        "id": 48,
        "table": "customers",
        "column": "customer_id" if rule_type == "is_null" else "status",
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


@pytest.mark.parametrize(
    ("rule", "expected_fragment"),
    [
        (
            {
                "id": 44,
                "table": "customers",
                "column": "amount",
                "type": "min",
                "params": {"expression": "amount > 10"},
            },
            "custom expression",
        ),
        (
            {
                "id": 45,
                "table": "customers",
                "column": "amount",
                "type": "equals",
                "params": {"sql_predicate": "amount > 10"},
            },
            "SQL predicate",
        ),
        (
            {
                "id": 46,
                "table": "customers",
                "column": "amount",
                "type": "not_null",
                "params": {"window": "row_number() over (partition by customer_id)"},
            },
            "window",
        ),
        (
            {
                "id": 47,
                "table": "customers",
                "column": "amount",
                "type": "query",
                "params": {"query": "SELECT customer_id, amount FROM source", "expected_count": 2},
            },
            "complex query",
        ),
        (
            {
                "id": 48,
                "table": "customers",
                "column": "amount",
                "type": "equals",
                "params": {"expected": 10, "columns": ["amount", "total"]},
            },
            "multi-column",
        ),
    ],
)
def test_lower_rule_to_spark_expectations_rejects_unsupported_constructs(rule: dict[str, object], expected_fragment: str) -> None:
    with pytest.raises(ValueError, match=expected_fragment):
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


def test_execute_spark_expectations_rule_from_adapter_executes_rows() -> None:
    req = SimpleNamespace(
        id=105,
        table="customers",
        column="customer_id",
        type="not_null",
        params={
            "rows": [
                {"customer_id": 1},
                {"customer_id": None},
                {"customer_id": 3},
                {"customer_id": None},
            ],
            "error_chunk_size": 2,
            "error_sample_size": 2,
        },
        output_dir=None,
        engine_type="spark_expectations",
    )

    payload = execute_spark_expectations_rule(req)

    assert payload["ok"] is True
    assert payload["passed_count"] == 2
    assert payload["failed_count"] == 2
    assert payload["error_management"]["total_error_count"] == 2


def test_execute_spark_expectations_rule_emits_execution_metadata() -> None:
    req = SimpleNamespace(
        id=107,
        table="customers",
        column="customer_id",
        type="not_null",
        params={
            "rows": [
                {"customer_id": 1},
                {"customer_id": None},
            ],
            "error_chunk_size": 2,
            "error_sample_size": 2,
        },
        output_dir=None,
        engine_type="spark_expectations",
    )

    payload = execute_spark_expectations_rule(req)

    metadata = payload["execution_metadata"]
    assert metadata["engine_type"] == "spark_expectations"
    assert metadata["runtime"] == "pyspark"
    assert metadata["source_row_count"] == 2
    assert metadata["duration_ms"] >= 0
    assert metadata["spark_app_name"] == "dq-engine-spark-expectations"
    assert metadata["started_at"].endswith("+00:00") or metadata["started_at"].endswith("Z")
    assert metadata["completed_at"].endswith("+00:00") or metadata["completed_at"].endswith("Z")


def test_execute_spark_expectations_rule_evaluates_aggregate_checks_with_metadata() -> None:
    req = SimpleNamespace(
        id=108,
        table="customers",
        column="amount",
        type="sum",
        params={
            "rows": [
                {"amount": 5},
                {"amount": 15},
                {"amount": 10},
            ],
            "expected_value": 30,
            "error_chunk_size": 2,
            "error_sample_size": 2,
        },
        output_dir=None,
        engine_type="spark_expectations",
    )

    payload = execute_spark_expectations_rule(req)

    assert payload["ok"] is True
    assert payload["result"] == "passed"
    assert payload["passed_count"] == 1
    assert payload["failed_count"] == 0
    assert payload["execution_metadata"]["evaluation"]["rule_family"] == "aggregate"
    assert payload["execution_metadata"]["evaluation"]["actual_value"] == 30
    assert payload["execution_metadata"]["evaluation"]["expected_value"] == 30


def test_execute_spark_expectations_rule_evaluates_query_checks_with_metadata() -> None:
    req = SimpleNamespace(
        id=109,
        table="customers",
        column="amount",
        type="query",
        params={
            "rows": [
                {"amount": 5},
                {"amount": 15},
                {"amount": 10},
            ],
            "query": "SELECT COUNT(*) AS c FROM source WHERE amount >= 10",
            "expected_count": 2,
            "error_chunk_size": 2,
            "error_sample_size": 2,
        },
        output_dir=None,
        engine_type="spark_expectations",
    )

    payload = execute_spark_expectations_rule(req)

    assert payload["ok"] is True
    assert payload["result"] == "passed"
    assert payload["passed_count"] == 1
    assert payload["failed_count"] == 0
    assert payload["execution_metadata"]["evaluation"]["rule_family"] == "query"
    assert payload["execution_metadata"]["evaluation"]["actual_value"] == 2
    assert payload["execution_metadata"]["evaluation"]["expected_value"] == 2


def test_execute_spark_expectations_rule_persists_execution_metadata_with_quarantine_artifact(tmp_path: Path) -> None:
    quarantine_path = tmp_path / "quarantine-rule-107.json"
    req = SimpleNamespace(
        id=107,
        table="customers",
        column="customer_id",
        type="not_null",
        params={
            "rows": [
                {"customer_id": 1},
                {"customer_id": None},
            ],
            "error_chunk_size": 2,
            "error_sample_size": 2,
            "quarantine_uri": str(quarantine_path),
        },
        output_dir=None,
        engine_type="spark_expectations",
    )

    payload = execute_spark_expectations_rule(req)

    artifact = payload["quarantine_artifact"]
    assert artifact["execution_metadata"]["rule_id"] == 107
    assert artifact["execution_metadata"]["engine_type"] == "spark_expectations"

    persisted_payload = json.loads(quarantine_path.read_text(encoding="utf-8"))
    assert persisted_payload["execution_metadata"]["rule_id"] == 107
    assert persisted_payload["execution_metadata"]["runtime"] == "pyspark"
    assert len(persisted_payload["failed_rows"]) == 1


def test_execute_spark_expectations_rule_publishes_quarantine_artifact_to_aistor(monkeypatch: pytest.MonkeyPatch) -> None:
    endpoint_url = os.getenv("DQ_S3_ENDPOINT") or os.getenv("AWS_ENDPOINT_URL") or "http://aistor:9000"
    if endpoint_url.startswith("http://dq-aistor:9000"):
        endpoint_url = "http://aistor:9000"

    monkeypatch.setenv("DQ_S3_ENDPOINT", endpoint_url)
    monkeypatch.setenv("DQ_S3_ACCESS_KEY", "aistoradmin")
    monkeypatch.setenv("DQ_S3_SECRET_KEY", "aistoradmin")
    monkeypatch.setenv("DQ_S3_REGION", "us-east-1")
    monkeypatch.setenv("DQ_S3_PATH_STYLE_ACCESS", "true")
    monkeypatch.setenv("DQ_S3_SSL_ENABLED", "false")

    import boto3

    client = boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id="aistoradmin",
        aws_secret_access_key="aistoradmin",
        region_name="us-east-1",
        verify=False,
    )

    bucket_name = "dq-test-data"
    key_name = "quarantine/rule-106.json"
    try:
        client.head_bucket(Bucket=bucket_name)
    except Exception as exc:
        import botocore.exceptions

        if isinstance(exc, botocore.exceptions.EndpointConnectionError):
            pytest.skip(f"AIStor endpoint unavailable for integration test: {endpoint_url}")
        try:
            client.create_bucket(Bucket=bucket_name)
        except Exception as create_exc:
            pytest.skip(f"AIStor bucket setup unavailable: {create_exc}")

    req = SimpleNamespace(
        id=106,
        table="customers",
        column="customer_id",
        type="not_null",
        params={
            "rows": [
                {"customer_id": 1},
                {"customer_id": None},
                {"customer_id": 3},
                {"customer_id": None},
            ],
            "error_chunk_size": 2,
            "error_sample_size": 2,
            "quarantine_uri": f"s3a://{bucket_name}/{key_name}",
        },
        output_dir=None,
        engine_type="spark_expectations",
    )

    payload = execute_spark_expectations_rule(req)

    assert payload["ok"] is True
    assert payload["failed_count"] == 2
    assert payload["quarantine_artifact"]["storage_uri"] == f"s3a://{bucket_name}/{key_name}"

    response = client.get_object(Bucket=bucket_name, Key=key_name)
    body = response["Body"].read().decode("utf-8")
    persisted_payload = json.loads(body)

    assert isinstance(persisted_payload, dict)
    assert len(persisted_payload["failed_rows"]) == 2
    assert all(isinstance(item, dict) for item in persisted_payload["failed_rows"])
    assert all("customer_id" in item for item in persisted_payload["failed_rows"])
    assert persisted_payload["execution_metadata"]["rule_id"] == 106


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
    assert payload["observability_summary"]["failed_count"] == 8
    assert payload["observability_summary"]["passed_count"] == 12
    assert payload["observability_summary"]["engine_type"] == "spark_expectations"
    assert (tmp_path / "spark_expectations_execution.json").exists()
    assert (tmp_path / "spark_expectations_errors.json").exists()

    persisted_execution = json.loads((tmp_path / "spark_expectations_execution.json").read_text(encoding="utf-8"))
    persisted_errors = json.loads((tmp_path / "spark_expectations_errors.json").read_text(encoding="utf-8"))
    assert persisted_execution["observability_summary"]["failed_count"] == 8
    assert persisted_errors["observability_summary"]["failed_count"] == 8


def test_execute_endpoint_evaluates_rows_with_pyspark(tmp_path: Path) -> None:
    client = TestClient(app)

    response = client.post(
        "/execute",
        json={
            "id": 104,
            "table": "customers",
            "column": "customer_id",
            "type": "not_null",
            "params": {
                "rows": [
                    {"customer_id": 1},
                    {"customer_id": None},
                    {"customer_id": 3},
                    {"customer_id": None},
                ],
                "error_chunk_size": 2,
                "error_sample_size": 2,
            },
            "output_dir": str(tmp_path),
            "engine_type": "spark_expectations",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["passed_count"] == 2
    assert payload["failed_count"] == 2
    assert payload["error_management"]["total_error_count"] == 2
    assert payload["error_management"]["chunk_count"] == 1
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
                "quarantine_uri": str(tmp_path / "dispatch-quarantine.json"),
            },
        },
        "output_dir": str(tmp_path),
    }

    process_dispatch_message(config, raw_message=json.dumps(payload))

    assert (tmp_path / "spark_expectations_execution.json").exists()
    assert (tmp_path / "spark_expectations_errors.json").exists()
    assert any(item.get("action") == "report_run" for item in created_reports)
    assert any(item.get("new_status") == "succeeded" for item in created_reports)

    succeeded_report = next(item for item in created_reports if item.get("new_status") == "succeeded")
    result_summary = succeeded_report.get("result_summary", {})
    assert result_summary.get("execution_metadata", {}).get("engine_type") == "spark_expectations"
    assert result_summary.get("quarantine_artifact", {}).get("storage_kind") in {"local_file", "s3"}
    assert result_summary.get("error_management", {}).get("storage_strategy") in {"chunked", "inline", "none"}

    details = succeeded_report.get("details", {})
    assert details.get("engine_type") == "spark_expectations"
    assert details.get("quarantine_artifact", {}).get("storage_kind") in {"local_file", "s3"}
