"""Postgres-backed connector sync schedule repository."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select, delete

from app.domain.entities.connector_sync import ConnectorSyncScheduleEntity
from app.domain.interfaces.v1.connector_sync_schedule_repository import (
    ConnectorSyncScheduleRepository as ConnectorSyncScheduleRepositoryProtocol,
)
from app.infrastructure.orm.models import ConnectorSyncScheduleRow
from app.infrastructure.orm.session import session_scope


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _now_dt() -> datetime:
    return datetime.now(UTC)


def _row_from_entity(e: ConnectorSyncScheduleEntity) -> ConnectorSyncScheduleRow:
    return ConnectorSyncScheduleRow(
        id=str(e.id or uuid4()).strip(),
        connector_instance_id=str(e.connector_instance_id).strip(),
        provider=str(e.provider).strip().lower(),
        frequency=str(e.frequency).strip(),
        cron_expression=e.cron_expression,
        interval_count=int(e.interval_count or 1),
        next_run_at=_parse_iso(e.next_run_at) if e.next_run_at else None,
        last_run_at=_parse_iso(e.last_run_at) if e.last_run_at else None,
        last_job_id=e.last_job_id,
        is_active=bool(e.is_active),
        timezone=str(e.timezone or "UTC").strip(),
        workspace_id=str(e.workspace_id or "").strip() or None,
        tenant_id=str(e.tenant_id or "").strip() or None,
        created_at=_parse_iso(e.created_at) if e.created_at else _now_dt(),
        updated_at=_parse_iso(e.updated_at) if e.updated_at else _now_dt(),
    )


def _entity_from_row(row: ConnectorSyncScheduleRow) -> ConnectorSyncScheduleEntity:
    return ConnectorSyncScheduleEntity.model_validate(
        {
            "id": str(row.id or "").strip(),
            "connector_instance_id": str(row.connector_instance_id or "").strip(),
            "provider": (row.provider or "").strip().lower(),
            "frequency": str(row.frequency or "").strip(),
            "cron_expression": row.cron_expression,
            "interval_count": row.interval_count or 1,
            "next_run_at": row.next_run_at.isoformat() if row.next_run_at else None,
            "last_run_at": row.last_run_at.isoformat() if row.last_run_at else None,
            "last_job_id": row.last_job_id,
            "is_active": row.is_active,
            "timezone": str(row.timezone or "UTC").strip(),
            "workspace_id": str(row.workspace_id or "").strip() or None,
            "tenant_id": str(row.tenant_id or "").strip() or None,
            "created_at": row.created_at.isoformat() if row.created_at else _now_iso(),
            "updated_at": row.updated_at.isoformat() if row.updated_at else _now_iso(),
        }
    )


def _parse_iso(value: str) -> datetime:
    stripped = str(value).strip()
    return datetime.fromisoformat(stripped) if stripped else _now_dt()


class PostgresConnectorSyncScheduleRepository(ConnectorSyncScheduleRepositoryProtocol):
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def create_schedule(self, schedule: ConnectorSyncScheduleEntity) -> ConnectorSyncScheduleEntity:
        with session_scope(self.database_url) as session:
            row = _row_from_entity(schedule)
            session.add(row)
            session.commit()
            return _entity_from_row(row)

    def get_schedule(self, schedule_id: str) -> ConnectorSyncScheduleEntity | None:
        if not schedule_id:
            return None
        with session_scope(self.database_url) as session:
            row = session.execute(
                select(ConnectorSyncScheduleRow).where(
                    ConnectorSyncScheduleRow.id == schedule_id.strip()
                )
            ).scalar_one_or_none()
            return _entity_from_row(row) if row else None

    def list_schedules(
        self,
        *,
        connector_instance_id: str | None = None,
        provider: str | None = None,
        is_active: bool | None = None,
        workspace_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ConnectorSyncScheduleEntity]:
        safe_limit = max(0, min(int(limit), 1000))
        safe_offset = max(0, int(offset))
        with session_scope(self.database_url) as session:
            stmt = select(ConnectorSyncScheduleRow)
            if connector_instance_id:
                stmt = stmt.where(
                    ConnectorSyncScheduleRow.connector_instance_id
                    == str(connector_instance_id).strip()
                )
            if provider:
                stmt = stmt.where(
                    ConnectorSyncScheduleRow.provider == str(provider).strip().lower()
                )
            if is_active is not None:
                stmt = stmt.where(ConnectorSyncScheduleRow.is_active == is_active)
            if workspace_id:
                stmt = stmt.where(
                    ConnectorSyncScheduleRow.workspace_id == str(workspace_id).strip()
                )
            rows = session.execute(
                stmt.order_by(
                    ConnectorSyncScheduleRow.created_at.desc(),
                )
                .offset(safe_offset)
                .limit(safe_limit)
            ).scalars().all()
            return [_entity_from_row(r) for r in rows]

    def update_schedule(
        self,
        schedule_id: str,
        *,
        is_active: bool | None = None,
        next_run_at: str | None = None,
        last_run_at: str | None = None,
        last_job_id: str | None = None,
    ) -> ConnectorSyncScheduleEntity | None:
        if not schedule_id:
            return None
        with session_scope(self.database_url) as session:
            row = session.execute(
                select(ConnectorSyncScheduleRow).where(
                    ConnectorSyncScheduleRow.id == schedule_id.strip()
                )
            ).scalar_one_or_none()
            if row is None:
                return None
            if is_active is not None:
                row.is_active = is_active
            if next_run_at is not None:
                row.next_run_at = _parse_iso(next_run_at) if next_run_at else None
            if last_run_at is not None:
                row.last_run_at = _parse_iso(last_run_at) if last_run_at else None
            row.last_job_id = last_job_id
            row.updated_at = _now_dt()
            session.commit()
            return _entity_from_row(row)

    def delete_schedule(self, schedule_id: str) -> bool:
        if not schedule_id:
            return False
        with session_scope(self.database_url) as session:
            result = session.execute(
                delete(ConnectorSyncScheduleRow).where(
                    ConnectorSyncScheduleRow.id == schedule_id.strip()
                )
            )
            session.commit()
            return result.rowcount > 0

    def list_due_schedules(self) -> list[ConnectorSyncScheduleEntity]:
        now = _now_dt()
        with session_scope(self.database_url) as session:
            rows = session.execute(
                select(ConnectorSyncScheduleRow)
                .where(
                    ConnectorSyncScheduleRow.is_active.is_(True),
                    ConnectorSyncScheduleRow.next_run_at.isnot(None),
                    ConnectorSyncScheduleRow.next_run_at <= now,
                )
                .order_by(ConnectorSyncScheduleRow.next_run_at.asc())
                .limit(50)
            ).scalars().all()
            return [_entity_from_row(r) for r in rows]
