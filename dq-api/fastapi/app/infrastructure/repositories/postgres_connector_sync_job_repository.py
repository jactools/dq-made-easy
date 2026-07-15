"""Postgres-backed connector sync job repository."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select, update, func

from app.domain.entities.connector_sync import ConnectorJobStatus
from app.domain.entities.connector_sync import ConnectorSyncJobEntity
from app.domain.interfaces.v1.connector_sync_job_repository import (
    ConnectorSyncJobRepository as ConnectorSyncJobRepositoryProtocol,
)
from app.infrastructure.orm.models import ConnectorSyncJobRow
from app.infrastructure.orm.session import session_scope


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _now_dt() -> datetime:
    return datetime.now(UTC)


def _row_from_entity(e: ConnectorSyncJobEntity) -> ConnectorSyncJobRow:
    return ConnectorSyncJobRow(
        id=str(e.id or uuid4()).strip(),
        connector_instance_id=str(e.connector_instance_id).strip(),
        provider=str(e.provider).strip().lower(),
        kind=str(e.kind).strip(),
        trigger=str(e.trigger).strip(),
        status=str(e.status).strip(),
        retry_count=int(e.retry_count or 0),
        max_retries=int(e.max_retries or 3),
        synced_count=int(e.synced_count or 0),
        added_count=int(e.added_count or 0),
        updated_count=int(e.updated_count or 0),
        removed_count=int(e.removed_count or 0),
        error_code=e.error_code,
        error_message=e.error_message,
        error_details=e.error_details or {},
        result_snapshot=e.result_snapshot or {},
        workspace_id=str(e.workspace_id or "").strip() or None,
        tenant_id=str(e.tenant_id or "").strip() or None,
        started_at=_parse_iso(e.started_at) if e.started_at else None,
        completed_at=_parse_iso(e.completed_at) if e.completed_at else None,
        created_at=_parse_iso(e.created_at) if e.created_at else _now_dt(),
        updated_at=_parse_iso(e.updated_at) if e.updated_at else _now_dt(),
    )


def _entity_from_row(row: ConnectorSyncJobRow) -> ConnectorSyncJobEntity:
    return ConnectorSyncJobEntity.model_validate(
        {
            "id": str(row.id or "").strip(),
            "connector_instance_id": str(row.connector_instance_id or "").strip(),
            "provider": (row.provider or "").strip().lower(),
            "kind": str(row.kind or "").strip(),
            "trigger": str(row.trigger or "").strip(),
            "status": str(row.status or "").strip(),
            "retry_count": row.retry_count or 0,
            "max_retries": row.max_retries or 3,
            "synced_count": row.synced_count or 0,
            "added_count": row.added_count or 0,
            "updated_count": row.updated_count or 0,
            "removed_count": row.removed_count or 0,
            "error_code": row.error_code,
            "error_message": row.error_message,
            "error_details": row.error_details or {},
            "result_snapshot": row.result_snapshot or {},
            "workspace_id": str(row.workspace_id or "").strip() or None,
            "tenant_id": str(row.tenant_id or "").strip() or None,
            "started_at": row.started_at.isoformat() if row.started_at else None,
            "completed_at": row.completed_at.isoformat() if row.completed_at else None,
            "created_at": row.created_at.isoformat() if row.created_at else _now_iso(),
            "updated_at": row.updated_at.isoformat() if row.updated_at else _now_iso(),
        }
    )


def _parse_iso(value: str) -> datetime:
    stripped = str(value).strip()
    return datetime.fromisoformat(stripped) if stripped else _now_dt()


class PostgresConnectorSyncJobRepository(ConnectorSyncJobRepositoryProtocol):
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def create_job(self, job: ConnectorSyncJobEntity) -> ConnectorSyncJobEntity:
        with session_scope(self.database_url) as session:
            row = _row_from_entity(job)
            session.add(row)
            session.commit()
            return _entity_from_row(row)

    def get_job(self, job_id: str) -> ConnectorSyncJobEntity | None:
        if not job_id:
            return None
        with session_scope(self.database_url) as session:
            row = session.execute(
                select(ConnectorSyncJobRow).where(ConnectorSyncJobRow.id == job_id.strip())
            ).scalar_one_or_none()
            return _entity_from_row(row) if row else None

    def list_jobs(
        self,
        *,
        connector_instance_id: str | None = None,
        provider: str | None = None,
        status: ConnectorJobStatus | None = None,
        workspace_id: str | None = None,
        tenant_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ConnectorSyncJobEntity]:
        safe_limit = max(0, min(int(limit), 1000))
        safe_offset = max(0, int(offset))
        with session_scope(self.database_url) as session:
            stmt = select(ConnectorSyncJobRow)
            if connector_instance_id:
                stmt = stmt.where(
                    ConnectorSyncJobRow.connector_instance_id == str(connector_instance_id).strip()
                )
            if provider:
                stmt = stmt.where(
                    ConnectorSyncJobRow.provider == str(provider).strip().lower()
                )
            if status:
                stmt = stmt.where(ConnectorSyncJobRow.status == status)
            if workspace_id:
                stmt = stmt.where(
                    ConnectorSyncJobRow.workspace_id == str(workspace_id).strip()
                )
            if tenant_id:
                stmt = stmt.where(
                    ConnectorSyncJobRow.tenant_id == str(tenant_id).strip()
                )
            rows = session.execute(
                stmt.order_by(
                    ConnectorSyncJobRow.created_at.desc(),
                )
                .offset(safe_offset)
                .limit(safe_limit)
            ).scalars().all()
            return [_entity_from_row(r) for r in rows]

    def update_status(
        self,
        job_id: str,
        status: ConnectorJobStatus,
        *,
        error_code: str | None = None,
        error_message: str | None = None,
        synced_count: int | None = None,
        added_count: int | None = None,
        updated_count: int | None = None,
        removed_count: int | None = None,
        result_snapshot: dict | None = None,
    ) -> ConnectorSyncJobEntity | None:
        if not job_id:
            return None
        with session_scope(self.database_url) as session:
            row = session.execute(
                select(ConnectorSyncJobRow).where(ConnectorSyncJobRow.id == job_id.strip())
            ).scalar_one_or_none()
            if row is None:
                return None
            row.status = status
            row.updated_at = _now_dt()
            if error_code is not None:
                row.error_code = error_code
            if error_message is not None:
                row.error_message = error_message
            if synced_count is not None:
                row.synced_count = synced_count
            if added_count is not None:
                row.added_count = added_count
            if updated_count is not None:
                row.updated_count = updated_count
            if removed_count is not None:
                row.removed_count = removed_count
            if result_snapshot is not None:
                row.result_snapshot = result_snapshot
            if status in ("running", "retrying"):
                row.started_at = row.started_at or _now_dt()
            if status in ("completed", "failed", "cancelled"):
                row.completed_at = _now_dt()
                if status == "failed" and row.started_at and row.started_at:
                    row.retry_count = row.retry_count + 1
            session.commit()
            return _entity_from_row(row)

    def claim_pending(self, provider: str | None = None) -> ConnectorSyncJobEntity | None:
        with session_scope(self.database_url) as session:
            stmt = (
                select(ConnectorSyncJobRow)
                .where(ConnectorSyncJobRow.status == "pending")
                .order_by(ConnectorSyncJobRow.created_at.asc())
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            if provider:
                stmt = stmt.where(
                    ConnectorSyncJobRow.provider == str(provider).strip().lower()
                )
            row = session.execute(stmt).scalar_one_or_none()
            if row is None:
                return None
            row.status = "running"
            row.started_at = _now_dt()
            row.updated_at = _now_dt()
            session.commit()
            return _entity_from_row(row)

    def list_stale_jobs(
        self,
        *,
        max_age_seconds: int = 86400,
    ) -> list[ConnectorSyncJobEntity]:
        with session_scope(self.database_url) as session:
            cutoff = _now_dt() - func.interval(f"{max_age_seconds} seconds")
            rows = session.execute(
                select(ConnectorSyncJobRow)
                .where(
                    ConnectorSyncJobRow.status.in_(("pending", "running", "retrying")),
                    ConnectorSyncJobRow.created_at < cutoff,
                )
                .order_by(ConnectorSyncJobRow.created_at.asc())
            ).scalars().all()
            return [_entity_from_row(r) for r in rows]
