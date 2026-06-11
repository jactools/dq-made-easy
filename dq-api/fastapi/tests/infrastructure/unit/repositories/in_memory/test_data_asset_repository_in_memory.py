from __future__ import annotations

from app.infrastructure.repositories.in_memory_data_asset_repository import InMemoryDataAssetRepository


def test_in_memory_data_asset_repository_roundtrip() -> None:
    repo = InMemoryDataAssetRepository()

    asset = repo.create_data_asset(
        {
            "id": "asset-1",
            "name": "Customer health",
            "workspace_id": "ws-1",
            "source_object_version_ids": ["dov-1"],
            "business_context": {
                "dataset_id": "dataset-1",
                "data_product_id": "product-1",
                "domain": "Customer",
                "owner": "data-owner@example.com",
                "tags": ["customer", "golden-record"],
                "business_definitions": ["Customer health metric used for support prioritization"],
                "lineage_references": ["dov-1", "dataset-1"],
                "validation_suites": ["validation-suite-customer-health"],
                "validation_plans": ["validation-plan-customer-health-daily"],
                "consumers": ["Support", "Analytics"],
            },
        }
    )
    assert asset.id == "asset-1"
    assert asset.workspace_id == "ws-1"
    assert asset.business_context.dataset_id == "dataset-1"
    assert asset.business_context.owner == "data-owner@example.com"
    assert asset.business_context.tags == ["customer", "golden-record"]
    assert asset.business_context.validation_suites == ["validation-suite-customer-health"]
    assert asset.business_context.validation_plans == ["validation-plan-customer-health-daily"]

    version = repo.create_data_asset_version(
        "asset-1",
        {
            "id": "asset-1-v1",
            "version": 1,
            "source_bindings": [
                {
                    "source_data_object_version_id": "dov-1",
                    "source_field_id": "field-1",
                    "source_field_name": "customer_id",
                    "source_field_type": "string",
                }
            ],
            "derived_fields": [
                {
                    "name": "customer_segment",
                    "expression": "case when amount > 100 then 'gold' end",
                }
            ],
        },
    )
    assert version.id == "asset-1-v1"
    assert version.data_asset_id == "asset-1"
    assert repo.get_data_asset("asset-1").current_version_id == "asset-1-v1"
    assert repo.get_data_asset_version("asset-1", "asset-1-v1").version == 1

    assets = repo.list_data_assets(workspace_id="ws-1")
    assert len(assets) == 1
    assert assets[0].id == "asset-1"
    assert assets[0].business_context.business_definitions == ["Customer health metric used for support prioritization"]

    versions = repo.list_data_asset_versions("asset-1")
    assert len(versions) == 1
    assert versions[0].derived_fields[0].name == "customer_segment"

    deleted = repo.delete_data_asset("asset-1")
    assert deleted is True
    assert repo.get_data_asset("asset-1") is None
    assert repo.list_data_asset_versions("asset-1") == []


def test_in_memory_data_asset_contract_versioning() -> None:
    repo = InMemoryDataAssetRepository()
    repo.create_data_asset(
        {
            "id": "asset-1",
            "name": "Customer health",
            "workspace_id": "ws-1",
        }
    )

    first = repo.save_data_asset_contract_version(
        "asset-1",
        {
            "contract_yaml": "apiVersion: v3.1.0\nkind: DataContract\nid: urn:dq:contract:asset-1\n",
            "generated_by": "user-1",
            "generated_where": "/rulebuilder/v1/data-assets/asset-1/contract",
            "generated_what": "Generated ODCS contract for Data Asset 'asset-1'",
        },
    )
    second = repo.save_data_asset_contract_version(
        "asset-1",
        {
            "contract_yaml": "apiVersion: v3.1.0\nkind: DataContract\nid: urn:dq:contract:asset-1\n",
            "generated_by": "user-2",
            "generated_where": "/rulebuilder/v1/data-assets/asset-1/contract",
            "generated_what": "Generated ODCS contract for Data Asset 'asset-1'",
        },
    )

    assert first.version == 1
    assert second.version == 1

    changed = repo.save_data_asset_contract_version(
        "asset-1",
        {
            "contract_yaml": "apiVersion: v3.1.0\nkind: DataContract\nid: urn:dq:contract:asset-1\nstatus: active\n",
            "generated_by": "user-3",
            "generated_where": "/rulebuilder/v1/data-assets/asset-1/contract",
            "generated_what": "Generated ODCS contract for Data Asset 'asset-1'",
        },
    )

    assert changed.version == 2
    assert repo.get_latest_data_asset_contract_version("asset-1").version == 2


def test_in_memory_data_asset_lineage_snapshots() -> None:
    repo = InMemoryDataAssetRepository()
    repo.create_data_asset(
        {
            "id": "asset-1",
            "name": "Customer health",
            "workspace_id": "ws-1",
        }
    )

    snapshot = repo.record_data_asset_lineage_snapshot(
        "asset-1",
        {
            "snapshot_kind": "lineage",
            "captured_at": "2026-05-25T13:00:00Z",
            "lineage_json": {"dataAsset": {"id": "asset-1"}},
            "business_context_overlay": {"domain": "Customer"},
            "classification_view": {"classification": "internal"},
            "anomaly_annotations": [{"kind": "contract_change"}],
        },
    )

    assert snapshot.data_asset_id == "asset-1"
    listed = repo.list_data_asset_lineage_snapshots("asset-1")
    assert len(listed) == 1
    assert listed[0].business_context_overlay["domain"] == "Customer"
    assert listed[0].classification_view["classification"] == "internal"
