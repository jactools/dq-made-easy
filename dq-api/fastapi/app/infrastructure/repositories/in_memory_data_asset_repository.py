from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
import hashlib
from uuid import uuid4

from app.domain.entities.data_asset import DataAssetEntity
from app.domain.entities.data_asset import DataAssetContractVersionEntity
from app.domain.entities.data_asset import DataAssetLineageSnapshotEntity
from app.domain.entities.data_asset import DataAssetVersionEntity
from app.domain.entities.data_asset import build_data_asset_contract_version_entity
from app.domain.entities.data_asset import build_data_asset_entity
from app.domain.entities.data_asset import build_data_asset_version_entity
from app.domain.interfaces.v1.data_asset_repository import DataAssetRepository


class InMemoryDataAssetRepository(DataAssetRepository):
    def __init__(self) -> None:
        self._data_assets: dict[str, dict] = {}
        self._data_asset_versions: dict[str, dict[str, dict]] = {}
        self._data_asset_contract_versions: dict[str, dict[str, dict]] = {}
        self._data_asset_lineage_snapshots: dict[str, list[dict]] = {}

    def list_data_assets(self, workspace_id: str | None = None) -> list[DataAssetEntity]:
        rows = list(self._data_assets.values())
        if workspace_id is not None:
            rows = [row for row in rows if str(row.get("workspace_id") or "") == str(workspace_id)]
        rows.sort(key=lambda row: (str(row.get("name") or ""), str(row.get("id") or "")))
        return [asset for asset in (build_data_asset_entity(deepcopy(row)) for row in rows) if asset is not None]

    def get_data_asset(self, asset_id: str) -> DataAssetEntity | None:
        row = self._data_assets.get(str(asset_id))
        return build_data_asset_entity(deepcopy(row)) if row is not None else None

    def list_data_asset_versions(self, asset_id: str) -> list[DataAssetVersionEntity]:
        versions = list(self._data_asset_versions.get(str(asset_id), {}).values())
        versions.sort(key=lambda row: (int(row.get("version") or 0), str(row.get("id") or "")), reverse=True)
        return [version for version in (build_data_asset_version_entity(deepcopy(row)) for row in versions) if version is not None]

    def get_data_asset_version(self, asset_id: str, version_id: str) -> DataAssetVersionEntity | None:
        row = self._data_asset_versions.get(str(asset_id), {}).get(str(version_id))
        return build_data_asset_version_entity(deepcopy(row)) if row is not None else None

    def create_data_asset(self, payload: dict) -> DataAssetEntity:
        entity = build_data_asset_entity(payload)
        if entity is None:
            raise ValueError("id is required")

        asset_id = str(entity.id).strip()
        if not asset_id:
            raise ValueError("id is required")
        if asset_id in self._data_assets:
            raise ValueError(f"Data Asset '{asset_id}' already exists")

        self._data_assets[asset_id] = entity.model_dump(mode="python", by_alias=False, exclude_none=False)
        self._data_asset_versions.setdefault(asset_id, {})
        return build_data_asset_entity(deepcopy(self._data_assets[asset_id])) or entity

    def update_data_asset(self, asset_id: str, payload: dict) -> DataAssetEntity:
        normalized_asset_id = str(asset_id).strip()
        existing = self._data_assets.get(normalized_asset_id)
        if existing is None:
            raise ValueError(f"Data Asset '{normalized_asset_id}' was not found")

        merged = dict(existing)
        merged.update({key: value for key, value in payload.items() if key != "id"})
        merged["id"] = normalized_asset_id
        entity = build_data_asset_entity(merged)
        if entity is None:
            raise ValueError(f"Data Asset '{normalized_asset_id}' could not be updated")

        self._data_assets[normalized_asset_id] = entity.model_dump(mode="python", by_alias=False, exclude_none=False)
        return entity

    def delete_data_asset(self, asset_id: str) -> bool:
        normalized_asset_id = str(asset_id).strip()
        removed = self._data_assets.pop(normalized_asset_id, None)
        self._data_asset_versions.pop(normalized_asset_id, None)
        return removed is not None

    def create_data_asset_version(self, asset_id: str, payload: dict) -> DataAssetVersionEntity:
        normalized_asset_id = str(asset_id).strip()
        asset = self._data_assets.get(normalized_asset_id)
        if asset is None:
            raise ValueError(f"Data Asset '{normalized_asset_id}' was not found")

        merged = dict(payload)
        merged["data_asset_id"] = normalized_asset_id
        if not merged.get("created_at"):
            merged["created_at"] = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        entity = build_data_asset_version_entity(merged)
        if entity is None:
            raise ValueError("id and data_asset_id are required")

        version_id = str(entity.id).strip()
        if not version_id:
            raise ValueError("id and data_asset_id are required")
        asset_versions = self._data_asset_versions.setdefault(normalized_asset_id, {})
        if version_id in asset_versions:
            raise ValueError(f"Data Asset version '{version_id}' already exists")

        asset_versions[version_id] = entity.model_dump(mode="python", by_alias=False, exclude_none=False)
        asset["current_version_id"] = version_id

        source_object_version_ids = list(asset.get("source_object_version_ids") or [])
        for source_binding in asset_versions[version_id].get("source_bindings") or []:
            source_version_id = str(source_binding.get("source_data_object_version_id") or "").strip()
            if source_version_id and source_version_id not in source_object_version_ids:
                source_object_version_ids.append(source_version_id)
        asset["source_object_version_ids"] = source_object_version_ids

        self._data_assets[normalized_asset_id] = asset
        return build_data_asset_version_entity(deepcopy(asset_versions[version_id])) or entity

    def get_latest_data_asset_contract_version(self, asset_id: str) -> DataAssetContractVersionEntity | None:
        versions = list(self._data_asset_contract_versions.get(str(asset_id), {}).values())
        versions.sort(key=lambda row: (int(row.get("version") or 0), str(row.get("id") or "")), reverse=True)
        return build_data_asset_contract_version_entity(deepcopy(versions[0])) if versions else None

    def list_data_asset_contract_versions(self, asset_id: str) -> list[DataAssetContractVersionEntity]:
        versions = list(self._data_asset_contract_versions.get(str(asset_id), {}).values())
        versions.sort(key=lambda row: (int(row.get("version") or 0), str(row.get("id") or "")), reverse=True)
        return [
            version
            for version in (build_data_asset_contract_version_entity(deepcopy(row)) for row in versions)
            if version is not None
        ]

    def update_data_asset_contract_version_review(self, asset_id: str, version_id: str, payload: dict) -> DataAssetContractVersionEntity:
        normalized_asset_id = str(asset_id).strip()
        normalized_version_id = str(version_id).strip()
        contract_versions = self._data_asset_contract_versions.get(normalized_asset_id, {})
        row = contract_versions.get(normalized_version_id)
        if row is None:
            raise ValueError(f"Data Asset contract version '{normalized_version_id}' was not found")

        updated_row = dict(row)
        updated_row.update(
            {
                "review_status": str(payload.get("review_status") or "pending").strip() or "pending",
                "reviewed_by": str(payload.get("reviewed_by") or "").strip() or None,
                "reviewed_at": str(payload.get("reviewed_at") or "").strip() or None,
                "review_comments": str(payload.get("review_comments") or "").strip() or None,
            }
        )
        contract_versions[normalized_version_id] = updated_row
        self._data_asset_contract_versions[normalized_asset_id] = contract_versions
        entity = build_data_asset_contract_version_entity(deepcopy(updated_row))
        if entity is None:
            raise ValueError(f"Data Asset contract version '{normalized_version_id}' could not be updated")
        return entity

    def save_data_asset_contract_version(self, asset_id: str, payload: dict) -> DataAssetContractVersionEntity:
        normalized_asset_id = str(asset_id).strip()
        asset = self._data_assets.get(normalized_asset_id)
        if asset is None:
            raise ValueError(f"Data Asset '{normalized_asset_id}' was not found")

        contract_yaml = str(payload.get("contract_yaml") or "")
        contract_hash = hashlib.sha256(contract_yaml.encode("utf-8")).hexdigest()
        contract_versions = self._data_asset_contract_versions.setdefault(normalized_asset_id, {})
        latest = self.get_latest_data_asset_contract_version(normalized_asset_id)
        if latest is not None and latest.contract_hash == contract_hash:
            return latest

        version_number = int(latest.version if latest is not None else 0) + 1
        generated_at = str(payload.get("generated_at") or datetime.now(UTC).isoformat().replace("+00:00", "Z"))
        entity = build_data_asset_contract_version_entity(
            {
                "id": payload.get("id") or f"{normalized_asset_id}-contract-v{version_number}",
                "data_asset_id": normalized_asset_id,
                "version": version_number,
                "contract_yaml": contract_yaml,
                "contract_hash": contract_hash,
                "generated_at": generated_at,
                "generated_by": payload.get("generated_by"),
                "generated_where": payload.get("generated_where"),
                "generated_what": payload.get("generated_what"),
                "source_data_asset_version_id": payload.get("source_data_asset_version_id"),
                "review_status": payload.get("review_status") or "pending",
                "reviewed_by": payload.get("reviewed_by"),
                "reviewed_at": payload.get("reviewed_at"),
                "review_comments": payload.get("review_comments"),
            }
        )
        if entity is None:
            raise ValueError("contract_yaml and data_asset_id are required")

        contract_versions[str(entity.id)] = entity.model_dump(mode="python", by_alias=False, exclude_none=False)
        return build_data_asset_contract_version_entity(deepcopy(contract_versions[str(entity.id)])) or entity

    def record_data_asset_lineage_snapshot(self, asset_id: str, payload: dict) -> DataAssetLineageSnapshotEntity:
        normalized_asset_id = str(asset_id).strip()
        asset = self._data_assets.get(normalized_asset_id)
        if asset is None:
            raise ValueError(f"Data Asset '{normalized_asset_id}' was not found")

        entity = DataAssetLineageSnapshotEntity(
            id=str(payload.get("snapshot_id") or payload.get("id") or f"{normalized_asset_id}-lineage-{uuid4()}").strip(),
            data_asset_id=normalized_asset_id,
            captured_at=str(payload.get("captured_at") or datetime.now(UTC).isoformat()).strip(),
            captured_by=str(payload.get("captured_by") or "").strip() or None,
            snapshot_kind=str(payload.get("snapshot_kind") or "lineage").strip() or "lineage",
            lineage_json=deepcopy(dict(payload.get("lineage_json") or payload)),
            business_context_overlay=deepcopy(payload.get("business_context_overlay")),
            classification_view=deepcopy(payload.get("classification_view")),
            anomaly_annotations=deepcopy(list(payload.get("anomaly_annotations") or [])),
        )
        snapshot_row = entity.model_dump(mode="python", by_alias=False, exclude_none=False)
        self._data_asset_lineage_snapshots.setdefault(normalized_asset_id, []).append(snapshot_row)
        return entity

    def list_data_asset_lineage_snapshots(self, asset_id: str, limit: int = 20) -> list[DataAssetLineageSnapshotEntity]:
        normalized_asset_id = str(asset_id).strip()
        snapshots = list(self._data_asset_lineage_snapshots.get(normalized_asset_id, []))
        snapshots.sort(key=lambda row: (str(row.get("captured_at") or ""), str(row.get("id") or "")), reverse=True)
        safe_limit = max(1, min(int(limit), 100))
        return [DataAssetLineageSnapshotEntity.model_validate(deepcopy(row)) for row in snapshots[:safe_limit]]
