"""EMR delivery endpoints for the Canonical Delivery Registry.

Provides Phase 1 functionality:
- Register and retrieve deliveries
- Store delivery metadata and lifecycle status
- Query deliveries by stream, producer, type, status
- Update delivery lifecycle status
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from emr.schemas import (
    EmrDeliveryCreateRequestView,
    EmrDeliveryLifecycleEventRequestView,
    EmrDeliveryPageView,
    EmrDeliveryResponseView,
    EmrDeliveryUpdateStatusRequestView,
    EmrDeliveryErrorRequestView,
    EmrDeliveryErrorResponseView,
    EmrDeliveryLifecycleEventResponseView,
    EmrDeliveryMetadataRequestView,
    EmrDeliveryMetadataResponseView,
)
from emr.dependencies import get_emr_repository
from emr_delivery_sdk import DeliveryId, DeliveryIdBuilder, generate_delivery_time_event

router = APIRouter(prefix="/deliveries", tags=["emr"])


@router.post("", response_model=EmrDeliveryResponseView)
async def register_delivery(
    body: EmrDeliveryCreateRequestView,
    repository=Depends(get_emr_repository),
) -> EmrDeliveryResponseView:
    """Register a new delivery in the Canonical Delivery Registry.

    Generates a delivery_time_event (UUIDv7) if not provided.
    """
    from emr.domain.entities import EmrDeliveryEntity

    delivery = EmrDeliveryEntity.model_validate(body.model_dump(mode="python"))

    # Validate DeliveryId format using SDK
    try:
        DeliveryId.from_string(delivery.delivery_id)
    except ValueError as e:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "invalid_delivery_id",
                "message": f"Invalid DeliveryId format: {str(e)}",
            },
        )

    # Generate delivery_time_event if not provided using EMR Delivery SDK
    if not delivery.delivery_time_event or not delivery.delivery_time_event.strip():
        delivery.delivery_time_event = generate_delivery_time_event()

    result = repository.register_delivery(delivery)
    return EmrDeliveryResponseView.model_validate(result.model_dump())


@router.get("/{delivery_time_event}", response_model=EmrDeliveryResponseView)
async def get_delivery(
    delivery_time_event: str,
    repository=Depends(get_emr_repository),
) -> EmrDeliveryResponseView:
    """Get a delivery by its unique occurrence ID (UUIDv7)."""
    delivery = repository.get_delivery(delivery_time_event)
    if delivery is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "delivery_not_found",
                "message": f"Delivery '{delivery_time_event}' not found",
            },
        )
    return EmrDeliveryResponseView.model_validate(delivery.model_dump())


@router.get("/stream/{delivery_id}", response_model=EmrDeliveryPageView)
async def get_deliveries_by_stream(
    delivery_id: str,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=100, ge=1, le=1000),
    repository=Depends(get_emr_repository),
) -> EmrDeliveryPageView:
    """List all deliveries for a delivery stream (deterministic DeliveryId)."""
    result = repository.get_deliveries_by_stream(delivery_id, page=page, limit=limit)
    return EmrDeliveryPageView.model_validate(result.model_dump())


@router.get("", response_model=EmrDeliveryPageView)
async def query_deliveries(
    producer_system: str | None = Query(default=None),
    data_object_logical_name: str | None = Query(default=None),
    delivery_type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=100, ge=1, le=1000),
    repository=Depends(get_emr_repository),
) -> EmrDeliveryPageView:
    """Query deliveries with optional filters."""
    result = repository.query_deliveries(
        producer_system=producer_system,
        data_object_logical_name=data_object_logical_name,
        delivery_type=delivery_type,
        status=status,
        page=page,
        limit=limit,
    )
    return EmrDeliveryPageView.model_validate(result.model_dump())


@router.post("/{delivery_time_event}/status", response_model=EmrDeliveryResponseView)
async def update_delivery_status(
    delivery_time_event: str,
    body: EmrDeliveryUpdateStatusRequestView,
    repository=Depends(get_emr_repository),
) -> EmrDeliveryResponseView:
    """Update the lifecycle status of a delivery."""
    result = repository.update_delivery_status(
        delivery_time_event,
        body.status,
        reason=body.reason,
    )
    if result is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "delivery_not_found",
                "message": f"Delivery '{delivery_time_event}' not found",
            },
        )
    return EmrDeliveryResponseView.model_validate(result.model_dump())


@router.post("/{delivery_time_event}/events", response_model=EmrDeliveryLifecycleEventResponseView)
async def record_lifecycle_event(
    delivery_time_event: str,
    body: EmrDeliveryLifecycleEventRequestView,
    repository=Depends(get_emr_repository),
) -> EmrDeliveryLifecycleEventResponseView:
    """Record a lifecycle event for a delivery."""
    from emr.domain.entities import EmrDeliveryLifecycleEventEntity

    event = EmrDeliveryLifecycleEventEntity.model_validate(body.model_dump(mode="python"))
    event.delivery_time_event = delivery_time_event
    result = repository.record_lifecycle_event(event)
    return EmrDeliveryLifecycleEventResponseView.model_validate(result.model_dump())


@router.get("/{delivery_time_event}/events", response_model=list[EmrDeliveryLifecycleEventResponseView])
async def get_lifecycle_events(
    delivery_time_event: str,
    repository=Depends(get_emr_repository),
) -> list[EmrDeliveryLifecycleEventResponseView]:
    """Get all lifecycle events for a delivery."""
    events = repository.get_lifecycle_events(delivery_time_event)
    return [
        EmrDeliveryLifecycleEventResponseView.model_validate(e.model_dump())
        for e in events
    ]


@router.post("/{delivery_time_event}/errors", response_model=EmrDeliveryErrorResponseView)
async def record_error(
    delivery_time_event: str,
    body: EmrDeliveryErrorRequestView,
    repository=Depends(get_emr_repository),
) -> EmrDeliveryErrorResponseView:
    """Record an error for a delivery."""
    from emr.domain.entities import EmrDeliveryErrorEntity

    error = EmrDeliveryErrorEntity.model_validate(body.model_dump(mode="python"))
    error.delivery_time_event = delivery_time_event
    result = repository.record_error(error)
    return EmrDeliveryErrorResponseView.model_validate(result.model_dump())


@router.get("/{delivery_time_event}/errors", response_model=list[EmrDeliveryErrorResponseView])
async def get_errors(
    delivery_time_event: str,
    repository=Depends(get_emr_repository),
) -> list[EmrDeliveryErrorResponseView]:
    """Get all errors for a delivery."""
    errors = repository.get_errors(delivery_time_event)
    return [
        EmrDeliveryErrorResponseView.model_validate(e.model_dump())
        for e in errors
    ]


@router.put("/{delivery_time_event}/metadata", response_model=EmrDeliveryMetadataResponseView)
async def upsert_metadata(
    delivery_time_event: str,
    body: EmrDeliveryMetadataRequestView,
    repository=Depends(get_emr_repository),
) -> EmrDeliveryMetadataResponseView:
    """Insert or update extended metadata for a delivery."""
    from emr.domain.entities import EmrDeliveryMetadataEntity

    metadata = EmrDeliveryMetadataEntity.model_validate(body.model_dump(mode="python"))
    metadata.delivery_time_event = delivery_time_event
    result = repository.upsert_metadata(metadata)
    return EmrDeliveryMetadataResponseView.model_validate(result.model_dump())


@router.get("/{delivery_time_event}/metadata", response_model=EmrDeliveryMetadataResponseView)
async def get_metadata(
    delivery_time_event: str,
    repository=Depends(get_emr_repository),
) -> EmrDeliveryMetadataResponseView:
    """Get extended metadata for a delivery."""
    metadata = repository.get_metadata(delivery_time_event)
    if metadata is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "metadata_not_found",
                "message": f"No metadata found for delivery '{delivery_time_event}'",
            },
        )
    return EmrDeliveryMetadataResponseView.model_validate(metadata.model_dump())
