from __future__ import annotations

from app.application.services.ui_registry import RegistryManifest
from app.domain.interfaces.v1.ui_registry_repository import UiRegistryRepository


class InMemoryUiRegistryRepository(UiRegistryRepository):
    def __init__(self, manifest: RegistryManifest | None = None) -> None:
        self.manifest = manifest

    def get_current_manifest(self) -> RegistryManifest | None:
        return self.manifest

    def upsert_current_manifest(
        self,
        manifest: RegistryManifest,
        *,
        source_type: str | None,
        source_ref: str | None = None,
    ) -> RegistryManifest:
        saved = RegistryManifest.from_dict(manifest.to_dict())
        saved.metadata.update(
            {
                "stored_in_database": True,
                "storage_table": "ui_registry_manifest",
                "source_type": source_type,
                "source_ref": source_ref,
            }
        )
        self.manifest = saved
        return saved