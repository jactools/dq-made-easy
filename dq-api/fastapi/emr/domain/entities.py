"""EMR (Enterprise Metadata Repository) domain entities for the Canonical Delivery Registry.

These entities represent the canonical delivery model per the Solution Design:
Canonical Data Delivery Phase 1. EMR stores delivery metadata, lifecycle events,
errors, and extended metadata in a dedicated `emr` schema.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from app.domain.entities.base import EntityModel


class EmrDeliveryEntity(EntityModel):
    """Core delivery record in the Canonical Delivery Registry.

    The DeliveryId is a deterministic business key:
    {producerSystem}:{dataObjectLogicalName}:{version}:{jobId}

    The delivery_time_event is a UUIDv7 — the unique occurrence identifier.
    """

    delivery_id: str  # Deterministic business key
    delivery_time_event: str  # UUIDv7 — unique occurrence identifier
    delivery_version: int = 1  # Monotonically increasing business version
    delivery_type: str = "initial"  # initial, retry, correction, backfill, deletion, retention
    producer_system: str  # Producer system code (e.g., sap, crm, emr)
    data_object_logical_name: str  # Data Object logical name (e.g., orders, payments)
    data_object_version: int | None = None  # Data Object version
    job_id: str  # Pipeline job ID used to deliver the data
    layer: str | None = None  # Brown, gold, silver layer
    delivery_location: str | None = None  # Consumer-facing delivery location
    storage_location: str | None = None  # Internal storage location
    record_count: int = 0
    size_bytes: int = 0
    checksum: str | None = None
    checksum_algorithm: str | None = None
    delivered_at: str = ""  # Canonical delivery timestamp
    delivered_by: str | None = None  # Pipeline or agent identifier
    status: str = "registered"  # registered, ingested, validated, archived, superseded
    predecessor_time_event: str | None = None  # UUIDv7 of the delivery being corrected
    superseded_by_time_event: str | None = None  # UUIDv7 of the delivery that supersedes this one
    correction_reason: str | None = None
    metadata_json: dict[str, Any] | None = None
    created_at: str = ""
    updated_at: str = ""


class EmrDeliveryLifecycleEventEntity(EntityModel):
    """Timeline event for a delivery's lifecycle.

    Supports both instantaneous events (occurred_at) and elapsed events
    (started_at / completed_at) per the timeline design.
    """

    id: str
    delivery_time_event: str  # UUIDv7 of the delivery
    event_type: str  # registered, ingested, validated, archived, superseded, error
    event_kind: str = "instantaneous"  # instantaneous, elapsed
    occurred_at: str | None = None  # Instantaneous event timestamp
    started_at: str | None = None  # Elapsed event start timestamp
    completed_at: str | None = None  # Elapsed event end timestamp
    triggered_by: str | None = None  # Service or agent that triggered this event
    correlation_id: str | None = None
    metadata_json: dict[str, Any] | None = None
    created_at: str = ""


class EmrDeliveryErrorEntity(EntityModel):
    """Error record for a delivery.

    Multiple errors can be reported for a single delivery throughout its lifecycle.
    """

    id: str
    delivery_time_event: str  # UUIDv7 of the delivery
    error_code: str | None = None
    error_message: str | None = None
    severity: str = "warning"  # warning, error, critical
    reported_by: str | None = None  # Service or agent that reported this error
    occurred_at: str = ""
    metadata_json: dict[str, Any] | None = None
    created_at: str = ""


class EmrDeliveryMetadataEntity(EntityModel):
    """Extended metadata for a delivery.

    References the Data Delivery Note and stores additional classification
    and storage metadata.
    """

    delivery_time_event: str  # UUIDv7 of the delivery
    data_product_id: str | None = None  # ODCS Data Product identifier
    data_set_id: str | None = None  # Data Set identifier
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
    created_at: str = ""
    updated_at: str = ""


class EmrDeliveryPageEntity(EntityModel):
    """Paginated delivery list for query results."""

    items: list[EmrDeliveryEntity] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    limit: int = 100
