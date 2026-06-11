from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select

from app.domain.entities.connector import ConnectorInstanceEntity
from app.domain.interfaces.v1.connector_instance_repository import ConnectorInstanceRepository
from app.infrastructure.orm.models import ConnectorInstanceRow
from app.infrastructure.orm.session import session_scope


def _normalized(value: str | None) -> str:
    return str(value or "").strip().lower()


def _row_from_instance(instance: ConnectorInstanceEntity) -> ConnectorInstanceRow:
    created_at = instance.created_at.strip() if isinstance(instance.created_at, str) else str(instance.created_at or "").strip()
    updated_at = instance.updated_at.strip() if isinstance(instance.updated_at, str) else str(instance.updated_at or "").strip()
    now = datetime.now(UTC)
    return ConnectorInstanceRow(
        id=str(instance.id or uuid4()).strip(),
        provider=_normalized(instance.provider),
        display_name=str(instance.display_name or "").strip(),
        workspace_id=str(instance.workspace_id or "").strip() or None,
        tenant_id=str(instance.tenant_id or "").strip() or None,
        configuration_json=dict(instance.configuration or {}),
        created_at=datetime.fromisoformat(created_at) if created_at else now,
        updated_at=datetime.fromisoformat(updated_at) if updated_at else now,
    )


def _instance_from_row(row: ConnectorInstanceRow) -> ConnectorInstanceEntity:
    return ConnectorInstanceEntity.model_validate(
        {
            "id": str(row.id or "").strip(),
            "provider": _normalized(row.provider),
            "display_name": str(row.display_name or "").strip(),
            "workspace_id": str(row.workspace_id or "").strip() or None,
            "tenant_id": str(row.tenant_id or "").strip() or None,
            "configuration": row.configuration_json or {},
            "created_at": row.created_at.isoformat(),
            "updated_at": row.updated_at.isoformat(),
        }
    )


class PostgresConnectorInstanceRepository(ConnectorInstanceRepository):
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def upsert_instance(self, instance: ConnectorInstanceEntity) -> ConnectorInstanceEntity:
        provider = _normalized(instance.provider)
        display_name = str(instance.display_name or "").strip()
        workspace_id = str(instance.workspace_id or "").strip() or None
        tenant_id = str(instance.tenant_id or "").strip() or None
        if not provider:
            raise ValueError("connector instance requires provider")
        if not display_name:
            raise ValueError("connector instance requires display_name")

        with session_scope(self.database_url) as session:
            row = session.execute(
                select(ConnectorInstanceRow).where(
                    ConnectorInstanceRow.provider == provider,
                    ConnectorInstanceRow.display_name == display_name,
                    ConnectorInstanceRow.workspace_id == workspace_id,
                    ConnectorInstanceRow.tenant_id == tenant_id,
                )
            ).scalar_one_or_none()
            if row is None:
                row = _row_from_instance(
                    ConnectorInstanceEntity(
                        id=str(instance.id or uuid4()),
                        provider=provider,
                        display_name=display_name,
                        workspace_id=workspace_id,
                        tenant_id=tenant_id,
                        configuration=dict(instance.configuration or {}),
                        created_at=instance.created_at or datetime.now(UTC).isoformat(),
                        updated_at=instance.updated_at or datetime.now(UTC).isoformat(),
                    )
                )
                session.add(row)
            else:
                row.provider = provider
                row.display_name = display_name
                row.workspace_id = workspace_id
                row.tenant_id = tenant_id
                row.configuration_json = dict(instance.configuration or {})
                row.updated_at = datetime.now(UTC)
            session.commit()
            return _instance_from_row(row)

    def list_instances(
        self,
        *,
        provider: str | None = None,
        workspace_id: str | None = None,
        tenant_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ConnectorInstanceEntity]:
        safe_limit = max(0, min(int(limit), 1000))
        safe_offset = max(0, int(offset))
        with session_scope(self.database_url) as session:
            stmt = select(ConnectorInstanceRow)
            if provider is not None:
                stmt = stmt.where(ConnectorInstanceRow.provider == _normalized(provider))
            if workspace_id is not None:
                stmt = stmt.where(ConnectorInstanceRow.workspace_id == str(workspace_id).strip() or None)
            if tenant_id is not None:
                stmt = stmt.where(ConnectorInstanceRow.tenant_id == str(tenant_id).strip() or None)
            rows = session.execute(
                stmt.order_by(
                    ConnectorInstanceRow.updated_at.desc(),
                    ConnectorInstanceRow.display_name.asc(),
                    ConnectorInstanceRow.id.asc(),
                ).offset(safe_offset).limit(safe_limit)
            ).scalars().all()
            return [_instance_from_row(row) for row in rows]

    def get_instance(self, instance_id: str) -> ConnectorInstanceEntity | None:
        normalized_instance_id = str(instance_id or "").strip()
        if not normalized_instance_id:
            return None
        with session_scope(self.database_url) as session:
            row = session.execute(
                select(ConnectorInstanceRow).where(ConnectorInstanceRow.id == normalized_instance_id)
            ).scalar_one_or_none()
            if row is None:
                return None
            return _instance_from_row(row)