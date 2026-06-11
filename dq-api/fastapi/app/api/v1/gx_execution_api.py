from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from app.api.v1 import gx_runtime_api as _gx_runtime_api
from app.api.v1.schemas import GxExecutionQueueStatusView
from app.api.v1.schemas import GxExecutionRunStatusHistoryView
from app.api.v1.schemas import GxExecutionRunView
from app.application.use_cases.gx_queue_status import GetGxExecutionQueueStatusQuery
from app.application.use_cases.gx_queue_status import get_gx_execution_queue_status as get_gx_execution_queue_status_use_case
from app.domain.interfaces import GxExecutionRunRepository


async def get_execution_run(
    *,
    run_id: str,
    repository: GxExecutionRunRepository,
) -> GxExecutionRunView:
    run = await repository.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"GX execution run '{run_id}' not found")

    payload = run.model_dump(mode="python", by_alias=False, exclude_none=True)
    handoff_payload = payload.get("handoffPayload") if isinstance(payload, dict) else None
    status_details = payload.get("statusDetails") if isinstance(payload, dict) else None
    execution_contract = payload.get("executionContract") if isinstance(payload, dict) else None
    run_plan_id = None
    resolved_delivery_id = None
    if isinstance(handoff_payload, dict):
        run_plan_id = handoff_payload.get("runPlanId") or handoff_payload.get("run_plan_id")
        resolved_delivery_id = handoff_payload.get("resolvedDataDeliveryId") or handoff_payload.get("resolved_data_delivery_id")
        if resolved_delivery_id is None:
            delivery_snapshot = handoff_payload.get("deliverySnapshot")
            if isinstance(delivery_snapshot, dict):
                resolved_delivery_id = delivery_snapshot.get("resolvedDataDeliveryId") or delivery_snapshot.get("resolved_data_delivery_id")
    if run_plan_id is None and isinstance(status_details, dict):
        run_plan_id = status_details.get("runPlanId") or status_details.get("run_plan_id")
    if resolved_delivery_id is None and isinstance(execution_contract, dict):
        resolved_delivery_id = execution_contract.get("resolvedDataDeliveryId") or execution_contract.get("resolved_data_delivery_id")

    if run_plan_id is not None:
        payload["runPlanId"] = run_plan_id
    if resolved_delivery_id is not None:
        payload["resolvedDataDeliveryId"] = resolved_delivery_id

    return GxExecutionRunView.model_validate(payload)


async def fetch_execution_run_view(
    *,
    run_id: str,
    repository: GxExecutionRunRepository,
) -> GxExecutionRunView:
    return await get_execution_run(run_id=run_id, repository=repository)


async def list_execution_run_status_history(
    *,
    run_id: str,
    repository: GxExecutionRunRepository,
) -> list[GxExecutionRunStatusHistoryView]:
    run = await repository.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"GX execution run '{run_id}' not found")

    history = await repository.list_run_status_history(run_id)
    return [GxExecutionRunStatusHistoryView.model_validate(entry) for entry in history]


async def fetch_execution_run_status_history(
    *,
    run_id: str,
    repository: GxExecutionRunRepository,
) -> list[GxExecutionRunStatusHistoryView]:
    return await list_execution_run_status_history(run_id=run_id, repository=repository)


def build_queue_status_view(result: Any) -> GxExecutionQueueStatusView:
    return GxExecutionQueueStatusView.model_validate(
        {
            "run_id": result.run_id,
            "business_key": result.business_key,
            "correlation_id": result.correlation_id,
            "queue_key": result.queue_key,
            "queue_message_id": result.queue_message_id,
            "queue_length": result.queue_length,
            "inspected_depth": result.inspected_depth,
            "found": result.found,
            "index_from_head": result.index_from_head,
            "index_from_tail": result.index_from_tail,
        }
    )


async def get_execution_run_queue_status(
    *,
    run_id: str,
    scan_limit: int,
    repository: GxExecutionRunRepository,
    settings: Any,
    async_redis_module: Any,
    sync_redis_module: Any,
    logger: Any,
) -> GxExecutionQueueStatusView:
    use_case_args = _gx_runtime_api.build_queue_status_args(
        settings_provider=lambda: settings,
        async_redis_module=async_redis_module,
        sync_redis_module=sync_redis_module,
        logger=logger,
    )
    result = await get_gx_execution_queue_status_use_case(
        query=GetGxExecutionQueueStatusQuery(run_id=run_id, scan_limit=scan_limit),
        repository=repository,
        resolve_redis_url=use_case_args.resolve_redis_url,
        fetch_queue_status=use_case_args.fetch_queue_status,
    )
    return build_queue_status_view(result)