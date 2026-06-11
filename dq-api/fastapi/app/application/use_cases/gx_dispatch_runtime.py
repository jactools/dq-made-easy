from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import uuid4

from fastapi import HTTPException

from app.domain.entities.gx_execution_run import build_gx_dispatch_payload_entity
from app.domain.entities.gx_execution_run import build_gx_execution_contract_entity
from app.domain.entities.gx_execution_run import build_gx_execution_result_summary_entity
from app.domain.entities.gx_execution_run import build_gx_execution_run_create_entity
from app.domain.entities.gx_execution_run import build_gx_execution_run_status_transition_entity
from app.domain.entities.gx_execution_run import GxDispatchPayloadEntity
from app.domain.entities.gx_execution_run import GxExecutionRunCreateEntity
from app.domain.interfaces import GxExecutionRunRepository


ResolveRedisUrl = Callable[[], str | None]
AssertQueueWorker = Callable[[str, str], Awaitable[None]]
BuildDispatchPayload = Callable[..., Any]
InjectTraceCarrier = Callable[[dict[str, Any]], None]
EnqueueDispatchPayload = Callable[[str, GxDispatchPayloadEntity], Awaitable[None]]
MapPersistenceError = Callable[[str, str, str, Exception], HTTPException]


_ACTIVE_GX_EXECUTION_STATUSES = {"pending", "running"}


@dataclass(slots=True)
class EnqueueScheduledGxSuiteRunCommand:
    suite: Any
    scheduled_at: datetime
    requested_by: str | None
    status_source: str
    status_reason: str
    run_plan_id: str | None = None
    run_plan_version_id: str | None = None
    execution_scope_override: list[str] | None = None
    source_overrides_by_data_object_version_id: dict[str, dict[str, Any]] | None = None
    delivery_snapshot: dict[str, Any] | None = None
    correlation_id: str | None = None
    queue_key: str = "dq-gx:execution-dispatch"
    join_pair_materialization_queue_key: str = "dq-gx:join-pair-materialize"


def _as_dispatch_payload_entity(payload: Any) -> GxDispatchPayloadEntity:
    try:
        dispatch_payload = build_gx_dispatch_payload_entity(payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "invalid_dispatch_payload",
                "message": str(exc),
            },
        ) from exc
    if dispatch_payload is None:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "invalid_dispatch_payload",
                "message": "GX dispatch payload could not be normalized",
            },
        )
    return dispatch_payload


def _dispatch_identity_for_conflict(payload: GxDispatchPayloadEntity) -> tuple[str | None, str | None, int | None]:
    run_plan_id = getattr(payload, "runPlanId", None)
    if run_plan_id is None:
        run_plan_id = getattr(payload, "run_plan_id", None)
    if run_plan_id is None:
        model_extra = getattr(payload, "model_extra", None) or {}
        if isinstance(model_extra, dict):
            run_plan_id = model_extra.get("runPlanId") or model_extra.get("run_plan_id")
    run_plan_id = str(run_plan_id or "").strip() or None
    suite_id = str(payload.suiteId or "").strip() or None
    suite_version = int(payload.suiteVersion) if payload.suiteVersion is not None else None
    return run_plan_id, suite_id, suite_version


def _active_run_plan_id(run: Any) -> str | None:
    handoff_payload = getattr(run, "handoffPayload", None)
    run_plan_id = getattr(handoff_payload, "runPlanId", None) if handoff_payload is not None else None
    if run_plan_id is None and handoff_payload is not None:
        run_plan_id = getattr(handoff_payload, "run_plan_id", None)
    if run_plan_id is None and isinstance(handoff_payload, dict):
        run_plan_id = handoff_payload.get("runPlanId") or handoff_payload.get("run_plan_id")
    if run_plan_id is None and handoff_payload is not None:
        model_extra = getattr(handoff_payload, "model_extra", None) or {}
        if isinstance(model_extra, dict):
            run_plan_id = model_extra.get("runPlanId") or model_extra.get("run_plan_id")
    normalized = str(run_plan_id or "").strip()
    return normalized or None


def _raise_active_gx_execution_conflict(
    *,
    run_plan_id: str | None,
    suite_id: str | None,
    suite_version: int | None,
    active_run: Any,
) -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={
            "error": "gx_execution_already_active",
            "message": "GX execution is already active for this object",
            "run_plan_id": run_plan_id,
            "suite_id": suite_id,
            "suite_version": suite_version,
            "active_run_id": str(getattr(active_run, "id", "") or "").strip(),
            "active_run_status": str(getattr(active_run, "status", "") or "").strip(),
        },
    )


async def _assert_no_active_gx_execution_conflict(
    execution_run_repository: GxExecutionRunRepository,
    *,
    run_plan_id: str | None = None,
    suite_id: str | None = None,
    suite_version: int | None = None,
) -> None:
    normalized_run_plan_id = str(run_plan_id or "").strip() or None
    normalized_suite_id = str(suite_id or "").strip() or None
    if normalized_run_plan_id is None and normalized_suite_id is None:
        return

    candidate_runs: list[Any] = []
    if normalized_run_plan_id is not None:
        candidate_runs.extend(await execution_run_repository.list_runs({"status": "pending"}))
        candidate_runs.extend(await execution_run_repository.list_runs({"status": "running"}))
    else:
        candidate_runs.extend(await execution_run_repository.list_runs({"suite_id": normalized_suite_id, "status": "pending"}))
        candidate_runs.extend(await execution_run_repository.list_runs({"suite_id": normalized_suite_id, "status": "running"}))

    for run in candidate_runs:
        if str(getattr(run, "status", "") or "").strip() not in _ACTIVE_GX_EXECUTION_STATUSES:
            continue
        if normalized_run_plan_id is not None:
            if _active_run_plan_id(run) == normalized_run_plan_id:
                raise _raise_active_gx_execution_conflict(
                    run_plan_id=normalized_run_plan_id,
                    suite_id=normalized_suite_id,
                    suite_version=suite_version,
                    active_run=run,
                )
            continue
        if normalized_suite_id is not None:
            if str(getattr(run, "suiteId", "") or "").strip() != normalized_suite_id:
                continue
            if suite_version is not None and getattr(run, "suiteVersion", None) != suite_version:
                continue
            raise _raise_active_gx_execution_conflict(
                run_plan_id=None,
                suite_id=normalized_suite_id,
                suite_version=suite_version,
                active_run=run,
            )


def _suite_id(suite: Any) -> str | None:
    value = str(getattr(suite, "suiteId", "") or "").strip()
    return value or None


def _suite_version(suite: Any) -> int | None:
    value = getattr(suite, "suiteVersion", None)
    return int(value) if value is not None else None


def _suite_execution_contract(suite: Any):
    return getattr(suite, "executionContract", None)


def _dispatch_engine_type(payload: GxDispatchPayloadEntity) -> str | None:
    engine_type = str(payload.engineType or "").strip().lower()
    return engine_type or None


def _required_dispatch_engine_type(payload: GxDispatchPayloadEntity, *, context: str) -> str:
    engine_type = _dispatch_engine_type(payload)
    if engine_type is None:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "missing_engine_type",
                "message": f"{context} requires explicit engine_type",
                "run_id": payload.runId,
                "correlation_id": payload.correlationId,
            },
        )
    return engine_type


def _assert_execution_contract_engine_type(
    execution_contract: Any,
    *,
    expected_engine_type: str,
    context: str,
    run_id: str | None,
    correlation_id: str | None,
) -> None:
    actual_engine_type = str(getattr(execution_contract, "engineType", "") or "").strip().lower()
    if not actual_engine_type:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "missing_engine_type",
                "message": f"{context} requires execution_contract.engine_type",
                "run_id": run_id,
                "correlation_id": correlation_id,
            },
        )
    if actual_engine_type != expected_engine_type:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "engine_type_mismatch",
                "message": (
                    f"{context} requires matching engine_type across dispatch and execution_contract"
                ),
                "engine_type": expected_engine_type,
                "execution_contract_engine_type": actual_engine_type,
                "run_id": run_id,
                "correlation_id": correlation_id,
            },
        )


def _with_trace_headers(
    payload: GxDispatchPayloadEntity,
    inject_trace_carrier: InjectTraceCarrier,
) -> GxDispatchPayloadEntity:
    carrier = dict(payload.headers or {})
    inject_trace_carrier(carrier)
    return payload.model_copy(update={"headers": carrier})


def suite_requires_join_pair_materialization(
    suite: Any,
    *,
    has_source_override: bool,
) -> bool:
    execution_contract = _suite_execution_contract(suite)
    if execution_contract is None:
        return False
    return str(getattr(execution_contract, "executionShape", "") or "").strip() == "join_pair" and not has_source_override


def build_join_pair_materialization_handoff_payload(
    *,
    dispatch_payload: GxDispatchPayloadEntity,
    queue_key: str,
) -> GxDispatchPayloadEntity:
    execution_contract = dispatch_payload.executionContract
    source_materialization = execution_contract.sourceMaterialization if execution_contract is not None else None
    if source_materialization is None:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "gx_suite_not_runnable",
                "message": "GX join_pair execution requires source_materialization before ETL enqueue",
                "reason": "missing_source_materialization",
                "suite_id": dispatch_payload.suiteId,
                "suite_version": dispatch_payload.suiteVersion,
            },
        )

    accepted_payload = build_gx_dispatch_payload_entity(
        {
            **dispatch_payload.model_dump(by_alias=True, exclude_none=True),
            "queue_key": queue_key,
            "materialization_job_type": "join_pair_materialization",
            "next_dispatch_payload": dispatch_payload.model_dump(by_alias=True, exclude_none=True),
        }
    )
    if accepted_payload is None:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "invalid_dispatch_payload",
                "message": "GX join-pair materialization handoff payload could not be normalized",
                "suite_id": dispatch_payload.suiteId,
                "correlation_id": dispatch_payload.correlationId,
            },
        )
    return accepted_payload


def build_execution_run_create_entity_for_suite_dispatch(
    *,
    suite: Any,
    handoff_payload: GxDispatchPayloadEntity,
    requested_by: str | None,
    status_source: str,
    status_reason: str,
    execution_scope_override: list[str] | None = None,
    source_overrides_by_data_object_version_id: dict[str, dict[str, Any]] | None = None,
) -> GxExecutionRunCreateEntity:
    execution_contract = handoff_payload.executionContract
    if execution_contract is None:
        execution_contract = build_gx_execution_contract_entity(_suite_execution_contract(suite))
    if execution_contract is None:
        suite_id = _suite_id(suite) or "unknown-suite"
        raise HTTPException(status_code=400, detail=f"GX suite '{suite_id}' is missing an execution_contract")

    traceability = execution_contract.traceability
    dispatch_engine_type = _required_dispatch_engine_type(handoff_payload, context="GX suite dispatch")
    _assert_execution_contract_engine_type(
        execution_contract,
        expected_engine_type=dispatch_engine_type,
        context="GX suite dispatch",
        run_id=handoff_payload.runId or handoff_payload.queueMessageId,
        correlation_id=handoff_payload.correlationId,
    )
    status_details: dict[str, Any] = {
        "source": status_source,
        "dispatch_mode": handoff_payload.dispatchMode,
        "queue_key": handoff_payload.queueKey,
        "queue_message_id": handoff_payload.queueMessageId,
        "handoff_status": handoff_payload.handoffStatus,
        "handoff_ready": handoff_payload.handoffReady,
        "scheduled_at": handoff_payload.scheduledAt,
    }
    status_details["engine_type"] = dispatch_engine_type
    if execution_scope_override:
        status_details["execution_scope_override"] = list(execution_scope_override)
    if source_overrides_by_data_object_version_id:
        status_details["source_overrides_by_data_object_version_id"] = source_overrides_by_data_object_version_id
    if handoff_payload.nextDispatchPayload is not None:
        status_details["pre_dispatch_phase"] = "join_pair_materialization"
        status_details["next_queue_key"] = handoff_payload.nextDispatchPayload.queueKey

    persisted_handoff_payload = build_gx_dispatch_payload_entity(
        {
            **handoff_payload.model_dump(by_alias=True, exclude_none=True),
            "status_details": status_details,
        }
    )

    return build_gx_execution_run_create_entity(
        {
            "run_id": str(handoff_payload.runId or handoff_payload.queueMessageId or ""),
            "suite_id": handoff_payload.suiteId or _suite_id(suite),
            "suite_version": handoff_payload.suiteVersion if handoff_payload.suiteVersion is not None else _suite_version(suite),
            "rule_id": str(traceability.ruleId or "").strip() or None if traceability is not None else None,
            "rule_version_id": str(traceability.ruleVersionId or "").strip() or None if traceability is not None else None,
            "correlation_id": str(handoff_payload.correlationId or ""),
            "requested_by": requested_by,
            "engine_type": dispatch_engine_type,
            "engine_target": str(handoff_payload.engineTarget or ""),
            "execution_shape": str(handoff_payload.executionShape or ""),
            "status": "pending",
            "submitted_at": str(handoff_payload.submittedAt or ""),
            "execution_contract": execution_contract,
            "handoff_payload": persisted_handoff_payload,
            "result_summary": build_gx_execution_result_summary_entity({}),
            "diagnostics": [],
            "status_reason": status_reason,
            "status_details": status_details,
        }
    )


def build_execution_run_create_entity_for_grouped_dispatch(
    *,
    handoff_payload: GxDispatchPayloadEntity,
    requested_by: str | None,
    status_source: str = "gx.run_plan.grouped.activate",
    status_reason: str = "Grouped GX run accepted",
) -> GxExecutionRunCreateEntity:
    dispatch_engine_type = _required_dispatch_engine_type(handoff_payload, context="GX grouped dispatch")
    grouped_plan = handoff_payload.groupedExecutionPlan
    execution_contract = build_gx_execution_contract_entity(
        {
            "engine_type": dispatch_engine_type,
            "selection_mode": "grouped_scope",
            "scope_selector": dict(handoff_payload.scopeSelector or {}),
            "suite_refs": list(handoff_payload.suiteRefs or []),
            "suite_count": grouped_plan.suiteCount if grouped_plan is not None else None,
            "batch_count": grouped_plan.batchCount if grouped_plan is not None else None,
        }
    )
    status_details = {
        "source": status_source,
        "handoff_status": handoff_payload.handoffStatus,
        "handoff_ready": handoff_payload.handoffReady,
        "queue_key": handoff_payload.queueKey,
        "queue_message_id": handoff_payload.queueMessageId,
        "dispatch_mode": handoff_payload.dispatchMode,
        "scheduled_at": handoff_payload.scheduledAt,
        "selection_mode": "grouped_scope",
        "engine_type": dispatch_engine_type,
    }
    persisted_handoff_payload = build_gx_dispatch_payload_entity(
        {
            **handoff_payload.model_dump(by_alias=True, exclude_none=True),
            "status_details": status_details,
        }
    )
    return build_gx_execution_run_create_entity(
        {
            "run_id": str(handoff_payload.runId or handoff_payload.queueMessageId or ""),
            "suite_id": None,
            "suite_version": None,
            "rule_id": None,
            "rule_version_id": None,
            "correlation_id": str(handoff_payload.correlationId or ""),
            "requested_by": requested_by,
            "engine_type": dispatch_engine_type,
            "engine_target": str(handoff_payload.engineTarget or "pyspark"),
            "execution_shape": "grouped_scope",
            "status": "pending",
            "submitted_at": str(handoff_payload.submittedAt or ""),
            "execution_contract": execution_contract,
            "handoff_payload": persisted_handoff_payload,
            "result_summary": build_gx_execution_result_summary_entity({}),
            "diagnostics": [],
            "status_reason": status_reason,
            "status_details": status_details,
        }
    )


async def persist_grouped_dispatch_run(
    *,
    dispatch_payload: GxDispatchPayloadEntity,
    execution_run_repository: GxExecutionRunRepository,
    requested_by: str | None,
    status_source: str = "gx.run_plan.grouped.activate",
    status_reason: str = "Grouped GX run accepted",
) -> None:
    run_plan_id, suite_id, suite_version = _dispatch_identity_for_conflict(dispatch_payload)
    await _assert_no_active_gx_execution_conflict(
        execution_run_repository,
        run_plan_id=run_plan_id,
        suite_id=suite_id,
        suite_version=suite_version,
    )
    await execution_run_repository.create_run(
        build_execution_run_create_entity_for_grouped_dispatch(
            handoff_payload=dispatch_payload,
            requested_by=requested_by,
            status_source=status_source,
            status_reason=status_reason,
        )
    )


async def enqueue_scheduled_gx_suite_run(
    *,
    command: EnqueueScheduledGxSuiteRunCommand,
    execution_run_repository: GxExecutionRunRepository,
    resolve_redis_url: ResolveRedisUrl,
    assert_dispatch_worker: AssertQueueWorker,
    assert_join_pair_materialization_worker: AssertQueueWorker,
    build_dispatch_payload: BuildDispatchPayload,
    inject_trace_carrier: InjectTraceCarrier,
    enqueue_payload: EnqueueDispatchPayload,
    map_persistence_error: MapPersistenceError,
) -> GxDispatchPayloadEntity:
    redis_url = resolve_redis_url()
    if not redis_url:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "dispatch_queue_unavailable",
                "message": "GX dispatch queue is not configured",
                "suite_id": _suite_id(command.suite),
            },
        )

    await assert_dispatch_worker(redis_url, command.queue_key)

    correlation_id = str(command.correlation_id or f"corr-{uuid4().hex[:12]}")
    dispatch_payload = _as_dispatch_payload_entity(
        build_dispatch_payload(
            suite=command.suite,
            correlation_id=correlation_id,
            requested_by=command.requested_by,
            scheduled_at=command.scheduled_at,
            run_plan_id=command.run_plan_id,
            run_plan_version_id=command.run_plan_version_id,
            execution_scope_override=command.execution_scope_override,
            source_overrides_by_data_object_version_id=command.source_overrides_by_data_object_version_id,
            delivery_snapshot=command.delivery_snapshot,
        )
    )

    await _assert_no_active_gx_execution_conflict(
        execution_run_repository,
        run_plan_id=command.run_plan_id,
        suite_id=_suite_id(command.suite),
        suite_version=_suite_version(command.suite),
    )

    if suite_requires_join_pair_materialization(
        command.suite,
        has_source_override=bool(command.source_overrides_by_data_object_version_id),
    ):
        await assert_join_pair_materialization_worker(redis_url, command.join_pair_materialization_queue_key)
        dispatch_payload = _with_trace_headers(dispatch_payload, inject_trace_carrier)
        accepted_payload = build_join_pair_materialization_handoff_payload(
            dispatch_payload=dispatch_payload,
            queue_key=command.join_pair_materialization_queue_key,
        )
        accepted_payload = _with_trace_headers(accepted_payload, inject_trace_carrier)
    else:
        accepted_payload = _with_trace_headers(dispatch_payload, inject_trace_carrier)

    try:
        await execution_run_repository.create_run(
            build_execution_run_create_entity_for_suite_dispatch(
                suite=command.suite,
                handoff_payload=accepted_payload,
                requested_by=command.requested_by,
                status_source=command.status_source,
                status_reason=command.status_reason,
                execution_scope_override=command.execution_scope_override,
                source_overrides_by_data_object_version_id=command.source_overrides_by_data_object_version_id,
            )
        )
    except Exception as exc:
        raise map_persistence_error(
            str(_suite_id(command.suite) or "unknown-suite"),
            str(accepted_payload.queueMessageId or accepted_payload.runId or ""),
            correlation_id,
            exc,
        ) from exc

    try:
        await enqueue_payload(redis_url, accepted_payload)
    except Exception as exc:
        await execution_run_repository.record_run_status_transition(
            build_gx_execution_run_status_transition_entity(
                {
                    "run_id": str(accepted_payload.queueMessageId or accepted_payload.runId or ""),
                    "new_status": "failed",
                    "changed_by": command.requested_by,
                    "reason": "GX dispatch queue enqueue failed",
                    "details": {
                        "source": command.status_source,
                        "exception": exc.__class__.__name__,
                        "queue_key": accepted_payload.queueKey,
                        "dispatch_mode": accepted_payload.dispatchMode,
                    },
                }
            )
        )
        raise HTTPException(
            status_code=503,
            detail={
                "error": "dispatch_enqueue_failed",
                "message": "Unable to enqueue GX dispatch",
                "suite_id": _suite_id(command.suite),
                "queue_key": accepted_payload.queueKey,
                "queue_message_id": accepted_payload.queueMessageId,
                "correlation_id": correlation_id,
                "exception": exc.__class__.__name__,
            },
        ) from exc

    return accepted_payload