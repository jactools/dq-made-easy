from typing import Any

from pydantic import ConfigDict, Field, model_validator

from dq_domain_validation import DataDeliveryExecutionMode
from dq_domain_validation import DataDeliveryExecutionRequestStatus
from dq_domain_validation import DataDeliveryExecutionSelectorType
from dq_domain_validation import GxRunPlanPlanningMode
from app.api.v1.schemas.common_view import PaginationView
from app.schemas.pydantic_base import SnakeModel, to_snake_alias


class DataProductView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    id: str
    name: str = ""
    description: str = ""
    owner: str = ""
    created_at: str = ""
    icon: str = ""
    workspace_id: str = ""
    odcs_data_product_id: str | None = None
    business_key: str = ""
    tags: list[str] = Field(default_factory=list)


class DataProductsPageView(SnakeModel):
    data: list[DataProductView]
    pagination: PaginationView


class DataSetView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    id: str
    product_id: str = ""
    name: str = ""
    description: str = ""
    owner: str = ""
    created_at: str = ""
    workspace_id: str = ""
    business_key: str = ""
    data_contract_download_url: str = ""
    tags: list[str] = Field(default_factory=list)


class DataSetsPageView(SnakeModel):
    data: list[DataSetView]
    pagination: PaginationView


class DataObjectView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    id: str
    name: str = ""
    description: str = ""
    status: str = "active"
    created_at: str = ""
    business_key: str = ""
    tags: list[str] = Field(default_factory=list)


class RuleAttributeView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    ruleId: str = ""
    attributeId: str = ""
    threshold_override: float | None = None


class AddRuleAttributesResultView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    added: int


class AttributeDefinitionMappingView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    id: str
    attribute_id: str
    definition_id: str | None = None
    mapping_state: str = "mapped"
    mapped_by: str | None = None
    created_at: str = ""
    updated_at: str = ""


class AttributeDefinitionMappingUpsertRequestView(SnakeModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=to_snake_alias)

    attribute_id: str
    definition_id: str | None = None
    mapping_state: str = "mapped"
    mapped_by: str | None = None


class AttributeDefinitionMappingUpsertResultView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    attribute_id: str
    definition_id: str | None = None
    mapping_state: str = "mapped"
    definition_mapping_status: str = "explicit"
    version_id: str = ""
    mapped_by: str | None = None
    created_at: str = ""
    updated_at: str = ""


class DataObjectCatalogView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    id: str
    dataset_id: str = ""
    name: str = ""
    description: str = ""
    icon: str = ""
    created_at: str = ""
    latest_version_id: str | None = None
    business_key: str = ""
    tags: list[str] = Field(default_factory=list)


class DataObjectCatalogPageView(SnakeModel):
    data: list[DataObjectCatalogView]
    pagination: PaginationView


class DataObjectVersionView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    id: str
    data_object_id: str = ""
    version: int = 0
    created_at: str = ""
    schema_hash: str = ""
    attribute_count: int = 0
    storage_uri: str | None = None
    storage_format: str | None = None
    storage_options_json: dict | None = None
    tags: list[str] = Field(default_factory=list)


class DataObjectVersionsPageView(SnakeModel):
    data: list[DataObjectVersionView]
    pagination: PaginationView


class AttributeCatalogView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    id: str
    name: str = ""
    type: str = ""
    nullable: bool = True
    format: str = ""
    is_cde: bool = False
    is_primary_key: bool = False
    is_business_key: bool = False
    data_object_id: str = ""
    version_id: str = ""
    workspace_id: str = ""
    source_kind: str = "data_object"
    source_name: str = ""
    source_version_label: str = ""
    masking_method: str = "none"
    encryption_required: bool = False
    encryption_key_id: str | None = None
    protection_configured_by: str | None = None
    protection_updated_at: str | None = None
    definition_id: str | None = None
    definition_mapping_status: str = "unmapped"
    definition_mapping_attribute_id: str | None = None
    definition_mapping_version_id: str | None = None
    definition_mapping_mapped_by: str | None = None
    definition_mapping_created_at: str | None = None
    tags: list[str] = Field(default_factory=list)


class AttributeCatalogPageView(SnakeModel):
    data: list[AttributeCatalogView]
    pagination: PaginationView


class DataDeliveryView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    id: str
    data_object_id: str = ""
    data_object_version_id: str | None = None
    version: int = 0
    delivered_at: str = ""
    timestamp: str = ""
    layer: str = "standardized"
    delivery_location: str | None = None
    record_count: int = 0
    size_bytes: int = 0
    status: str = ""
    attributes_count: int = 0


class DataDeliveriesPageView(SnakeModel):
    data: list[DataDeliveryView]
    pagination: PaginationView


class DataDeliveryInventoryView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    id: str
    data_object_version_id: str | None = None
    version: int = 0
    delivered_at: str = ""
    layer: str = "standardized"
    delivery_location: str | None = None
    storage_exists: bool = False
    storage_object_count: int = 0


class DataDeliveryInventoryPageView(SnakeModel):
    data: list[DataDeliveryInventoryView]
    pagination: PaginationView


class DataDeliveryNoteView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    id: str
    data_delivery_id: str = ""
    data_object_id: str = ""
    data_object_version_id: str | None = None
    version: int = 0
    delivered_at: str = ""
    timestamp: str = ""
    layer: str = "standardized"
    storage_location: str | None = None
    delivery_location: str | None = None
    object_storage_classification: str | None = None
    evidence_classification: str | None = None
    delivery_status: str = ""
    delivery_format: str | None = None
    delivery_format_warning: str | None = None
    record_count: int = 0
    size_bytes: int = 0
    attributes_count: int = 0
    file_count: int | None = None
    file_names: list[str] | None = None
    storage_exists: bool | None = None
    storage_object_count: int | None = None
    execution_summary: "DataDeliveryExecutionSummaryView | None" = None
    execution_references: list["DataDeliveryExecutionReferenceView"] = Field(default_factory=list)
    ingestor_name: str | None = None
    ingestor_run_id: str | None = None
    source_system: str | None = None
    source_snapshot_id: str | None = None
    checksum: str | None = None
    checksum_algorithm: str | None = None
    metadata_json: dict[str, Any] | None = None


class DataDeliveryExecutionReferenceView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    execution_run_id: str
    execution_status: str
    correlation_id: str
    requested_by: str | None = None
    suite_id: str | None = None
    suite_version: int | None = None
    rule_id: str | None = None
    rule_version_id: str | None = None
    engine_target: str | None = None
    execution_shape: str | None = None
    submitted_at: str
    started_at: str | None = None
    completed_at: str | None = None


class DataDeliveryExecutionSummaryView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    total_execution_runs: int = 0
    status_counts: dict[str, int] = Field(default_factory=dict)
    latest_execution_run_id: str | None = None
    latest_execution_status: str | None = None
    latest_execution_submitted_at: str | None = None
    latest_execution_completed_at: str | None = None


class DataDeliveryExecutionSelectorView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    selector_type: DataDeliveryExecutionSelectorType
    gx_suite_id: str | None = None
    suite_version: int | None = Field(default=None, ge=1)
    run_plan_id: str | None = None
    run_plan_version_id: str | None = None

    @model_validator(mode="after")
    def validate_selector(self) -> "DataDeliveryExecutionSelectorView":
        if self.selector_type == "gx_suite":
            if not str(self.gx_suite_id or "").strip():
                raise ValueError("gx_suite_id is required when selector_type is gx_suite")
            if str(self.run_plan_id or "").strip() or str(self.run_plan_version_id or "").strip():
                raise ValueError("run_plan_id and run_plan_version_id are not allowed when selector_type is gx_suite")
            return self

        if not str(self.run_plan_id or "").strip():
            raise ValueError("run_plan_id is required when selector_type is run_plan")
        if str(self.gx_suite_id or "").strip() or self.suite_version is not None:
            raise ValueError("gx_suite_id and suite_version are not allowed when selector_type is run_plan")
        return self


class DataDeliveryExecutionRequestView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    execution_selector: DataDeliveryExecutionSelectorView | None = None


class DataDeliveryExecutionSuiteCandidateView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    suite_id: str
    suite_version: int
    engine_type: str | None = None
    status: str
    assignment_scope: dict[str, Any]
    resolved_execution_scope: dict[str, Any]
    execution_hints: dict[str, Any]


class DataDeliveryExecutionRunPlanVersionCandidateView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    run_plan_version_id: str
    governance_state: str
    engine_type: str | None = None
    suite_id: str | None = None
    suite_version: int | None = None


class DataDeliveryExecutionRunPlanCandidateView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    run_plan_id: str
    workspace_id: str
    planning_mode: GxRunPlanPlanningMode
    status: str
    scope_selector: dict[str, Any]
    current_active_version_id: str
    active_version: DataDeliveryExecutionRunPlanVersionCandidateView


class DataDeliveryExecutionResolutionView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    applicable_gx_suites: list[DataDeliveryExecutionSuiteCandidateView] = Field(default_factory=list)
    applicable_run_plans: list[DataDeliveryExecutionRunPlanCandidateView] = Field(default_factory=list)
    grouped_execution_plan: dict[str, Any] = Field(default_factory=dict)


class DataDeliveryExecutionReceiptView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    data_delivery_id: str
    resolved_data_object_version_id: str
    resolved_delivery_location: str
    execution_request_status: DataDeliveryExecutionRequestStatus = "accepted"
    delivery_note: DataDeliveryNoteView
    execution_resolution: DataDeliveryExecutionResolutionView
    execution_selector: DataDeliveryExecutionSelectorView | None = None
    execution_mode: DataDeliveryExecutionMode | None = None
    execution_run_id: str | None = None
    execution_dispatch: dict[str, Any] | None = None
    resolved_engine_type: str | None = None
    resolved_gx_suite_id: str | None = None
    resolved_gx_suite_version: int | None = None
    resolved_run_plan_id: str | None = None
    resolved_run_plan_version_id: str | None = None
