from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.api.v1 import validation_run_plan_api as _validation_run_plan_api
from app.api.v1.schemas import ValidationRunPlanReplayRequestView
from app.api.v1.schemas import ValidationRunPlanReplayView
from app.api.v1.schemas import ValidationRunPlanView
from app.application.services import gx_queue_service
from app.core.config import get_settings
from app.core.dependencies import get_approvals_repository
from app.core.request_context import get_correlation_id
from app.core.request_context import get_user_id
from app.core.dependencies import get_data_catalog_repository
from app.core.dependencies import get_gx_execution_run_repository
from app.core.dependencies import get_validation_run_plan_repository
from app.domain.interfaces import DataCatalogRepository
from app.domain.interfaces import ApprovalsRepository
from app.domain.interfaces import GxExecutionRunRepository
from app.domain.interfaces import ValidationRunPlanRepository

router = APIRouter(prefix="/validation-run-plans", tags=["validation-run-plans"])
_log = logging.getLogger(__name__)


@router.get("", response_model=list[ValidationRunPlanView], responses={200: {"description": "Validation plans."}})
async def list_validation_run_plans(
    workspace_id: str | None = Query(default=None, alias="workspaceId"),
    business_key: str | None = Query(default=None, alias="businessKey"),
    suite_id: str | None = Query(default=None, alias="suiteId"),
    status: str | None = Query(default=None),
    repository: ValidationRunPlanRepository = Depends(get_validation_run_plan_repository),
) -> list[ValidationRunPlanView]:
    return await _validation_run_plan_api.list_run_plans(
        workspace_id=workspace_id,
        business_key=business_key,
        suite_id=suite_id,
        status=status,
        repository=repository,
    )


@router.post(
    "/{run_plan_id}/replay",
    response_model=ValidationRunPlanReplayView,
    status_code=202,
    responses={
        202: {"description": "Validation plan replay accepted and enqueued."},
        404: {"description": "Validation run plan not found or has no active version to replay."},
        422: {"description": "Validation run plan replay payload is not runnable."},
        503: {"description": "Dispatch queue is unavailable."},
    },
)
async def replay_validation_run_plan(
    request: Request,
    run_plan_id: str,
    payload: ValidationRunPlanReplayRequestView | None = None,
    repository: ValidationRunPlanRepository = Depends(get_validation_run_plan_repository),
    execution_run_repository: GxExecutionRunRepository = Depends(get_gx_execution_run_repository),
    data_catalog_repository: DataCatalogRepository = Depends(get_data_catalog_repository),
    approvals_repository: ApprovalsRepository = Depends(get_approvals_repository),
) -> ValidationRunPlanReplayView:
    replay_result = await _validation_run_plan_api.replay_run_plan(
        request=request,
        run_plan_id=run_plan_id,
        repository=repository,
        execution_run_repository=execution_run_repository,
        data_catalog_repository=data_catalog_repository,
        requested_by=get_user_id() or "system",
        correlation_id=get_correlation_id(),
        trigger_type=payload.triggerType if payload is not None else "manual",
        source_pipeline=payload.sourcePipeline if payload is not None else None,
        scheduled_at=payload.scheduledAt if payload is not None else None,
        settings_provider=get_settings,
        async_redis_module=gx_queue_service.aioredis,
        sync_redis_module=gx_queue_service.redis_sync,
        logger=_log,
    )

    dispatch = replay_result.dispatch
    if dispatch is None:
        raise HTTPException(status_code=500, detail="Validation plan replay did not return a dispatch payload")

    workspace_id = str(getattr(replay_result, "workspace_id", "") or "").strip()
    if not workspace_id:
        raise HTTPException(status_code=500, detail="Validation run plan workspace is unavailable")

    approvals_repository.append_audit_event(
        approval_id=f"validation-run-plan:{replay_result.run_plan_id}:{replay_result.run_plan_version_id}",
        action="validation_run_plan.replayed",
        actor_id=get_user_id() or "system",
        details={
            "workspace_id": workspace_id,
            "run_plan_id": replay_result.run_plan_id,
            "run_plan_version_id": replay_result.run_plan_version_id,
            "trigger_type": replay_result.trigger_type,
            "source_pipeline": replay_result.source_pipeline,
            "selection_mode": replay_result.selection_mode,
            "suite_id": dispatch.suiteId,
            "suite_version": dispatch.suiteVersion,
            "engine_type": dispatch.engineType,
            "dispatch_mode": dispatch.dispatchMode,
            "queue_message_id": dispatch.queueMessageId,
            "run_id": dispatch.runId,
            "message": f"Validation run plan {replay_result.run_plan_id} replayed",
        },
    )

    return ValidationRunPlanReplayView.model_validate(
        {
            "runId": dispatch.runId or dispatch.queueMessageId,
            "queueMessageId": dispatch.queueMessageId or dispatch.runId,
            "runPlanId": replay_result.run_plan_id,
            "runPlanVersionId": replay_result.run_plan_version_id,
            "triggerType": replay_result.trigger_type,
            "sourcePipeline": replay_result.source_pipeline,
            "selectionMode": replay_result.selection_mode,
            "suiteId": dispatch.suiteId,
            "suiteVersion": dispatch.suiteVersion,
            "engineType": dispatch.engineType,
            "engineTarget": dispatch.engineTarget,
            "executionShape": dispatch.executionShape,
            "dispatchMode": dispatch.dispatchMode,
            "queueKey": dispatch.queueKey,
            "scheduledAt": dispatch.scheduledAt or "",
            "correlationId": dispatch.correlationId,
        }
    )
