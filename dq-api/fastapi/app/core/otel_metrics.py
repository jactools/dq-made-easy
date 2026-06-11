from __future__ import annotations

import os
from collections.abc import Callable, Iterable
from urllib.parse import quote

from opentelemetry import metrics
from opentelemetry.metrics import CallbackOptions, Observation

from app.core.config import get_settings
from app.core.runtime_queues import resolve_gx_execution_queue_key as _resolve_runtime_execution_queue_key
from app.core.runtime_queues import resolve_gx_join_pair_materialization_queue_key as _resolve_runtime_gx_join_pair_materialization_queue_key
from app.core.runtime_queues import resolve_natural_language_draft_queue_key as _resolve_runtime_natural_language_draft_queue_key
from app.core.runtime_queues import resolve_profiling_queue_key as _resolve_runtime_profiling_queue_key
from app.core.runtime_queues import resolve_test_data_materialization_queue_key as _resolve_runtime_test_data_materialization_queue_key

try:
    import redis as redis_sync
except Exception:  # pragma: no cover - dependency guard
    redis_sync = None

_METER = metrics.get_meter("dq-api")

_REQUEST_COUNTER = _METER.create_counter(
    name="dq_api_request_count",
    unit="1",
    description="Total API requests by endpoint group and status bucket.",
)

_LATENCY_HISTOGRAM = _METER.create_histogram(
    name="dq_api_operation_latency_ms",
    unit="ms",
    description="API operation latency in milliseconds.",
)

_AUTH_FAILURE_COUNTER = _METER.create_counter(
    name="dq_api_auth_failures",
    unit="1",
    description="Authentication and authorization failures.",
)

_CONTRACT_POLICY_CACHE_EVENT_COUNTER = _METER.create_counter(
    name="dq_api_contract_policy_cache_events",
    unit="1",
    description="Contract policy resolution cache events by provider and cache status.",
)

_GX_OPERATION_COUNTER = _METER.create_counter(
    name="dq_gx_operation_events",
    unit="1",
    description="GX orchestration events by surface, operation, and result.",
)

_GX_OPERATION_LATENCY_HISTOGRAM = _METER.create_histogram(
    name="dq_gx_operation_latency_ms",
    unit="ms",
    description="GX orchestration latency in milliseconds.",
)

_GX_FAILURE_COUNTER = _METER.create_counter(
    name="dq_gx_failure_events",
    unit="1",
    description="GX orchestration failures by surface, operation, and reason.",
)

_EXECUTION_COMPILE_EVENT_COUNTER = _METER.create_counter(
    name="dq_execution_compile_events",
    unit="1",
    description="Canonical execution compile/publish events by engine type and result.",
)

_EXECUTION_DISPATCH_EVENT_COUNTER = _METER.create_counter(
    name="dq_execution_dispatch_events",
    unit="1",
    description="Canonical execution dispatch/start events by executor, engine type, and result.",
)

_EXECUTION_FAILURE_COUNTER = _METER.create_counter(
    name="dq_execution_failures",
    unit="1",
    description="Canonical execution failures by executor, engine type, and failure kind.",
)

_EXECUTION_PLANNER_CHOICE_COUNTER = _METER.create_counter(
    name="dq_execution_planner_choice_events",
    unit="1",
    description="Execution planner choice events by planner, choice, and execution path.",
)

_EXECUTION_RUNTIME_COST_HISTOGRAM = _METER.create_histogram(
    name="dq_execution_runtime_cost_ms",
    unit="ms",
    description="Execution runtime cost in milliseconds.",
)

_EXECUTION_DATA_SCANNED_ROWS_HISTOGRAM = _METER.create_histogram(
    name="dq_execution_data_scanned_rows",
    unit="rows",
    description="Execution data scanned in rows.",
)

_EXECUTION_DATA_SCANNED_BYTES_HISTOGRAM = _METER.create_histogram(
    name="dq_execution_data_scanned_bytes",
    unit="bytes",
    description="Execution data scanned in bytes.",
)

_SUGGESTIONS_PREVIEW_EVENT_COUNTER = _METER.create_counter(
    name="dq_suggestions_preview_events",
    unit="1",
    description="Natural-language preview usage events by action, result, and normalized error code.",
)

_NATURAL_LANGUAGE_DRAFT_REQUEST_EVENT_COUNTER = _METER.create_counter(
    name="dq_natural_language_draft_request_events",
    unit="1",
    description="Natural-language draft queue events by stage, result, and analysis provider.",
)

_QUEUE_EVENT_COUNTER = _METER.create_counter(
    name="dq_queue_events",
    unit="1",
    description="Async queue events by service, queue type, stage, and result.",
)

_SUGGESTIONS_REDIS_REQUEST_COUNTER = _METER.create_counter(
    name="dq_suggestions_redis_request_count",
    unit="1",
    description="Redis operations from the suggestions workflow by operation type and status.",
)

_SUGGESTIONS_REDIS_FAILURE_COUNTER = _METER.create_counter(
    name="dq_suggestions_redis_failure_count",
    unit="1",
    description="Redis operation failures from the suggestions workflow by operation type and failure reason.",
)


def _canonical_compile_operation(operation: str) -> str | None:
    normalized = str(operation or "unknown").strip().lower() or "unknown"
    if normalized == "save_suite":
        return "compile_artifact"
    return None


def _canonical_dispatch_operation(operation: str) -> str | None:
    normalized = str(operation or "unknown").strip().lower() or "unknown"
    if normalized == "start_suite_run":
        return "start_run"
    if normalized == "schedule_suite_run":
        return "schedule_run"
    return None


def _is_execution_failure_surface(surface: str) -> bool:
    normalized = str(surface or "unknown").strip().lower() or "unknown"
    return normalized in {"pyspark_executor"}


def _resolve_gx_dispatch_redis_url() -> str | None:
    explicit_url = os.environ.get("GX_EXECUTION_REDIS_URL") or os.environ.get("REDIS_URL")
    if explicit_url:
        text = str(explicit_url).strip()
        return text or None

    settings = get_settings()
    redis_host = str(settings.redis_host or "").strip()
    if not redis_host:
        return None

    redis_port = int(settings.redis_port)
    redis_db = int(settings.redis_db)
    redis_password = settings.redis_password
    if redis_password:
        return f"redis://:{quote(str(redis_password), safe='')}@{redis_host}:{redis_port}/{redis_db}"
    return f"redis://{redis_host}:{redis_port}/{redis_db}"


def _resolve_profiling_redis_url() -> str | None:
    explicit_url = os.environ.get("PROFILING_REDIS_URL") or os.environ.get("REDIS_URL")
    if explicit_url:
        text = str(explicit_url).strip()
        return text or None

    settings = get_settings()
    redis_host = str(settings.redis_host or "").strip()
    if not redis_host:
        return None

    redis_port = int(settings.redis_port)
    redis_db = int(settings.redis_db)
    redis_password = settings.redis_password
    if redis_password:
        return f"redis://:{quote(str(redis_password), safe='')}@{redis_host}:{redis_port}/{redis_db}"
    return f"redis://{redis_host}:{redis_port}/{redis_db}"


def _resolve_gx_execution_queue_key() -> str:
    queue_key = _resolve_runtime_execution_queue_key()
    if queue_key:
        return queue_key
    raise RuntimeError("GX execution queue key is not configured")


def _gx_queue_backlog_callback(_: CallbackOptions) -> Iterable[Observation]:
    redis_url = _resolve_gx_dispatch_redis_url()
    if not redis_url:
        raise RuntimeError("GX dispatch Redis URL is not configured")
    if redis_sync is None:
        raise RuntimeError("redis package is unavailable")

    queue_key = _resolve_gx_execution_queue_key()
    client = redis_sync.from_url(redis_url, decode_responses=True)
    try:
        queue_length = int(client.llen(queue_key))
    finally:
        close_method = getattr(client, "close", None)
        if callable(close_method):
            close_method()

    yield Observation(queue_length, {"queue_key": queue_key})


_QUEUE_BACKLOG_GAUGE = _METER.create_observable_gauge(
    name="dq_gx_dispatch_queue_backlog",
    callbacks=[_gx_queue_backlog_callback],
    unit="1",
    description="Current GX dispatch queue backlog by queue key.",
)


def _resolve_natural_language_draft_redis_url() -> str | None:
    explicit_url = os.environ.get("NATURAL_LANGUAGE_DRAFT_REDIS_URL") or os.environ.get("REDIS_URL")
    if explicit_url:
        text = str(explicit_url).strip()
        return text or None

    settings = get_settings()
    redis_host = str(settings.redis_host or "").strip()
    if not redis_host:
        return None

    redis_port = int(settings.redis_port)
    redis_db = int(settings.redis_db)
    redis_password = settings.redis_password
    if redis_password:
        return f"redis://:{quote(str(redis_password), safe='')}@{redis_host}:{redis_port}/{redis_db}"
    return f"redis://{redis_host}:{redis_port}/{redis_db}"


def _resolve_natural_language_draft_queue_key() -> str:
    queue_key = _resolve_runtime_natural_language_draft_queue_key()
    if queue_key:
        return queue_key
    raise RuntimeError("Natural-language draft queue key is not configured")


def _natural_language_draft_queue_backlog_callback(_: CallbackOptions) -> Iterable[Observation]:
    redis_url = _resolve_natural_language_draft_redis_url()
    if not redis_url:
        raise RuntimeError("Natural-language draft Redis URL is not configured")
    if redis_sync is None:
        raise RuntimeError("redis package is unavailable")

    queue_key = _resolve_natural_language_draft_queue_key()
    client = redis_sync.from_url(redis_url, decode_responses=True)
    try:
        queue_length = int(client.llen(queue_key))
    finally:
        close_method = getattr(client, "close", None)
        if callable(close_method):
            close_method()

    yield Observation(queue_length, {"queue_key": queue_key})


_NATURAL_LANGUAGE_DRAFT_QUEUE_BACKLOG_GAUGE = _METER.create_observable_gauge(
    name="dq_natural_language_draft_queue_backlog",
    callbacks=[_natural_language_draft_queue_backlog_callback],
    unit="1",
    description="Current natural-language draft queue backlog by queue key.",
)


def _configured_queue_specs() -> Iterable[tuple[str, str, str, Callable[[], str | None]]]:
    queue_specs: tuple[tuple[str, str, Callable[[], str | None], Callable[[], str | None]], ...] = (
        ("profiling", "dq-api", _resolve_runtime_profiling_queue_key, _resolve_profiling_redis_url),
        ("natural_language_draft", "dq-api", _resolve_runtime_natural_language_draft_queue_key, _resolve_natural_language_draft_redis_url),
        ("gx_execution", "dq-api", _resolve_runtime_execution_queue_key, _resolve_gx_dispatch_redis_url),
        ("gx_join_pair_materialization", "dq-api", _resolve_runtime_gx_join_pair_materialization_queue_key, _resolve_gx_dispatch_redis_url),
        ("test_data_materialization", "dq-api", _resolve_runtime_test_data_materialization_queue_key, _resolve_profiling_redis_url),
    )

    for queue_type, service, resolve_queue_key, resolve_redis_url in queue_specs:
        queue_key = resolve_queue_key()
        if not queue_key:
            continue
        yield queue_type, service, queue_key, resolve_redis_url


def _queue_backlog_callback(_: CallbackOptions) -> Iterable[Observation]:
    if redis_sync is None:
        raise RuntimeError("redis package is unavailable")

    for queue_type, service, queue_key, resolve_redis_url in _configured_queue_specs():
        redis_url = resolve_redis_url()
        if not redis_url:
            raise RuntimeError(f"Redis URL is not configured for queue type {queue_type}")

        client = redis_sync.from_url(redis_url, decode_responses=True)
        try:
            queue_length = int(client.llen(queue_key))
        finally:
            close_method = getattr(client, "close", None)
            if callable(close_method):
                close_method()

        yield Observation(queue_length, {"service": service, "queue_type": queue_type, "queue_key": queue_key})


_QUEUE_BACKLOG_GAUGE = _METER.create_observable_gauge(
    name="dq_queue_backlog",
    callbacks=[_queue_backlog_callback],
    unit="1",
    description="Current async queue backlog by service, queue type, and queue key.",
)


def _endpoint_group_from_path(path: str) -> str:
    parts = [part for part in str(path or "").split("/") if part]
    if not parts:
        return "unknown"

    def _is_version_token(value: str | None) -> bool:
        return str(value or "").lower().startswith("v") and str(value or "")[1:].isdigit()

    # Internal API: /api/<group>/v1/<resource>/...
    if len(parts) >= 4 and parts[0] == "api" and _is_version_token(parts[2]):
        return parts[3] or "unknown"

    # Gateway/public API: /<group>/v1/...
    if len(parts) >= 2 and _is_version_token(parts[1]):
        return parts[0] or "unknown"

    # Legacy version-first paths: /api/v1/<resource>/... and /v1/<resource>/...
    if len(parts) >= 3 and parts[0] == "api" and _is_version_token(parts[1]):
        return parts[2] or "unknown"
    if len(parts) >= 2 and _is_version_token(parts[0]):
        return parts[1] or "unknown"

    return parts[0] or "unknown"


def _api_version_from_path(path: str) -> str:
    parts = [part for part in str(path or "").split("/") if part]
    if not parts:
        return "unknown"

    def _is_version_token(value: str | None) -> bool:
        return str(value or "").lower().startswith("v") and str(value or "")[1:].isdigit()

    # Internal API: /api/<group>/v1/<resource>/...
    if len(parts) >= 4 and parts[0] == "api" and _is_version_token(parts[2]):
        return parts[2] or "unknown"

    # Gateway/public API: /<group>/v1/...
    if len(parts) >= 2 and _is_version_token(parts[1]):
        return parts[1] or "unknown"

    # Legacy version-first paths: /api/v1/<resource>/... and /v1/<resource>/...
    if len(parts) >= 3 and parts[0] == "api" and _is_version_token(parts[1]):
        return parts[1] or "unknown"
    if len(parts) >= 2 and _is_version_token(parts[0]):
        return parts[0] or "unknown"

    return "unknown"


def _status_bucket(status_code: int) -> str:
    return "success" if int(status_code) < 400 else "error"


def record_request_metric(
    *,
    method: str,
    path: str,
    operation: str,
    status_code: int,
    duration_ms: float,
) -> None:
    endpoint_group = _endpoint_group_from_path(path)
    api_version = _api_version_from_path(path)
    status = _status_bucket(status_code)
    attributes = {
        "endpoint_group": endpoint_group,
        "api_version": api_version,
        "status": status,
        "method": str(method or "GET").upper(),
        "operation": str(operation or "unknown"),
    }

    _REQUEST_COUNTER.add(1, attributes=attributes)
    _LATENCY_HISTOGRAM.record(float(duration_ms), attributes=attributes)


def increment_auth_failure(*, method: str, path: str, reason: str) -> None:
    _AUTH_FAILURE_COUNTER.add(
        1,
        attributes={
            "endpoint_group": _endpoint_group_from_path(path),
            "method": str(method or "GET").upper(),
            "reason": str(reason or "unknown"),
        },
    )


def increment_contract_policy_cache_event(*, provider: str, cache_status: str) -> None:
    normalized_status = str(cache_status or "unknown").strip().lower()
    if normalized_status not in {"hit", "miss"}:
        normalized_status = "unknown"

    _CONTRACT_POLICY_CACHE_EVENT_COUNTER.add(
        1,
        attributes={
            "provider": str(provider or "unknown").strip().lower() or "unknown",
            "cache_status": normalized_status,
        },
    )


def record_async_queue_event(*, service: str, queue_type: str, stage: str, result: str) -> None:
    normalized_service = str(service or "unknown").strip().lower() or "unknown"
    normalized_queue_type = str(queue_type or "unknown").strip().lower() or "unknown"
    normalized_stage = str(stage or "unknown").strip().lower() or "unknown"
    normalized_result = str(result or "unknown").strip().lower() or "unknown"
    _QUEUE_EVENT_COUNTER.add(
        1,
        attributes={
            "service": normalized_service,
            "queue_type": normalized_queue_type,
            "stage": normalized_stage,
            "result": normalized_result,
        },
    )


def increment_suggestions_preview_event(*, action: str, result: str, error_code: str | None = None) -> None:
    normalized_action = str(action or "unknown").strip().lower() or "unknown"
    normalized_result = str(result or "unknown").strip().lower() or "unknown"
    normalized_error_code = str(error_code or "none").strip().lower() or "none"
    _SUGGESTIONS_PREVIEW_EVENT_COUNTER.add(
        1,
        attributes={
            "action": normalized_action,
            "result": normalized_result,
            "error_code": normalized_error_code,
        },
    )


def record_natural_language_draft_request_event(*, stage: str, result: str, analysis_provider: str, error_code: str | None = None) -> None:
    normalized_stage = str(stage or "unknown").strip().lower() or "unknown"
    normalized_result = str(result or "unknown").strip().lower() or "unknown"
    normalized_provider = str(analysis_provider or "unknown").strip().lower() or "unknown"
    normalized_error_code = str(error_code or "none").strip().lower() or "none"
    _NATURAL_LANGUAGE_DRAFT_REQUEST_EVENT_COUNTER.add(
        1,
        attributes={
            "stage": normalized_stage,
            "result": normalized_result,
            "analysis_provider": normalized_provider,
            "error_code": normalized_error_code,
        },
    )
    record_async_queue_event(
        service="dq-api",
        queue_type="natural_language_draft",
        stage=normalized_stage,
        result=normalized_result,
    )


def record_suggestions_redis_request(*, operation_type: str, status: str) -> None:
    normalized_operation_type = str(operation_type or "unknown").strip().lower() or "unknown"
    normalized_status = str(status or "unknown").strip().lower() or "unknown"
    _SUGGESTIONS_REDIS_REQUEST_COUNTER.add(
        1,
        attributes={
            "operation_type": normalized_operation_type,
            "status": normalized_status,
        },
    )


def record_suggestions_redis_failure(*, operation_type: str, failure_type: str) -> None:
    normalized_operation_type = str(operation_type or "unknown").strip().lower() or "unknown"
    normalized_failure_type = str(failure_type or "unknown").strip().lower() or "unknown"
    _SUGGESTIONS_REDIS_FAILURE_COUNTER.add(
        1,
        attributes={
            "operation_type": normalized_operation_type,
            "failure_type": normalized_failure_type,
        },
    )


def record_gx_operation_metric(
    *,
    surface: str,
    operation: str,
    result: str,
    status_code: int,
    duration_ms: float,
    engine_target: str | None = None,
    execution_shape: str | None = None,
) -> None:
    attributes = {
        "surface": str(surface or "unknown").strip().lower() or "unknown",
        "operation": str(operation or "unknown").strip().lower() or "unknown",
        "result": str(result or "unknown").strip().lower() or "unknown",
        "status_code": int(status_code),
    }
    if engine_target:
        attributes["engine_target"] = str(engine_target).strip().lower() or "unknown"
    if execution_shape:
        attributes["execution_shape"] = str(execution_shape).strip().lower() or "unknown"

    _GX_OPERATION_COUNTER.add(1, attributes=attributes)
    _GX_OPERATION_LATENCY_HISTOGRAM.record(float(duration_ms), attributes=attributes)

    compile_operation = _canonical_compile_operation(operation)
    if compile_operation is not None:
        _EXECUTION_COMPILE_EVENT_COUNTER.add(
            1,
            attributes={
                "engine_type": "gx",
                "operation": compile_operation,
                "result": attributes["result"],
            },
        )

    dispatch_operation = _canonical_dispatch_operation(operation)
    if dispatch_operation is not None:
        dispatch_attributes = {
            "executor": "gx",
            "engine_type": "gx",
            "operation": dispatch_operation,
            "result": attributes["result"],
        }
        if execution_shape:
            dispatch_attributes["execution_shape"] = str(execution_shape).strip().lower() or "unknown"
        _EXECUTION_DISPATCH_EVENT_COUNTER.add(1, attributes=dispatch_attributes)


def increment_gx_failure(*, surface: str, operation: str, reason: str) -> None:
    normalized_surface = str(surface or "unknown").strip().lower() or "unknown"
    normalized_operation = str(operation or "unknown").strip().lower() or "unknown"
    normalized_reason = str(reason or "unknown").strip().lower() or "unknown"

    _GX_FAILURE_COUNTER.add(
        1,
        attributes={
            "surface": normalized_surface,
            "operation": normalized_operation,
            "reason": normalized_reason,
        },
    )

    if _is_execution_failure_surface(normalized_surface):
        _EXECUTION_FAILURE_COUNTER.add(
            1,
            attributes={
                "executor": "gx",
                "engine_type": "gx",
                "failure_kind": normalized_reason,
            },
        )


def record_execution_planner_choice(
    *,
    planner: str,
    choice: str,
    execution_path: str,
    batch_count: int,
    suite_count: int,
    engine_target: str | None = None,
    execution_shape: str | None = None,
) -> None:
    attributes = {
        "planner": str(planner or "unknown").strip().lower() or "unknown",
        "choice": str(choice or "unknown").strip().lower() or "unknown",
        "execution_path": str(execution_path or "unknown").strip().lower() or "unknown",
        "batch_count": int(batch_count),
        "suite_count": int(suite_count),
    }
    if engine_target:
        attributes["engine_target"] = str(engine_target).strip().lower() or "unknown"
    if execution_shape:
        attributes["execution_shape"] = str(execution_shape).strip().lower() or "unknown"

    _EXECUTION_PLANNER_CHOICE_COUNTER.add(1, attributes=attributes)


def record_execution_runtime_cost(
    *,
    executor: str,
    execution_path: str,
    planner_choice: str,
    runtime_ms: float,
    batch_count: int,
    suite_count: int,
    engine_target: str | None = None,
    execution_shape: str | None = None,
) -> None:
    attributes = {
        "executor": str(executor or "unknown").strip().lower() or "unknown",
        "execution_path": str(execution_path or "unknown").strip().lower() or "unknown",
        "planner_choice": str(planner_choice or "unknown").strip().lower() or "unknown",
        "batch_count": int(batch_count),
        "suite_count": int(suite_count),
    }
    if engine_target:
        attributes["engine_target"] = str(engine_target).strip().lower() or "unknown"
    if execution_shape:
        attributes["execution_shape"] = str(execution_shape).strip().lower() or "unknown"

    _EXECUTION_RUNTIME_COST_HISTOGRAM.record(float(runtime_ms), attributes=attributes)


def record_execution_data_scanned(
    *,
    executor: str,
    execution_path: str,
    planner_choice: str,
    batch_count: int,
    suite_count: int,
    data_scanned_rows: int | None = None,
    data_scanned_bytes: int | None = None,
    engine_target: str | None = None,
    execution_shape: str | None = None,
) -> None:
    attributes = {
        "executor": str(executor or "unknown").strip().lower() or "unknown",
        "execution_path": str(execution_path or "unknown").strip().lower() or "unknown",
        "planner_choice": str(planner_choice or "unknown").strip().lower() or "unknown",
        "batch_count": int(batch_count),
        "suite_count": int(suite_count),
    }
    if engine_target:
        attributes["engine_target"] = str(engine_target).strip().lower() or "unknown"
    if execution_shape:
        attributes["execution_shape"] = str(execution_shape).strip().lower() or "unknown"

    if data_scanned_rows is not None:
        _EXECUTION_DATA_SCANNED_ROWS_HISTOGRAM.record(float(data_scanned_rows), attributes=attributes)
    if data_scanned_bytes is not None:
        _EXECUTION_DATA_SCANNED_BYTES_HISTOGRAM.record(float(data_scanned_bytes), attributes=attributes)
