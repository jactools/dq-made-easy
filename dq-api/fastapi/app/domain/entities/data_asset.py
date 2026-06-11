from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import ConfigDict
from pydantic import Field

from app.domain.entities.base import EntityModel


class DataAssetSourceBindingEntity(EntityModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    source_data_object_version_id: str
    source_field_id: str
    source_field_name: str = ""
    source_field_type: str = ""
    nullable: bool = True


class DataAssetFilterEntity(EntityModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    expression: str
    enabled: bool = True
    description: str | None = None


class DataAssetDerivedFieldEntity(EntityModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    name: str
    expression: str
    data_type: str | None = None
    nullable: bool | None = None
    source_field_ids: list[str] = Field(default_factory=list)


class DataAssetUploadPreviewColumnEntity(EntityModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    name: str
    data_type: str
    nullable: bool = True


class DataAssetUploadPreviewEntity(EntityModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    file_name: str | None = None
    file_format: str | None = None
    source_uri: str | None = None
    columns: list[DataAssetUploadPreviewColumnEntity] = Field(default_factory=list)


class DataAssetVersionEntity(EntityModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: str
    data_asset_id: str = ""
    version: int = 1
    created_at: str = ""
    source_bindings: list[DataAssetSourceBindingEntity] = Field(default_factory=list)
    filters: list[DataAssetFilterEntity] = Field(default_factory=list)
    derived_fields: list[DataAssetDerivedFieldEntity] = Field(default_factory=list)
    upload_preview: DataAssetUploadPreviewEntity | None = None


class DataAssetContractVersionEntity(EntityModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: str
    data_asset_id: str = ""
    version: int = 1
    contract_yaml: str = ""
    contract_hash: str = ""
    generated_at: str = ""
    generated_by: str | None = None
    generated_where: str | None = None
    generated_what: str | None = None
    source_data_asset_version_id: str | None = None
    review_status: str = "pending"
    reviewed_by: str | None = None
    reviewed_at: str | None = None
    review_comments: str | None = None

class DataAssetLineageSnapshotEntity(EntityModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: str
    data_asset_id: str = ""
    captured_at: str = ""
    captured_by: str | None = None
    snapshot_kind: str = "lineage"
    lineage_json: dict[str, Any] = Field(default_factory=dict)
    business_context_overlay: dict[str, Any] | None = None
    classification_view: dict[str, Any] | None = None
    anomaly_annotations: list[dict[str, Any]] = Field(default_factory=list)


class DataAssetBusinessContextEntity(EntityModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    dataset_id: str = ""
    data_product_id: str = ""
    domain: str = ""
    owner: str = ""
    purpose: str = ""
    steward: str = ""
    criticality: str = ""
    tags: list[str] = Field(default_factory=list)
    business_definitions: list[str] = Field(default_factory=list)
    lineage_references: list[str] = Field(default_factory=list)
    validation_suites: list[str] = Field(default_factory=list)
    validation_plans: list[str] = Field(default_factory=list)
    consumers: list[str] = Field(default_factory=list)


class DataAssetEntity(EntityModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: str
    name: str = ""
    description: str = ""
    workspace_id: str = ""
    status: str = "draft"
    created_at: str = ""
    current_version_id: str | None = None
    source_object_version_ids: list[str] = Field(default_factory=list)
    business_context: DataAssetBusinessContextEntity | None = None


def _clean_str(value: Any) -> str:
    return str(value).strip()


def _clean_optional_str(value: Any) -> str | None:
    normalized = _clean_str(value)
    return normalized or None


def _clean_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []

    cleaned_values = [_clean_str(item) for item in value if _clean_str(item)]
    return list(dict.fromkeys(cleaned_values))


def build_data_asset_source_binding_entity(
    payload: Mapping[str, Any] | DataAssetSourceBindingEntity | None,
) -> DataAssetSourceBindingEntity | None:
    if isinstance(payload, DataAssetSourceBindingEntity):
        return payload
    if not isinstance(payload, Mapping):
        return None

    source_data_object_version_id = _clean_optional_str(payload.get("source_data_object_version_id"))
    source_field_id = _clean_optional_str(payload.get("source_field_id"))
    if not source_data_object_version_id or not source_field_id:
        return None

    return DataAssetSourceBindingEntity(
        source_data_object_version_id=source_data_object_version_id,
        source_field_id=source_field_id,
        source_field_name=_clean_str(payload.get("source_field_name")) if payload.get("source_field_name") is not None else "",
        source_field_type=_clean_str(payload.get("source_field_type")) if payload.get("source_field_type") is not None else "",
        nullable=bool(payload.get("nullable", True)),
    )


def build_data_asset_filter_entity(
    payload: Mapping[str, Any] | DataAssetFilterEntity | None,
) -> DataAssetFilterEntity | None:
    if isinstance(payload, DataAssetFilterEntity):
        return payload
    if not isinstance(payload, Mapping):
        return None

    expression = _clean_optional_str(payload.get("expression"))
    if not expression:
        return None

    return DataAssetFilterEntity(
        expression=expression,
        enabled=bool(payload.get("enabled", True)),
        description=_clean_optional_str(payload.get("description")),
    )


def build_data_asset_derived_field_entity(
    payload: Mapping[str, Any] | DataAssetDerivedFieldEntity | None,
) -> DataAssetDerivedFieldEntity | None:
    if isinstance(payload, DataAssetDerivedFieldEntity):
        return payload
    if not isinstance(payload, Mapping):
        return None

    name = _clean_optional_str(payload.get("name"))
    expression = _clean_optional_str(payload.get("expression"))
    if not name or not expression:
        return None

    return DataAssetDerivedFieldEntity(
        name=name,
        expression=expression,
        data_type=_clean_optional_str(payload.get("data_type")),
        nullable=(bool(payload.get("nullable")) if payload.get("nullable") is not None else None),
        source_field_ids=[_clean_str(item) for item in (payload.get("source_field_ids") if isinstance(payload.get("source_field_ids"), list) else []) if _clean_str(item)],
    )


def build_data_asset_upload_preview_column_entity(
    payload: Mapping[str, Any] | DataAssetUploadPreviewColumnEntity | None,
) -> DataAssetUploadPreviewColumnEntity | None:
    if isinstance(payload, DataAssetUploadPreviewColumnEntity):
        return payload
    if not isinstance(payload, Mapping):
        return None

    name = _clean_optional_str(payload.get("name"))
    data_type = _clean_optional_str(payload.get("data_type"))
    if not name or not data_type:
        return None

    return DataAssetUploadPreviewColumnEntity(
        name=name,
        data_type=data_type,
        nullable=bool(payload.get("nullable", True)),
    )


def build_data_asset_upload_preview_entity(
    payload: Mapping[str, Any] | DataAssetUploadPreviewEntity | None,
) -> DataAssetUploadPreviewEntity | None:
    if isinstance(payload, DataAssetUploadPreviewEntity):
        return payload
    if not isinstance(payload, Mapping):
        return None

    columns = [
        column
        for column in (
            build_data_asset_upload_preview_column_entity(item)
            for item in (payload.get("columns") if isinstance(payload.get("columns"), list) else [])
        )
        if column is not None
    ]

    return DataAssetUploadPreviewEntity(
        file_name=_clean_optional_str(payload.get("file_name")),
        file_format=_clean_optional_str(payload.get("file_format")),
        source_uri=_clean_optional_str(payload.get("source_uri")),
        columns=columns,
    )


def build_data_asset_version_entity(
    payload: Mapping[str, Any] | DataAssetVersionEntity | None,
) -> DataAssetVersionEntity | None:
    if isinstance(payload, DataAssetVersionEntity):
        return payload
    if not isinstance(payload, Mapping):
        return None

    version_id = _clean_optional_str(payload.get("id"))
    data_asset_id = _clean_optional_str(payload.get("data_asset_id"))
    if not version_id or not data_asset_id:
        return None

    source_bindings = [
        binding
        for binding in (
            build_data_asset_source_binding_entity(item)
            for item in (payload.get("source_bindings") if isinstance(payload.get("source_bindings"), list) else [])
        )
        if binding is not None
    ]
    filters = [
        filter_entity
        for filter_entity in (
            build_data_asset_filter_entity(item)
            for item in (payload.get("filters") if isinstance(payload.get("filters"), list) else [])
        )
        if filter_entity is not None
    ]
    derived_fields = [
        derived_field
        for derived_field in (
            build_data_asset_derived_field_entity(item)
            for item in (payload.get("derived_fields") if isinstance(payload.get("derived_fields"), list) else [])
        )
        if derived_field is not None
    ]

    upload_preview = build_data_asset_upload_preview_entity(payload.get("upload_preview"))
    version_raw = payload.get("version")
    try:
        version = int(version_raw) if version_raw not in (None, "") else 1
    except (TypeError, ValueError):
        version = 1

    return DataAssetVersionEntity(
        id=version_id,
        data_asset_id=data_asset_id,
        version=version,
        created_at=_clean_str(payload.get("created_at")) if payload.get("created_at") is not None else "",
        source_bindings=source_bindings,
        filters=filters,
        derived_fields=derived_fields,
        upload_preview=upload_preview,
    )


def build_data_asset_contract_version_entity(
    payload: Mapping[str, Any] | DataAssetContractVersionEntity | None,
) -> DataAssetContractVersionEntity | None:
    if isinstance(payload, DataAssetContractVersionEntity):
        return payload
    if not isinstance(payload, Mapping):
        return None

    contract_id = _clean_optional_str(payload.get("id"))
    data_asset_id = _clean_optional_str(payload.get("data_asset_id"))
    if not contract_id or not data_asset_id:
        return None

    version_raw = payload.get("version")
    try:
        version = int(version_raw) if version_raw not in (None, "") else 1
    except (TypeError, ValueError):
        version = 1

    return DataAssetContractVersionEntity(
        id=contract_id,
        data_asset_id=data_asset_id,
        version=version,
        contract_yaml=_clean_str(payload.get("contract_yaml")) if payload.get("contract_yaml") is not None else "",
        contract_hash=_clean_str(payload.get("contract_hash")) if payload.get("contract_hash") is not None else "",
        generated_at=_clean_str(payload.get("generated_at")) if payload.get("generated_at") is not None else "",
        generated_by=_clean_optional_str(payload.get("generated_by")),
        generated_where=_clean_optional_str(payload.get("generated_where")),
        generated_what=_clean_optional_str(payload.get("generated_what")),
        source_data_asset_version_id=_clean_optional_str(payload.get("source_data_asset_version_id")),
        review_status=_clean_str(payload.get("review_status")) if payload.get("review_status") is not None else "pending",
        reviewed_by=_clean_optional_str(payload.get("reviewed_by")),
        reviewed_at=_clean_optional_str(payload.get("reviewed_at")),
        review_comments=_clean_optional_str(payload.get("review_comments")),
    )


def build_data_asset_business_context_entity(
    payload: Mapping[str, Any] | DataAssetBusinessContextEntity | None,
) -> DataAssetBusinessContextEntity | None:
    if isinstance(payload, DataAssetBusinessContextEntity):
        return payload
    if not isinstance(payload, Mapping):
        return None

    dataset_id = _clean_optional_str(payload.get("dataset_id"))
    data_product_id = _clean_optional_str(payload.get("data_product_id"))
    domain = _clean_optional_str(payload.get("domain"))
    owner = _clean_optional_str(payload.get("owner"))
    purpose = _clean_optional_str(payload.get("purpose"))
    steward = _clean_optional_str(payload.get("steward"))
    criticality = _clean_optional_str(payload.get("criticality"))
    tags = _clean_str_list(payload.get("tags"))
    business_definitions = _clean_str_list(payload.get("business_definitions"))
    lineage_references = _clean_str_list(payload.get("lineage_references"))
    validation_suites = _clean_str_list(payload.get("validation_suites"))
    validation_plans = _clean_str_list(payload.get("validation_plans"))
    consumers = _clean_str_list(payload.get("consumers"))

    if not any([
        dataset_id,
        data_product_id,
        domain,
        owner,
        purpose,
        steward,
        criticality,
        tags,
        business_definitions,
        lineage_references,
        validation_suites,
        validation_plans,
        consumers,
    ]):
        return None

    return DataAssetBusinessContextEntity(
        dataset_id=dataset_id or "",
        data_product_id=data_product_id or "",
        domain=domain or "",
        owner=owner or "",
        purpose=purpose or "",
        steward=steward or "",
        criticality=criticality or "",
        tags=tags,
        business_definitions=business_definitions,
        lineage_references=lineage_references,
        validation_suites=validation_suites,
        validation_plans=validation_plans,
        consumers=consumers,
    )


def build_data_asset_entity(
    payload: Mapping[str, Any] | DataAssetEntity | None,
) -> DataAssetEntity | None:
    if isinstance(payload, DataAssetEntity):
        return payload
    if not isinstance(payload, Mapping):
        return None

    asset_id = _clean_optional_str(payload.get("id"))
    if not asset_id:
        return None

    return DataAssetEntity(
        id=asset_id,
        name=_clean_str(payload.get("name")) if payload.get("name") is not None else "",
        description=_clean_str(payload.get("description")) if payload.get("description") is not None else "",
        workspace_id=_clean_str(payload.get("workspace_id")) if payload.get("workspace_id") is not None else "",
        status=_clean_str(payload.get("status")) if payload.get("status") is not None else "draft",
        created_at=_clean_str(payload.get("created_at")) if payload.get("created_at") is not None else "",
        current_version_id=_clean_optional_str(payload.get("current_version_id")),
        source_object_version_ids=[
            _clean_str(item)
            for item in (
                payload.get("source_object_version_ids") if isinstance(payload.get("source_object_version_ids"), list) else []
            )
            if _clean_str(item)
        ],
        business_context=build_data_asset_business_context_entity(payload.get("business_context")),
    )
