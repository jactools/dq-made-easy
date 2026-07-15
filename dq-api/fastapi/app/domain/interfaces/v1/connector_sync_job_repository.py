from __future__ import annotations

from typing import Protocol

from app.domain.entities.connector_sync import ConnectorJobStatus
from app.domain.entities.connector_sync import ConnectorSyncJobEntity


class ConnectorSyncJobRepository(Protocol):
    def create_job(self, job: ConnectorSyncJobEntity) -> ConnectorSyncJobEntity: ...

    def get_job(self, job_id: str) -> ConnectorSyncJobEntity | None: ...

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
    ) -> list[ConnectorSyncJobEntity]: ...

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
    ) -> ConnectorSyncJobEntity | None: ...

    def claim_pending(self, provider: str | None = None) -> ConnectorSyncJobEntity | None: ...

    def list_stale_jobs(
        self,
        *,
        max_age_seconds: int = 86400,
    ) -> list[ConnectorSyncJobEntity]: ...
