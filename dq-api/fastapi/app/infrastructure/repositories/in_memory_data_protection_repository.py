from __future__ import annotations

from hashlib import sha256
from uuid import uuid4

from app.domain.entities.data_protection import DataEncryptionKeyEntity
from app.domain.interfaces.v1.data_protection_repository import DataProtectionRepository
from app.infrastructure.security import EntityFieldEncryptor


class InMemoryDataProtectionRepository(DataProtectionRepository):
    def __init__(self) -> None:
        self._field_encryptor = EntityFieldEncryptor.from_env()
        self._encryption_keys: list[dict[str, object]] = [
            {
                "id": "dek-app-default",
                "key_name": "Default app key",
                "key_scope": "app",
                "workspace_id": None,
                "key_algorithm": "fernet",
                "key_material_encrypted": self._field_encryptor.encrypt_value("default-app-key"),
                "key_fingerprint": sha256(b"default-app-key").hexdigest()[:16],
                "is_active": True,
                "created_by": "seed",
                "created_at": "2026-05-25T00:00:00Z",
                "updated_at": "2026-05-25T00:00:00Z",
            }
        ]

    def list_encryption_keys(self, workspace_id: str | None = None, scope: str | None = None) -> list[DataEncryptionKeyEntity]:
        rows = self._encryption_keys
        if workspace_id is not None:
            rows = [row for row in rows if str(row.get("workspace_id") or "") == str(workspace_id)]
        if scope is not None:
            rows = [row for row in rows if str(row.get("key_scope") or "") == str(scope)]
        return [self._to_entity(row) for row in rows]

    def get_encryption_key(self, key_id: str) -> DataEncryptionKeyEntity | None:
        row = next((item for item in self._encryption_keys if str(item.get("id") or "") == str(key_id)), None)
        if row is None:
            return None
        return self._to_entity(row)

    def create_encryption_key(self, payload: dict[str, object], *, created_by: str | None = None) -> DataEncryptionKeyEntity:
        key_name = str(payload.get("key_name") or payload.get("keyName") or "").strip()
        if not key_name:
            raise ValueError("key_name is required")
        key_material = str(payload.get("key_material") or payload.get("keyMaterial") or "").strip()
        if not key_material:
            raise ValueError("key_material is required")

        key_scope = str(payload.get("key_scope") or payload.get("keyScope") or "app").strip().lower() or "app"
        workspace_id = str(payload.get("workspace_id") or payload.get("workspaceId") or "").strip() or None
        key_algorithm = str(payload.get("key_algorithm") or payload.get("keyAlgorithm") or "fernet").strip().lower() or "fernet"
        is_active_raw = payload.get("is_active") if "is_active" in payload else payload.get("isActive")
        is_active = True if is_active_raw is None else bool(is_active_raw)

        row = {
            "id": f"dek-{uuid4().hex[:12]}",
            "key_name": key_name,
            "key_scope": key_scope,
            "workspace_id": workspace_id,
            "key_algorithm": key_algorithm,
            "key_material_encrypted": self._field_encryptor.encrypt_value(key_material),
            "key_fingerprint": sha256(key_material.encode("utf-8")).hexdigest()[:16],
            "is_active": is_active,
            "created_by": created_by,
            "created_at": "2026-05-25T00:00:00Z",
            "updated_at": "2026-05-25T00:00:00Z",
        }
        self._encryption_keys.append(row)
        return self._to_entity(row)

    @staticmethod
    def _to_entity(row: dict[str, object]) -> DataEncryptionKeyEntity:
        return DataEncryptionKeyEntity(
            id=str(row.get("id") or ""),
            keyName=str(row.get("key_name") or ""),
            keyScope=str(row.get("key_scope") or "app"),
            workspaceId=str(row.get("workspace_id") or "").strip() or None,
            keyAlgorithm=str(row.get("key_algorithm") or "fernet"),
            keyFingerprint=str(row.get("key_fingerprint") or ""),
            isActive=bool(row.get("is_active")) if row.get("is_active") is not None else True,
            createdBy=str(row.get("created_by") or "").strip() or None,
            createdAt=str(row.get("created_at") or ""),
            updatedAt=str(row.get("updated_at") or ""),
        )