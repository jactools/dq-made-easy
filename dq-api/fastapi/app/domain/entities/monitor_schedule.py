from __future__ import annotations

from typing import Any

from app.domain.entities.base import EntityModel


class MonitorScheduleEntity(EntityModel):
    id: str
    scope_kind: str
    scope_id: str
    workspace_id: str
    monitor_type: str = "scheduled_monitor"
    cron_expression: str
    timezone: str = "UTC"
    window_minutes: int = 1440
    enabled: bool = True
    signals: list[str] | None = None
    created_by: str | None = None
    created_at: str | None = None
    updated_by: str | None = None
    updated_at: str | None = None
