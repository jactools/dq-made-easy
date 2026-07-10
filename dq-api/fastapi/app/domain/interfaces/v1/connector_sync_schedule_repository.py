from __future__ import annotations

from typing import Protocol

from app.domain.entities.connector_sync import ConnectorSyncScheduleEntity


class ConnectorSyncScheduleRepository(Protocol):
    def create_schedule(self, schedule: ConnectorSyncScheduleEntity) -> ConnectorSyncScheduleEntity: ...

    def get_schedule(self, schedule_id: str) -> ConnectorSyncScheduleEntity | None: ...

    def list_schedules(
        self,
        *,
        connector_instance_id: str | None = None,
        provider: str | None = None,
        is_active: bool | None = None,
        workspace_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ConnectorSyncScheduleEntity]: ...

    def update_schedule(
        self,
        schedule_id: str,
        *,
        is_active: bool | None = None,
        next_run_at: str | None = None,
        last_run_at: str | None = None,
        last_job_id: str | None = None,
    ) -> ConnectorSyncScheduleEntity | None: ...

    def delete_schedule(self, schedule_id: str) -> bool: ...

    def list_due_schedules(self) -> list[ConnectorSyncScheduleEntity]: ...
