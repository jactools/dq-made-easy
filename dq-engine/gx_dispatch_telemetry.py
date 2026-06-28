from __future__ import annotations

import logging
import os
import time
from contextlib import contextmanager
from threading import Lock
from typing import Iterable
from typing import Any
from typing import Iterator
from urllib.parse import urlparse

from opentelemetry import metrics
from opentelemetry import trace
from opentelemetry.metrics import CallbackOptions
from opentelemetry.metrics import Observation
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter as OTLPGrpcMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter as OTLPGrpcSpanExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ParentBased
from opentelemetry.sdk.trace.sampling import TraceIdRatioBased
from opentelemetry.trace import Span
from opentelemetry.trace import Status
from opentelemetry.trace import StatusCode

logger = logging.getLogger(__name__)

_SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "dq-engine-gx-worker")
_SERVICE_VERSION = os.getenv("OTEL_SERVICE_VERSION", "unknown")
_TELEMETRY_CONFIGURED = False


def _telemetry_endpoint() -> str:
    return str(os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT") or "").strip()


def _otlp_protocol(endpoint: str | None = None) -> str:
    raw_value = str(os.getenv("OTEL_EXPORTER_OTLP_PROTOCOL") or "").strip().lower()
    if raw_value in {"grpc"}:
        return "grpc"
    if raw_value in {"http", "http/protobuf"}:
        return "http"

    resolved = endpoint or _telemetry_endpoint()
    parsed = urlparse(resolved if "://" in resolved else f"http://{resolved}")
    port = parsed.port
    if port == 4317:
        return "grpc"
    return "http"


def _otlp_grpc_exporter_endpoint(endpoint: str) -> tuple[str, bool]:
    parsed = urlparse(endpoint if "://" in endpoint else f"http://{endpoint}")
    host = parsed.hostname
    if not host:
        return endpoint, True

    port = parsed.port or 4317
    insecure = parsed.scheme != "https"
    return f"{host}:{port}", insecure


def _http_signal_endpoint(endpoint: str, suffix: str) -> str:
    normalized = endpoint.rstrip("/")
    if normalized.startswith("http://") or normalized.startswith("https://"):
        if not normalized.endswith(suffix):
            normalized = normalized + suffix
    return normalized


def _trace_sample_ratio() -> float:
    raw_value = str(os.getenv("OTEL_TRACES_SAMPLER_ARG") or "0.1").strip()
    try:
        sample_ratio = float(raw_value)
    except Exception:
        sample_ratio = 0.1
    return max(0.0, min(sample_ratio, 1.0))


def configure_worker_telemetry() -> None:
    global _TELEMETRY_CONFIGURED
    if _TELEMETRY_CONFIGURED:
        return

    endpoint = _telemetry_endpoint()
    if not endpoint:
        _TELEMETRY_CONFIGURED = True
        return

    resource = Resource.create(
        {
            "service.name": _SERVICE_NAME,
            "service.version": _SERVICE_VERSION,
        }
    )
    protocol = _otlp_protocol(endpoint)

    try:
        if protocol == "grpc":
            exporter_endpoint, insecure = _otlp_grpc_exporter_endpoint(endpoint)
            metric_reader = PeriodicExportingMetricReader(
                OTLPGrpcMetricExporter(endpoint=exporter_endpoint, insecure=insecure)
            )
            span_exporter = OTLPGrpcSpanExporter(endpoint=exporter_endpoint, insecure=insecure)
        else:
            metric_reader = PeriodicExportingMetricReader(
                OTLPMetricExporter(endpoint=_http_signal_endpoint(endpoint, "/v1/metrics"))
            )
            span_exporter = OTLPSpanExporter(endpoint=_http_signal_endpoint(endpoint, "/v1/traces"))

        metrics.set_meter_provider(MeterProvider(resource=resource, metric_readers=[metric_reader]))

        tracer_provider = TracerProvider(resource=resource, sampler=ParentBased(TraceIdRatioBased(_trace_sample_ratio())))
        tracer_provider.add_span_processor(BatchSpanProcessor(span_exporter))
        trace.set_tracer_provider(tracer_provider)
    except Exception:
        logger.exception(
            "gx.worker.telemetry.configuration_failed",
            extra={
                "event": "gx.worker.telemetry.configuration_failed",
                "otel_endpoint": endpoint,
                "otel_protocol": protocol,
            },
        )
    finally:
        _TELEMETRY_CONFIGURED = True


configure_worker_telemetry()

_METER = metrics.get_meter(_SERVICE_NAME)
_EXECUTOR_KIND = "gx"
_ENGINE_TYPE = "gx"

_WORKER_EXECUTION_DURATION = _METER.create_histogram(
    name="dq_gx_worker_execution_duration_ms",
    unit="ms",
    description="GX worker execution duration by stage and result.",
)

_WORKER_SOURCE_READ_DURATION = _METER.create_histogram(
    name="dq_gx_worker_source_read_duration_ms",
    unit="ms",
    description="GX worker source read latency by storage format and result.",
)

_WORKER_EXPECTATION_RESULTS = _METER.create_counter(
    name="dq_gx_worker_expectation_results_total",
    unit="1",
    description="GX worker expectation outcomes by result.",
)

_WORKER_FAILURES = _METER.create_counter(
    name="dq_gx_worker_failure_total",
    unit="1",
    description="GX worker failures by stage and reason.",
)

_EXECUTION_LATENCY = _METER.create_histogram(
    name="dq_execution_latency_ms",
    unit="ms",
    description="Canonical execution latency by executor, engine type, and phase.",
)

_EXECUTION_RESULTS = _METER.create_counter(
    name="dq_execution_results_total",
    unit="1",
    description="Canonical execution result counts by executor and engine type.",
)

_EXECUTION_FAILURES = _METER.create_counter(
    name="dq_execution_failures_total",
    unit="1",
    description="Canonical execution failure counts by executor and engine type.",
)

_WORKER_HEARTBEAT_STATE_LOCK = Lock()
_WORKER_HEARTBEAT_STATE: dict[str, dict[str, float]] = {}


def _worker_heartbeat_timestamp_callback(_: CallbackOptions) -> Iterable[Observation]:
    with _WORKER_HEARTBEAT_STATE_LOCK:
        snapshots = list(_WORKER_HEARTBEAT_STATE.items())

    for queue_key, state in snapshots:
        yield Observation(state["timestamp_seconds"], {"queue_key": queue_key})


def _worker_heartbeat_ttl_callback(_: CallbackOptions) -> Iterable[Observation]:
    with _WORKER_HEARTBEAT_STATE_LOCK:
        snapshots = list(_WORKER_HEARTBEAT_STATE.items())

    for queue_key, state in snapshots:
        yield Observation(state["ttl_seconds"], {"queue_key": queue_key})


def _executor_heartbeat_timestamp_callback(_: CallbackOptions) -> Iterable[Observation]:
    with _WORKER_HEARTBEAT_STATE_LOCK:
        snapshots = list(_WORKER_HEARTBEAT_STATE.items())

    for queue_key, state in snapshots:
        yield Observation(
            state["timestamp_seconds"],
            {"executor": _EXECUTOR_KIND, "queue_key": queue_key},
        )


def _executor_heartbeat_ttl_callback(_: CallbackOptions) -> Iterable[Observation]:
    with _WORKER_HEARTBEAT_STATE_LOCK:
        snapshots = list(_WORKER_HEARTBEAT_STATE.items())

    for queue_key, state in snapshots:
        yield Observation(
            state["ttl_seconds"],
            {"executor": _EXECUTOR_KIND, "queue_key": queue_key},
        )


_WORKER_HEARTBEAT_TIMESTAMP = _METER.create_observable_gauge(
    name="dq_gx_worker_heartbeat_timestamp_seconds",
    callbacks=[_worker_heartbeat_timestamp_callback],
    unit="s",
    description="Unix timestamp of the last successful GX worker heartbeat by queue key.",
)

_WORKER_HEARTBEAT_TTL = _METER.create_observable_gauge(
    name="dq_gx_worker_heartbeat_ttl_seconds",
    callbacks=[_worker_heartbeat_ttl_callback],
    unit="s",
    description="Configured GX worker heartbeat TTL by queue key.",
)

_EXECUTOR_HEARTBEAT_TIMESTAMP = _METER.create_observable_gauge(
    name="dq_executor_heartbeat_timestamp_seconds",
    callbacks=[_executor_heartbeat_timestamp_callback],
    unit="s",
    description="Canonical executor heartbeat timestamp by executor and queue key.",
)

_EXECUTOR_HEARTBEAT_TTL = _METER.create_observable_gauge(
    name="dq_executor_heartbeat_ttl_seconds",
    callbacks=[_executor_heartbeat_ttl_callback],
    unit="s",
    description="Canonical executor heartbeat TTL by executor and queue key.",
)


def _canonical_phase(stage: str) -> str:
    normalized_stage = str(stage or "unknown").strip().lower() or "unknown"
    if normalized_stage == "source_read":
        return "source_read"
    if normalized_stage == "dispatch":
        return "dispatch"
    return "execution"


def _set_span_attributes(span: Span, **attributes: Any) -> None:
    if span is None or not span.is_recording():
        return

    for key, value in attributes.items():
        if value is None:
            continue
        if isinstance(value, (bool, int, float, str)):
            span.set_attribute(key, value)
            continue
        if isinstance(value, (list, tuple)) and all(isinstance(item, (bool, int, float, str)) for item in value):
            span.set_attribute(key, list(value))
            continue
        span.set_attribute(key, str(value))


@contextmanager
def traced_worker_span(name: str, **attributes: Any) -> Iterator[Span]:
    tracer = trace.get_tracer(_SERVICE_NAME)
    with tracer.start_as_current_span(name) as span:
        _set_span_attributes(span, **attributes)
        try:
            yield span
        except Exception as exc:
            if span.is_recording():
                span.record_exception(exc)
                span.set_status(Status(StatusCode.ERROR, str(exc)))
            raise


def record_worker_duration(
    *,
    stage: str,
    execution_shape: str,
    duration_ms: float,
    result: str,
    source_format: str | None = None,
    batch_count: int | None = None,
    suite_count: int | None = None,
    target_count: int | None = None,
) -> None:
    attributes: dict[str, Any] = {
        "stage": str(stage or "unknown").strip().lower() or "unknown",
        "execution_shape": str(execution_shape or "unknown").strip().lower() or "unknown",
        "result": str(result or "unknown").strip().lower() or "unknown",
    }
    if source_format:
        attributes["source_format"] = str(source_format).strip().lower() or "unknown"
    if batch_count is not None:
        attributes["batch_count"] = int(batch_count)
    if suite_count is not None:
        attributes["suite_count"] = int(suite_count)
    if target_count is not None:
        attributes["target_count"] = int(target_count)

    _WORKER_EXECUTION_DURATION.record(float(duration_ms), attributes=attributes)
    if stage == "source_read":
        _WORKER_SOURCE_READ_DURATION.record(float(duration_ms), attributes=attributes)

    _EXECUTION_LATENCY.record(
        float(duration_ms),
        attributes={
            "executor": _EXECUTOR_KIND,
            "engine_type": _ENGINE_TYPE,
            "phase": _canonical_phase(stage),
            "execution_shape": str(execution_shape or "unknown").strip().lower() or "unknown",
            "result": str(result or "unknown").strip().lower() or "unknown",
        },
    )


def record_worker_expectation_results(
    *,
    execution_shape: str,
    passed_count: int,
    failed_count: int,
) -> None:
    attributes = {
        "execution_shape": str(execution_shape or "unknown").strip().lower() or "unknown",
    }
    if passed_count > 0:
        _WORKER_EXPECTATION_RESULTS.add(int(passed_count), attributes={**attributes, "result": "passed"})
        _EXECUTION_RESULTS.add(
            int(passed_count),
            attributes={
                "executor": _EXECUTOR_KIND,
                "engine_type": _ENGINE_TYPE,
                "execution_shape": attributes["execution_shape"],
                "result": "passed",
            },
        )
    if failed_count > 0:
        _WORKER_EXPECTATION_RESULTS.add(int(failed_count), attributes={**attributes, "result": "failed"})
        _EXECUTION_RESULTS.add(
            int(failed_count),
            attributes={
                "executor": _EXECUTOR_KIND,
                "engine_type": _ENGINE_TYPE,
                "execution_shape": attributes["execution_shape"],
                "result": "failed",
            },
        )


def record_worker_failure(*, stage: str, execution_shape: str, reason: str) -> None:
    _WORKER_FAILURES.add(
        1,
        attributes={
            "stage": str(stage or "unknown").strip().lower() or "unknown",
            "execution_shape": str(execution_shape or "unknown").strip().lower() or "unknown",
            "reason": str(reason or "unknown").strip().lower() or "unknown",
        },
    )
    _EXECUTION_FAILURES.add(
        1,
        attributes={
            "executor": _EXECUTOR_KIND,
            "engine_type": _ENGINE_TYPE,
            "failure_kind": str(reason or "unknown").strip().lower() or "unknown",
        },
    )


def record_spark_expectations_observability(*, observability_summary: dict[str, Any] | None, result: str | None = None) -> None:
    summary = dict(observability_summary or {})
    if not summary:
        return

    attributes = {
        "executor": "spark_expectations",
        "engine_type": "spark_expectations",
        "rule_family": str(summary.get("rule_family") or "unknown").strip().lower() or "unknown",
        "result": str(result or summary.get("result") or "unknown").strip().lower() or "unknown",
    }
    if summary.get("storage_kind") is not None:
        attributes["storage_kind"] = str(summary.get("storage_kind") or "unknown").strip().lower() or "unknown"
    if summary.get("storage_uri") is not None:
        attributes["storage_uri"] = str(summary.get("storage_uri") or "")

    passed_count = int(summary.get("passed_count") or 0)
    failed_count = int(summary.get("failed_count") or 0)
    if passed_count > 0:
        _EXECUTION_RESULTS.add(
            passed_count,
            attributes={**attributes, "result": "passed"},
        )
    if failed_count > 0:
        _EXECUTION_RESULTS.add(
            failed_count,
            attributes={**attributes, "result": "failed"},
        )
    _EXECUTION_LATENCY.record(
        float(summary.get("duration_ms") or 0.0),
        attributes={**attributes, "phase": "execution", "execution_shape": "single_object"},
    )


def record_worker_heartbeat(*, queue_key: str, heartbeat_ttl_seconds: int) -> None:
    normalized_queue_key = str(queue_key or "unknown").strip() or "unknown"
    try:
        ttl_seconds = max(int(heartbeat_ttl_seconds), 1)
    except Exception:
        ttl_seconds = 1

    with _WORKER_HEARTBEAT_STATE_LOCK:
        _WORKER_HEARTBEAT_STATE[normalized_queue_key] = {
            "timestamp_seconds": float(time.time()),
            "ttl_seconds": float(ttl_seconds),
        }
