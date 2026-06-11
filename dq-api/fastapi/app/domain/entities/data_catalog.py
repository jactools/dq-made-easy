from __future__ import annotations

from pydantic import Field

from app.domain.entities.base import EntityModel


SUPPORTED_DELIVERY_FORMATS = frozenset({"parquet", "csv", "json", "avro", "delta", "iceberg"})


def delivery_format_warning(delivery_format: str | None) -> str | None:
    normalized = str(delivery_format or "").strip().lower()
    if not normalized or normalized in SUPPORTED_DELIVERY_FORMATS:
        return None
    return f"Unsupported file format: {normalized}. The delivery note records a format this runtime cannot seed."


def delivery_note_metadata_label(metadata_json: dict | None, key: str) -> str | None:
    if not isinstance(metadata_json, dict):
        return None
    normalized = str(metadata_json.get(key) or "").strip()
    return normalized or None


class DataProductEntity(EntityModel):
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


class DataSetEntity(EntityModel):
    id: str
    product_id: str = ""
    name: str = ""
    description: str = ""
    owner: str = ""
    created_at: str = ""
    workspace_id: str = ""
    business_key: str = ""
    tags: list[str] = Field(default_factory=list)


class DataObjectEntity(EntityModel):
    id: str
    name: str = ""
    description: str = ""
    status: str = "active"
    created_at: str = ""
    business_key: str = ""
    tags: list[str] = Field(default_factory=list)


class RuleAttributeEntity(EntityModel):
    ruleId: str = ""
    attributeId: str = ""
    threshold_override: float | None = None


class AddRuleAttributesResultEntity(EntityModel):
    added: int


class DataObjectCatalogEntity(EntityModel):
    id: str
    dataset_id: str = ""
    name: str = ""
    description: str = ""
    icon: str = ""
    created_at: str = ""
    latest_version_id: str | None = None
    business_key: str = ""
    tags: list[str] = Field(default_factory=list)


class DataObjectVersionEntity(EntityModel):
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


class AttributeCatalogEntity(EntityModel):
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
    definition_id: str | None = None
    definition_mapping_status: str = "unmapped"
    definition_mapping_attribute_id: str | None = None
    definition_mapping_version_id: str | None = None
    definition_mapping_mapped_by: str | None = None
    definition_mapping_created_at: str | None = None
    masking_method: str = "none"
    encryption_required: bool = False
    encryption_key_id: str | None = None
    protection_configured_by: str | None = None
    protection_updated_at: str | None = None
    tags: list[str] = Field(default_factory=list)


class AttributeDefinitionMappingEntity(EntityModel):
    id: str
    attribute_id: str = ""
    definition_id: str | None = None
    mapping_state: str = "mapped"
    mapped_by: str | None = None
    created_at: str = ""
    updated_at: str = ""


class AttributeDefinitionMappingUpsertResultEntity(EntityModel):
    attribute_id: str
    definition_id: str | None = None
    mapping_state: str = "mapped"
    definition_mapping_status: str = "explicit"
    version_id: str = ""
    mapped_by: str | None = None
    created_at: str = ""
    updated_at: str = ""


class DataDeliveryEntity(EntityModel):
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


class DataDeliveryNoteEntity(EntityModel):
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
    ingestor_name: str | None = None
    ingestor_run_id: str | None = None
    source_system: str | None = None
    source_snapshot_id: str | None = None
    checksum: str | None = None
    checksum_algorithm: str | None = None
    metadata_json: dict | None = None


class DomainEntity(EntityModel):
    id: str
    name: str = ""
    description: str = ""
    owner: str = ""
    workspace_id: str = ""
    business_key: str = ""
    tags: list[str] = Field(default_factory=list)
