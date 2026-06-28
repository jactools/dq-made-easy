from __future__ import annotations

import json
import os
import sys
import unittest
from tempfile import TemporaryDirectory
from unittest.mock import patch

TESTS_DIR = os.path.dirname(__file__)
ENGINE_DIR = os.path.abspath(os.path.join(TESTS_DIR, ".."))
REPO_ROOT = os.path.abspath(os.path.join(TESTS_DIR, "..", ".."))
DQ_UTILS_SRC = os.path.join(REPO_ROOT, "dq-utils", "src")

os.environ.setdefault("OTEL_EXPORTER_OTLP_ENDPOINT", "")

sys.path.insert(0, DQ_UTILS_SRC)
sys.path.insert(0, ENGINE_DIR)

from gx_dispatch_worker import GxWorkerConfig
from gx_dispatch_worker import GxWorkerExecutionError
from gx_dispatch_worker import _create_spark_session
from gx_dispatch_worker import _configure_worker_spark_builder
from gx_dispatch_worker import _coerce_reported_failure
from gx_dispatch_worker import _resolve_spark_ui_port
from gx_dispatch_worker import _resolve_worker_heartbeat_key
from gx_dispatch_worker import _resolve_worker_heartbeat_interval_seconds
from gx_dispatch_worker import _resolve_worker_heartbeat_ttl_seconds
from gx_dispatch_worker import _write_worker_heartbeat
from gx_dispatch_worker import process_dispatch_message
from gx_dispatch_worker import run_worker_forever
import gx_dispatch_worker


class _StubRedisClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, str], int | None]] = []

    def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.calls.append((key, json.loads(value), ex))


class GxDispatchWorkerHeartbeatTests(unittest.TestCase):
    def test_resolve_worker_heartbeat_key_defaults_from_queue_key(self) -> None:
        self.assertEqual(
            _resolve_worker_heartbeat_key("dq-gx:execution-dispatch"),
            "dq-gx:execution-dispatch:worker-heartbeat",
        )

    def test_resolve_worker_heartbeat_ttl_seconds_clamps_invalid_values(self) -> None:
        previous = os.environ.get("GX_EXECUTION_WORKER_HEARTBEAT_TTL_SECONDS")
        try:
            os.environ["GX_EXECUTION_WORKER_HEARTBEAT_TTL_SECONDS"] = "bad"
            self.assertEqual(_resolve_worker_heartbeat_ttl_seconds(), 30)

            os.environ["GX_EXECUTION_WORKER_HEARTBEAT_TTL_SECONDS"] = "1"
            self.assertEqual(_resolve_worker_heartbeat_ttl_seconds(), 5)
        finally:
            if previous is None:
                os.environ.pop("GX_EXECUTION_WORKER_HEARTBEAT_TTL_SECONDS", None)
            else:
                os.environ["GX_EXECUTION_WORKER_HEARTBEAT_TTL_SECONDS"] = previous

    def test_resolve_worker_heartbeat_interval_seconds_defaults_below_ttl(self) -> None:
        previous = os.environ.get("GX_EXECUTION_WORKER_HEARTBEAT_INTERVAL_SECONDS")
        try:
            os.environ.pop("GX_EXECUTION_WORKER_HEARTBEAT_INTERVAL_SECONDS", None)
            self.assertEqual(_resolve_worker_heartbeat_interval_seconds(30), 10)
            self.assertEqual(_resolve_worker_heartbeat_interval_seconds(6), 2)
        finally:
            if previous is None:
                os.environ.pop("GX_EXECUTION_WORKER_HEARTBEAT_INTERVAL_SECONDS", None)
            else:
                os.environ["GX_EXECUTION_WORKER_HEARTBEAT_INTERVAL_SECONDS"] = previous

    def test_resolve_spark_ui_port_defaults_to_4044(self) -> None:
        previous = os.environ.get("DQ_SPARK_UI_PORT")
        try:
            os.environ.pop("DQ_SPARK_UI_PORT", None)
            self.assertEqual(_resolve_spark_ui_port(), 4044)
        finally:
            if previous is None:
                os.environ.pop("DQ_SPARK_UI_PORT", None)
            else:
                os.environ["DQ_SPARK_UI_PORT"] = previous

    def test_write_worker_heartbeat_sets_ttl_payload(self) -> None:
        client = _StubRedisClient()
        config = GxWorkerConfig(
            redis_url="redis://redis:6379/0",
            queue_key="dq-gx:execution-dispatch",
            processing_queue_key="dq-gx:execution-dispatch:processing",
            heartbeat_key="dq-gx:execution-dispatch:worker-heartbeat",
            heartbeat_ttl_seconds=30,
            heartbeat_interval_seconds=10,
            max_rows=100000,
            poll_timeout_seconds=5,
            api_url="http://kong:8000",
            spark_master="local[*]",
            spark_ui_port=4044,
            s3_endpoint=None,
            s3_access_key=None,
            s3_secret_key=None,
            s3_region=None,
            s3_path_style_access=True,
            s3_ssl_enabled=False,
        )

        with patch("gx_dispatch_worker.record_worker_heartbeat") as record_worker_heartbeat_mock:
            _write_worker_heartbeat(client, config=config, worker_id="dq-engine-gx-worker-test")

        self.assertEqual(len(client.calls), 1)
        key, payload, ttl = client.calls[0]
        self.assertEqual(key, config.heartbeat_key)
        self.assertEqual(ttl, 30)
        self.assertEqual(payload["workerId"], "dq-engine-gx-worker-test")
        self.assertEqual(payload["queueKey"], config.queue_key)
        self.assertEqual(payload["processingQueueKey"], config.processing_queue_key)
        self.assertTrue(payload["updatedAt"].endswith("Z"))
        record_worker_heartbeat_mock.assert_called_once_with(
            queue_key=config.queue_key,
            heartbeat_ttl_seconds=config.heartbeat_ttl_seconds,
        )


class _FakeSparkBuilder:
    def __init__(self) -> None:
        self.configs: dict[str, str] = {}

    def config(self, key: str, value: str) -> "_FakeSparkBuilder":
        self.configs[key] = value
        return self


class _TransientGatewaySparkBuilder(_FakeSparkBuilder):
    def __init__(self) -> None:
        super().__init__()
        self.get_or_create_calls = 0

    def getOrCreate(self) -> _StubSparkSession:
        self.get_or_create_calls += 1
        if self.get_or_create_calls == 1:
            raise ConnectionRefusedError(111, "Connection refused")
        return _StubSparkSession()


class GxDispatchWorkerSparkBuilderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = GxWorkerConfig(
            redis_url="redis://redis:6379/0",
            queue_key="dq-gx:execution-dispatch",
            processing_queue_key="dq-gx:execution-dispatch:processing",
            heartbeat_key="dq-gx:execution-dispatch:worker-heartbeat",
            heartbeat_ttl_seconds=30,
            heartbeat_interval_seconds=10,
            max_rows=100000,
            poll_timeout_seconds=5,
            api_url="http://kong:8000",
            spark_master="local[*]",
            spark_ui_port=4044,
            s3_endpoint="http://aistor:9000",
            s3_access_key="aistor",
            s3_secret_key="aistorpass",
            s3_region="eu-west-1",
            s3_path_style_access=True,
            s3_ssl_enabled=False,
        )

    def test_configure_worker_spark_builder_applies_default_memory_settings(self) -> None:
        builder = _FakeSparkBuilder()

        with patch("dq_utils.spark_jars.configure_spark_builder_with_local_jars", side_effect=lambda candidate: candidate):
            configured = _configure_worker_spark_builder(builder, self.config, enable_delta=False)

        self.assertIs(configured, builder)
        self.assertEqual(builder.configs["spark.driver.memory"], "2g")
        self.assertEqual(builder.configs["spark.executor.memory"], "2g")
        self.assertEqual(builder.configs["spark.driver.maxResultSize"], "512m")
        self.assertEqual(builder.configs["spark.hadoop.fs.s3a.endpoint"], "http://aistor:9000")
        self.assertEqual(builder.configs["spark.hadoop.fs.s3a.path.style.access"], "true")
        self.assertEqual(builder.configs["spark.hadoop.fs.s3a.connection.ssl.enabled"], "false")

    def test_configure_worker_spark_builder_honors_memory_overrides_and_delta(self) -> None:
        builder = _FakeSparkBuilder()
        previous_driver = os.environ.get("DQ_SPARK_DRIVER_MEMORY")
        previous_executor = os.environ.get("DQ_SPARK_EXECUTOR_MEMORY")
        previous_result = os.environ.get("DQ_SPARK_DRIVER_MAX_RESULT_SIZE")
        try:
            os.environ["DQ_SPARK_DRIVER_MEMORY"] = "3g"
            os.environ["DQ_SPARK_EXECUTOR_MEMORY"] = "1536m"
            os.environ["DQ_SPARK_DRIVER_MAX_RESULT_SIZE"] = "768m"

            with patch("dq_utils.spark_jars.configure_spark_builder_with_local_jars", side_effect=lambda candidate: candidate):
                configured = _configure_worker_spark_builder(builder, self.config, enable_delta=True)

            self.assertIs(configured, builder)
            self.assertEqual(builder.configs["spark.driver.memory"], "3g")
            self.assertEqual(builder.configs["spark.executor.memory"], "1536m")
            self.assertEqual(builder.configs["spark.driver.maxResultSize"], "768m")
            self.assertEqual(
                builder.configs["spark.sql.extensions"],
                "io.delta.sql.DeltaSparkSessionExtension",
            )
            self.assertEqual(
                builder.configs["spark.sql.catalog.spark_catalog"],
                "org.apache.spark.sql.delta.catalog.DeltaCatalog",
            )
        finally:
            if previous_driver is None:
                os.environ.pop("DQ_SPARK_DRIVER_MEMORY", None)
            else:
                os.environ["DQ_SPARK_DRIVER_MEMORY"] = previous_driver

            if previous_executor is None:
                os.environ.pop("DQ_SPARK_EXECUTOR_MEMORY", None)
            else:
                os.environ["DQ_SPARK_EXECUTOR_MEMORY"] = previous_executor

            if previous_result is None:
                os.environ.pop("DQ_SPARK_DRIVER_MAX_RESULT_SIZE", None)
            else:
                os.environ["DQ_SPARK_DRIVER_MAX_RESULT_SIZE"] = previous_result

    def test_create_spark_session_retries_transient_gateway_failure(self) -> None:
        builder = _TransientGatewaySparkBuilder()

        with patch("gx_dispatch_worker._resolve_spark_session_class", return_value=object), patch(
            "gx_dispatch_worker.build_spark_session_builder", return_value=builder
        ), patch(
            "dq_utils.spark_jars.configure_spark_builder_with_local_jars",
            side_effect=lambda candidate: candidate,
        ), patch("gx_dispatch_worker.time.sleep", return_value=None) as sleep_mock:
            spark_session = _create_spark_session(self.config, enable_delta=False)

        self.assertIsInstance(spark_session, _StubSparkSession)
        self.assertEqual(builder.get_or_create_calls, 2)
        sleep_mock.assert_called_once_with(1.0)


class GxDispatchWorkerFailureReportingTests(unittest.TestCase):
    def test_coerce_reported_failure_preserves_worker_error(self) -> None:
        failure = _coerce_reported_failure(
            GxWorkerExecutionError("missing suite", failure_code="GX_SUITE_NOT_RUNNABLE")
        )

        self.assertEqual(failure.failure_code, "GX_SUITE_NOT_RUNNABLE")
        self.assertEqual(str(failure), "missing suite")


class GxDispatchWorkerQueryComparisonTests(unittest.TestCase):
    def test_evaluate_expectations_spark_routes_query_comparison_to_native_gx(self) -> None:
        stub_runner = _StubNativeGxRunner()
        expectation = {
            "expectation_type": "expect_query_results_to_match_comparison",
            "kwargs": {
                "base_query": "SELECT 1",
                "comparison_data_source_name": "warehouse_reporting",
                "comparison_query": "SELECT 1",
                "mostly": 1.0,
            },
        }

        with patch("gx_dispatch_worker._NativeGxBatchRunner", return_value=stub_runner):
            ok, summary, diagnostics = gx_dispatch_worker._evaluate_expectations_spark(object(), [expectation])

        self.assertTrue(ok)
        self.assertEqual(summary["expectation_count"], 1)
        self.assertEqual(summary["passed_expectation_count"], 1)
        self.assertEqual(summary["failed_expectation_count"], 0)
        self.assertIsNone(summary["row_count"])
        self.assertEqual(diagnostics, [])
        self.assertEqual(stub_runner.validated_expectations, [expectation])

    def test_coerce_reported_failure_surfaces_py4j_chain_without_api_failure_code(self) -> None:
        class FakePy4JNetworkError(RuntimeError):
            pass

        FakePy4JNetworkError.__module__ = "py4j.protocol"

        try:
            try:
                raise FakePy4JNetworkError("Answer from Java side is empty")
            except FakePy4JNetworkError as spark_exc:
                raise ConnectionRefusedError(111, "Connection refused") from spark_exc
        except ConnectionRefusedError as exc:
            failure = _coerce_reported_failure(exc)

        self.assertEqual(failure.failure_code, "GX_WORKER_EXECUTION_ERROR")
        self.assertEqual(str(failure), "FakePy4JNetworkError: Answer from Java side is empty")

    def test_process_dispatch_message_preserves_spark_error_when_stop_fails(self) -> None:
        class FakePy4JNetworkError(RuntimeError):
            pass

        FakePy4JNetworkError.__module__ = "py4j.protocol"

        config = GxWorkerConfig(
            redis_url="redis://redis:6379/0",
            queue_key="dq-gx:execution-dispatch",
            processing_queue_key="dq-gx:execution-dispatch:processing",
            heartbeat_key="dq-gx:execution-dispatch:worker-heartbeat",
            heartbeat_ttl_seconds=30,
            heartbeat_interval_seconds=10,
            max_rows=100000,
            poll_timeout_seconds=5,
            api_url="http://kong:8000",
            spark_master="local[*]",
            spark_ui_port=4044,
            s3_endpoint="http://aistor:9000",
            s3_access_key="aistor",
            s3_secret_key="aistorpass",
            s3_region="eu-west-1",
            s3_path_style_access=True,
            s3_ssl_enabled=False,
        )
        payload = {
            "run_id": "run-join-stop-failure",
            "queue_message_id": "run-join-stop-failure",
            "correlation_id": "corr-join-stop-failure",
            "requested_by": "user-1",
            "engine_target": "pyspark",
            "execution_shape": "join_pair",
            "suite_id": "gx_suite_join_stop_failure",
            "suite_version": 1,
        }
        envelope = {
            "suite_id": "gx_suite_join_stop_failure",
            "suite_version": 1,
            "gx_suite": {
                "expectations": [
                    {
                        "expectation_type": "expect_column_values_to_equal_other_column",
                        "kwargs": {"column": "status", "other_column": "rhs.status"},
                    }
                ]
            },
            "resolved_execution_scope": {"data_object_version_ids": ["dov_left", "dov_right"]},
            "execution_contract": {
                "engine_target": "pyspark",
                "execution_shape": "join_pair",
                "traceability": {
                    "rule_id": "rule-1",
                    "rule_version_id": "rv-1",
                    "gx_suite_id": "gx_suite_join_stop_failure",
                    "gx_suite_version": 1,
                    "data_object_version_id": "dov_left",
                },
                "source_materialization": {
                    "landing_zone_artifact_id": "lz_gx_suite_join_stop_failure",
                    "landing_zone_version_id": "lzv_1",
                    "output_location": "s3://dq-landing-zone/gx/join-pairs/suite_id=gx_suite_join_stop_failure/suite_version=1/format=parquet",
                    "join_type": "inner",
                    "join_keys": ["order_id"],
                    "left_source": {"data_object_id": "do-left", "data_object_version_id": "dov_left"},
                    "right_source": {"data_object_id": "do-right", "data_object_version_id": "dov_right"},
                },
            },
        }

        with TemporaryDirectory() as tmpdir:
            with patch("gx_dispatch_worker._build_token_provider", return_value=_StubTokenProvider()), patch(
                "gx_dispatch_worker._api_report_run",
                side_effect=lambda *args, **kwargs: None,
            ), patch(
                "gx_dispatch_worker._api_get_suite_envelope",
                return_value=envelope,
            ), patch(
                "gx_dispatch_worker._create_spark_session",
                return_value=_FailingStopSparkSession(),
            ), patch(
                "gx_dispatch_worker._download_s3a_prefix_to_tempdir",
                return_value=(TemporaryDirectory(), tmpdir),
            ), patch(
                "gx_dispatch_worker._spark_read_dataset",
                return_value=object(),
            ), patch(
                "gx_dispatch_worker._evaluate_expectations_spark",
                side_effect=FakePy4JNetworkError("Answer from Java side is empty"),
            ):
                with self.assertRaises(FakePy4JNetworkError):
                    process_dispatch_message(config, raw_message=json.dumps(payload))

    def test_run_worker_forever_removes_failed_message_after_reporting_failure(self) -> None:
        config = GxWorkerConfig(
            redis_url="redis://redis:6379/0",
            queue_key="dq-gx:execution-dispatch",
            processing_queue_key="dq-gx:execution-dispatch:processing",
            heartbeat_key="dq-gx:execution-dispatch:worker-heartbeat",
            heartbeat_ttl_seconds=30,
            heartbeat_interval_seconds=10,
            max_rows=100000,
            poll_timeout_seconds=5,
            api_url="http://kong:8000",
            spark_master="local[*]",
            spark_ui_port=4044,
            s3_endpoint=None,
            s3_access_key=None,
            s3_secret_key=None,
            s3_region=None,
            s3_path_style_access=True,
            s3_ssl_enabled=False,
        )
        raw_message = json.dumps(
            {
                "run_id": "run-failure-cleanup-1",
                "queue_message_id": "run-failure-cleanup-1",
                "correlation_id": "corr-failure-cleanup-1",
                "requested_by": "user-1",
                "execution_shape": "join_pair",
            }
        )
        redis_client = _StubQueueRedisClient(raw_message)
        reports: list[dict[str, object]] = []

        with patch("gx_dispatch_worker.configure_logging", return_value=None), patch(
            "gx_dispatch_worker.configure_worker_telemetry",
            return_value=None,
        ), patch(
            "gx_dispatch_worker.load_config",
            return_value=config,
        ), patch(
            "gx_dispatch_worker._require_redis",
            return_value=_StubRedisModule(redis_client),
        ), patch(
            "gx_dispatch_worker._build_token_provider",
            return_value=_StubTokenProvider(),
        ), patch(
            "gx_dispatch_worker._write_worker_heartbeat",
            return_value=None,
        ), patch(
            "gx_dispatch_worker._start_worker_heartbeat_loop",
            return_value=(_StubStopEvent(), _StubThread()),
        ), patch(
            "gx_dispatch_worker.process_dispatch_message",
            side_effect=ConnectionRefusedError(111, "Connection refused"),
        ), patch(
            "gx_dispatch_worker._api_report_run",
            side_effect=lambda *args, **kwargs: reports.append(kwargs),
        ), patch(
            "gx_dispatch_worker.time.sleep",
            return_value=None,
        ):
            with self.assertRaises(KeyboardInterrupt):
                run_worker_forever()

        self.assertEqual(
            redis_client.lrem_calls,
            [(config.processing_queue_key, 1, raw_message)],
        )
        self.assertEqual(reports[-1]["new_status"], "failed")

    def test_run_worker_forever_removes_message_when_failure_report_returns_404(self) -> None:
        config = GxWorkerConfig(
            redis_url="redis://redis:6379/0",
            queue_key="dq-gx:execution-dispatch",
            processing_queue_key="dq-gx:execution-dispatch:processing",
            heartbeat_key="dq-gx:execution-dispatch:worker-heartbeat",
            heartbeat_ttl_seconds=30,
            heartbeat_interval_seconds=10,
            max_rows=100000,
            poll_timeout_seconds=5,
            api_url="http://kong:8000",
            spark_master="local[*]",
            spark_ui_port=4044,
            s3_endpoint=None,
            s3_access_key=None,
            s3_secret_key=None,
            s3_region=None,
            s3_path_style_access=True,
            s3_ssl_enabled=False,
        )
        raw_message = json.dumps(
            {
                "run_id": "run-not-found-1",
                "queue_message_id": "run-not-found-1",
                "correlation_id": "corr-not-found-1",
                "requested_by": "user-1",
                "execution_shape": "join_pair",
            }
        )
        redis_client = _StubQueueRedisClient(raw_message)

        with patch("gx_dispatch_worker.configure_logging", return_value=None), patch(
            "gx_dispatch_worker.configure_worker_telemetry",
            return_value=None,
        ), patch(
            "gx_dispatch_worker.load_config",
            return_value=config,
        ), patch(
            "gx_dispatch_worker._require_redis",
            return_value=_StubRedisModule(redis_client),
        ), patch(
            "gx_dispatch_worker._build_token_provider",
            return_value=_StubTokenProvider(),
        ), patch(
            "gx_dispatch_worker._write_worker_heartbeat",
            return_value=None,
        ), patch(
            "gx_dispatch_worker._start_worker_heartbeat_loop",
            return_value=(_StubStopEvent(), _StubThread()),
        ), patch(
            "gx_dispatch_worker.process_dispatch_message",
            side_effect=ConnectionRefusedError(111, "Connection refused"),
        ), patch(
            "gx_dispatch_worker._api_report_run",
            side_effect=GxWorkerExecutionError(
                "API request failed: POST /rulebuilder/v1/gx/runs/run-not-found-1/report -> 404",
                failure_code="GX_API_REQUEST_FAILED",
                status_code=404,
            ),
        ), patch(
            "gx_dispatch_worker.time.sleep",
            return_value=None,
        ):
            with self.assertRaises(KeyboardInterrupt):
                run_worker_forever()

        self.assertEqual(
            redis_client.lrem_calls,
            [(config.processing_queue_key, 1, raw_message)],
        )

    def test_run_worker_forever_fail_closes_on_py4j_connection_refused(self) -> None:
        class FakePy4JNetworkError(RuntimeError):
            pass

        FakePy4JNetworkError.__module__ = "py4j.protocol"

        config = GxWorkerConfig(
            redis_url="redis://redis:6379/0",
            queue_key="dq-gx:execution-dispatch",
            processing_queue_key="dq-gx:execution-dispatch:processing",
            heartbeat_key="dq-gx:execution-dispatch:worker-heartbeat",
            heartbeat_ttl_seconds=30,
            heartbeat_interval_seconds=10,
            max_rows=100000,
            poll_timeout_seconds=5,
            api_url="http://kong:8000",
            spark_master="local[*]",
            spark_ui_port=4044,
            s3_endpoint=None,
            s3_access_key=None,
            s3_secret_key=None,
            s3_region=None,
            s3_path_style_access=True,
            s3_ssl_enabled=False,
        )
        raw_message = json.dumps(
            {
                "run_id": "run-fail-closed-1",
                "queue_message_id": "run-fail-closed-1",
                "correlation_id": "corr-fail-closed-1",
                "requested_by": "user-1",
                "execution_shape": "single_object",
            }
        )
        redis_client = _StubQueueRedisClient(raw_message)
        reports: list[dict[str, object]] = []

        fatal_exc = ConnectionRefusedError(111, "Connection refused")
        fatal_exc.__cause__ = FakePy4JNetworkError("Answer from Java side is empty")

        with patch("gx_dispatch_worker.configure_logging", return_value=None), patch(
            "gx_dispatch_worker.configure_worker_telemetry",
            return_value=None,
        ), patch(
            "gx_dispatch_worker.load_config",
            return_value=config,
        ), patch(
            "gx_dispatch_worker._require_redis",
            return_value=_StubRedisModule(redis_client),
        ), patch(
            "gx_dispatch_worker._build_token_provider",
            return_value=_StubTokenProvider(),
        ), patch(
            "gx_dispatch_worker._write_worker_heartbeat",
            return_value=None,
        ), patch(
            "gx_dispatch_worker._start_worker_heartbeat_loop",
            return_value=(_StubStopEvent(), _StubThread()),
        ), patch(
            "gx_dispatch_worker.process_dispatch_message",
            side_effect=fatal_exc,
        ), patch(
            "gx_dispatch_worker._api_report_run",
            side_effect=lambda *args, **kwargs: reports.append(kwargs),
        ), patch(
            "gx_dispatch_worker.time.sleep",
            return_value=None,
        ):
            with self.assertRaises(ConnectionRefusedError):
                run_worker_forever()

        self.assertEqual(
            redis_client.lrem_calls,
            [(config.processing_queue_key, 1, raw_message)],
        )
        self.assertEqual(reports[-1]["new_status"], "failed")

    def test_run_worker_forever_reports_system_exit_and_cleans_up_message(self) -> None:
        config = GxWorkerConfig(
            redis_url="redis://redis:6379/0",
            queue_key="dq-gx:execution-dispatch",
            processing_queue_key="dq-gx:execution-dispatch:processing",
            heartbeat_key="dq-gx:execution-dispatch:worker-heartbeat",
            heartbeat_ttl_seconds=30,
            heartbeat_interval_seconds=10,
            max_rows=100000,
            poll_timeout_seconds=5,
            api_url="http://kong:8000",
            spark_master="local[*]",
            spark_ui_port=4044,
            s3_endpoint=None,
            s3_access_key=None,
            s3_secret_key=None,
            s3_region=None,
            s3_path_style_access=True,
            s3_ssl_enabled=False,
        )
        raw_message = json.dumps(
            {
                "run_id": "run-system-exit-1",
                "queue_message_id": "run-system-exit-1",
                "correlation_id": "corr-system-exit-1",
                "requested_by": "user-1",
                "execution_shape": "single_object",
            }
        )
        redis_client = _StubQueueRedisClient(raw_message)
        reports: list[dict[str, object]] = []

        with patch("gx_dispatch_worker.configure_logging", return_value=None), patch(
            "gx_dispatch_worker.configure_worker_telemetry",
            return_value=None,
        ), patch(
            "gx_dispatch_worker.load_config",
            return_value=config,
        ), patch(
            "gx_dispatch_worker._require_redis",
            return_value=_StubRedisModule(redis_client),
        ), patch(
            "gx_dispatch_worker._build_token_provider",
            return_value=_StubTokenProvider(),
        ), patch(
            "gx_dispatch_worker._write_worker_heartbeat",
            return_value=None,
        ), patch(
            "gx_dispatch_worker._start_worker_heartbeat_loop",
            return_value=(_StubStopEvent(), _StubThread()),
        ), patch(
            "gx_dispatch_worker.process_dispatch_message",
            side_effect=SystemExit("Spark jar directory not found"),
        ), patch(
            "gx_dispatch_worker._api_report_run",
            side_effect=lambda *args, **kwargs: reports.append(kwargs),
        ), patch(
            "gx_dispatch_worker.time.sleep",
            return_value=None,
        ):
            with self.assertRaises(KeyboardInterrupt):
                run_worker_forever()

        self.assertEqual(
            redis_client.lrem_calls,
            [(config.processing_queue_key, 1, raw_message)],
        )
        self.assertEqual(reports[-1]["new_status"], "failed")
        self.assertEqual(reports[-1]["failure_message"], "SystemExit: Spark jar directory not found")


class _StubTokenProvider:
    def get_token(self, correlation_id: str | None = None) -> str:
        return "token"


class _StubSparkSession:
    def stop(self) -> None:
        return None


class _FailingStopSparkSession:
    def stop(self) -> None:
        raise ConnectionRefusedError(111, "Connection refused")


class _StubNativeGxRunner:
    def __init__(self) -> None:
        self.validated_expectations: list[dict[str, object]] = []

    def validate(self, expectation: dict[str, object]) -> tuple[bool, dict[str, object] | None]:
        self.validated_expectations.append(expectation)
        return True, None


class _StubStopEvent:
    def set(self) -> None:
        return None


class _StubThread:
    def join(self, timeout: float | None = None) -> None:
        return None


class _StubQueueRedisClient:
    def __init__(self, raw_message: str) -> None:
        self.raw_message = raw_message
        self.lrem_calls: list[tuple[str, int, str]] = []
        self.deleted_keys: list[str] = []
        self._dispatch_calls = 0

    def set(self, key: str, value: str, ex: int | None = None) -> None:
        return None

    def delete(self, key: str) -> None:
        self.deleted_keys.append(key)

    def rpoplpush(self, source: str, destination: str) -> None:
        return None

    def brpoplpush(self, source: str, destination: str, timeout: int) -> str:
        self._dispatch_calls += 1
        if self._dispatch_calls == 1:
            return self.raw_message
        raise KeyboardInterrupt()

    def lrem(self, key: str, count: int, value: str) -> None:
        self.lrem_calls.append((key, count, value))


class _StubRedisModule:
    def __init__(self, client: _StubQueueRedisClient) -> None:
        self._client = client

    def from_url(self, url: str, decode_responses: bool = True) -> _StubQueueRedisClient:
        return self._client


class GxDispatchWorkerGroupedExecutionTests(unittest.TestCase):
    def _build_config(self) -> GxWorkerConfig:
        return GxWorkerConfig(
            redis_url="redis://redis:6379/0",
            queue_key="dq-gx:execution-dispatch",
            processing_queue_key="dq-gx:execution-dispatch:processing",
            heartbeat_key="dq-gx:execution-dispatch:worker-heartbeat",
            heartbeat_ttl_seconds=30,
            heartbeat_interval_seconds=10,
            max_rows=100000,
            poll_timeout_seconds=5,
            api_url="http://kong:8000",
            spark_master="local[*]",
            spark_ui_port=4044,
            s3_endpoint="http://aistor:9000",
            s3_access_key="aistor",
            s3_secret_key="aistorpass",
            s3_region="eu-west-1",
            s3_path_style_access=True,
            s3_ssl_enabled=False,
        )

    def test_process_dispatch_message_executes_grouped_scope_payload(self) -> None:
        payload = {
            "run_id": "run-grouped-1",
            "queue_message_id": "run-grouped-1",
            "correlation_id": "corr-grouped-1",
            "requested_by": "user-1",
            "engine_target": "pyspark",
            "execution_shape": "grouped_scope",
            "grouped_execution_plan": {
                "suite_count": 2,
                "batch_count": 1,
                "batches": [
                    {
                        "data_object_version_id": "dov_1",
                        "suite_count": 2,
                        "suites": [
                            {
                                "suite_id": "gx_suite_1",
                                "suite_version": 1,
                                "gx_suite": {
                                    "expectations": [
                                        {"expectation_type": "expect_column_values_to_not_be_null", "kwargs": {"column": "order_id"}}
                                    ]
                                },
                                "resolved_execution_scope": {"data_object_version_ids": ["dov_1"]},
                                "compiled_from": {"rule_ids": ["rule_1"]},
                            },
                            {
                                "suite_id": "gx_suite_2",
                                "suite_version": 1,
                                "gx_suite": {
                                    "expectations": [
                                        {"expectation_type": "expect_column_values_to_not_be_null", "kwargs": {"column": "customer_id"}}
                                    ]
                                },
                                "resolved_execution_scope": {"data_object_version_ids": ["dov_1"]},
                                "compiled_from": {"rule_ids": ["rule_2"]},
                            },
                        ],
                    }
                ],
            },
        }
        reports: list[dict] = []
        duration_events: list[dict[str, object]] = []
        expectation_events: list[dict[str, object]] = []

        with TemporaryDirectory() as tmpdir:
            with patch("gx_dispatch_worker._build_token_provider", return_value=_StubTokenProvider()), patch(
                "gx_dispatch_worker._api_report_run",
                side_effect=lambda *args, **kwargs: reports.append(kwargs),
            ), patch(
                "gx_dispatch_worker._api_get_data_object_version",
                return_value={"storage_uri": "s3://bucket/path", "storage_format": "parquet", "storage_options_json": {}},
            ), patch(
                "gx_dispatch_worker._create_spark_session",
                return_value=_StubSparkSession(),
            ), patch(
                "gx_dispatch_worker._download_s3a_prefix_to_tempdir",
                return_value=(TemporaryDirectory(), tmpdir),
            ), patch(
                "gx_dispatch_worker._spark_read_dataset",
                return_value=object(),
            ), patch(
                "gx_dispatch_worker._evaluate_expectations_spark",
                return_value=(True, {"passed": 1}, []),
            ), patch(
                "gx_dispatch_worker.record_worker_duration",
                side_effect=lambda *args, **kwargs: duration_events.append(kwargs),
            ), patch(
                "gx_dispatch_worker.record_worker_expectation_results",
                side_effect=lambda *args, **kwargs: expectation_events.append(kwargs),
            ):
                process_dispatch_message(self._build_config(), raw_message=json.dumps(payload))

        self.assertGreaterEqual(len(reports), 4)
        self.assertEqual(reports[0]["new_status"], "running")
        self.assertEqual(reports[-1]["new_status"], "succeeded")
        self.assertEqual(reports[-1]["result_summary"]["selection_mode"], "grouped_scope")
        self.assertEqual(reports[-1]["result_summary"]["suite_count"], 2)
        self.assertTrue(any(event["stage"] == "source_read" for event in duration_events))
        self.assertTrue(any(event["stage"] == "batch_execution" for event in duration_events))
        self.assertTrue(any(event["stage"] == "dispatch" for event in duration_events))
        self.assertTrue(expectation_events)

    def test_process_dispatch_message_rejects_grouped_payload_without_batches(self) -> None:
        payload = {
            "run_id": "run-grouped-2",
            "correlation_id": "corr-grouped-2",
            "execution_shape": "grouped_scope",
            "grouped_execution_plan": {"suite_count": 0, "batch_count": 0},
        }

        with self.assertRaises(GxWorkerExecutionError) as error:
            process_dispatch_message(self._build_config(), raw_message=json.dumps(payload))

        self.assertEqual(error.exception.failure_code, "GX_DISPATCH_INVALID_PAYLOAD")

    def test_process_dispatch_message_executes_join_pair_from_materialized_source(self) -> None:
        payload = {
            "run_id": "run-join-1",
            "queue_message_id": "run-join-1",
            "correlation_id": "corr-join-1",
            "requested_by": "user-1",
            "engine_target": "pyspark",
            "execution_shape": "join_pair",
            "suite_id": "gx_suite_join",
            "suite_version": 3,
        }
        reports: list[dict] = []
        duration_events: list[dict[str, object]] = []

        envelope = {
            "suite_id": "gx_suite_join",
            "suite_version": 3,
            "gx_suite": {
                "expectations": [
                    {
                        "expectation_type": "expect_column_values_to_equal_other_column",
                        "kwargs": {"column": "status", "other_column": "rhs.status"},
                    }
                ]
            },
            "resolved_execution_scope": {"data_object_version_ids": ["dov_left", "dov_right"]},
            "execution_contract": {
                "engine_target": "pyspark",
                "execution_shape": "join_pair",
                "traceability": {
                    "rule_id": "rule-1",
                    "rule_version_id": "rv-1",
                    "gx_suite_id": "gx_suite_join",
                    "gx_suite_version": 3,
                    "data_object_version_id": "dov_left",
                },
                "source_materialization": {
                    "landing_zone_artifact_id": "lz_gx_suite_join",
                    "landing_zone_version_id": "lzv_3",
                    "output_location": "s3://dq-landing-zone/gx/join-pairs/suite_id=gx_suite_join/suite_version=3/format=parquet",
                    "join_type": "inner",
                    "join_keys": ["order_id"],
                    "left_source": {"data_object_id": "do-left", "data_object_version_id": "dov_left"},
                    "right_source": {"data_object_id": "do-right", "data_object_version_id": "dov_right"},
                },
            },
        }

        with TemporaryDirectory() as tmpdir:
            with patch("gx_dispatch_worker._build_token_provider", return_value=_StubTokenProvider()), patch(
                "gx_dispatch_worker._api_report_run",
                side_effect=lambda *args, **kwargs: reports.append(kwargs),
            ), patch(
                "gx_dispatch_worker._api_get_suite_envelope",
                return_value=envelope,
            ), patch(
                "gx_dispatch_worker._api_get_data_object_version",
                side_effect=AssertionError("join_pair should not resolve per-target source locations"),
            ), patch(
                "gx_dispatch_worker._create_spark_session",
                return_value=_StubSparkSession(),
            ), patch(
                "gx_dispatch_worker._download_s3a_prefix_to_tempdir",
                return_value=(TemporaryDirectory(), tmpdir),
            ), patch(
                "gx_dispatch_worker._spark_read_dataset",
                return_value=object(),
            ), patch(
                "gx_dispatch_worker._evaluate_expectations_spark",
                return_value=(True, {"passed_expectation_count": 1, "failed_expectation_count": 0}, []),
            ), patch(
                "gx_dispatch_worker.record_worker_duration",
                side_effect=lambda *args, **kwargs: duration_events.append(kwargs),
            ), patch(
                "gx_dispatch_worker.record_worker_expectation_results",
                side_effect=lambda *args, **kwargs: None,
            ):
                process_dispatch_message(self._build_config(), raw_message=json.dumps(payload))

        self.assertGreaterEqual(len(reports), 3)
        self.assertEqual(reports[0]["new_status"], "running")
        self.assertEqual(reports[-1]["new_status"], "succeeded")
        self.assertEqual(
            reports[-1]["result_summary"]["results"][0]["storage_uri"],
            "s3://dq-landing-zone/gx/join-pairs/suite_id=gx_suite_join/suite_version=3/format=parquet",
        )
        self.assertEqual(reports[-1]["result_summary"]["results"][0]["storage_format"], "parquet")
        self.assertTrue(any(event["execution_shape"] == "join_pair" for event in duration_events))


if __name__ == "__main__":
    unittest.main()