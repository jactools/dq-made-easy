"""EMR (Enterprise Metadata Repository) domain entities for the Canonical Delivery Registry.

These entities represent the canonical delivery model per the Solution Design:
Canonical Data Delivery Phase 1. EMR stores delivery metadata, lifecycle events,
errors, and extended metadata in a dedicated `emr` schema.

EMR entities are self-contained and do not import from the DQ API (app.*).
They use types from emr-delivery-sdk for delivery_type, status, and delivery_id.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from emr_delivery_sdk.delivery_status import DeliveryStatus
from emr_delivery_sdk.delivery_type import DeliveryType


class EmrDeliveryEntity(BaseModel):
    """Core delivery record in the Canonical Delivery Registry.

    The delivery_id is a deterministic business key:
    {producer_system}:{data_object_logical_name}:{version}:{job_id}

    The delivery_time_event is a UUIDv7 — the unique occurrence identifier.
    """

    delivery_id: str  # Deterministic business key
    delivery_time_event: str  # UUIDv7 — unique occurrence identifier
    delivery_version: int = 1  # Monotonically increasing business version
    delivery_type: DeliveryType = DeliveryType.INITIAL
    producer_system: str
    data_object_logical_name: str
    data_object_version: int | None = None
    job_id: str
    layer: str | None = None
    delivery_location: str | None = None
    storage_location: str | None = None
    record_count: int = 0
    size_bytes: int = 0
    checksum: str | None = None
    checksum_algorithm: str | None = None
    delivered_at: str = ""
    delivered_by: str | None = None
    status: DeliveryStatus = DeliveryStatus.REGISTERED
    predecessor_time_event: str | None = None
    superseded_by_time_event: str | None = None
    correction_reason: str | None = None
    metadata_json: dict[str, Any] | None = None
    created_at: str = ""
    updated_at: str = ""


class EmrDeliveryLifecycleEventEntity(BaseModel):
    """Timeline event for a delivery's lifecycle.

    Supports both instantaneous events (occurred_at) and elapsed events
    (started_at / completed_at) per the timeline design.
    """

    id: str
    delivery_time_event: str
    event_type: str
    event_kind: str = "instantaneous"
    occurred_at: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    triggered_by: str | None = None
    correlation_id: str | None = None
    metadata_json: dict[str, Any] | None = None
    created_at: str = ""


class EmrDeliveryErrorEntity(BaseModel):
    """Error record for a delivery.

    Multiple errors can be reported for a single delivery throughout its lifecycle.
    """

    id: str
    delivery_time_event: str
    error_code: str | None = None
    error_message: str | None = None
    severity: str = "warning"
    reported_by: str | None = None
    occurred_at: str = ""
    metadata_json: dict[str, Any] | None = None
    created_at: str = ""


class EmrDeliveryMetadataEntity(BaseModel):
    """Extended metadata for a delivery.

    References the Data Delivery Note and stores additional classification
    and storage metadata.
    """

    delivery_time_event: str
    data_product_id: str | None = None
    data_set_id: str | None = None
    workspace_id: str | None = None
    source_system: str | None = None
    source_snapshot_id: str | None = None
    object_storage_classification: str | None = None
    evidence_classification: str | None = None
    delivery_format: str | None = None
    file_count: int | None = None
    file_names: list[str] | None = None
    ingestor_name: str | None = None
    ingestor_run_id: str | None = None
    checksum: str | None = None
    checksum_algorithm: str | None = None
    ddn_reference: str | None = None
    metadata_json: dict[str, Any] | None = None
    created_at: str = ""
    updated_at: str = ""


class EmrDeliveryPageEntity(BaseModel):
    """Paginated delivery list for query results."""

    items: list[EmrDeliveryEntity] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    limit: int = 100
