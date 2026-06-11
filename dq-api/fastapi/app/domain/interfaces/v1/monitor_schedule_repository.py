from typing import Protocol

from app.domain.entities.monitor_schedule import MonitorScheduleEntity


class MonitorScheduleRepository(Protocol):
    def list_monitor_schedules(
        self, workspace_id: str | None = None
    ) -> list[MonitorScheduleEntity]: ...

    def get_monitor_schedule(
        self, scope_kind: str, scope_id: str
    ) -> MonitorScheduleEntity | None: ...

    def upsert_monitor_schedule(
        self, entity: MonitorScheduleEntity
    ) -> MonitorScheduleEntity: ...

    def delete_monitor_schedule(self, scope_kind: str, scope_id: str) -> None: ...
