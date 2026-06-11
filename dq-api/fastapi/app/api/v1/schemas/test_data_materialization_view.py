from typing import Any

from dq_domain_validation import TestingOutputFormat
from pydantic import ConfigDict, Field

from app.api.v1.schemas.data_catalog_view import DataDeliveryNoteView
from app.schemas.pydantic_base import SnakeModel, to_snake_alias


class TestDataMaterializationRequestView(SnakeModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid", alias_generator=to_snake_alias)

    request_id: str
    job_id: str
    request_contract: str | None = None
    status: str
    data_object_version_id: str
    target_data_object_version_ids: list[str] | None = None
    sample_count: int
    output_format: str
    output_uri: str
    requested_at: str
    started_at: str | None = None
    completed_at: str | None = None
    error_message: str | None = None
    correlation_id: str
    queue_key: str
    processing_queue_key: str
    events_url: str | None = None
    selection: dict[str, Any] | None = None
    result: dict[str, Any] | None = None


class ReportTestDataMaterializationCompletionRequest(SnakeModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid", alias_generator=to_snake_alias)

    row_count: int = Field(ge=0)
    output_uri: str
    output_format: TestingOutputFormat


class TestDataMaterializationCompletionView(SnakeModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid", alias_generator=to_snake_alias)

    data_delivery_id: str
    delivery_note: DataDeliveryNoteView


class MaterializationTargetResultRequest(SnakeModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid", alias_generator=to_snake_alias)

    data_object_version_id: str
    row_count: int = Field(ge=0)
    output_uri: str
    output_format: TestingOutputFormat


class MaterializationDeliveryView(SnakeModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid", alias_generator=to_snake_alias)

    data_object_version_id: str
    row_count: int
    output_uri: str
    output_format: str
    data_delivery_id: str
    delivery_note: DataDeliveryNoteView


class MaterializationCompletionBatchView(SnakeModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid", alias_generator=to_snake_alias)

    request_id: str
    data_deliveries: list[MaterializationDeliveryView]
    delivery_summary: dict[str, Any] | None = None
    data_delivery_id: str | None = None
    delivery_note: DataDeliveryNoteView | None = None