"""Schema models for EMR (Enterprise Metadata Repository) API endpoints.

These models support the Canonical Delivery Registry endpoints that expose
delivery metadata, lifecycle events, errors, and extended metadata.

EMR schemas are self-contained and do not import from the DQ API (app.*).
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def _to_snake(s: str) -> str:
    """Convert CamelCase/camelCase to snake_case for use as Pydantic alias generator."""
    s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", s)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1).lower()


class EmrBaseModel(BaseModel):
    """Base model for EMR schemas — emits snake_case aliases."""

    model_config = ConfigDict(
        alias_generator=_to_snake,
        populate_by_name=True,
        from_attributes=True,
    )


class EmrDeliveryCreateRequestView(EmrBaseModel):
    """Request to register a new delivery."""

    delivery_id: str  # Deterministic business key
    delivery_time_event: str | None = None  # UUIDv7 (optional — generated if not provided)
    delivery_version: int = 1
    delivery_type: str = "initial"  # initial, retry, correction, backfill, deletion, retention
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
    delivered_at: str | None = None
    delivered_by: str | None = None
    predecessor_time_event: str | None = None
    correction_reason: str | None = None
    metadata_json: dict[str, Any] | None = None


class EmrDeliveryResponseView(EmrBaseModel):
    """Response for a delivery record."""

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


class EmrDeliveryPageView(EmrBaseModel):
    """Paginated delivery list."""

    items: list[EmrDeliveryResponseView] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    limit: int = 100


class EmrDeliveryUpdateStatusRequestView(EmrBaseModel):
    """Request to update delivery status."""

    status: str
    reason: str | None = None


class EmrDeliveryLifecycleEventRequestView(EmrBaseModel):
    """Request to record a lifecycle event."""

    event_type: str
    event_kind: str = "instantaneous"
    occurred_at: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    triggered_by: str | None = None
    correlation_id: str | None = None
    metadata_json: dict[str, Any] | None = None


class EmrDeliveryLifecycleEventResponseView(EmrBaseModel):
    """Response for a lifecycle event."""

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


class EmrDeliveryErrorRequestView(EmrBaseModel):
    """Request to record a delivery error."""

    error_code: str | None = None
    error_message: str | None = None
    severity: str = "warning"
    reported_by: str | None = None
    occurred_at: str | None = None
    metadata_json: dict[str, Any] | None = None


class EmrDeliveryErrorResponseView(EmrBaseModel):
    """Response for a delivery error."""

    id: str
    delivery_time_event: str
    error_code: str | None = None
    error_message: str | None = None
    severity: str = "warning"
    reported_by: str | None = None
    occurred_at: str = ""
    metadata_json: dict[str, Any] | None = None
    created_at: str = ""


class EmrDeliveryMetadataRequestView(EmrBaseModel):
    """Request to insert or update extended metadata."""

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


class EmrDeliveryMetadataResponseView(EmrBaseModel):
    """Response for extended delivery metadata."""

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


class EmrDqResultResponseView(EmrBaseModel):
    """Response for a DQ result linked to a delivery."""

    delivery_id: str
    delivery_time_event: str | None = None
    execution_run_id: str
    rule_id: str
    rule_name: str | None = None
    status: str
    result: str | None = None
    passed: bool | None = None
    score: float | None = None
    score_label: str | None = None
    total_count: int | None = None
    valid_count: int | None = None
    invalid_count: int | None = None
    warning_count: int | None = None
    error_count: int | None = None
    observed_at: str | None = None
    duration_ms: int | None = None
    message: str | None = None
    data_product_id: str | None = None
    data_set_id: str | None = None
    workspace_id: str | None = None
    id: str = ""
    created_at: str = ""


class EmrDqResultPageView(EmrBaseModel):
    """Paginated DQ result list."""

    items: list[EmrDqResultResponseView] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    limit: int = 100
