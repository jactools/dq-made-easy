from typing import Any

from fastapi import HTTPException

from app.api.v1 import test_data_materialization_support as _materialization_support
from app.domain.entities import QueuedTestDataRequestRecordEntity
from app.domain.entities import QueuedTestDataResultEntity
from app.domain.entities import build_queued_test_data_request_record_entity
from app.domain.entities import build_queued_test_data_result_entity
from app.domain.interfaces.v1.data_asset_repository import DataAssetRepository
from app.domain.interfaces.v1.data_catalog_repository import DataCatalogRepository

_MOCK_PREVIEW_SOURCE_ID = "mock-preview-source"
_ACTIVE_TEST_DATA_REQUEST_STATUSES = {"pending", "started"}


def _payload_value(payload: Any, *names: str) -> Any:
    if isinstance(payload, dict):
        for name in names:
            if name in payload:
                return payload[name]
        return None

    for name in names:
        if hasattr(payload, name):
            return getattr(payload, name)
    return None


def require_queued_test_data_request_record(
    record: QueuedTestDataRequestRecordEntity | dict[str, Any],
) -> QueuedTestDataRequestRecordEntity:
    if isinstance(record, QueuedTestDataRequestRecordEntity):
        return record

    entity = build_queued_test_data_request_record_entity(record)
    if entity is None:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "invalid_test_data_request_record",
                "message": "Stored queued test data request record is invalid",
            },
        )
    return entity


def queued_test_data_request_record_payload(
    record: QueuedTestDataRequestRecordEntity | dict[str, Any],
) -> dict[str, Any]:
    entity = require_queued_test_data_request_record(record)
    return entity.model_dump(mode="python")


def queued_test_data_request_field(
    record: QueuedTestDataRequestRecordEntity | dict[str, Any],
    field_name: str,
) -> Any:
    if isinstance(record, QueuedTestDataRequestRecordEntity):
        return getattr(record, field_name, None)
    if isinstance(record, dict):
        return record.get(field_name)
    return None


def queued_test_data_result_entity(payload: Any) -> QueuedTestDataResultEntity:
    entity = build_queued_test_data_result_entity(payload)
    return entity if entity is not None else QueuedTestDataResultEntity()


async def find_active_queued_test_data_request(redis_url: str, request_payload: dict[str, Any]) -> dict[str, Any] | None:
    target_type = str(_payload_value(request_payload, "targetType", "target_type") or "").strip()
    target_id = str(_payload_value(request_payload, "targetId", "target_id") or "").strip()
    if not target_type or not target_id:
        return None

    for record in await _materialization_support.redis_scan_json(redis_url, "test-data-request:*"):
        if str(record.get("target_type") or "").strip() != target_type:
            continue
        if str(record.get("target_id") or "").strip() != target_id:
            continue
        if str(record.get("status") or "").strip().lower() not in _ACTIVE_TEST_DATA_REQUEST_STATUSES:
            continue
        return record
    return None


def build_mock_preview_attributes() -> list[dict[str, Any]]:
    return [
        {
            "name": "column_id",
            "type": "integer",
            "nullable": False,
            "format": "",
            "is_primary_key": True,
        },
        {
            "name": "column_x",
            "type": "text",
            "nullable": True,
            "format": "",
            "is_primary_key": False,
        },
        {
            "name": "column_y",
            "type": "text",
            "nullable": True,
            "format": "",
            "is_primary_key": False,
        },
    ]


def _build_data_asset_attributes(version: Any) -> list[dict[str, Any]]:
    source_bindings = list(getattr(version, "source_bindings", None) or [])
    derived_fields = list(getattr(version, "derived_fields", None) or [])
    upload_preview = getattr(version, "upload_preview", None)
    preview_columns = list(getattr(upload_preview, "columns", None) or []) if upload_preview is not None else []

    if source_bindings:
        raw_attributes = [
            {
                "name": getattr(binding, "source_field_name", None) or getattr(binding, "source_field_id", ""),
                "type": getattr(binding, "source_field_type", None) or "text",
                "nullable": bool(getattr(binding, "nullable", True)),
                "format": "",
                "is_primary_key": False,
            }
            for binding in source_bindings
        ]
    elif preview_columns:
        raw_attributes = [
            {
                "name": getattr(column, "name", ""),
                "type": getattr(column, "data_type", None) or "text",
                "nullable": bool(getattr(column, "nullable", True)),
                "format": "",
                "is_primary_key": False,
            }
            for column in preview_columns
        ]
    else:
        raw_attributes = []

    raw_attributes.extend(
        {
            "name": getattr(field, "name", ""),
            "type": getattr(field, "data_type", None) or "text",
            "nullable": bool(getattr(field, "nullable", True)),
            "format": "",
            "is_primary_key": False,
        }
        for field in derived_fields
    )
    return _materialization_support.build_attribute_payloads(list(raw_attributes))


def resolve_data_asset_generation_payload(
    asset_id: str,
    sample_count: int,
    data_asset_repository: DataAssetRepository,
) -> dict[str, Any]:
    asset = data_asset_repository.get_data_asset(asset_id)
    if asset is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "data_asset_not_found",
                "message": f"Data Asset '{asset_id}' was not found",
                "data_asset_id": asset_id,
            },
        )

    version_id = str(asset.current_version_id or "").strip()
    version = None
    if version_id:
        version = data_asset_repository.get_data_asset_version(str(asset.id), version_id)
    if version is None:
        versions = data_asset_repository.list_data_asset_versions(str(asset.id))
        version = versions[0] if versions else None
        version_id = str(getattr(version, "id", "") or "").strip()

    if version is None or not version_id:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "data_asset_has_no_versions",
                "message": f"Data Asset '{asset_id}' has no versions to generate test data from",
                "data_asset_id": asset_id,
            },
        )

    attributes = _build_data_asset_attributes(version)
    return {
        "target_type": "data_asset",
        "target_id": str(asset.id),
        "sample_count": sample_count,
        "version_id": version_id,
        "version_name": getattr(version, "version", None),
        "data_object_id": str(asset.id),
        "data_object_name": str(asset.name or "").strip() or None,
        "source_name": str(asset.name or "").strip() or None,
        "data_asset_id": str(asset.id),
        "data_asset_version_id": version_id,
        "attributes": attributes,
    }


def resolve_version_generation_payload(
    version_id: str,
    sample_count: int,
    catalog_repository: DataCatalogRepository,
) -> dict[str, Any]:
    version = next(
        (item for item in catalog_repository.list_data_object_versions() if str(item.id) == str(version_id)),
        None,
    )
    attributes = _materialization_support.build_attribute_payloads(catalog_repository.list_attributes_catalog(version_id))
    data_object_name = None
    if version is not None:
        data_object = next(
            (
                item
                for item in catalog_repository.list_data_objects_catalog()
                if str(item.id) == str(getattr(version, "data_object_id", ""))
            ),
            None,
        )
        if data_object is not None:
            data_object_name = str(getattr(data_object, "name", "") or "").strip() or None
    return {
        "target_type": "data_object_version",
        "target_id": version_id,
        "sample_count": sample_count,
        "version_id": version_id,
        "version_name": getattr(version, "version", None) if version is not None else None,
        "data_object_id": getattr(version, "data_object_id", None) if version is not None else None,
        "data_object_name": data_object_name,
        "source_name": None,
        "attributes": attributes,
    }


def resolve_queued_test_data_request_payload(
    payload: Any,
    catalog_repository: DataCatalogRepository,
    data_asset_repository: DataAssetRepository | None = None,
) -> dict[str, Any]:
    target_type = str(_payload_value(payload, "targetType", "target_type") or "").strip()
    target_id = str(_payload_value(payload, "targetId", "target_id") or "").strip()
    sample_count = int(_payload_value(payload, "sampleCount", "sample_count") or 0)
    if not target_type or not target_id:
        raise HTTPException(status_code=400, detail="target_type and target_id are required")

    if target_type == "data_object_version":
        return resolve_version_generation_payload(target_id, sample_count, catalog_repository)

    if target_type == "mock_data_source":
        attributes = _materialization_support.build_attribute_payloads(
            list(_payload_value(payload, "attributes") or [])
        ) or build_mock_preview_attributes()
        return {
            "target_type": target_type,
            "target_id": target_id,
            "sample_count": sample_count,
            "version_id": None,
            "version_name": _payload_value(payload, "versionName", "version_name"),
            "data_object_id": _payload_value(payload, "dataObjectId", "data_object_id"),
            "source_name": _payload_value(payload, "sourceName", "source_name")
            or ("Mock Data Source (Preview)" if target_id == _MOCK_PREVIEW_SOURCE_ID else target_id),
            "attributes": attributes,
        }

    if target_type == "data_asset":
        if data_asset_repository is None:
            raise HTTPException(status_code=503, detail="Data asset repository is not configured")
        return resolve_data_asset_generation_payload(target_id, sample_count, data_asset_repository)

    raise HTTPException(status_code=400, detail=f"Unsupported test data target_type '{target_type}'")