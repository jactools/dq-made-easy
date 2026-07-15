"""Connector sync orchestrator — manages background sync jobs and scheduling."""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from app.domain.entities.connector import ConnectorInstanceEntity
from app.domain.entities.connector_sync import (
    ConnectorAssetSnapshotEntity,
    ConnectorJobKind,
    ConnectorJobStatus,
    ConnectorJobTrigger,
    ConnectorRetryPolicyEntity,
    ConnectorSyncJobEntity,
    ConnectorSyncJobView,
    ConnectorSyncScheduleEntity,
    ConnectorSyncScheduleView,
)
from app.domain.interfaces.v1.connector import Connector as ConnectorService
from app.domain.interfaces.v1.connector_instance_repository import ConnectorInstanceRepository
from app.domain.interfaces.v1.connector_sync_job_repository import ConnectorSyncJobRepository
from app.domain.interfaces.v1.connector_sync_schedule_repository import ConnectorSyncScheduleRepository

logger = logging.getLogger(__name__)

SYNC_QUEUE_KEY = "dq:connector:sync:queue"


# ---------------------------------------------------------------------------
# Sync orchestrator
# ---------------------------------------------------------------------------
class ConnectorSyncOrchestrator:
    """Business logic for connector sync jobs, schedules and incremental sync."""

    def __init__(
        self,
        job_repo: ConnectorSyncJobRepository,
        schedule_repo: ConnectorSyncScheduleRepository,
        instance_repo: ConnectorInstanceRepository,
        connector_services: dict[str, ConnectorService],
        retry_policy: ConnectorRetryPolicyEntity | None = None,
    ) -> None:
        self._job_repo = job_repo
        self._schedule_repo = schedule_repo
        self._instance_repo = instance_repo
        self._connector_services = connector_services
        self._retry_policy = retry_policy or ConnectorRetryPolicyEntity()

    # ------------------------------------------------------------------
    # Job creation
    # ------------------------------------------------------------------

    def create_sync_job(
        self,
        *,
        connector_instance_id: str,
        kind: ConnectorJobKind = "full_sync",
        trigger: ConnectorJobTrigger = "manual",
    ) -> ConnectorSyncJobView:
        instance = self._instance_repo.get_instance(connector_instance_id)
        if instance is None:
            raise ValueError(f"connector instance {connector_instance_id} not found")

        job = ConnectorSyncJobEntity(
            id=str(uuid4()),
            connector_instance_id=connector_instance_id,
            provider=instance.provider,
            kind=kind,
            trigger=trigger,
            status="pending",
            max_retries=self._retry_policy.max_retries,
            workspace_id=instance.workspace_id,
            tenant_id=instance.tenant_id,
            created_at=datetime.now(UTC).isoformat(),
            updated_at=datetime.now(UTC).isoformat(),
        )
        saved = self._job_repo.create_job(job)
        return self._job_to_view(saved)

    def cancel_sync_job(self, job_id: str) -> ConnectorSyncJobView:
        job = self._job_repo.get_job(job_id)
        if job is None:
            raise ValueError(f"sync job {job_id} not found")
        if job.status not in ("pending", "retrying"):
            raise ValueError(f"cannot cancel job in {job.status} state")
        updated = self._job_repo.update_status(job_id, "cancelled")
        if updated is None:
            raise ValueError(f"sync job {job_id} not found during cancel")
        return self._job_to_view(updated)

    # ------------------------------------------------------------------
    # Job status / history
    # ------------------------------------------------------------------

    def get_sync_job(self, job_id: str) -> ConnectorSyncJobView | None:
        job = self._job_repo.get_job(job_id)
        return self._job_to_view(job) if job else None

    def list_sync_jobs(
        self,
        *,
        connector_instance_id: str | None = None,
        provider: str | None = None,
        status: ConnectorJobStatus | None = None,
        workspace_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ConnectorSyncJobView]:
        jobs = self._job_repo.list_jobs(
            connector_instance_id=connector_instance_id,
            provider=provider,
            status=status,
            workspace_id=workspace_id,
            limit=limit,
            offset=offset,
        )
        return [self._job_to_view(j) for j in jobs]

    # ------------------------------------------------------------------
    # Schedule management
    # ------------------------------------------------------------------

    def create_sync_schedule(
        self,
        *,
        connector_instance_id: str,
        frequency: str = "day",
        interval_count: int = 1,
        cron_expression: str | None = None,
        timezone: str = "UTC",
    ) -> ConnectorSyncScheduleView:
        instance = self._instance_repo.get_instance(connector_instance_id)
        if instance is None:
            raise ValueError(f"connector instance {connector_instance_id} not found")

        now = datetime.now(UTC)
        next_run = self._compute_next_run(
            frequency=frequency,
            interval_count=interval_count,
            cron_expression=cron_expression,
            timezone=timezone,
            from_dt=now,
        )
        schedule = ConnectorSyncScheduleEntity(
            id=str(uuid4()),
            connector_instance_id=connector_instance_id,
            provider=instance.provider,
            frequency=frequency,
            cron_expression=cron_expression,
            interval_count=interval_count,
            next_run_at=next_run.isoformat() if next_run else None,
            timezone=timezone,
            workspace_id=instance.workspace_id,
            tenant_id=instance.tenant_id,
            created_at=now.isoformat(),
            updated_at=now.isoformat(),
        )
        saved = self._schedule_repo.create_schedule(schedule)
        return self._schedule_to_view(saved)

    def list_sync_schedules(
        self,
        *,
        connector_instance_id: str | None = None,
        is_active: bool | None = None,
        workspace_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ConnectorSyncScheduleView]:
        schedules = self._schedule_repo.list_schedules(
            connector_instance_id=connector_instance_id,
            is_active=is_active,
            workspace_id=workspace_id,
            limit=limit,
            offset=offset,
        )
        return [self._schedule_to_view(s) for s in schedules]

    def update_sync_schedule(
        self,
        schedule_id: str,
        *,
        is_active: bool | None = None,
    ) -> ConnectorSyncScheduleView | None:
        updated = self._schedule_repo.update_schedule(
            schedule_id,
            is_active=is_active,
        )
        return self._schedule_to_view(updated) if updated else None

    def delete_sync_schedule(self, schedule_id: str) -> bool:
        return self._schedule_repo.delete_schedule(schedule_id)

    # ------------------------------------------------------------------
    # Scheduler trigger
    # ------------------------------------------------------------------

    def trigger_due_schedules(self) -> list[ConnectorSyncJobView]:
        due_schedules = self._schedule_repo.list_due_schedules()
        created_jobs: list[ConnectorSyncJobView] = []
        now = datetime.now(UTC)
        for schedule in due_schedules:
            try:
                view = self.create_sync_job(
                    connector_instance_id=schedule.connector_instance_id,
                    kind="full_sync",
                    trigger="scheduled",
                )
                created_jobs.append(view)
                # Update schedule metadata
                self._schedule_repo.update_schedule(
                    schedule.id,
                    last_run_at=now.isoformat(),
                    last_job_id=view.jobId,
                    next_run_at=self._compute_next_run(
                        frequency=schedule.frequency,
                        interval_count=schedule.interval_count,
                        cron_expression=schedule.cron_expression,
                        timezone=schedule.timezone,
                        from_dt=now,
                    ).isoformat() if True else None,
                )
            except Exception as exc:
                logger.error("failed to trigger schedule %s: %s", schedule.id, exc)
        return created_jobs

    # ------------------------------------------------------------------
    # Incremental sync helpers
    # ------------------------------------------------------------------

    def compute_asset_checksum(self, asset_id: str, metadata: dict[str, Any]) -> str:
        normalized = json.dumps(
            {k: metadata[k] for k in sorted(metadata.keys())},
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(normalized.encode()).hexdigest()

    def get_syncable_assets(
        self,
        connector_instance: ConnectorInstanceEntity,
        *,
        kind: ConnectorJobKind = "full_sync",
    ) -> list[dict[str, Any]]:
        """Delegate to connector service for asset listing."""
        service = self._connector_services.get(connector_instance.provider)
        if service is None:
            raise ValueError(f"no connector service for {connector_instance.provider}")
        return service.discover(
            connector_instance,
            filter_expression=None,
        )

    # ------------------------------------------------------------------
    # Retry / staleness
    # ------------------------------------------------------------------

    def get_retry_policy(self) -> ConnectorRetryPolicyEntity:
        return self._retry_policy

    def check_staleness(
        self,
        connector_instance: ConnectorInstanceEntity,
        *,
        max_age_seconds: int = 86400,
    ) -> dict[str, Any]:
        """Check if the last sync is stale for a connector instance."""
        jobs = self._job_repo.list_jobs(
            connector_instance_id=connector_instance.id,
            status="completed",
            limit=1,
            offset=0,
        )
        if not jobs:
            return {
                "stale": True,
                "reason": "no_successful_sync",
                "last_synced_at": None,
                "age_seconds": None,
            }
        last_job = jobs[0]
        if last_job.completed_at:
            last_synced = datetime.fromisoformat(last_job.completed_at)
            age = (datetime.now(UTC) - last_synced).total_seconds()
            is_stale = age > max_age_seconds
            return {
                "stale": is_stale,
                "reason": "age_exceeded" if is_stale else "ok",
                "last_synced_at": last_job.completed_at,
                "age_seconds": int(age),
            }
        return {
            "stale": True,
            "reason": "no_timestamp",
            "last_synced_at": None,
            "age_seconds": None,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _job_to_view(job: ConnectorSyncJobEntity) -> ConnectorSyncJobView:
        return ConnectorSyncJobView(
            jobId=job.id,
            connectorInstanceId=job.connector_instance_id,
            provider=job.provider,
            kind=job.kind,
            trigger=job.trigger,
            status=job.status,
            retryCount=job.retry_count,
            maxRetries=job.max_retries,
            syncedCount=job.synced_count,
            addedCount=job.added_count,
            updatedCount=job.updated_count,
            removedCount=job.removed_count,
            errorCode=job.error_code,
            errorMessage=job.error_message,
            startedAt=job.started_at,
            completedAt=job.completed_at,
            createdAt=job.created_at,
            updatedAt=job.updated_at,
        )

    @staticmethod
    def _schedule_to_view(schedule: ConnectorSyncScheduleEntity) -> ConnectorSyncScheduleView:
        return ConnectorSyncScheduleView(
            id=schedule.id,
            connectorInstanceId=schedule.connector_instance_id,
            provider=schedule.provider,
            frequency=schedule.frequency,
            cronExpression=schedule.cron_expression,
            intervalCount=schedule.interval_count,
            nextRunAt=schedule.next_run_at,
            lastRunAt=schedule.last_run_at,
            lastJobId=schedule.last_job_id,
            isActive=schedule.is_active,
            timezone=schedule.timezone,
            workspaceId=schedule.workspace_id,
            tenantId=schedule.tenant_id,
            createdAt=schedule.created_at,
            updatedAt=schedule.updated_at,
        )

    def _compute_next_run(
        self,
        *,
        frequency: str,
        interval_count: int,
        cron_expression: str | None,
        timezone: str,
        from_dt: datetime,
    ) -> datetime | None:
        """Simple next-run computation (cron handled by worker scheduler)."""
        if cron_expression:
            # Cron expressions are handled by the worker's scheduler
            # Return a placeholder; the worker will compute actual next run
            return from_dt + timedelta(seconds=60)

        delta_map = {
            "minute": timedelta(minutes=interval_count),
            "hour": timedelta(hours=interval_count),
            "day": timedelta(days=interval_count),
            "week": timedelta(weeks=interval_count),
        }
        delta = delta_map.get(frequency)
        if delta is None:
            return None
        return from_dt + delta
