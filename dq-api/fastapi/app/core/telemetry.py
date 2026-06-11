from __future__ import annotations

import os
import socket
import logging
from contextlib import contextmanager
from typing import Sequence
from typing import Iterator
from typing import Any
from urllib.parse import urlparse

from fastapi import FastAPI
from opentelemetry import metrics
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter as OTLPGrpcMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter as OTLPGrpcSpanExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter as OTLPHttpMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter as OTLPHttpSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from opentelemetry.trace import Span
from opentelemetry.trace import Status
from opentelemetry.trace import StatusCode

from app.core.config import Settings
from app.infrastructure.orm.session import get_engine

_TRACE_PROVIDER: TracerProvider | None = None
_METER_PROVIDER: MeterProvider | None = None
_TELEMETRY_CONFIGURED = False
_LOGGING_INSTRUMENTED = False
_HTTPX_INSTRUMENTED = False
_SQLALCHEMY_INSTRUMENTED: set[str] = set()
_INSTRUMENTED_APPS: set[int] = set()
logger = logging.getLogger(__name__)


def _trace_export_debug_enabled() -> bool:
    return os.getenv("OTEL_TRACE_EXPORT_DEBUG", "0").lower() in {"1", "true", "yes"}


class _LoggingSpanExporter(SpanExporter):
    def __init__(self, exporter: SpanExporter, endpoint: str) -> None:
        self._exporter = exporter
        self._endpoint = endpoint

    def export(self, spans: Sequence[Any]) -> SpanExportResult:
        span_summaries: list[dict[str, Any]] = []
        trace_ids: list[str] = []
        for span in spans[:8]:
            span_context = getattr(span, "context", None)
            trace_id = None
            span_id = None
            if span_context is not None:
                trace_id = f"{span_context.trace_id:032x}"
                span_id = f"{span_context.span_id:016x}"
                trace_ids.append(trace_id)
            attributes = dict(getattr(span, "attributes", {}) or {})
            span_summaries.append(
                {
                    "name": getattr(span, "name", None),
                    "trace_id": trace_id,
                    "span_id": span_id,
                    "correlation_id": attributes.get("correlation_id"),
                    "job_id": attributes.get("job_id"),
                    "profiling_request_id": attributes.get("profiling_request_id"),
                }
            )

        logger.info(
            "OTLP trace export attempt",
            extra={
                "event": "otel.trace.export.attempt",
                "otel_endpoint": self._endpoint,
                "span_count": len(spans),
                "trace_ids": sorted(set(trace_ids)),
                "span_summaries": span_summaries,
            },
        )
        try:
            result = self._exporter.export(spans)
        except Exception:
            logger.exception(
                "OTLP trace export failed",
                extra={
                    "event": "otel.trace.export.failure",
                    "otel_endpoint": self._endpoint,
                    "span_count": len(spans),
                    "trace_ids": sorted(set(trace_ids)),
                },
            )
            raise

        logger.info(
            "OTLP trace export result",
            extra={
                "event": "otel.trace.export.result",
                "otel_endpoint": self._endpoint,
                "span_count": len(spans),
                "trace_ids": sorted(set(trace_ids)),
                "result": getattr(result, "name", str(result)),
            },
        )
        return result

    def shutdown(self) -> None:
        self._exporter.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return self._exporter.force_flush(timeout_millis)


def _build_trace_exporter(endpoint: str) -> SpanExporter:
    protocol = _otlp_protocol(endpoint)
    if protocol == "grpc":
        exporter_endpoint, insecure = _otlp_grpc_exporter_endpoint(endpoint)
        exporter = OTLPGrpcSpanExporter(endpoint=exporter_endpoint, insecure=insecure)
    else:
        exporter = OTLPHttpSpanExporter(endpoint=endpoint)

    if _trace_export_debug_enabled():
        logger.info("OTLP trace export debug enabled", extra={"event": "otel.trace.export.debug", "otel_endpoint": endpoint})
        exporter = _LoggingSpanExporter(exporter, endpoint)
    return exporter


def normalize_environment_label(environment: str | None) -> str:
    normalized = (environment or "dev").strip().lower()
    if normalized in {"development", "local"}:
        return "dev"
    if normalized in {"testing", "ci"}:
        return "test"
    if normalized in {"production"}:
        return "prod"
    return normalized or "dev"


def current_trace_id() -> str | None:
    span_context = trace.get_current_span().get_span_context()
    if not span_context.is_valid:
        return None
    return f"{span_context.trace_id:032x}"


def current_span_id() -> str | None:
    span_context = trace.get_current_span().get_span_context()
    if not span_context.is_valid:
        return None
    return f"{span_context.span_id:016x}"


def set_span_attributes(span: Span, **attributes: Any) -> None:
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
def traced_span(name: str, **attributes: Any) -> Iterator[Span]:
    tracer = trace.get_tracer(_service_name())
    with tracer.start_as_current_span(name) as span:
        set_span_attributes(span, **attributes)
        try:
            yield span
        except Exception as exc:
            if span.is_recording():
                span.record_exception(exc)
                span.set_status(Status(StatusCode.ERROR, str(exc)))
            raise


def _service_name() -> str:
    return os.getenv("OTEL_SERVICE_NAME", "dq-api")


def _service_version() -> str:
    return os.getenv("OTEL_SERVICE_VERSION", "unknown")


def _environment(settings: Settings) -> str:
    env = os.getenv("ENVIRONMENT", settings.environment)
    return normalize_environment_label(env)


def _otlp_endpoint() -> str:
    return os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")


def _otlp_protocol(endpoint: str | None = None) -> str:
    raw = os.getenv("OTEL_EXPORTER_OTLP_PROTOCOL", "").strip().lower()
    if raw in {"grpc"}:
        return "grpc"
    if raw in {"http/protobuf", "http"}:
        return "http"

    resolved = endpoint or _otlp_endpoint()
    target = _otlp_target(resolved)
    if target and target[1] == 4317:
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


def _otlp_target(endpoint: str) -> tuple[str, int] | None:
    parsed = urlparse(endpoint if "://" in endpoint else f"http://{endpoint}")
    host = parsed.hostname
    if not host:
        return None
    port = parsed.port
    if port is None:
        # Default ports: use 443 for https and 4318 for http (OTLP/HTTP),
        # fall back to 4317 for legacy gRPC if needed.
        if parsed.scheme == "https":
            port = 443
        elif parsed.scheme == "http":
            port = 4318
        else:
            port = 4317
    return host, port


def _is_otlp_endpoint_reachable(endpoint: str, timeout_seconds: float = 0.5) -> bool:
    target = _otlp_target(endpoint)
    if target is None:
        return False
    try:
        with socket.create_connection(target, timeout=timeout_seconds):
            return True
    except OSError:
        return False


def _metric_export_interval_ms() -> int:
    raw = os.getenv("OTEL_METRIC_EXPORT_INTERVAL_MS", "10000")
    try:
        value = int(raw)
    except ValueError:
        return 10000
    return max(1000, value)


def _sampler_ratio() -> float:
    raw = os.getenv("OTEL_TRACES_SAMPLER_ARG", "0.1")
    try:
        value = float(raw)
    except ValueError:
        return 0.1
    return max(0.0, min(value, 1.0))


def _extract_header(scope: dict[str, Any], header_name: str) -> str | None:
    target = header_name.lower().encode("latin-1")
    for key, value in scope.get("headers", []):
        if key.lower() == target:
            return value.decode("latin-1")
    return None


def _server_request_hook(span, scope: dict[str, Any]) -> None:
    if span is None or not span.is_recording():
        return

    correlation_id = _extract_header(scope, "x-correlation-id")
    if correlation_id:
        span.set_attribute("correlation_id", correlation_id)

    span.set_attribute("environment", normalize_environment_label(os.getenv("ENVIRONMENT", "dev")))
    span.set_attribute("service.version", _service_version())
    scope["otel.trace_id"] = f"{span.get_span_context().trace_id:032x}"


def configure_telemetry(settings: Settings) -> None:
    global _TRACE_PROVIDER, _METER_PROVIDER, _TELEMETRY_CONFIGURED, _LOGGING_INSTRUMENTED, _HTTPX_INSTRUMENTED

    if _TELEMETRY_CONFIGURED:
        return

    endpoint = _otlp_endpoint()
    protocol = _otlp_protocol(endpoint)
    # Allow forcing OTLP exporter via environment when collector may be brought up later
    force_export = os.getenv("OTEL_EXPORTER_OTLP_FORCE", "0").lower() in {"1", "true", "yes"}
    exporter_available = _is_otlp_endpoint_reachable(endpoint) or force_export
    if not exporter_available:
        logger.warning(
            "OpenTelemetry exporter endpoint %s is unavailable; telemetry export is disabled for this run.",
            endpoint,
            extra={
                "event": "otel.export.disabled",
                "otel_endpoint": endpoint,
                "otel_protocol": protocol,
            },
        )
    if force_export and exporter_available:
        logger.info("OTLP exporter forced on by OTEL_EXPORTER_OTLP_FORCE; exporter endpoint: %s", endpoint)

    provider = TracerProvider(
        resource=Resource.create(
            {
                "service.name": _service_name(),
                "service.version": _service_version(),
                "deployment.environment": _environment(settings),
            }
        ),
        sampler=ParentBased(TraceIdRatioBased(_sampler_ratio())),
    )
    if exporter_available:
        if protocol == "grpc":
            provider.add_span_processor(BatchSpanProcessor(_build_trace_exporter(endpoint)))
        else:
            # Use OTLP HTTP exporter when endpoint is an HTTP URL, ensure correct v1 path.
            span_endpoint = endpoint.rstrip("/")
            if span_endpoint.startswith("http://") or span_endpoint.startswith("https://"):
                if not span_endpoint.endswith("/v1/traces"):
                    span_endpoint = span_endpoint + "/v1/traces"
            provider.add_span_processor(BatchSpanProcessor(_build_trace_exporter(span_endpoint)))
    else:
        # If OTLP endpoint is unavailable, allow a console exporter for local debugging
        if os.getenv("OTEL_CONSOLE_EXPORT", "0").lower() in {"1", "true", "yes"}:
            provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(provider)
    _TRACE_PROVIDER = provider

    # Optional: allow console export even when OTLP exporter is available
    if os.getenv("OTEL_CONSOLE_EXPORT", "0").lower() in {"1", "true", "yes"}:
        provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))

    endpoint = _otlp_endpoint()
    protocol = _otlp_protocol(endpoint)
    metric_readers: list[PeriodicExportingMetricReader] = []
    if exporter_available:
        if protocol == "grpc":
            exporter_endpoint, insecure = _otlp_grpc_exporter_endpoint(endpoint)
            metric_readers.append(
                PeriodicExportingMetricReader(
                    OTLPGrpcMetricExporter(endpoint=exporter_endpoint, insecure=insecure),
                    export_interval_millis=_metric_export_interval_ms(),
                )
            )
        else:
            metric_endpoint = endpoint.rstrip("/")
            if metric_endpoint.startswith("http://") or metric_endpoint.startswith("https://"):
                if not metric_endpoint.endswith("/v1/metrics"):
                    metric_endpoint = metric_endpoint + "/v1/metrics"
            metric_readers.append(
                PeriodicExportingMetricReader(
                    OTLPHttpMetricExporter(endpoint=metric_endpoint),
                    export_interval_millis=_metric_export_interval_ms(),
                )
            )
    _METER_PROVIDER = MeterProvider(
        resource=Resource.create(
            {
                "service.name": _service_name(),
                "service.version": _service_version(),
                "deployment.environment": _environment(settings),
            }
        ),
        metric_readers=metric_readers,
    )
    metrics.set_meter_provider(_METER_PROVIDER)

    _TELEMETRY_CONFIGURED = True

    if not _LOGGING_INSTRUMENTED:
        LoggingInstrumentor().instrument(set_logging_format=False)
        _LOGGING_INSTRUMENTED = True

    if not _HTTPX_INSTRUMENTED:
        HTTPXClientInstrumentor().instrument()
        _HTTPX_INSTRUMENTED = True

    if settings.database_url and settings.database_url not in _SQLALCHEMY_INSTRUMENTED:
        SQLAlchemyInstrumentor().instrument(engine=get_engine(settings.database_url))
        _SQLALCHEMY_INSTRUMENTED.add(settings.database_url)


def instrument_app(app: FastAPI, settings: Settings) -> None:
    configure_telemetry(settings)
    if id(app) in _INSTRUMENTED_APPS:
        return

    FastAPIInstrumentor.instrument_app(
        app,
        server_request_hook=_server_request_hook,
    )
    _INSTRUMENTED_APPS.add(id(app))


def shutdown_telemetry() -> None:
    if _TRACE_PROVIDER is None:
        return
    _TRACE_PROVIDER.force_flush()
    if _METER_PROVIDER is not None:
        _METER_PROVIDER.force_flush()
