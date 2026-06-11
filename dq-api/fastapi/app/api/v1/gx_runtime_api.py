from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import partial
import os
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from opentelemetry import propagate

from app.application.services import gx_queue_service
from app.core.runtime_queues import resolve_gx_execution_queue_key as _resolve_runtime_execution_queue_key
from app.core.runtime_queues import resolve_gx_join_pair_materialization_queue_key as _resolve_runtime_join_pair_queue_key
from app.application.services.data_delivery_resolver import DataDeliveryResolutionError
from app.application.services.data_delivery_resolver import DataDeliveryResolver
from app.application.services.gx_suite_validation import assert_gx_suite_runnable as assert_gx_suite_runnable_service
from app.application.services.gx_suite_validation import GxSuiteValidationError
from app.application.use_cases.gx_dispatch import CreateGroupedScopeGxRunCommand
from app.application.use_cases.gx_dispatch import create_grouped_scope_gx_run as create_grouped_scope_gx_run_use_case
from app.application.use_cases.gx_dispatch_runtime import persist_grouped_dispatch_run as persist_grouped_dispatch_run_use_case
from app.application.use_cases.gx_dispatch_runtime import EnqueueScheduledGxSuiteRunCommand
from app.application.use_cases.gx_dispatch_runtime import enqueue_scheduled_gx_suite_run as enqueue_scheduled_gx_suite_run_use_case
from app.core.otel_metrics import record_async_queue_event
from app.domain.entities.gx_execution_run import build_gx_execution_contract_entity
from app.domain.entities.gx_execution_run import build_gx_execution_delivery_snapshot_entity
from app.domain.entities.gx_execution_run import build_gx_grouped_execution_plan_entity
from app.domain.entities.gx_execution_run import GxDispatchPayloadEntity
from app.domain.entities.gx_execution_run import build_gx_dispatch_payload_entity
from app.domain.entities.gx_run_plan import build_gx_run_plan_scope_selector_entity
from app.domain.entities.gx_run_plan import build_gx_run_plan_suite_ref_entities
from app.domain.interfaces import GxExecutionRunRepository
from app.domain.interfaces import DataCatalogRepository
from app.schemas.pydantic_base import to_snake_alias


ResolveRedisUrl = Callable[[], str | None]
AssertQueueWorker = Callable[[str, str], Awaitable[None]]
BuildDispatchPayload = Callable[..., Any]
InjectTraceCarrier = Callable[[dict[str, Any]], None]
EnqueueDispatchPayload = Callable[[str, GxDispatchPayloadEntity], Awaitable[None]]
EnqueueGroupedDispatchPayload = Callable[[str, str, GxDispatchPayloadEntity], Awaitable[None]]
MapPersistenceError = Callable[[str, str, str, Exception], HTTPException]
PersistGroupedDispatchRunUseCase = Callable[..., Awaitable[None]]
FetchQueueStatus = Callable[[str, str, int], Awaitable[tuple[int, list[str]]]]
SettingsProvider = Callable[[], Any]
HeartbeatKeyBuilder = Callable[[str], str]


def _parse_worker_heartbeat_ttl(raw_value: str | None, *, default: int = 30) -> int:
    try:
        parsed = int(raw_value or default)
    except Exception:
        parsed = default
    return max(parsed, 5)


def resolve_execution_queue_key() -> str:
    queue_key = _resolve_runtime_execution_queue_key()
    if queue_key:
        return queue_key
    raise HTTPException(
        status_code=503,
        detail={
            "error": "gx_execution_queue_not_configured",
            "message": "GX execution queue is not configured",
            "env_vars": ["GX_EXECUTION_QUEUE_KEY", "DQ_GX_EXECUTION_QUEUE_KEY"],
        },
    )


def resolve_execution_worker_heartbeat_key(queue_key: str | None = None) -> str:
    normalized_queue_key = str(queue_key or resolve_execution_queue_key()).strip() or resolve_execution_queue_key()
    return f"{normalized_queue_key}:worker-heartbeat"


def resolve_execution_worker_heartbeat_ttl_seconds() -> int:
    return _parse_worker_heartbeat_ttl(
        os.environ.get("GX_EXECUTION_WORKER_HEARTBEAT_TTL_SECONDS")
        or os.environ.get("DQ_GX_EXECUTION_WORKER_HEARTBEAT_TTL_SECONDS")
        or "30"
    )


def resolve_join_pair_materialization_queue_key() -> str:
    queue_key = _resolve_runtime_join_pair_queue_key()
    if queue_key:
        return queue_key
    raise HTTPException(
        status_code=503,
        detail={
            "error": "gx_join_pair_materialization_queue_not_configured",
            "message": "GX join-pair materialization queue is not configured",
            "env_vars": [
                "GX_JOIN_PAIR_MATERIALIZATION_QUEUE_KEY",
                "DQ_GX_JOIN_PAIR_MATERIALIZATION_QUEUE_KEY",
            ],
        },
    )


def resolve_join_pair_materialization_worker_heartbeat_key(queue_key: str | None = None) -> str:
    normalized_queue_key = str(
        queue_key or resolve_join_pair_materialization_queue_key()
    ).strip() or resolve_join_pair_materialization_queue_key()
    return f"{normalized_queue_key}:worker-heartbeat"


def resolve_join_pair_materialization_worker_heartbeat_ttl_seconds() -> int:
    return _parse_worker_heartbeat_ttl(
        os.environ.get("GX_JOIN_PAIR_MATERIALIZATION_WORKER_HEARTBEAT_TTL_SECONDS")
        or os.environ.get("DQ_GX_JOIN_PAIR_MATERIALIZATION_WORKER_HEARTBEAT_TTL_SECONDS")
        or "30"
    )


def map_execution_run_persistence_error(
    *,
    suite_id: str,
    run_id: str,
    correlation_id: str,
    exc: Exception,
) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={
            "error": "execution_run_persistence_failed",
            "message": "Unable to persist GX execution run",
            "suite_id": suite_id,
            "run_id": run_id,
            "correlation_id": correlation_id,
            "exception": exc.__class__.__name__,
        },
    )


def _snakecase_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {to_snake_alias(str(key)): _snakecase_payload(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_snakecase_payload(item) for item in value]
    return value


def _reject_non_runnable_suite(
    *,
    suite_id: str,
    suite_version: int | None,
    message: str,
    reason: str,
) -> HTTPException:
    return HTTPException(
        status_code=422,
        detail={
            "error": "gx_suite_not_runnable",
            "message": message,
            "reason": reason,
            "suite_id": suite_id,
            "suite_version": suite_version,
        },
    )


def _assert_suite_runnable(suite: Any) -> None:
    try:
        assert_gx_suite_runnable_service(suite)
    except GxSuiteValidationError as exc:
        raise _reject_non_runnable_suite(
            suite_id=exc.suite_id,
            suite_version=exc.suite_version,
            message=exc.message,
            reason=exc.reason,
        ) from exc


def _resolve_primary_data_object_version_id(suite: Any) -> str | None:
    raw_execution_contract = getattr(suite, "executionContract", None)
    execution_contract = build_gx_execution_contract_entity(
        raw_execution_contract.model_dump() if raw_execution_contract is not None else None
    )
    if execution_contract is not None:
        traceability = execution_contract.traceability
        primary_version_id = str(traceability.dataObjectVersionId or "").strip() if traceability is not None else ""
        if primary_version_id:
            return primary_version_id

    resolved_scope = getattr(suite, "resolvedExecutionScope", None)
    if resolved_scope is None:
        return None

    target_ids = [str(value or "").strip() for value in getattr(resolved_scope, "dataObjectVersionIds", []) if str(value or "").strip()]
    if len(target_ids) == 1:
        return target_ids[0]
    return None


def _resolve_execution_delivery_snapshot(*, suite: Any, data_catalog_repository: DataCatalogRepository):
    data_object_version_id = _resolve_primary_data_object_version_id(suite)
    if not data_object_version_id:
        return None

    resolver = DataDeliveryResolver(catalog_repository=data_catalog_repository)
    try:
        return build_gx_execution_delivery_snapshot_entity(
            resolver.resolve_delivery(data_object_version_id=data_object_version_id)
        )
    except DataDeliveryResolutionError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={
                "error": exc.reason,
                "message": str(exc),
                "data_object_version_id": data_object_version_id,
            },
        ) from exc


def _merge_execution_contract_delivery_snapshot(
    execution_contract_payload: dict[str, Any],
    delivery_snapshot_payload: Any,
) -> dict[str, Any]:
    merged_payload = dict(execution_contract_payload)
    delivery_snapshot = build_gx_execution_delivery_snapshot_entity(delivery_snapshot_payload)
    if delivery_snapshot is not None:
        merged_payload.update(delivery_snapshot.model_dump(by_alias=True, exclude_none=True))
    return merged_payload


def _require_payload_engine_type(
    payload: dict[str, Any],
    *,
    context: str,
    correlation_id: str,
    field_name: str = "engine_type",
) -> str:
    engine_type = str(payload.get(field_name) or "").strip().lower() if isinstance(payload, dict) else ""
    if not engine_type:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "missing_engine_type",
                "message": f"{context} requires explicit {field_name}",
                "correlation_id": correlation_id,
            },
        )
    return engine_type


def build_execution_dispatch_payload(
    *,
    suite: Any,
    correlation_id: str,
    requested_by: str | None,
    scheduled_at: datetime,
    run_plan_id: str | None = None,
    run_plan_version_id: str | None = None,
    execution_scope_override: list[str] | None = None,
    source_overrides_by_data_object_version_id: dict[str, dict[str, Any]] | None = None,
    delivery_snapshot: dict[str, Any] | None = None,
    queue_key: str,
    data_catalog_repository: DataCatalogRepository,
) -> dict[str, Any]:
    _assert_suite_runnable(suite)
    execution_contract = getattr(suite, "executionContract", None)
    if execution_contract is None:
        raise _reject_non_runnable_suite(
            suite_id=str(getattr(suite, "suiteId", "") or ""),
            suite_version=getattr(suite, "suiteVersion", None),
            message=f"GX suite '{getattr(suite, 'suiteId', '')}' is missing an execution_contract",
            reason="missing_execution_contract",
        )

    if delivery_snapshot is not None:
        resolved_delivery_snapshot = build_gx_execution_delivery_snapshot_entity(delivery_snapshot)
    else:
        resolved_delivery_snapshot = _resolve_execution_delivery_snapshot(
            suite=suite,
            data_catalog_repository=data_catalog_repository,
        )
    execution_contract_payload = _merge_execution_contract_delivery_snapshot(
        _snakecase_payload(execution_contract.model_dump()),
        resolved_delivery_snapshot,
    )
    dispatch_engine_type = _require_payload_engine_type(
        execution_contract_payload,
        context="GX suite dispatch",
        correlation_id=correlation_id,
    )
    if resolved_delivery_snapshot is not None and str(resolved_delivery_snapshot.engineType or "").strip().lower() not in {"", dispatch_engine_type}:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "engine_type_mismatch",
                "message": "GX suite dispatch requires matching engine_type across execution_contract and delivery_snapshot",
                "engine_type": dispatch_engine_type,
                "delivery_snapshot_engine_type": str(resolved_delivery_snapshot.engineType or "").strip().lower(),
                "correlation_id": correlation_id,
            },
        )

    run_id = f"run-{uuid4().hex[:12]}"
    payload: dict[str, Any] = {
        "run_id": run_id,
        "queue_message_id": run_id,
        "suite_id": getattr(suite, "suiteId", None),
        "suite_version": getattr(suite, "suiteVersion", None),
        "correlation_id": correlation_id,
        "requested_by": requested_by,
        "engine_target": execution_contract.engineTarget,
        "execution_shape": execution_contract.executionShape,
        "dispatch_mode": "queued",
        "executor_target": "dq-engine",
        "queue_key": queue_key,
        "handoff_status": "accepted",
        "handoff_ready": True,
        "submitted_at": datetime.now(UTC).isoformat(),
        "scheduled_at": scheduled_at.isoformat(),
        "execution_contract": execution_contract_payload,
        "engine_type": dispatch_engine_type,
    }
    normalized_run_plan_id = str(run_plan_id or "").strip()
    if normalized_run_plan_id:
        payload["run_plan_id"] = normalized_run_plan_id
    normalized_run_plan_version_id = str(run_plan_version_id or "").strip()
    if normalized_run_plan_version_id:
        payload["run_plan_version_id"] = normalized_run_plan_version_id
    normalized_scope = [str(v).strip() for v in (execution_scope_override or []) if str(v).strip()]
    if normalized_scope:
        payload["execution_scope_override"] = normalized_scope
    if source_overrides_by_data_object_version_id:
        payload["source_overrides_by_data_object_version_id"] = source_overrides_by_data_object_version_id

    dispatch_entity = build_gx_dispatch_payload_entity(payload)
    return dispatch_entity.model_dump(by_alias=True, exclude_none=True) if dispatch_entity is not None else payload


def build_grouped_execution_dispatch_payload(
    *,
    grouped_execution_plan: dict[str, Any],
    scope_selector: dict[str, Any],
    suite_refs: list[dict[str, Any]],
    correlation_id: str,
    requested_by: str | None,
    scheduled_at: datetime,
    run_plan_id: str | None = None,
    run_plan_version_id: str | None = None,
    source_overrides_by_data_object_version_id: dict[str, dict[str, Any]] | None = None,
    delivery_snapshot: dict[str, Any] | None = None,
    queue_key: str,
) -> dict[str, Any]:
    normalized_suite_refs = _snakecase_payload([dict(item) for item in suite_refs or []])
    dispatch_engine_type = None
    if isinstance(delivery_snapshot, dict):
        dispatch_engine_type = str(delivery_snapshot.get("engine_type") or delivery_snapshot.get("engineType") or "").strip() or None
    suite_engine_types = {
        str(item.get("engine_type") or item.get("engineType") or "").strip().lower()
        for item in normalized_suite_refs
        if isinstance(item, dict) and str(item.get("engine_type") or item.get("engineType") or "").strip()
    }
    if dispatch_engine_type is None:
        if not suite_engine_types:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "missing_engine_type",
                    "message": "GX grouped dispatch requires explicit engine_type on suite_refs or delivery_snapshot",
                    "correlation_id": correlation_id,
                },
            )
        if len(suite_engine_types) > 1:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "mixed_engine_types",
                    "message": "GX grouped dispatch requires a single engine_type",
                    "engine_types": sorted(suite_engine_types),
                    "correlation_id": correlation_id,
                },
            )
        dispatch_engine_type = next(iter(suite_engine_types))
    elif suite_engine_types and any(engine_type != dispatch_engine_type.lower() for engine_type in suite_engine_types):
        raise HTTPException(
            status_code=422,
            detail={
                "error": "engine_type_mismatch",
                "message": "GX grouped dispatch requires matching engine_type across suite_refs and delivery_snapshot",
                "engine_type": dispatch_engine_type.lower(),
                "suite_ref_engine_types": sorted(suite_engine_types),
                "correlation_id": correlation_id,
            },
        )

    run_id = f"run-{uuid4().hex[:12]}"
    payload: dict[str, Any] = {
        "run_id": run_id,
        "queue_message_id": run_id,
        "correlation_id": correlation_id,
        "requested_by": requested_by,
        "engine_type": dispatch_engine_type,
        "engine_target": "pyspark",
        "execution_shape": "grouped_scope",
        "dispatch_mode": "queued",
        "executor_target": "dq-engine",
        "queue_key": queue_key,
        "handoff_status": "accepted",
        "handoff_ready": True,
        "submitted_at": datetime.now(UTC).isoformat(),
        "scheduled_at": scheduled_at.isoformat(),
        "selection_mode": "grouped_scope",
        "scope_selector": _snakecase_payload(dict(scope_selector or {})),
        "suite_refs": normalized_suite_refs,
        "grouped_execution_plan": _snakecase_payload(dict(grouped_execution_plan or {})),
    }
    normalized_run_plan_id = str(run_plan_id or "").strip()
    if normalized_run_plan_id:
        payload["run_plan_id"] = normalized_run_plan_id
    normalized_run_plan_version_id = str(run_plan_version_id or "").strip()
    if normalized_run_plan_version_id:
        payload["run_plan_version_id"] = normalized_run_plan_version_id
    if source_overrides_by_data_object_version_id:
        payload["source_overrides_by_data_object_version_id"] = source_overrides_by_data_object_version_id
    if delivery_snapshot is not None:
        payload["delivery_snapshot"] = delivery_snapshot
    dispatch_entity = build_gx_dispatch_payload_entity(payload)
    return dispatch_entity.model_dump(by_alias=True, exclude_none=True) if dispatch_entity is not None else payload


def build_grouped_scope_command(
    *,
    grouped_execution_plan: dict[str, Any],
    scope_selector: dict[str, Any],
    suite_refs: list[dict[str, Any]],
    scheduled_at: datetime,
    requested_by: str | None,
    correlation_id: str,
    run_plan_id: str | None,
    run_plan_version_id: str | None,
    source_overrides_by_data_object_version_id: dict[str, dict[str, Any]] | None,
    delivery_snapshot: dict[str, Any] | None,
    queue_key: str,
) -> CreateGroupedScopeGxRunCommand:
    return CreateGroupedScopeGxRunCommand(
        grouped_execution_plan=build_gx_grouped_execution_plan_entity(grouped_execution_plan),
        scope_selector=build_gx_run_plan_scope_selector_entity(scope_selector),
        suite_refs=build_gx_run_plan_suite_ref_entities(suite_refs),
        scheduled_at=scheduled_at,
        requested_by=requested_by,
        correlation_id=correlation_id,
        run_plan_id=run_plan_id,
        run_plan_version_id=run_plan_version_id,
        source_overrides_by_data_object_version_id=source_overrides_by_data_object_version_id,
        delivery_snapshot=build_gx_execution_delivery_snapshot_entity(delivery_snapshot),
        queue_key=queue_key,
    )


def bind_scheduled_suite_run_enqueue(
    *,
    data_catalog_repository: DataCatalogRepository,
    settings_provider: SettingsProvider,
    async_redis_module,
    sync_redis_module,
    logger,
) -> Callable[..., Awaitable[GxDispatchPayloadEntity]]:
    return partial(
        enqueue_scheduled_suite_run,
        queue_key=resolve_execution_queue_key(),
        join_pair_materialization_queue_key=resolve_join_pair_materialization_queue_key(),
        data_catalog_repository=data_catalog_repository,
        settings_provider=settings_provider,
        dispatch_worker_heartbeat_key_builder=resolve_execution_worker_heartbeat_key,
        dispatch_worker_heartbeat_ttl_seconds=resolve_execution_worker_heartbeat_ttl_seconds(),
        join_pair_materialization_worker_heartbeat_key_builder=resolve_join_pair_materialization_worker_heartbeat_key,
        join_pair_materialization_worker_heartbeat_ttl_seconds=resolve_join_pair_materialization_worker_heartbeat_ttl_seconds(),
        inject_trace_carrier=propagate.inject,
        map_persistence_error=map_execution_run_persistence_error,
        async_redis_module=async_redis_module,
        sync_redis_module=sync_redis_module,
        logger=logger,
    )


def bind_grouped_scope_run_enqueue(
    *,
    settings_provider: SettingsProvider,
    async_redis_module,
    sync_redis_module,
    logger,
) -> Callable[..., Awaitable[GxDispatchPayloadEntity]]:
    return partial(
        enqueue_grouped_scope_run,
        queue_key=resolve_execution_queue_key(),
        settings_provider=settings_provider,
        dispatch_worker_heartbeat_key_builder=resolve_execution_worker_heartbeat_key,
        dispatch_worker_heartbeat_ttl_seconds=resolve_execution_worker_heartbeat_ttl_seconds(),
        build_grouped_scope_command=build_grouped_scope_command,
        inject_trace_carrier=propagate.inject,
        persist_grouped_dispatch_run_use_case=persist_grouped_dispatch_run_use_case,
        async_redis_module=async_redis_module,
        sync_redis_module=sync_redis_module,
        logger=logger,
    )


def _build_grouped_dispatch_payload_with_tracing(
    *,
    grouped_execution_plan: dict[str, Any],
    scope_selector: dict[str, Any],
    suite_refs: list[dict[str, Any]],
    correlation_id: str,
    requested_by: str | None,
    scheduled_at: datetime,
    run_plan_id: str | None,
    run_plan_version_id: str | None,
    source_overrides_by_data_object_version_id: dict[str, dict[str, Any]] | None,
    delivery_snapshot: dict[str, Any] | None,
    queue_key: str,
    inject_trace_carrier: InjectTraceCarrier,
) -> GxDispatchPayloadEntity:
    dispatch_payload = build_grouped_execution_dispatch_payload(
        grouped_execution_plan=grouped_execution_plan,
        scope_selector=scope_selector,
        suite_refs=suite_refs,
        correlation_id=correlation_id,
        requested_by=requested_by,
        scheduled_at=scheduled_at,
        run_plan_id=run_plan_id,
        run_plan_version_id=run_plan_version_id,
        source_overrides_by_data_object_version_id=source_overrides_by_data_object_version_id,
        delivery_snapshot=delivery_snapshot,
        queue_key=queue_key,
    )
    dispatch_entity = build_gx_dispatch_payload_entity(dispatch_payload)
    if dispatch_entity is None:
        raise HTTPException(status_code=500, detail="Failed to normalize grouped GX dispatch payload")
    carrier = dict(dispatch_entity.headers or {})
    inject_trace_carrier(carrier)
    return dispatch_entity.model_copy(update={"headers": carrier})


@dataclass(slots=True)
class ScheduledSuiteRunUseCaseArgs:
    command: EnqueueScheduledGxSuiteRunCommand
    resolve_redis_url: ResolveRedisUrl
    assert_dispatch_worker: AssertQueueWorker
    assert_join_pair_materialization_worker: AssertQueueWorker
    build_dispatch_payload: BuildDispatchPayload
    inject_trace_carrier: InjectTraceCarrier
    enqueue_payload: EnqueueDispatchPayload
    map_persistence_error: MapPersistenceError


@dataclass(slots=True)
class GroupedScopeRunUseCaseArgs:
    command: CreateGroupedScopeGxRunCommand
    resolve_redis_url: ResolveRedisUrl
    assert_dispatch_worker: AssertQueueWorker
    build_dispatch_payload: BuildDispatchPayload
    persist_run: Callable[[GxDispatchPayloadEntity], Awaitable[None]]
    enqueue_payload: EnqueueGroupedDispatchPayload


@dataclass(slots=True)
class QueueStatusUseCaseArgs:
    resolve_redis_url: ResolveRedisUrl
    fetch_queue_status: FetchQueueStatus


def request_correlation_id(request: Any, explicit_correlation_id: str | None = None) -> str:
    if explicit_correlation_id is not None:
        normalized = str(explicit_correlation_id).strip()
        if normalized:
            return normalized

    headers = getattr(request, "headers", None)
    if headers is not None:
        header_value = str(headers.get("X-Correlation-ID") or "").strip()
        if header_value:
            return header_value

    return f"corr-{uuid4().hex[:12]}"


def _bind_resolve_redis_url(*, settings_provider: SettingsProvider) -> ResolveRedisUrl:
    def _resolve() -> str | None:
        return gx_queue_service.resolve_redis_url(settings_provider())

    return _resolve


def _bind_worker_heartbeat_assertion(
    *,
    heartbeat_key_builder: HeartbeatKeyBuilder,
    expected_ttl_seconds: int,
    unavailable_error: str,
    unavailable_message: str,
    status_failed_error: str,
    status_failed_message: str,
    async_redis_module,
    sync_redis_module,
    logger,
) -> AssertQueueWorker:
    async def _assert(redis_url: str, queue_key: str) -> None:
        await gx_queue_service.assert_worker_heartbeat(
            redis_url,
            queue_key=queue_key,
            heartbeat_key=heartbeat_key_builder(queue_key),
            expected_ttl_seconds=expected_ttl_seconds,
            unavailable_error=unavailable_error,
            unavailable_message=unavailable_message,
            status_failed_error=status_failed_error,
            status_failed_message=status_failed_message,
            async_redis_module=async_redis_module,
            sync_redis_module=sync_redis_module,
            logger=logger,
        )

    return _assert


def _bind_dispatch_payload_enqueuer(*, async_redis_module, sync_redis_module, logger) -> EnqueueDispatchPayload:
    async def _enqueue(redis_url: str, payload: GxDispatchPayloadEntity) -> None:
        try:
            await gx_queue_service.redis_lpush(
                redis_url,
                str(payload.queueKey or ""),
                payload.model_dump(by_alias=True, exclude_none=True),
                async_redis_module=async_redis_module,
                sync_redis_module=sync_redis_module,
                logger=logger,
            )
        except Exception:
            record_async_queue_event(service="dq-api", queue_type="gx_execution", stage="enqueue", result="failure")
            raise
        record_async_queue_event(service="dq-api", queue_type="gx_execution", stage="enqueue", result="success")

    return _enqueue


def _bind_grouped_dispatch_payload_enqueuer(*, async_redis_module, sync_redis_module, logger) -> EnqueueGroupedDispatchPayload:
    async def _enqueue(redis_url: str, queue_key: str, payload: GxDispatchPayloadEntity) -> None:
        try:
            await gx_queue_service.redis_lpush(
                redis_url,
                queue_key,
                payload.model_dump(by_alias=True, exclude_none=True),
                async_redis_module=async_redis_module,
                sync_redis_module=sync_redis_module,
                logger=logger,
            )
        except Exception:
            record_async_queue_event(
                service="dq-api",
                queue_type="gx_join_pair_materialization",
                stage="enqueue",
                result="failure",
            )
            raise
        record_async_queue_event(
            service="dq-api",
            queue_type="gx_join_pair_materialization",
            stage="enqueue",
            result="success",
        )

    return _enqueue


def _bind_queue_status_fetcher(*, async_redis_module, sync_redis_module, logger) -> FetchQueueStatus:
    async def _fetch(redis_url: str, queue_key: str, scan_limit: int) -> tuple[int, list[str]]:
        return await gx_queue_service.redis_queue_status(
            redis_url,
            queue_key,
            scan_limit,
            async_redis_module=async_redis_module,
            sync_redis_module=sync_redis_module,
            logger=logger,
        )

    return _fetch


def _bind_grouped_dispatch_persistence(
    *,
    persist_grouped_dispatch_run_use_case: PersistGroupedDispatchRunUseCase,
    execution_run_repository: GxExecutionRunRepository,
    requested_by: str | None,
    status_source: str,
    status_reason: str,
) -> Callable[[GxDispatchPayloadEntity], Awaitable[None]]:
    async def _persist(dispatch_payload: GxDispatchPayloadEntity) -> None:
        await persist_grouped_dispatch_run_use_case(
            dispatch_payload=dispatch_payload,
            execution_run_repository=execution_run_repository,
            requested_by=requested_by,
            status_source=status_source,
            status_reason=status_reason,
        )

    return _persist


def build_scheduled_suite_run_args(
    *,
    request: Any,
    suite: Any,
    scheduled_at,
    requested_by: str | None,
    status_source: str,
    status_reason: str,
    run_plan_id: str | None,
    run_plan_version_id: str | None,
    execution_scope_override: list[str] | None,
    source_overrides_by_data_object_version_id: dict[str, dict[str, Any]] | None,
    delivery_snapshot: dict[str, Any] | None,
    correlation_id: str | None,
    queue_key: str,
    join_pair_materialization_queue_key: str,
    settings_provider: SettingsProvider,
    dispatch_worker_heartbeat_key_builder: HeartbeatKeyBuilder,
    dispatch_worker_heartbeat_ttl_seconds: int,
    join_pair_materialization_worker_heartbeat_key_builder: HeartbeatKeyBuilder,
    join_pair_materialization_worker_heartbeat_ttl_seconds: int,
    build_dispatch_payload: BuildDispatchPayload,
    inject_trace_carrier: InjectTraceCarrier,
    map_persistence_error: MapPersistenceError,
    async_redis_module,
    sync_redis_module,
    logger,
) -> ScheduledSuiteRunUseCaseArgs:
    return ScheduledSuiteRunUseCaseArgs(
        command=EnqueueScheduledGxSuiteRunCommand(
            suite=suite,
            scheduled_at=scheduled_at,
            requested_by=requested_by,
            status_source=status_source,
            status_reason=status_reason,
            run_plan_id=run_plan_id,
            run_plan_version_id=run_plan_version_id,
            execution_scope_override=execution_scope_override,
            source_overrides_by_data_object_version_id=source_overrides_by_data_object_version_id,
            delivery_snapshot=delivery_snapshot,
            correlation_id=request_correlation_id(request, correlation_id),
            queue_key=queue_key,
            join_pair_materialization_queue_key=join_pair_materialization_queue_key,
        ),
        resolve_redis_url=_bind_resolve_redis_url(settings_provider=settings_provider),
        assert_dispatch_worker=_bind_worker_heartbeat_assertion(
            heartbeat_key_builder=dispatch_worker_heartbeat_key_builder,
            expected_ttl_seconds=dispatch_worker_heartbeat_ttl_seconds,
            unavailable_error="dispatch_worker_unavailable",
            unavailable_message="No active GX dispatch worker heartbeat found",
            status_failed_error="dispatch_worker_status_failed",
            status_failed_message="Unable to determine GX dispatch worker availability",
            async_redis_module=async_redis_module,
            sync_redis_module=sync_redis_module,
            logger=logger,
        ),
        assert_join_pair_materialization_worker=_bind_worker_heartbeat_assertion(
            heartbeat_key_builder=join_pair_materialization_worker_heartbeat_key_builder,
            expected_ttl_seconds=join_pair_materialization_worker_heartbeat_ttl_seconds,
            unavailable_error="join_pair_materialization_worker_unavailable",
            unavailable_message="No active join-pair materialization worker heartbeat found",
            status_failed_error="join_pair_materialization_worker_status_failed",
            status_failed_message="Unable to determine join-pair materialization worker availability",
            async_redis_module=async_redis_module,
            sync_redis_module=sync_redis_module,
            logger=logger,
        ),
        build_dispatch_payload=build_dispatch_payload,
        inject_trace_carrier=inject_trace_carrier,
        enqueue_payload=_bind_dispatch_payload_enqueuer(
            async_redis_module=async_redis_module,
            sync_redis_module=sync_redis_module,
            logger=logger,
        ),
        map_persistence_error=map_persistence_error,
    )


def build_grouped_scope_run_args(
    *,
    command: CreateGroupedScopeGxRunCommand,
    requested_by: str | None,
    status_source: str,
    status_reason: str,
    execution_run_repository: GxExecutionRunRepository,
    settings_provider: SettingsProvider,
    dispatch_worker_heartbeat_key_builder: HeartbeatKeyBuilder,
    dispatch_worker_heartbeat_ttl_seconds: int,
    build_dispatch_payload: BuildDispatchPayload,
    persist_grouped_dispatch_run_use_case: PersistGroupedDispatchRunUseCase,
    async_redis_module,
    sync_redis_module,
    logger,
) -> GroupedScopeRunUseCaseArgs:
    return GroupedScopeRunUseCaseArgs(
        command=command,
        resolve_redis_url=_bind_resolve_redis_url(settings_provider=settings_provider),
        assert_dispatch_worker=_bind_worker_heartbeat_assertion(
            heartbeat_key_builder=dispatch_worker_heartbeat_key_builder,
            expected_ttl_seconds=dispatch_worker_heartbeat_ttl_seconds,
            unavailable_error="dispatch_worker_unavailable",
            unavailable_message="No active GX dispatch worker heartbeat found",
            status_failed_error="dispatch_worker_status_failed",
            status_failed_message="Unable to determine GX dispatch worker availability",
            async_redis_module=async_redis_module,
            sync_redis_module=sync_redis_module,
            logger=logger,
        ),
        build_dispatch_payload=build_dispatch_payload,
        persist_run=_bind_grouped_dispatch_persistence(
            persist_grouped_dispatch_run_use_case=persist_grouped_dispatch_run_use_case,
            execution_run_repository=execution_run_repository,
            requested_by=requested_by,
            status_source=status_source,
            status_reason=status_reason,
        ),
        enqueue_payload=_bind_grouped_dispatch_payload_enqueuer(
            async_redis_module=async_redis_module,
            sync_redis_module=sync_redis_module,
            logger=logger,
        ),
    )


def build_queue_status_args(
    *,
    settings_provider: SettingsProvider,
    async_redis_module,
    sync_redis_module,
    logger,
) -> QueueStatusUseCaseArgs:
    return QueueStatusUseCaseArgs(
        resolve_redis_url=_bind_resolve_redis_url(settings_provider=settings_provider),
        fetch_queue_status=_bind_queue_status_fetcher(
            async_redis_module=async_redis_module,
            sync_redis_module=sync_redis_module,
            logger=logger,
        ),
    )


async def enqueue_scheduled_suite_run(
    *,
    request: Any,
    suite: Any,
    scheduled_at,
    execution_run_repository: GxExecutionRunRepository,
    requested_by: str | None,
    status_source: str,
    status_reason: str,
    run_plan_id: str | None = None,
    run_plan_version_id: str | None = None,
    execution_scope_override: list[str] | None = None,
    source_overrides_by_data_object_version_id: dict[str, dict[str, Any]] | None = None,
    delivery_snapshot: dict[str, Any] | None = None,
    correlation_id: str | None = None,
    queue_key: str,
    join_pair_materialization_queue_key: str,
    data_catalog_repository: DataCatalogRepository,
    settings_provider: SettingsProvider,
    dispatch_worker_heartbeat_key_builder: HeartbeatKeyBuilder,
    dispatch_worker_heartbeat_ttl_seconds: int,
    join_pair_materialization_worker_heartbeat_key_builder: HeartbeatKeyBuilder,
    join_pair_materialization_worker_heartbeat_ttl_seconds: int,
    inject_trace_carrier: InjectTraceCarrier,
    map_persistence_error: MapPersistenceError,
    async_redis_module,
    sync_redis_module,
    logger,
) -> GxDispatchPayloadEntity:
    use_case_args = build_scheduled_suite_run_args(
        request=request,
        suite=suite,
        scheduled_at=scheduled_at,
        requested_by=requested_by,
        status_source=status_source,
        status_reason=status_reason,
        run_plan_id=run_plan_id,
        run_plan_version_id=run_plan_version_id,
        execution_scope_override=execution_scope_override,
        source_overrides_by_data_object_version_id=source_overrides_by_data_object_version_id,
        delivery_snapshot=delivery_snapshot,
        correlation_id=correlation_id,
        queue_key=queue_key,
        join_pair_materialization_queue_key=join_pair_materialization_queue_key,
        settings_provider=settings_provider,
        dispatch_worker_heartbeat_key_builder=dispatch_worker_heartbeat_key_builder,
        dispatch_worker_heartbeat_ttl_seconds=dispatch_worker_heartbeat_ttl_seconds,
        join_pair_materialization_worker_heartbeat_key_builder=join_pair_materialization_worker_heartbeat_key_builder,
        join_pair_materialization_worker_heartbeat_ttl_seconds=join_pair_materialization_worker_heartbeat_ttl_seconds,
        build_dispatch_payload=lambda **payload_kwargs: build_execution_dispatch_payload(
            **payload_kwargs,
            queue_key=queue_key,
            data_catalog_repository=data_catalog_repository,
        ),
        inject_trace_carrier=inject_trace_carrier,
        map_persistence_error=map_persistence_error,
        async_redis_module=async_redis_module,
        sync_redis_module=sync_redis_module,
        logger=logger,
    )
    return await enqueue_scheduled_gx_suite_run_use_case(
        command=use_case_args.command,
        execution_run_repository=execution_run_repository,
        resolve_redis_url=use_case_args.resolve_redis_url,
        assert_dispatch_worker=use_case_args.assert_dispatch_worker,
        assert_join_pair_materialization_worker=use_case_args.assert_join_pair_materialization_worker,
        build_dispatch_payload=use_case_args.build_dispatch_payload,
        inject_trace_carrier=use_case_args.inject_trace_carrier,
        enqueue_payload=use_case_args.enqueue_payload,
        map_persistence_error=use_case_args.map_persistence_error,
    )


async def enqueue_grouped_scope_run(
    *,
    request: Any,
    grouped_execution_plan: dict[str, Any],
    scope_selector: dict[str, Any],
    suite_refs: list[dict[str, Any]],
    scheduled_at,
    execution_run_repository: GxExecutionRunRepository,
    requested_by: str | None,
    status_source: str = "gx.run_plan.grouped.activate",
    status_reason: str = "Grouped GX run accepted",
    run_plan_id: str | None = None,
    run_plan_version_id: str | None = None,
    source_overrides_by_data_object_version_id: dict[str, dict[str, Any]] | None = None,
    delivery_snapshot: dict[str, Any] | None = None,
    correlation_id: str | None = None,
    queue_key: str,
    settings_provider: SettingsProvider,
    dispatch_worker_heartbeat_key_builder: HeartbeatKeyBuilder,
    dispatch_worker_heartbeat_ttl_seconds: int,
    build_grouped_scope_command: Callable[..., CreateGroupedScopeGxRunCommand],
    persist_grouped_dispatch_run_use_case: PersistGroupedDispatchRunUseCase,
    inject_trace_carrier: InjectTraceCarrier,
    async_redis_module,
    sync_redis_module,
    logger,
) -> GxDispatchPayloadEntity:
    use_case_args = build_grouped_scope_run_args(
        command=build_grouped_scope_command(
            grouped_execution_plan=grouped_execution_plan,
            scope_selector=scope_selector,
            suite_refs=suite_refs,
            scheduled_at=scheduled_at,
            requested_by=requested_by,
            correlation_id=request_correlation_id(request, correlation_id),
            run_plan_id=run_plan_id,
            run_plan_version_id=run_plan_version_id,
            source_overrides_by_data_object_version_id=source_overrides_by_data_object_version_id,
            delivery_snapshot=delivery_snapshot,
            queue_key=queue_key,
        ),
        requested_by=requested_by,
        status_source=status_source,
        status_reason=status_reason,
        execution_run_repository=execution_run_repository,
        settings_provider=settings_provider,
        dispatch_worker_heartbeat_key_builder=dispatch_worker_heartbeat_key_builder,
        dispatch_worker_heartbeat_ttl_seconds=dispatch_worker_heartbeat_ttl_seconds,
        build_dispatch_payload=lambda **payload_kwargs: _build_grouped_dispatch_payload_with_tracing(
            **payload_kwargs,
            queue_key=queue_key,
            inject_trace_carrier=inject_trace_carrier,
        ),
        persist_grouped_dispatch_run_use_case=persist_grouped_dispatch_run_use_case,
        async_redis_module=async_redis_module,
        sync_redis_module=sync_redis_module,
        logger=logger,
    )
    return await create_grouped_scope_gx_run_use_case(
        command=use_case_args.command,
        resolve_redis_url=use_case_args.resolve_redis_url,
        assert_dispatch_worker=use_case_args.assert_dispatch_worker,
        build_dispatch_payload=use_case_args.build_dispatch_payload,
        persist_run=use_case_args.persist_run,
        enqueue_payload=use_case_args.enqueue_payload,
    )