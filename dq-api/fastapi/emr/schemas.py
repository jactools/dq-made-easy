"""Schema models for EMR (Enterprise Metadata Repository) API endpoints.

These models support the Canonical Delivery Registry endpoints that expose
delivery metadata, lifecycle events, errors, and extended metadata.
"""

from __future__ import annotations

from typing import Any

from pydantic import ConfigDict, Field

from app.schemas.pydantic_base import SnakeModel, to_snake_alias


class EmrDeliveryCreateRequestView(SnakeModel):
    """Request to register a new delivery."""

    delivery_id: str  # Deterministic business key
    delivery_time_event: str | None = None  # UUIDv7 (optional — generated if not provided)
    delivery_version: int = 1
    delivery_type: str = "initial"  # initial, retry, correction, backfill, deletion, retention
    producer_system: str  # Producer system code (e.g., sap, crm, emr)
    data_object_logical_name: str  # Data Object logical name (e.g., orders, payments)
    data_object_version: int | None = None
    job_id: str  # Pipeline job ID used to deliver the data
    layer: str | None = None  # Brown, gold, silver layer
    delivery_location: str | None = None
    storage_location: str | None = None
    record_count: int = 0
    size_bytes: int = 0
    checksum: str | None = None
    checksum_algorithm: str | None = None
    delivered_at: str | None = None
    delivered_by: str | None = None
    predecessor_time_event: str | None = None
    correction_reason: str | None = None
    metadata_json: dict[str, Any] | None = None


class EmrDeliveryResponseView(SnakeModel):
    """Response for a delivery record."""

    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    delivery_id: str
    delivery_time_event: str
    delivery_version: int = 1
    delivery_type: str = "initial"
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
    status: str = "registered"
    predecessor_time_event: str | None = None
    superseded_by_time_event: str | None = None
    correction_reason: str | None = None
    metadata_json: dict[str, Any] | None = None
    created_at: str = ""
    updated_at: str = ""


class EmrDeliveryPageView(SnakeModel):
    """Paginated delivery list."""

    items: list[EmrDeliveryResponseView] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    limit: int = 100


class EmrDeliveryUpdateStatusRequestView(SnakeModel):
    """Request to update delivery status."""

    status: str  # registered, ingested, validated, archived, superseded
    reason: str | None = None


class EmrDeliveryLifecycleEventRequestView(SnakeModel):
    """Request to record a lifecycle event."""

    event_type: str  # registered, ingested, validated, archived, superseded, error
    event_kind: str = "instantaneous"  # instantaneous, elapsed
    occurred_at: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    triggered_by: str | None = None
    correlation_id: str | None = None
    metadata_json: dict[str, Any] | None = None


class EmrDeliveryLifecycleEventResponseView(SnakeModel):
    """Response for a lifecycle event."""

    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

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


class EmrDeliveryErrorRequestView(SnakeModel):
    """Request to record a delivery error."""

    error_code: str | None = None
    error_message: str | None = None
    severity: str = "warning"  # warning, error, critical
    reported_by: str | None = None
    occurred_at: str | None = None
    metadata_json: dict[str, Any] | None = None


class EmrDeliveryErrorResponseView(SnakeModel):
    """Response for a delivery error."""

    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    id: str
    delivery_time_event: str
    error_code: str | None = None
    error_message: str | None = None
    severity: str = "warning"
    reported_by: str | None = None
    occurred_at: str = ""
    metadata_json: dict[str, Any] | None = None
    created_at: str = ""


class EmrDeliveryMetadataRequestView(SnakeModel):
    """Request to insert or update extended metadata."""

    data_product_id: str | None = None  # ODCS Data Product identifier
    data_set_id: str | None = None
    workspace_id: str | None = None
    source_system: str | None = None
    source_snapshot_id: str | None = None
    object_storage_classification: str | None = None  # synthetic, real
    evidence_classification: str | None = None  # test, evidence
    delivery_format: str | None = None
    file_count: int | None = None
    file_names: list[str] | None = None
    ingestor_name: str | None = None
    ingestor_run_id: str | None = None
    checksum: str | None = None
    checksum_algorithm: str | None = None
    ddn_reference: str | None = None  # Reference to the Data Delivery Note ID
    metadata_json: dict[str, Any] | None = None


class EmrDeliveryMetadataResponseView(SnakeModel):
    """Response for extended delivery metadata."""

    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

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
