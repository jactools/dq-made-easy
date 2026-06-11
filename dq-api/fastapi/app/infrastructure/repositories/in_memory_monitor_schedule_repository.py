from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from app.domain.entities.monitor_schedule import MonitorScheduleEntity
from app.domain.interfaces.v1.monitor_schedule_repository import MonitorScheduleRepository


class InMemoryMonitorScheduleRepository(MonitorScheduleRepository):
    """In-memory repository for unit tests."""

    def __init__(self) -> None:
        # key: (scope_kind, scope_id) → entity
        self._store: dict[tuple[str, str], MonitorScheduleEntity] = {}

    def list_monitor_schedules(
        self, workspace_id: str | None = None
    ) -> list[MonitorScheduleEntity]:
        rows = list(self._store.values())
        if workspace_id:
            rows = [r for r in rows if r.workspace_id == workspace_id]
        return rows

    def get_monitor_schedule(
        self, scope_kind: str, scope_id: str
    ) -> MonitorScheduleEntity | None:
        return self._store.get((scope_kind, scope_id))

    def upsert_monitor_schedule(
        self, entity: MonitorScheduleEntity
    ) -> MonitorScheduleEntity:
        now = datetime.now(tz=timezone.utc).isoformat()
        saved = MonitorScheduleEntity(
            id=entity.id or str(uuid4()),
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
        self._store[(entity.scope_kind, entity.scope_id)] = saved
        return saved

    def delete_monitor_schedule(self, scope_kind: str, scope_id: str) -> None:
        self._store.pop((scope_kind, scope_id), None)
