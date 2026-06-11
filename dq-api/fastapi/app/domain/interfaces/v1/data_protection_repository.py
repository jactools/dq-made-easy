from typing import Any, Protocol

from app.domain.entities.data_protection import DataEncryptionKeyEntity


class DataProtectionRepository(Protocol):
    def list_encryption_keys(
        self,
        workspace_id: str | None = None,
        scope: str | None = None,
    ) -> list[DataEncryptionKeyEntity]: ...

    def get_encryption_key(self, key_id: str) -> DataEncryptionKeyEntity | None: ...

    def create_encryption_key(self, payload: dict[str, Any], *, created_by: str | None = None) -> DataEncryptionKeyEntity: ...