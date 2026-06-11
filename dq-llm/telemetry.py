import logging
import os
from contextlib import contextmanager
from typing import Any, Iterator

logger = logging.getLogger(__name__)


class _NoOpSpan:
    def is_recording(self) -> bool:
        return False

    def set_attribute(self, key: str, value: Any) -> None:
        return None

    def record_exception(self, exc: Exception) -> None:
        return None

    def set_status(self, status: Any) -> None:
        return None


class _NoOpSpanContext:
    is_valid = False
    trace_id = 0
    span_id = 0


class _NoOpContextManager:
    def __enter__(self):
        return _NoOpSpan()

    def __exit__(self, exc_type, exc, tb):
        return False


class _NoOpTracer:
    def start_as_current_span(self, name: str):
        return _NoOpContextManager()


class _NoOpTrace:
    def get_tracer(self, name: str):
        return _NoOpTracer()

    def get_current_span(self):
        return _NoOpSpanContext()


try:
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.trace import Span, Status, StatusCode
except ImportError:  # pragma: no cover - exercised when dependencies are unavailable
    trace = _NoOpTrace()
    OTLPSpanExporter = None
    FastAPIInstrumentor = None
    Resource = None
    TracerProvider = None
    BatchSpanProcessor = None
    Span = Any
    Status = None
    StatusCode = None


_SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "dq-llm")


def _service_version() -> str:
    return os.getenv("OTEL_SERVICE_VERSION", "unknown")


def _environment() -> str:
    return os.getenv("ENVIRONMENT", "dev").strip().lower() or "dev"


def _endpoint() -> str:
    return os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")


def configure_telemetry() -> None:
    """Initialize the tracing pipeline for the Pi agent harness."""
    if trace is None or OTLPSpanExporter is None or Resource is None or TracerProvider is None or BatchSpanProcessor is None:
        logger.debug("OpenTelemetry tracing dependencies are not available; tracing remains disabled.")
        return

    provider = TracerProvider(
        resource=Resource.create(
            {
                "service.name": _SERVICE_NAME,
                "service.version": _service_version(),
                "deployment.environment": _environment(),
            }
        )
    )

    endpoint = _endpoint().rstrip("/")
    if endpoint.startswith("http://") or endpoint.startswith("https://"):
        if not endpoint.endswith("/v1/traces"):
            endpoint = f"{endpoint}/v1/traces"

    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    trace.set_tracer_provider(provider)


def instrument_app(app: Any) -> None:
    """Instrument the FastAPI application with OpenTelemetry if available."""
    if FastAPIInstrumentor is None:
        return
    FastAPIInstrumentor.instrument_app(app)


def current_trace_id() -> str | None:
    span_context = trace.get_current_span().get_span_context() if trace is not None else None
    if span_context is None or not getattr(span_context, "is_valid", False):
        return None
    return f"{span_context.trace_id:032x}"


@contextmanager
def traced_span(name: str, **attributes: Any) -> Iterator[Any]:
    """Create a tracing span around an agent or tool execution step."""
    tracer = trace.get_tracer(_SERVICE_NAME) if trace is not None else None
    if tracer is None:
        yield None
        return

    with tracer.start_as_current_span(name) as span:
        for key, value in attributes.items():
            if value is not None:
                span.set_attribute(key, value)
        try:
            yield span
        except Exception as exc:
            if getattr(span, "is_recording", lambda: False)() and Status is not None and StatusCode is not None:
                span.record_exception(exc)
                span.set_status(Status(StatusCode.ERROR, str(exc)))
            raise
