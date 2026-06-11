from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select, delete
from sqlalchemy.dialects.postgresql import insert

from app.domain.entities.monitor_schedule import MonitorScheduleEntity
from app.domain.interfaces.v1.monitor_schedule_repository import MonitorScheduleRepository
from app.infrastructure.orm.models import MonitorScheduleRow
from app.infrastructure.orm.session import session_scope


def _row_to_entity(row: MonitorScheduleRow) -> MonitorScheduleEntity:
    return MonitorScheduleEntity(
        id=str(row.id or ""),
        scope_kind=str(row.scope_kind or ""),
        scope_id=str(row.scope_id or ""),
        workspace_id=str(row.workspace_id or ""),
        monitor_type=str(row.monitor_type or "scheduled_monitor"),
        cron_expression=str(row.cron_expression or ""),
        timezone=str(row.timezone or "UTC"),
        window_minutes=int(row.window_minutes or 1440),
        enabled=bool(row.enabled),
        signals=list(row.signals) if row.signals is not None else None,
        created_by=str(row.created_by) if row.created_by else None,
        created_at=row.created_at.isoformat() if row.created_at else None,
        updated_by=str(row.updated_by) if row.updated_by else None,
        updated_at=row.updated_at.isoformat() if row.updated_at else None,
    )


class PostgresMonitorScheduleRepository(MonitorScheduleRepository):
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def list_monitor_schedules(
        self, workspace_id: str | None = None
    ) -> list[MonitorScheduleEntity]:
        with session_scope(self.database_url) as session:
            stmt = select(MonitorScheduleRow)
            if workspace_id:
                stmt = stmt.where(MonitorScheduleRow.workspace_id == workspace_id)
            rows = session.execute(stmt).scalars().all()
            return [_row_to_entity(row) for row in rows]

    def get_monitor_schedule(
        self, scope_kind: str, scope_id: str
    ) -> MonitorScheduleEntity | None:
        with session_scope(self.database_url) as session:
            row = session.execute(
                select(MonitorScheduleRow).where(
                    MonitorScheduleRow.scope_kind == scope_kind,
                    MonitorScheduleRow.scope_id == scope_id,
                )
            ).scalar_one_or_none()
            if row is None:
                return None
            return _row_to_entity(row)

    def upsert_monitor_schedule(
        self, entity: MonitorScheduleEntity
    ) -> MonitorScheduleEntity:
        now = datetime.now(tz=timezone.utc).replace(tzinfo=None)
        schedule_id = entity.id or str(uuid4())
        with session_scope(self.database_url) as session:
            stmt = insert(MonitorScheduleRow).values(
                id=schedule_id,
                scope_kind=entity.scope_kind,
                scope_id=entity.scope_id,
                workspace_id=entity.workspace_id,
                monitor_type=entity.monitor_type or "scheduled_monitor",
                cron_expression=entity.cron_expression,
                timezone=entity.timezone or "UTC",
                window_minutes=entity.window_minutes or 1440,
                enabled=entity.enabled,
                signals=entity.signals,
                created_by=entity.created_by,
                created_at=now,
                updated_by=entity.updated_by,
                updated_at=now,
            )
            stmt = stmt.on_conflict_do_update(
                constraint="uq_monitor_schedules_scope",
                set_={
                    "monitor_type": stmt.excluded.monitor_type,
                    "cron_expression": stmt.excluded.cron_expression,
                    "timezone": stmt.excluded.timezone,
                    "window_minutes": stmt.excluded.window_minutes,
                    "enabled": stmt.excluded.enabled,
                    "signals": stmt.excluded.signals,
                    "updated_by": stmt.excluded.updated_by,
                    "updated_at": stmt.excluded.updated_at,
                },
            )
            session.execute(stmt)
            session.commit()
        return self.get_monitor_schedule(entity.scope_kind, entity.scope_id) or MonitorScheduleEntity(
            id=schedule_id,
            scope_kind=entity.scope_kind,
            scope_id=entity.scope_id,
            workspace_id=entity.workspace_id,
            monitor_type=entity.monitor_type or "scheduled_monitor",
            cron_expression=entity.cron_expression,
            timezone=entity.timezone or "UTC",
            window_minutes=entity.window_minutes or 1440,
            enabled=entity.enabled,
            signals=entity.signals,
            created_by=entity.created_by,
            updated_by=entity.updated_by,
            updated_at=now.isoformat(),
        )

    def delete_monitor_schedule(self, scope_kind: str, scope_id: str) -> None:
        with session_scope(self.database_url) as session:
            session.execute(
                delete(MonitorScheduleRow).where(
                    MonitorScheduleRow.scope_kind == scope_kind,
                    MonitorScheduleRow.scope_id == scope_id,
                )
            )
            session.commit()
