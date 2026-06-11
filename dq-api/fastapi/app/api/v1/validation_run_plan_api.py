from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from fastapi import HTTPException, Request

from app.api.presenters.validation_run_plans import build_validation_run_plan_view
from app.api.v1 import gx_runtime_api as _gx_runtime_api
from app.api.v1.schemas import ValidationRunPlanView
from app.application.services.gx_run_plan_validation import GxRunPlanActivationSnapshotError
from app.application.services.gx_run_plan_validation import resolve_single_suite_activation_snapshot
from app.domain.entities.gx_execution_run import GxDispatchPayloadEntity
from app.domain.entities.gx_run_plan import build_gx_run_plan_schedule_definition_entity
from app.domain.entities.gx_run_plan import build_gx_run_plan_suite_selection_entity
from app.domain.entities.validation_run_plan import build_gx_run_plan_entity_from_validation_run_plan
from app.domain.interfaces import DataCatalogRepository
from app.domain.interfaces import GxExecutionRunRepository
from app.domain.interfaces import ValidationRunPlanRepository


@dataclass(slots=True)
class ValidationRunPlanReplayResult:
    run_plan_id: str
    run_plan_version_id: str
    workspace_id: str
    trigger_type: str
    source_pipeline: str | None
    selection_mode: str | None
    dispatch: GxDispatchPayloadEntity


ReplayTriggerType = Literal["manual", "pipeline_run", "schedule"]


def _resolve_replay_schedule(
    *,
    active_version: object,
    trigger_type: ReplayTriggerType,
    scheduled_at: datetime | None,
    run_plan_id: str,
    run_plan_version_id: str,
) -> datetime:
    if scheduled_at is not None:
        return scheduled_at
    if trigger_type != "schedule":
        return datetime.now(UTC)

    schedule_definition = build_gx_run_plan_schedule_definition_entity(getattr(active_version, "scheduleDefinition", None))
    scheduled_at_raw = str(schedule_definition.scheduledAt or "").strip()
    if not scheduled_at_raw:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "missing_schedule_definition",
                "message": "Validation run plan active version is missing scheduled_at",
                "run_plan_id": run_plan_id,
                "run_plan_version_id": run_plan_version_id,
            },
        )
    return datetime.fromisoformat(scheduled_at_raw.replace("Z", "+00:00"))


def _replay_status(trigger_type: ReplayTriggerType) -> tuple[str, str]:
    if trigger_type == "pipeline_run":
        return ("validation_run_plan.pipeline_run", "Validation plan pipeline-run trigger requested")
    if trigger_type == "schedule":
        return ("validation_run_plan.schedule", "Validation plan schedule trigger requested")
    return ("validation_run_plan.replay", "Validation plan replay requested")


async def list_run_plans(
    *,
    workspace_id: str | None,
    business_key: str | None,
    suite_id: str | None,
    status: str | None,
    repository: ValidationRunPlanRepository,
) -> list[ValidationRunPlanView]:
    rows = await repository.list_plans(
        workspace_id=workspace_id,
        business_key=business_key,
        status=status,
        artifact_id=suite_id,
    )
    return [build_validation_run_plan_view(row) for row in rows]


async def replay_run_plan(
    *,
    request: Request,
    run_plan_id: str,
    repository: ValidationRunPlanRepository,
    execution_run_repository: GxExecutionRunRepository,
    data_catalog_repository: DataCatalogRepository,
    requested_by: str | None,
    correlation_id: str | None,
    trigger_type: ReplayTriggerType = "manual",
    source_pipeline: str | None = None,
    scheduled_at: datetime | None = None,
    settings_provider,
    async_redis_module,
    sync_redis_module,
    logger,
) -> ValidationRunPlanReplayResult:
    plan = await repository.get_plan(run_plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail=f"Validation run plan '{run_plan_id}' not found")

    gx_plan = build_gx_run_plan_entity_from_validation_run_plan(plan)
    active_version_id = str(gx_plan.currentActiveVersionId or "").strip()
    if not active_version_id:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "no_active_version",
                "message": "Validation run plan has no active version to replay",
                "run_plan_id": run_plan_id,
            },
        )

    active_version = next((item for item in gx_plan.versions if item.runPlanVersionId == active_version_id), None)
    if active_version is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "active_version_not_found",
                "message": "Validation run plan active version was not found",
                "run_plan_id": run_plan_id,
                "run_plan_version_id": active_version_id,
            },
        )

    selection = build_gx_run_plan_suite_selection_entity(active_version.gxSuiteSelection)
    selection_mode = str(selection.selectionMode or "").strip() or None
    replay_scheduled_at = _resolve_replay_schedule(
        active_version=active_version,
        trigger_type=trigger_type,
        scheduled_at=scheduled_at,
        run_plan_id=run_plan_id,
        run_plan_version_id=active_version_id,
    )
    status_source, status_reason = _replay_status(trigger_type)

    if selection_mode == "grouped_scope":
        if not selection.suiteRefs:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "missing_suite_refs",
                    "message": "Validation run plan grouped replay requires suite refs",
                    "run_plan_id": run_plan_id,
                    "run_plan_version_id": active_version_id,
                },
            )

        enqueue_grouped_scope_run = _gx_runtime_api.bind_grouped_scope_run_enqueue(
            settings_provider=settings_provider,
            async_redis_module=async_redis_module,
            sync_redis_module=sync_redis_module,
            logger=logger,
        )
        dispatch = await enqueue_grouped_scope_run(
            request=request,
            grouped_execution_plan=selection.groupedExecutionPlan.model_dump(by_alias=True, exclude_none=True)
            if selection.groupedExecutionPlan is not None
            else {},
            scope_selector=selection.scopeSelector.model_dump(by_alias=True, exclude_none=True),
            suite_refs=[item.model_dump(by_alias=True, exclude_none=True) for item in selection.suiteRefs],
            scheduled_at=replay_scheduled_at,
            execution_run_repository=execution_run_repository,
            requested_by=requested_by,
            status_source=status_source,
            status_reason=status_reason,
            run_plan_id=run_plan_id,
            run_plan_version_id=active_version_id,
            correlation_id=correlation_id,
        )
        dispatched_run_id = str(dispatch.runId or dispatch.queueMessageId or "").strip()
        if not dispatched_run_id:
            raise HTTPException(status_code=500, detail="Validation run plan replay did not return a run_id")
        await repository.record_plan_dispatch(
            run_plan_id=run_plan_id,
            run_plan_version_id=active_version_id,
            dispatched_run_id=dispatched_run_id,
            dispatched_by=requested_by,
            correlation_id=correlation_id,
            details={
                "trigger_type": trigger_type,
                "source_pipeline": source_pipeline,
                "selection_mode": selection_mode,
            },
        )
        return ValidationRunPlanReplayResult(
            run_plan_id=run_plan_id,
            run_plan_version_id=active_version_id,
            workspace_id=str(getattr(plan, "workspaceId", None) or "").strip(),
            trigger_type=trigger_type,
            source_pipeline=source_pipeline,
            selection_mode=selection_mode,
            dispatch=dispatch,
        )

    try:
        suite = resolve_single_suite_activation_snapshot(active_version)
    except GxRunPlanActivationSnapshotError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": exc.code,
                "message": exc.message,
                "details": exc.details,
                "run_plan_id": run_plan_id,
                "run_plan_version_id": active_version_id,
            },
        ) from exc

    enqueue_scheduled_suite_run = _gx_runtime_api.bind_scheduled_suite_run_enqueue(
        data_catalog_repository=data_catalog_repository,
        settings_provider=settings_provider,
        async_redis_module=async_redis_module,
        sync_redis_module=sync_redis_module,
        logger=logger,
    )
    dispatch = await enqueue_scheduled_suite_run(
        request=request,
        suite=suite,
        scheduled_at=replay_scheduled_at,
        execution_run_repository=execution_run_repository,
        requested_by=requested_by,
        status_source=status_source,
        status_reason=status_reason,
        run_plan_id=run_plan_id,
        run_plan_version_id=active_version_id,
        correlation_id=correlation_id,
    )
    dispatched_run_id = str(dispatch.runId or dispatch.queueMessageId or "").strip()
    if not dispatched_run_id:
        raise HTTPException(status_code=500, detail="Validation run plan replay did not return a run_id")
    await repository.record_plan_dispatch(
        run_plan_id=run_plan_id,
        run_plan_version_id=active_version_id,
        dispatched_run_id=dispatched_run_id,
        dispatched_by=requested_by,
        correlation_id=correlation_id,
        details={
            "trigger_type": trigger_type,
            "source_pipeline": source_pipeline,
            "selection_mode": selection_mode,
        },
    )
    return ValidationRunPlanReplayResult(
        run_plan_id=run_plan_id,
        run_plan_version_id=active_version_id,
        workspace_id=str(getattr(plan, "workspaceId", None) or "").strip(),
        trigger_type=trigger_type,
        source_pipeline=source_pipeline,
        selection_mode=selection_mode,
        dispatch=dispatch,
    )
