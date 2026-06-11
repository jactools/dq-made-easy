import os
import unittest
from unittest.mock import patch

import gx_dispatch_telemetry


os.environ.setdefault("OTEL_EXPORTER_OTLP_ENDPOINT", "")

from gx_dispatch_telemetry import _http_signal_endpoint
from gx_dispatch_telemetry import _executor_heartbeat_timestamp_callback
from gx_dispatch_telemetry import _executor_heartbeat_ttl_callback
from gx_dispatch_telemetry import _otlp_grpc_exporter_endpoint
from gx_dispatch_telemetry import _otlp_protocol
from gx_dispatch_telemetry import _worker_heartbeat_timestamp_callback
from gx_dispatch_telemetry import _worker_heartbeat_ttl_callback
from gx_dispatch_telemetry import record_worker_duration
from gx_dispatch_telemetry import record_worker_expectation_results
from gx_dispatch_telemetry import record_worker_failure
from gx_dispatch_telemetry import record_worker_heartbeat


class GxDispatchTelemetryTests(unittest.TestCase):
    def test_otlp_protocol_uses_grpc_for_4317(self) -> None:
        self.assertEqual(_otlp_protocol("http://dq-otel-collector:4317"), "grpc")

    def test_otlp_protocol_uses_http_for_non_grpc_port(self) -> None:
        self.assertEqual(_otlp_protocol("http://dq-otel-collector:4319"), "http")

    def test_http_signal_endpoint_appends_suffix_once(self) -> None:
        self.assertEqual(
            _http_signal_endpoint("http://dq-otel-collector:4319", "/v1/metrics"),
            "http://dq-otel-collector:4319/v1/metrics",
        )
        self.assertEqual(
            _http_signal_endpoint("http://dq-otel-collector:4319/v1/metrics", "/v1/metrics"),
            "http://dq-otel-collector:4319/v1/metrics",
        )

    def test_otlp_grpc_exporter_endpoint_preserves_host_port_and_insecure(self) -> None:
        self.assertEqual(
            _otlp_grpc_exporter_endpoint("http://dq-otel-collector:4317"),
            ("dq-otel-collector:4317", True),
        )

    def test_record_worker_heartbeat_updates_observable_state(self) -> None:
        record_worker_heartbeat(queue_key="dq-gx:execution-dispatch", heartbeat_ttl_seconds=30)

        timestamp_observations = list(_worker_heartbeat_timestamp_callback(None))
        ttl_observations = list(_worker_heartbeat_ttl_callback(None))
        canonical_timestamp_observations = list(_executor_heartbeat_timestamp_callback(None))
        canonical_ttl_observations = list(_executor_heartbeat_ttl_callback(None))

        self.assertTrue(
            any(
                observation.attributes.get("queue_key") == "dq-gx:execution-dispatch" and observation.value > 0
                for observation in timestamp_observations
            )
        )
        self.assertTrue(
            any(
                observation.attributes.get("queue_key") == "dq-gx:execution-dispatch" and observation.value == 30
                for observation in ttl_observations
            )
        )
        self.assertTrue(
            any(
                observation.attributes.get("queue_key") == "dq-gx:execution-dispatch"
                and observation.attributes.get("executor") == "gx"
                and observation.value > 0
                for observation in canonical_timestamp_observations
            )
        )
        self.assertTrue(
            any(
                observation.attributes.get("queue_key") == "dq-gx:execution-dispatch"
                and observation.attributes.get("executor") == "gx"
                and observation.value == 30
                for observation in canonical_ttl_observations
            )
        )

    def test_record_worker_duration_emits_canonical_latency(self) -> None:
        class _Histogram:
            def __init__(self) -> None:
                self.calls: list[tuple[float, dict[str, object]]] = []

            def record(self, value, attributes):
                self.calls.append((value, attributes))

        legacy_execution = _Histogram()
        legacy_source = _Histogram()
        canonical = _Histogram()

        with (
            patch.object(gx_dispatch_telemetry, "_WORKER_EXECUTION_DURATION", legacy_execution),
            patch.object(gx_dispatch_telemetry, "_WORKER_SOURCE_READ_DURATION", legacy_source),
            patch.object(gx_dispatch_telemetry, "_EXECUTION_LATENCY", canonical),
        ):
            record_worker_duration(
                stage="batch_execution",
                execution_shape="single_object",
                duration_ms=42.0,
                result="succeeded",
            )

        self.assertEqual(canonical.calls[0][0], 42.0)
        self.assertEqual(
            canonical.calls[0][1],
            {
                "executor": "gx",
                "engine_type": "gx",
                "phase": "execution",
                "execution_shape": "single_object",
                "result": "succeeded",
            },
        )

    def test_record_worker_expectation_results_emits_canonical_results(self) -> None:
        class _Counter:
            def __init__(self) -> None:
                self.calls: list[tuple[int, dict[str, object]]] = []

            def add(self, value, attributes):
                self.calls.append((value, attributes))

        legacy = _Counter()
        canonical = _Counter()

        with (
            patch.object(gx_dispatch_telemetry, "_WORKER_EXPECTATION_RESULTS", legacy),
            patch.object(gx_dispatch_telemetry, "_EXECUTION_RESULTS", canonical),
        ):
            record_worker_expectation_results(
                execution_shape="single_object",
                passed_count=3,
                failed_count=1,
            )

        self.assertEqual(
            canonical.calls,
            [
                (3, {"executor": "gx", "engine_type": "gx", "execution_shape": "single_object", "result": "passed"}),
                (1, {"executor": "gx", "engine_type": "gx", "execution_shape": "single_object", "result": "failed"}),
            ],
        )

    def test_record_worker_failure_emits_canonical_failures(self) -> None:
        class _Counter:
            def __init__(self) -> None:
                self.calls: list[tuple[int, dict[str, object]]] = []

            def add(self, value, attributes):
                self.calls.append((value, attributes))

        legacy = _Counter()
        canonical = _Counter()

        with (
            patch.object(gx_dispatch_telemetry, "_WORKER_FAILURES", legacy),
            patch.object(gx_dispatch_telemetry, "_EXECUTION_FAILURES", canonical),
        ):
            record_worker_failure(stage="dispatch", execution_shape="single_object", reason="runtime_error")

        self.assertEqual(
            canonical.calls,
            [(1, {"executor": "gx", "engine_type": "gx", "failure_kind": "runtime_error"})],
        )


if __name__ == "__main__":
    unittest.main()