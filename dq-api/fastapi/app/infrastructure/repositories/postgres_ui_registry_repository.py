from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from app.application.services.ui_registry import RegistryManifest
from app.domain.interfaces.v1.ui_registry_repository import UiRegistryRepository
from app.infrastructure.orm.models import UiRegistryManifestRow
from app.infrastructure.orm.session import session_scope


def _manifest_from_row(row: UiRegistryManifestRow) -> RegistryManifest:
    manifest = RegistryManifest.from_dict(row.manifest_json or {})
    manifest.metadata.update(
        {
            "stored_in_database": True,
            "storage_table": "ui_registry_manifest",
            "manifest_key": str(row.manifest_key or "current"),
            "source_type": str(row.source_type or "default"),
            "source_ref": str(row.source_ref or "") or None,
            "persisted_at": row.persisted_at.isoformat() if row.persisted_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }
    )
    return manifest


def _row_from_manifest(
    manifest: RegistryManifest,
    *,
    manifest_key: str,
    source_type: str | None,
    source_ref: str | None,
) -> UiRegistryManifestRow:
    now = datetime.now(UTC)
    return UiRegistryManifestRow(
        manifest_key=manifest_key,
        source_type=source_type,
        source_ref=source_ref,
        manifest_version=str(manifest.version or "1.0.0"),
        manifest_json=manifest.to_dict(),
        persisted_at=now,
        updated_at=now,
    )


class PostgresUiRegistryRepository(UiRegistryRepository):
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def get_current_manifest(self) -> RegistryManifest | None:
        with session_scope(self.database_url) as session:
            row = session.execute(
                select(UiRegistryManifestRow).where(UiRegistryManifestRow.manifest_key == "current")
            ).scalar_one_or_none()
            if row is None:
                return None
            return _manifest_from_row(row)

    def upsert_current_manifest(
        self,
        manifest: RegistryManifest,
        *,
        source_type: str | None,
        source_ref: str | None = None,
    ) -> RegistryManifest:
        with session_scope(self.database_url) as session:
            row = session.execute(
                select(UiRegistryManifestRow).where(UiRegistryManifestRow.manifest_key == "current")
            ).scalar_one_or_none()
            if row is None:
                row = _row_from_manifest(
                    manifest,
                    manifest_key="current",
                    source_type=source_type,
                    source_ref=source_ref,
                )
                session.add(row)
            else:
                row.source_type = source_type
                row.source_ref = source_ref
                row.manifest_version = str(manifest.version or "1.0.0")
                row.manifest_json = manifest.to_dict()
                row.updated_at = datetime.now(UTC)
                if row.persisted_at is None:
                    row.persisted_at = row.updated_at
            session.commit()
            return _manifest_from_row(row)