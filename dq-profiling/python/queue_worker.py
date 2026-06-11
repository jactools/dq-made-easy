import os
import json
import logging
import uuid
import urllib.error
import urllib.request
from urllib.parse import quote
from typing import Any, Sequence

from profiling_metrics import (
    record_failure,
    record_redis_failure,
    record_redis_request,
    record_request,
    start_metrics_server,
)

try:
    import redis
except Exception:
    redis = None
try:
    import fakeredis
except Exception:
    fakeredis = None
try:
    import psycopg  # noqa: F401
except Exception:  # pragma: no cover
    psycopg = None
try:
    from opentelemetry import trace, propagate
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter, SimpleSpanProcessor
    from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
except Exception:
    trace = None
    propagate = None
    OTLPSpanExporter = None
    Resource = None
    TracerProvider = None
    BatchSpanProcessor = None
    ConsoleSpanExporter = None
    SimpleSpanProcessor = None
    SpanExporter = None
    SpanExportResult = None

from etl import handle_etl_job
from test_data_jobs import handle_test_data_job

LOG = logging.getLogger("dq.profiling.worker")
logging.basicConfig(level=logging.INFO)


def _failure_type_from_exception(exc: Exception) -> str:
    return exc.__class__.__name__.strip() or "unknown"


def _request_type_from_data(data: dict[str, Any]) -> str:
    return str(data.get("type") or "profiling").strip().lower() or "profiling"


class _InstrumentedRedisClient:
    def __init__(self, client: Any) -> None:
        self._client = client

    def __getattr__(self, name: str) -> Any:
        return getattr(self._client, name)

    def _call(self, operation_type: str, callable_obj: Any, *args: Any, **kwargs: Any) -> Any:
        try:
            result = callable_obj(*args, **kwargs)
        except Exception as exc:
            record_redis_failure(operation_type, _failure_type_from_exception(exc))
            raise

        record_redis_request(operation_type, "success")
        return result

    def ping(self, *args: Any, **kwargs: Any) -> Any:
        return self._call("ping", self._client.ping, *args, **kwargs)

    def brpop(self, *args: Any, **kwargs: Any) -> Any:
        return self._call("brpop", self._client.brpop, *args, **kwargs)

    def get(self, *args: Any, **kwargs: Any) -> Any:
        return self._call("get", self._client.get, *args, **kwargs)

    def set(self, *args: Any, **kwargs: Any) -> Any:
        return self._call("set", self._client.set, *args, **kwargs)

    def lpush(self, *args: Any, **kwargs: Any) -> Any:
        return self._call("lpush", self._client.lpush, *args, **kwargs)


class ProfilingRequestStatusStore:
    """Backwards-compatible name for test fakes.

    This worker no longer connects directly to Postgres. It reports profiling
    request status transitions back to the dq-api over HTTP.
    """


class ProfilingRequestStatusReporter:
    def __init__(self, api_url: str, *, timeout_seconds: int = 10) -> None:
        api_url = str(api_url or "").strip().rstrip("/")
        if not api_url:
            raise RuntimeError("DQ_API_INTERNAL_URL is required for profiling worker status reporting")
        self._api_url = api_url
        self._timeout_seconds = int(timeout_seconds)

    def set_started(self, profiling_request_id: str, job_id: str, *, correlation_id: str | None = None) -> None:
        self._post(
            f"/rulebuilder/v1/profiling/requests/{profiling_request_id}/report",
            payload={"new_status": "started", "job_id": job_id},
            correlation_id=correlation_id,
        )

    def set_completed(
        self,
        profiling_request_id: str,
        success: bool,
        error_message: str | None = None,
        *,
        correlation_id: str | None = None,
    ) -> None:
        self._post(
            f"/rulebuilder/v1/profiling/requests/{profiling_request_id}/report",
            payload={
                "new_status": "completed" if success else "failed",
                "error_message": error_message,
            },
            correlation_id=correlation_id,
        )

    def _post(self, path: str, *, payload: dict[str, Any], correlation_id: str | None) -> None:
        url = f"{self._api_url}{path}"
        body = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if correlation_id:
            headers["X-Correlation-ID"] = correlation_id
            headers["X-Kong-Request-Id"] = correlation_id
        else:
            headers["X-Kong-Request-Id"] = f"dq-profiling-worker-{uuid.uuid4()}"

        req = urllib.request.Request(url, data=body, method="POST", headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self._timeout_seconds) as response:
                status = int(getattr(response, "status", 200) or 200)
                if status >= 400:
                    raise RuntimeError(f"profiling status report failed: HTTP {status}")
        except urllib.error.HTTPError as exc:
            raise RuntimeError(
                f"profiling status report failed: HTTP {exc.code}"
            ) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(
                f"profiling worker cannot reach API at '{self._api_url}'"
            ) from exc


def _trace_export_debug_enabled() -> bool:
    return os.environ.get("OTEL_TRACE_EXPORT_DEBUG", "0").lower() in {"1", "true", "yes"}


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

        LOG.info(
            "OTLP trace export attempt endpoint=%s span_count=%s trace_ids=%s span_summaries=%s",
            self._endpoint,
            len(spans),
            sorted(set(trace_ids)),
            span_summaries,
        )
        try:
            result = self._exporter.export(spans)
        except Exception:
            LOG.exception(
                "OTLP trace export failed endpoint=%s span_count=%s trace_ids=%s",
                self._endpoint,
                len(spans),
                sorted(set(trace_ids)),
            )
            raise

        LOG.info(
            "OTLP trace export result endpoint=%s span_count=%s trace_ids=%s result=%s",
            self._endpoint,
            len(spans),
            sorted(set(trace_ids)),
            getattr(result, "name", str(result)),
        )
        return result

    def shutdown(self) -> None:
        self._exporter.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return self._exporter.force_flush(timeout_millis)


def _build_trace_exporter(endpoint: str) -> SpanExporter:
    exporter: SpanExporter = OTLPSpanExporter(endpoint=endpoint)
    if _trace_export_debug_enabled():
        LOG.info("OTLP trace export debug enabled endpoint=%s", endpoint)
        exporter = _LoggingSpanExporter(exporter, endpoint)
    return exporter


def _resolve_queue_key() -> str:
    return (
        os.environ.get("DQ_PROFILING_LOCAL_QUEUE")
        or os.environ.get("DQ_PROFILING_QUEUE_KEY")
        or os.environ.get("PROFILING_QUEUE_KEY")
        or "dq-profiling:local-queue"
    )


def _resolve_redis_url() -> str:
    explicit_url = os.environ.get("REDIS_URL") or os.environ.get("PROFILING_REDIS_URL")
    if explicit_url:
        return explicit_url

    redis_host = str(os.environ.get("REDIS_HOST") or "").strip()
    if not redis_host:
        return "redis://localhost:6379/0"

    redis_port = int(os.environ.get("REDIS_PORT", "6379"))
    redis_db = int(os.environ.get("REDIS_DB", "0"))
    redis_password = os.environ.get("REDIS_PASSWORD")
    if redis_password:
        return f"redis://:{quote(redis_password, safe='')}@{redis_host}:{redis_port}/{redis_db}"
    return f"redis://{redis_host}:{redis_port}/{redis_db}"


def _resolve_api_url() -> str | None:
    api_url = str(os.environ.get("DQ_API_INTERNAL_URL") or "").strip()
    return api_url.rstrip("/") or None


def _build_status_reporter() -> ProfilingRequestStatusReporter:
    api_url = _resolve_api_url()
    if not api_url:
        raise RuntimeError("DQ_API_INTERNAL_URL is required for profiling worker (used for request status reporting)")
    return ProfilingRequestStatusReporter(api_url)


def _handle_job(
    data: dict[str, Any],
    status_store: Any,
    redis_client: Any | None = None,
) -> dict[str, Any]:
    job_type = _request_type_from_data(data)
    if job_type == "test_data_generation":
        if redis_client is None:
            error = RuntimeError("Redis client is required for test_data_generation jobs")
            record_request(job_type, "failure")
            record_failure(job_type, _failure_type_from_exception(error))
            raise error

        try:
            result = handle_test_data_job(data, redis_client)
        except Exception as exc:
            record_request(job_type, "failure")
            record_failure(job_type, _failure_type_from_exception(exc))
            raise

        record_request(job_type, "success")
        return result

    profiling_request_id = str(data.get("profiling_request_id") or "").strip()
    job_id = str(data.get("job_id") or "").strip()
    correlation_id = str(data.get("correlation_id") or "").strip() or None

    if profiling_request_id and job_id:
        status_store.set_started(profiling_request_id, job_id, correlation_id=correlation_id)

    try:
        result = handle_etl_job(data)
    except Exception as exc:
        if profiling_request_id:
            status_store.set_completed(profiling_request_id, success=False, error_message=str(exc), correlation_id=correlation_id)
        record_request(job_type, "failure")
        record_failure(job_type, _failure_type_from_exception(exc))
        raise

    if profiling_request_id:
        status_store.set_completed(profiling_request_id, success=True, correlation_id=correlation_id)

    record_request(job_type, "success")
    return result


def _configure_telemetry():
    if trace is None or TracerProvider is None or OTLPSpanExporter is None or Resource is None:
        LOG.warning("OpenTelemetry SDK is unavailable in profiling worker; traces are disabled")
        return None

    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318").rstrip("/")
    if endpoint.startswith("http://") or endpoint.startswith("https://"):
        if not endpoint.endswith("/v1/traces"):
            endpoint = endpoint + "/v1/traces"

    provider = TracerProvider(
        resource=Resource.create(
            {
                "service.name": os.environ.get("OTEL_SERVICE_NAME", "dq-profiling"),
                "service.version": os.environ.get("OTEL_SERVICE_VERSION", "dev"),
                "deployment.environment": os.environ.get("ENVIRONMENT", "dev"),
            }
        )
    )
    provider.add_span_processor(BatchSpanProcessor(_build_trace_exporter(endpoint)))
    if os.environ.get("OTEL_CONSOLE_EXPORT", "0").lower() in {"1", "true", "yes"}:
        provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(provider)
    return provider


def run_worker():
    queue_key = _resolve_queue_key()
    redis_url = _resolve_redis_url()
    telemetry_provider = _configure_telemetry()
    status_store = _build_status_reporter()

    metrics_port_raw = str(os.environ.get("PROFILING_METRICS_PORT") or "").strip()
    if metrics_port_raw:
        try:
            start_metrics_server(int(metrics_port_raw))
        except Exception:
            LOG.exception("Failed to start profiling metrics server on port %s", metrics_port_raw)
            raise

    if redis is None:
        LOG.error("redis package not installed. Install with pip install -r requirements.txt")
        return 1

    use_fakeredis = os.environ.get('USE_FAKEREDIS', '').lower() in ('1', 'true', 'yes')
    if use_fakeredis:
        if fakeredis is None:
            LOG.error("fakeredis not installed. Install with pip install -r requirements.txt")
            return 3
        r = _InstrumentedRedisClient(fakeredis.FakeStrictRedis(decode_responses=True))
        LOG.info("Using fakeredis in-memory instance for testing")
    else:
        try:
            r = _InstrumentedRedisClient(redis.from_url(redis_url, decode_responses=True))
            r.ping()
        except Exception as exc:
            record_redis_failure("connect", _failure_type_from_exception(exc))
            LOG.error("Cannot connect to Redis at %s: %s", redis_url, exc)
            return 2

    LOG.info("Listening on local queue key=%s", queue_key)
    try:
        while True:
            # BRPOP returns (key, value) or None
            item = r.brpop(queue_key, timeout=5)
            if not item:
                continue
            _, payload = item
            try:
                data = json.loads(payload)
            except Exception:
                LOG.exception("Failed to parse payload: %r", payload)
                continue

            LOG.info("Received job from queue: %s", data.get('job_id'))
            try:
                # Try to continue/extract trace context and create a span around processing
                if trace is not None:
                    tracer = trace.get_tracer("dq-profiling-worker")
                else:
                    tracer = None

                ctx = None
                try:
                    carrier = data.get('headers') if isinstance(data.get('headers'), dict) else {}
                    if propagate is not None and carrier:
                        ctx = propagate.extract(carrier)
                except Exception:
                    ctx = None

                if tracer is not None:
                    if ctx is not None:
                        span_cm = tracer.start_as_current_span("profiling.worker.process", context=ctx)
                    else:
                        span_cm = tracer.start_as_current_span("profiling.worker.process")
                else:
                    span_cm = None

                if span_cm is not None:
                    with span_cm as span:
                        try:
                            if span.is_recording():
                                span.set_attribute("job_id", data.get('job_id'))
                                span.set_attribute("profiling_request_id", data.get('profiling_request_id'))
                                span.set_attribute("correlation_id", data.get('correlation_id'))
                            result = _handle_job(data, status_store, r)
                            LOG.info("Processed job. artifactUri=%s", result.get('artifactUri'))
                        except Exception:
                            LOG.exception("Error handling job: %r", data)
                            raise
                else:
                    result = _handle_job(data, status_store, r)
                    LOG.info("Processed job. artifactUri=%s", result.get('artifactUri'))
            except Exception:
                # Already logged inside span block; ensure we continue
                LOG.exception("Error handling job: %r", data)
    except KeyboardInterrupt:
        LOG.info("Worker interrupted, shutting down")
    if telemetry_provider is not None:
        telemetry_provider.force_flush()
    return 0


if __name__ == '__main__':
    exit(run_worker())
