from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import delete
from sqlalchemy import select

from app.domain.entities.data_asset import DataAssetEntity
from app.domain.entities.data_asset import DataAssetContractVersionEntity
from app.domain.entities.data_asset import DataAssetLineageSnapshotEntity
from app.domain.entities.data_asset import DataAssetVersionEntity
from app.domain.entities.data_asset import build_data_asset_contract_version_entity
from app.domain.entities.data_asset import build_data_asset_entity
from app.domain.entities.data_asset import build_data_asset_version_entity
from app.domain.interfaces.v1.data_asset_repository import DataAssetRepository
from app.infrastructure.orm.models import DataAssetRow
from app.infrastructure.orm.models import DataAssetContractVersionRow
from app.infrastructure.orm.models import DataAssetLineageSnapshotRow
from app.infrastructure.orm.models import DataAssetVersionRow
from app.infrastructure.orm.session import session_scope


class PostgresDataAssetRepository(DataAssetRepository):
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def list_data_assets(self, workspace_id: str | None = None) -> list[DataAssetEntity]:
        with session_scope(self.database_url) as session:
            stmt = select(DataAssetRow)
            if workspace_id is not None:
                stmt = stmt.where(DataAssetRow.workspace_id == workspace_id)
            rows = session.execute(stmt.order_by(DataAssetRow.name.asc(), DataAssetRow.id.asc())).scalars().all()
            return [self._row_to_asset_entity(row) for row in rows]

    def get_data_asset(self, asset_id: str) -> DataAssetEntity | None:
        with session_scope(self.database_url) as session:
            row = session.get(DataAssetRow, str(asset_id))
            return self._row_to_asset_entity(row) if row is not None else None

    def list_data_asset_versions(self, asset_id: str) -> list[DataAssetVersionEntity]:
        with session_scope(self.database_url) as session:
            rows = session.execute(
                select(DataAssetVersionRow)
                .where(DataAssetVersionRow.data_asset_id == str(asset_id))
                .order_by(DataAssetVersionRow.version.desc(), DataAssetVersionRow.id.asc())
            ).scalars().all()
            return [self._row_to_version_entity(row) for row in rows]

    def get_data_asset_version(self, asset_id: str, version_id: str) -> DataAssetVersionEntity | None:
        with session_scope(self.database_url) as session:
            row = session.get(DataAssetVersionRow, str(version_id))
            if row is None or str(row.data_asset_id or "") != str(asset_id):
                return None
            return self._row_to_version_entity(row)

    def create_data_asset(self, payload: dict[str, Any]) -> DataAssetEntity:
        entity = build_data_asset_entity(payload)
        if entity is None:
            raise ValueError("id is required")

        asset_id = str(entity.id).strip()
        if not asset_id:
            raise ValueError("id is required")

        with session_scope(self.database_url) as session:
            existing = session.get(DataAssetRow, asset_id)
            if existing is not None:
                raise ValueError(f"Data Asset '{asset_id}' already exists")

            row = self._entity_to_row(entity)
            session.add(row)
            session.commit()
            return self._row_to_asset_entity(row)

    def update_data_asset(self, asset_id: str, payload: dict[str, Any]) -> DataAssetEntity:
        normalized_asset_id = str(asset_id).strip()
        with session_scope(self.database_url) as session:
            row = session.get(DataAssetRow, normalized_asset_id)
            if row is None:
                raise ValueError(f"Data Asset '{normalized_asset_id}' was not found")

            merged = self._row_to_asset_payload(row)
            merged.update({key: value for key, value in payload.items() if key != "id"})
            merged["id"] = normalized_asset_id
            entity = build_data_asset_entity(merged)
            if entity is None:
                raise ValueError(f"Data Asset '{normalized_asset_id}' could not be updated")

            row.name = entity.name
            row.description = entity.description or None
            row.workspace_id = entity.workspace_id or None
            row.status = entity.status or None
            row.current_version_id = entity.current_version_id
            row.source_object_version_ids_json = list(entity.source_object_version_ids)
            row.business_context_json = (
                entity.business_context.model_dump(mode="python", by_alias=False, exclude_none=False)
                if entity.business_context is not None
                else None
            )
            session.commit()
            return self._row_to_asset_entity(row)

    def delete_data_asset(self, asset_id: str) -> bool:
        normalized_asset_id = str(asset_id).strip()
        with session_scope(self.database_url) as session:
            existing = session.get(DataAssetRow, normalized_asset_id)
            if existing is None:
                return False
            result = session.execute(delete(DataAssetRow).where(DataAssetRow.id == normalized_asset_id))
            session.commit()
            return True

    def create_data_asset_version(self, asset_id: str, payload: dict[str, Any]) -> DataAssetVersionEntity:
        normalized_asset_id = str(asset_id).strip()
        with session_scope(self.database_url) as session:
            asset_row = session.get(DataAssetRow, normalized_asset_id)
            if asset_row is None:
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

            existing = session.get(DataAssetVersionRow, version_id)
            if existing is not None:
                raise ValueError(f"Data Asset version '{version_id}' already exists")

            row = self._entity_to_version_row(entity)
            session.add(row)
            asset_row.current_version_id = version_id
            asset_row.source_object_version_ids_json = self._collect_source_object_version_ids(asset_row, row)
            session.commit()
            return self._row_to_version_entity(row)

    def get_latest_data_asset_contract_version(self, asset_id: str) -> DataAssetContractVersionEntity | None:
        with session_scope(self.database_url) as session:
            row = session.execute(
                select(DataAssetContractVersionRow)
                .where(DataAssetContractVersionRow.data_asset_id == str(asset_id))
                .order_by(DataAssetContractVersionRow.version.desc(), DataAssetContractVersionRow.id.asc())
            ).scalars().first()
            return self._row_to_contract_entity(row) if row is not None else None

    def list_data_asset_contract_versions(self, asset_id: str) -> list[DataAssetContractVersionEntity]:
        with session_scope(self.database_url) as session:
            rows = session.execute(
                select(DataAssetContractVersionRow)
                .where(DataAssetContractVersionRow.data_asset_id == str(asset_id))
                .order_by(DataAssetContractVersionRow.version.desc(), DataAssetContractVersionRow.id.asc())
            ).scalars().all()
            return [self._row_to_contract_entity(row) for row in rows]

    def update_data_asset_contract_version_review(self, asset_id: str, version_id: str, payload: dict[str, Any]) -> DataAssetContractVersionEntity:
        normalized_asset_id = str(asset_id).strip()
        normalized_version_id = str(version_id).strip()
        with session_scope(self.database_url) as session:
            row = session.get(DataAssetContractVersionRow, normalized_version_id)
            if row is None or str(row.data_asset_id or "") != normalized_asset_id:
                raise ValueError(f"Data Asset contract version '{normalized_version_id}' was not found")

            row.review_status = str(payload.get("review_status") or "pending").strip() or "pending"
            row.reviewed_by = str(payload.get("reviewed_by") or "").strip() or None
            row.reviewed_at = self._parse_datetime(str(payload.get("reviewed_at") or ""))
            row.review_comments = str(payload.get("review_comments") or "").strip() or None
            session.commit()
            return self._row_to_contract_entity(row)

    def save_data_asset_contract_version(self, asset_id: str, payload: dict[str, Any]) -> DataAssetContractVersionEntity:
        normalized_asset_id = str(asset_id).strip()
        with session_scope(self.database_url) as session:
            asset_row = session.get(DataAssetRow, normalized_asset_id)
            if asset_row is None:
                raise ValueError(f"Data Asset '{normalized_asset_id}' was not found")

            latest_row = session.execute(
                select(DataAssetContractVersionRow)
                .where(DataAssetContractVersionRow.data_asset_id == normalized_asset_id)
                .order_by(DataAssetContractVersionRow.version.desc(), DataAssetContractVersionRow.id.asc())
            ).scalars().first()

            contract_yaml = str(payload.get("contract_yaml") or "")
            contract_hash = hashlib.sha256(contract_yaml.encode("utf-8")).hexdigest()
            if latest_row is not None and str(latest_row.contract_hash or "") == contract_hash:
                return self._row_to_contract_entity(latest_row)

            version_number = int(latest_row.version if latest_row is not None else 0) + 1
            row = DataAssetContractVersionRow(
                id=str(payload.get("id") or f"{normalized_asset_id}-contract-v{version_number}"),
                data_asset_id=normalized_asset_id,
                version=version_number,
                contract_yaml=contract_yaml,
                contract_hash=contract_hash,
                generated_at=self._parse_datetime(str(payload.get("generated_at") or "")),
                generated_by=str(payload.get("generated_by") or "").strip() or None,
                generated_where=str(payload.get("generated_where") or "").strip() or None,
                generated_what=str(payload.get("generated_what") or "").strip() or None,
                source_data_asset_version_id=str(payload.get("source_data_asset_version_id") or "").strip() or None,
                review_status=str(payload.get("review_status") or "pending").strip() or "pending",
                reviewed_by=str(payload.get("reviewed_by") or "").strip() or None,
                reviewed_at=self._parse_datetime(str(payload.get("reviewed_at") or "")),
                review_comments=str(payload.get("review_comments") or "").strip() or None,
            )
            session.add(row)
            session.commit()
            return self._row_to_contract_entity(row)

    def record_data_asset_lineage_snapshot(self, asset_id: str, payload: dict[str, Any]) -> DataAssetLineageSnapshotEntity:
        normalized_asset_id = str(asset_id).strip()
        with session_scope(self.database_url) as session:
            asset_row = session.get(DataAssetRow, normalized_asset_id)
            if asset_row is None:
                raise ValueError(f"Data Asset '{normalized_asset_id}' was not found")

            entity = self._build_lineage_snapshot_entity(normalized_asset_id, payload)
            if entity is None:
                raise ValueError("lineage snapshot payload is required")

            row = self._entity_to_lineage_snapshot_row(entity)
            session.add(row)
            session.commit()
            return self._row_to_lineage_snapshot_entity(row)

    def list_data_asset_lineage_snapshots(self, asset_id: str, limit: int = 20) -> list[DataAssetLineageSnapshotEntity]:
        normalized_asset_id = str(asset_id).strip()
        safe_limit = max(1, min(int(limit), 100))
        with session_scope(self.database_url) as session:
            rows = session.execute(
                select(DataAssetLineageSnapshotRow)
                .where(DataAssetLineageSnapshotRow.data_asset_id == normalized_asset_id)
                .order_by(DataAssetLineageSnapshotRow.captured_at.desc(), DataAssetLineageSnapshotRow.id.desc())
                .limit(safe_limit)
            ).scalars().all()
            return [self._row_to_lineage_snapshot_entity(row) for row in rows]

    def _row_to_asset_payload(self, row: DataAssetRow) -> dict[str, Any]:
        return {
            "id": str(row.id or ""),
            "name": str(row.name or ""),
            "description": str(row.description or ""),
            "workspace_id": str(row.workspace_id or ""),
            "status": str(row.status or "draft"),
            "created_at": self._to_text(row.created_at),
            "current_version_id": str(row.current_version_id or "").strip() or None,
            "source_object_version_ids": list(row.source_object_version_ids_json or []),
            "business_context": row.business_context_json or None,
        }

    def _row_to_asset_entity(self, row: DataAssetRow | None) -> DataAssetEntity:
        if row is None:
            raise ValueError("Data Asset row is required")
        entity = build_data_asset_entity(self._row_to_asset_payload(row))
        if entity is None:
            raise ValueError("Data Asset row could not be converted")
        return entity

    def _entity_to_row(self, entity: DataAssetEntity) -> DataAssetRow:
        return DataAssetRow(
            id=str(entity.id).strip(),
            name=str(entity.name or ""),
            description=str(entity.description or "").strip() or None,
            workspace_id=str(entity.workspace_id or "").strip() or None,
            status=str(entity.status or "draft").strip() or "draft",
            created_at=self._parse_datetime(entity.created_at),
            current_version_id=str(entity.current_version_id or "").strip() or None,
            source_object_version_ids_json=list(entity.source_object_version_ids),
            business_context_json=(
                entity.business_context.model_dump(mode="python", by_alias=False, exclude_none=False)
                if entity.business_context is not None
                else None
            ),
        )

    def _row_to_version_payload(self, row: DataAssetVersionRow) -> dict[str, Any]:
        return {
            "id": str(row.id or ""),
            "data_asset_id": str(row.data_asset_id or ""),
            "version": int(row.version or 0),
            "created_at": self._to_text(row.created_at),
            "source_bindings": list(row.source_bindings_json or []),
            "filters": list(row.filters_json or []),
            "derived_fields": list(row.derived_fields_json or []),
            "upload_preview": row.upload_preview_json or None,
        }

    def _row_to_contract_payload(self, row: DataAssetContractVersionRow) -> dict[str, Any]:
        return {
            "id": str(row.id or ""),
            "data_asset_id": str(row.data_asset_id or ""),
            "version": int(row.version or 0),
            "contract_yaml": str(row.contract_yaml or ""),
            "contract_hash": str(row.contract_hash or ""),
            "generated_at": self._to_text(row.generated_at),
            "generated_by": str(row.generated_by or "").strip() or None,
            "generated_where": str(row.generated_where or "").strip() or None,
            "generated_what": str(row.generated_what or "").strip() or None,
            "source_data_asset_version_id": str(row.source_data_asset_version_id or "").strip() or None,
            "review_status": str(row.review_status or "pending").strip() or "pending",
            "reviewed_by": str(row.reviewed_by or "").strip() or None,
            "reviewed_at": self._to_text(row.reviewed_at) if row.reviewed_at is not None else None,
            "review_comments": str(row.review_comments or "").strip() or None,
        }

    def _row_to_lineage_snapshot_payload(self, row: DataAssetLineageSnapshotRow) -> dict[str, Any]:
        return {
            "id": str(row.id or ""),
            "data_asset_id": str(row.data_asset_id or ""),
            "captured_at": self._to_text(row.captured_at),
            "captured_by": str(row.captured_by or "").strip() or None,
            "snapshot_kind": str(row.snapshot_kind or "lineage").strip() or "lineage",
            "lineage_json": row.lineage_json or {},
            "business_context_overlay": row.business_context_overlay_json or None,
            "classification_view": row.classification_view_json or None,
            "anomaly_annotations": list(row.anomaly_annotations_json or []),
        }

    def _row_to_version_entity(self, row: DataAssetVersionRow | None) -> DataAssetVersionEntity:
        if row is None:
            raise ValueError("Data Asset version row is required")
        entity = build_data_asset_version_entity(self._row_to_version_payload(row))
        if entity is None:
            raise ValueError("Data Asset version row could not be converted")
        return entity

    def _row_to_contract_entity(self, row: DataAssetContractVersionRow | None) -> DataAssetContractVersionEntity:
        if row is None:
            raise ValueError("Data Asset contract version row is required")
        entity = build_data_asset_contract_version_entity(self._row_to_contract_payload(row))
        if entity is None:
            raise ValueError("Data Asset contract version row could not be converted")
        return entity

    def _row_to_lineage_snapshot_entity(self, row: DataAssetLineageSnapshotRow | None) -> DataAssetLineageSnapshotEntity:
        if row is None:
            raise ValueError("Data Asset lineage snapshot row is required")
        entity = self._build_lineage_snapshot_entity(str(row.data_asset_id or ""), self._row_to_lineage_snapshot_payload(row))
        if entity is None:
            raise ValueError("Data Asset lineage snapshot row could not be converted")
        return entity

    def _entity_to_version_row(self, entity: DataAssetVersionEntity) -> DataAssetVersionRow:
        return DataAssetVersionRow(
            id=str(entity.id).strip(),
            data_asset_id=str(entity.data_asset_id or "").strip(),
            version=int(entity.version or 1),
            created_at=self._parse_datetime(entity.created_at),
            source_bindings_json=[item.model_dump(mode="python", by_alias=False, exclude_none=False) for item in entity.source_bindings],
            filters_json=[item.model_dump(mode="python", by_alias=False, exclude_none=False) for item in entity.filters],
            derived_fields_json=[item.model_dump(mode="python", by_alias=False, exclude_none=False) for item in entity.derived_fields],
            upload_preview_json=(entity.upload_preview.model_dump(mode="python", by_alias=False, exclude_none=False) if entity.upload_preview is not None else None),
        )

    def _build_lineage_snapshot_entity(self, asset_id: str, payload: dict[str, Any]) -> DataAssetLineageSnapshotEntity | None:
        snapshot_id = str(payload.get("snapshot_id") or payload.get("id") or f"{asset_id}-lineage-{uuid4()}").strip()
        captured_at = str(payload.get("captured_at") or datetime.now(UTC).isoformat()).strip()
        lineage_json = payload.get("lineage_json") or payload
        return DataAssetLineageSnapshotEntity(
            id=snapshot_id,
            data_asset_id=asset_id,
            captured_at=captured_at,
            captured_by=str(payload.get("captured_by") or "").strip() or None,
            snapshot_kind=str(payload.get("snapshot_kind") or "lineage").strip() or "lineage",
            lineage_json=dict(lineage_json),
            business_context_overlay=payload.get("business_context_overlay"),
            classification_view=payload.get("classification_view"),
            anomaly_annotations=list(payload.get("anomaly_annotations") or []),
        )

    def _entity_to_lineage_snapshot_row(self, entity: DataAssetLineageSnapshotEntity) -> DataAssetLineageSnapshotRow:
        return DataAssetLineageSnapshotRow(
            id=str(entity.id).strip(),
            data_asset_id=str(entity.data_asset_id or "").strip(),
            snapshot_kind=str(entity.snapshot_kind or "lineage").strip() or "lineage",
            captured_at=self._parse_datetime(entity.captured_at),
            captured_by=str(entity.captured_by or "").strip() or None,
            lineage_json=dict(entity.lineage_json or {}),
            business_context_overlay_json=entity.business_context_overlay,
            classification_view_json=entity.classification_view,
            anomaly_annotations_json=list(entity.anomaly_annotations or []),
        )

    def _collect_source_object_version_ids(self, asset_row: DataAssetRow, version_row: DataAssetVersionRow) -> list[str]:
        source_object_version_ids = list(asset_row.source_object_version_ids_json or [])
        for binding in version_row.source_bindings_json or []:
            source_version_id = str(binding.get("source_data_object_version_id") or "").strip()
            if source_version_id and source_version_id not in source_object_version_ids:
                source_object_version_ids.append(source_version_id)
        return source_object_version_ids

    @staticmethod
    def _to_text(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, datetime):
            return value.isoformat()
        return str(value)

    @staticmethod
    def _parse_datetime(value: str) -> datetime:
        raw = str(value or "").strip()
        if not raw:
            return datetime.now(UTC)
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return datetime.now(UTC)
