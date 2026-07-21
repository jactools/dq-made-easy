"""EMR DQ Results endpoints — query DQ results by delivery.

DQ Results are published to Kafka by the DQ engine and consumed by EMR.
These endpoints allow querying results by delivery_time_event or delivery_id.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from emr.dependencies import get_emr_repository
from emr.schemas import EmrDqResultResponseView, EmrDqResultPageView

router = APIRouter(prefix="/dq-results", tags=["emr-dq-results"])


@router.get("/delivery/{delivery_time_event}", response_model=EmrDqResultPageView)
async def get_dq_results_by_delivery(
    delivery_time_event: str,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=100, ge=1, le=1000),
    repository=Depends(get_emr_repository),
) -> EmrDqResultPageView:
    """Get all DQ results for a specific delivery occurrence (UUIDv7)."""
    result = repository.get_dq_results_by_delivery(
        delivery_time_event, page=page, limit=limit
    )
    return EmrDqResultPageView.model_validate(result.model_dump())


@router.get("/stream/{delivery_id}", response_model=EmrDqResultPageView)
async def get_dq_results_by_stream(
    delivery_id: str,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=100, ge=1, le=1000),
    repository=Depends(get_emr_repository),
) -> EmrDqResultPageView:
    """Get all DQ results for a delivery stream (all occurrences)."""
    result = repository.get_dq_results_by_stream(
        delivery_id, page=page, limit=limit
    )
    return EmrDqResultPageView.model_validate(result.model_dump())


@router.get("", response_model=EmrDqResultPageView)
async def query_dq_results(
    delivery_id: str | None = Query(default=None),
    execution_run_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=100, ge=1, le=1000),
    repository=Depends(get_emr_repository),
) -> EmrDqResultPageView:
    """Query DQ results with optional filters."""
    items = repository._dq_results
    if delivery_id:
        items = [r for r in items if r.delivery_id == delivery_id]
    if execution_run_id:
        items = [r for r in items if r.execution_run_id == execution_run_id]
    if status:
        items = [r for r in items if r.status == status]

    total = len(items)
    start = (page - 1) * limit
    end = start + limit

    from emr.domain.dq_result import EmrDqResultPageEntity
    return EmrDqResultPageView.model_validate(
        EmrDqResultPageEntity(
            items=items[start:end],
            total=total,
            page=page,
            limit=limit,
        ).model_dump()
    )
