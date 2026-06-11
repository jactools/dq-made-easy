from app.domain.entities import DataAssetEntity
from app.domain.entities import DataAssetUploadPreviewEntity
from app.domain.entities import DataAssetVersionEntity
from app.domain.entities import build_data_asset_entity
from app.domain.entities import build_data_asset_version_entity


def test_data_asset_entity_serializes_snake_case() -> None:
    entity = DataAssetEntity(
        id="asset-1",
        name="Customer health",
        workspace_id="ws-1",
        current_version_id="asset-1-v1",
        source_object_version_ids=["dov-1", "dov-2"],
    )

    payload = entity.model_dump(mode="python", by_alias=True, exclude_none=True)

    assert payload["id"] == "asset-1"
    assert payload["workspace_id"] == "ws-1"
    assert payload["source_object_version_ids"] == ["dov-1", "dov-2"]


def test_build_data_asset_version_entity_normalizes_nested_payload() -> None:
    version = build_data_asset_version_entity(
        {
            "id": "asset-1-v1",
            "data_asset_id": "asset-1",
            "version": "2",
            "created_at": "2026-05-21T10:00:00Z",
            "source_bindings": [
                {
                    "source_data_object_version_id": "dov-1",
                    "source_field_id": "field-1",
                    "source_field_name": "customer_id",
                    "source_field_type": "string",
                    "nullable": False,
                },
                {"source_data_object_version_id": "", "source_field_id": "field-2"},
            ],
            "filters": [{"expression": "amount > 0"}, {"expression": ""}],
            "derived_fields": [
                {
                    "name": "customer_segment",
                    "expression": "case when amount > 100 then 'gold' end",
                    "data_type": "string",
                    "source_field_ids": ["field-1", " "],
                }
            ],
            "upload_preview": {
                "file_name": "customers.csv",
                "file_format": "csv",
                "columns": [
                    {"name": "customer_id", "data_type": "string"},
                    {"name": "", "data_type": "number"},
                ],
            },
        }
    )

    assert isinstance(version, DataAssetVersionEntity)
    assert version.id == "asset-1-v1"
    assert version.version == 2
    assert len(version.source_bindings) == 1
    assert version.source_bindings[0].source_field_name == "customer_id"
    assert len(version.filters) == 1
    assert version.filters[0].expression == "amount > 0"
    assert version.derived_fields[0].source_field_ids == ["field-1"]
    assert isinstance(version.upload_preview, DataAssetUploadPreviewEntity)
    assert [column.name for column in version.upload_preview.columns] == ["customer_id"]
