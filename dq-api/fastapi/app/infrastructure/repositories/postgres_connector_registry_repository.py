from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from app.domain.entities.connector import ConnectorRegistryEntryEntity
from app.domain.interfaces.v1.connector_registry_repository import ConnectorRegistryRepository
from app.infrastructure.orm.models import ConnectorRegistryRow
from app.infrastructure.orm.session import session_scope


def _row_from_entry(entry: ConnectorRegistryEntryEntity) -> ConnectorRegistryRow:
    now = datetime.now(UTC)
    return ConnectorRegistryRow(
        provider=str(entry.provider).strip().lower(),
        display_name=str(entry.display_name or "").strip(),
        description=str(entry.description or "").strip() or None,
        implementation_path=str(entry.implementation_path or "").strip() or None,
        capabilities_json=entry.capabilities.model_dump(mode="python", by_alias=False, exclude_none=True),
        supported_asset_kinds_json=list(entry.supported_asset_kinds),
        registered_at=now,
        updated_at=now,
    )


def _entry_from_row(row: ConnectorRegistryRow) -> ConnectorRegistryEntryEntity:
    return ConnectorRegistryEntryEntity.model_validate(
        {
            "provider": str(row.provider or "").strip().lower(),
            "display_name": str(row.display_name or "").strip(),
            "description": str(row.description or "").strip() or None,
            "implementation_path": str(row.implementation_path or "").strip() or None,
            "capabilities": row.capabilities_json or {},
            "supported_asset_kinds": row.supported_asset_kinds_json or [],
        }
    )


class PostgresConnectorRegistryRepository(ConnectorRegistryRepository):
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def upsert_entry(self, entry: ConnectorRegistryEntryEntity) -> ConnectorRegistryEntryEntity:
        provider = str(entry.provider or "").strip().lower()
        if not provider:
            raise ValueError("connector registry entry requires provider")

        with session_scope(self.database_url) as session:
            row = session.execute(
                select(ConnectorRegistryRow).where(ConnectorRegistryRow.provider == provider)
            ).scalar_one_or_none()
            if row is None:
                row = _row_from_entry(entry)
                session.add(row)
            else:
                row.display_name = str(entry.display_name or "").strip()
                row.description = str(entry.description or "").strip() or None
                row.implementation_path = str(entry.implementation_path or "").strip() or None
                row.capabilities_json = entry.capabilities.model_dump(mode="python", by_alias=False, exclude_none=True)
                row.supported_asset_kinds_json = list(entry.supported_asset_kinds)
                row.updated_at = datetime.now(UTC)
            session.commit()
            return _entry_from_row(row)

    def list_entries(self) -> list[ConnectorRegistryEntryEntity]:
        with session_scope(self.database_url) as session:
            rows = session.execute(
                select(ConnectorRegistryRow).order_by(
                    ConnectorRegistryRow.display_name.asc(),
                    ConnectorRegistryRow.provider.asc(),
                )
            ).scalars().all()
            return [_entry_from_row(row) for row in rows]

    def get_entry(self, provider: str) -> ConnectorRegistryEntryEntity | None:
        normalized_provider = str(provider or "").strip().lower()
        if not normalized_provider:
            return None

        with session_scope(self.database_url) as session:
            row = session.execute(
                select(ConnectorRegistryRow).where(ConnectorRegistryRow.provider == normalized_provider)
            ).scalar_one_or_none()
            if row is None:
                return None
            return _entry_from_row(row)