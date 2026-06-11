from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from uuid import uuid4

from sqlalchemy import select

from app.domain.entities.data_protection import DataEncryptionKeyEntity
from app.domain.interfaces.v1.data_protection_repository import DataProtectionRepository
from app.infrastructure.orm.models import DataEncryptionKeyRow
from app.infrastructure.orm.session import session_scope
from app.infrastructure.security import EntityFieldEncryptor


class PostgresDataProtectionRepository(DataProtectionRepository):
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        self._field_encryptor = EntityFieldEncryptor.from_env()

    def list_encryption_keys(self, workspace_id: str | None = None, scope: str | None = None) -> list[DataEncryptionKeyEntity]:
        with session_scope(self.database_url) as session:
            stmt = select(DataEncryptionKeyRow)
            if workspace_id is not None:
                stmt = stmt.where(DataEncryptionKeyRow.workspace_id == workspace_id)
            if scope is not None:
                stmt = stmt.where(DataEncryptionKeyRow.key_scope == scope)
            stmt = stmt.order_by(DataEncryptionKeyRow.created_at.desc())
            rows = session.execute(stmt).scalars().all()
            return [self._to_entity(row) for row in rows]

    def get_encryption_key(self, key_id: str) -> DataEncryptionKeyEntity | None:
        with session_scope(self.database_url) as session:
            row = session.get(DataEncryptionKeyRow, str(key_id).strip())
            return self._to_entity(row) if row is not None else None

    def create_encryption_key(self, payload: dict[str, object], *, created_by: str | None = None) -> DataEncryptionKeyEntity:
        key_name = str(payload.get("key_name") or payload.get("keyName") or "").strip()
        if not key_name:
            raise ValueError("key_name is required")
        key_material = str(payload.get("key_material") or payload.get("keyMaterial") or "").strip()
        if not key_material:
            raise ValueError("key_material is required")

        key_scope = str(payload.get("key_scope") or payload.get("keyScope") or "app").strip().lower() or "app"
        if key_scope not in {"app", "workspace"}:
            raise ValueError("key_scope must be 'app' or 'workspace'")

        workspace_id = str(payload.get("workspace_id") or payload.get("workspaceId") or "").strip() or None
        if key_scope == "workspace" and not workspace_id:
            raise ValueError("workspace_id is required when key_scope is 'workspace'")

        key_algorithm = str(payload.get("key_algorithm") or payload.get("keyAlgorithm") or "fernet").strip().lower() or "fernet"
        if key_algorithm not in {"fernet"}:
            raise ValueError("key_algorithm must be 'fernet'")

        is_active_raw = payload.get("is_active") if "is_active" in payload else payload.get("isActive")
        is_active = True if is_active_raw is None else bool(is_active_raw)
        fingerprint = sha256(key_material.encode("utf-8")).hexdigest()[:16]
        encrypted_key_material = self._field_encryptor.encrypt_value(key_material)

        with session_scope(self.database_url) as session:
            row = DataEncryptionKeyRow(
                id=f"dek-{uuid4().hex[:12]}",
                key_name=key_name,
                key_scope=key_scope,
                workspace_id=workspace_id,
                key_algorithm=key_algorithm,
                key_material_encrypted=encrypted_key_material,
                key_fingerprint=fingerprint,
                is_active=is_active,
                created_by=created_by,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return self._to_entity(row)

    def _to_entity(self, row: DataEncryptionKeyRow | None) -> DataEncryptionKeyEntity | None:
        if row is None:
            return None
        return DataEncryptionKeyEntity(
            id=str(row.id or ""),
            keyName=str(row.key_name or ""),
            keyScope=str(row.key_scope or "app"),
            workspaceId=str(row.workspace_id or "").strip() or None,
            keyAlgorithm=str(row.key_algorithm or "fernet"),
            keyFingerprint=str(row.key_fingerprint or ""),
            isActive=bool(row.is_active) if row.is_active is not None else True,
            createdBy=str(row.created_by or "").strip() or None,
            createdAt=self._to_text(row.created_at),
            updatedAt=self._to_text(row.updated_at),
        )

    @staticmethod
    def _to_text(value: object) -> str:
        if value is None:
            return ""
        if hasattr(value, "isoformat"):
            return value.isoformat()  # type: ignore[union-attr]
        return str(value)