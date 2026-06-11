from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.v1.test_data_queue_support import resolve_data_asset_generation_payload


class _DataAssetRepository:
    def __init__(self) -> None:
        self.asset = SimpleNamespace(
            id="asset-1",
            name="Customer health",
            current_version_id="asset-1-v1",
        )
        self.version = SimpleNamespace(
            id="asset-1-v1",
            version=3,
            source_bindings=[
                SimpleNamespace(
                    source_field_name="customer_id",
                    source_field_type="string",
                    nullable=False,
                ),
                SimpleNamespace(
                    source_field_id="fallback_field_id",
                    source_field_type="number",
                    nullable=True,
                ),
            ],
            derived_fields=[
                SimpleNamespace(
                    name="customer_segment",
                    data_type="string",
                    nullable=True,
                )
            ],
            upload_preview=SimpleNamespace(columns=[]),
        )

    def get_data_asset(self, asset_id: str):
        return self.asset if asset_id == self.asset.id else None

    def get_data_asset_version(self, asset_id: str, version_id: str):
        if asset_id == self.asset.id and version_id == self.version.id:
            return self.version
        return None

    def list_data_asset_versions(self, asset_id: str):
        return [self.version] if asset_id == self.asset.id else []


def test_resolve_data_asset_generation_payload_uses_version_attributes() -> None:
    repository = _DataAssetRepository()

    payload = resolve_data_asset_generation_payload("asset-1", 5, repository)

    assert payload["target_type"] == "data_asset"
    assert payload["target_id"] == "asset-1"
    assert payload["version_id"] == "asset-1-v1"
    assert payload["data_object_id"] == "asset-1"
    assert payload["data_object_name"] == "Customer health"
    assert [attribute["name"] for attribute in payload["attributes"]] == [
        "customer_id",
        "fallback_field_id",
        "customer_segment",
    ]


def test_resolve_data_asset_generation_payload_raises_for_missing_asset() -> None:
    repository = _DataAssetRepository()

    with pytest.raises(HTTPException) as exc_info:
        resolve_data_asset_generation_payload("missing", 5, repository)

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["error"] == "data_asset_not_found"
