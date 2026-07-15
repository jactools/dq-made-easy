"""Tests for connector sync orchestrator."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.domain.entities.connector import ConnectorInstanceEntity
from app.domain.entities.connector_sync import (
    ConnectorJobStatus,
    ConnectorRetryPolicyEntity,
    ConnectorSyncJobEntity,
    ConnectorSyncJobView,
    ConnectorSyncScheduleEntity,
    ConnectorSyncScheduleView,
)
from app.domain.interfaces.v1.connector_instance_repository import ConnectorInstanceRepository
from app.domain.interfaces.v1.connector_sync_job_repository import ConnectorSyncJobRepository
from app.domain.interfaces.v1.connector_sync_schedule_repository import ConnectorSyncScheduleRepository
from app.application.services.connector_sync_orchestrator import ConnectorSyncOrchestrator


# ---------------------------------------------------------------------------
# Fake repositories
# ---------------------------------------------------------------------------


class _FakeJobRepository:
    def __init__(self) -> None:
        self._jobs: dict[str, ConnectorSyncJobEntity] = {}

    def create_job(self, job: ConnectorSyncJobEntity) -> ConnectorSyncJobEntity:
        self._jobs[job.id] = job
        return job

    def get_job(self, job_id: str) -> ConnectorSyncJobEntity | None:
        return self._jobs.get(job_id)

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
        jobs = list(self._jobs.values())
        if connector_instance_id:
            jobs = [j for j in jobs if j.connector_instance_id == connector_instance_id]
        if provider:
            jobs = [j for j in jobs if j.provider == provider]
        if status:
            jobs = [j for j in jobs if j.status == status]
        return jobs[offset : offset + limit]

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
        job = self._jobs.get(job_id)
        if job is None:
            return None
        kwargs: dict[str, Any] = {"status": status, "updated_at": datetime.now(UTC).isoformat()}
        if error_code is not None:
            kwargs["error_code"] = error_code
        if error_message is not None:
            kwargs["error_message"] = error_message
        if synced_count is not None:
            kwargs["synced_count"] = synced_count
        self._jobs[job_id] = job.model_copy(update=kwargs)
        return self._jobs[job_id]

    def claim_pending(self, provider: str | None = None) -> ConnectorSyncJobEntity | None:
        for job in self._jobs.values():
            if job.status == "pending":
                if provider and job.provider != provider:
                    continue
                return job
        return None

    def list_stale_jobs(
        self,
        *,
        max_age_seconds: int = 86400,
    ) -> list[ConnectorSyncJobEntity]:
        return []


class _FakeScheduleRepository:
    def __init__(self) -> None:
        self._schedules: dict[str, ConnectorSyncScheduleEntity] = {}

    def create_schedule(self, schedule: ConnectorSyncScheduleEntity) -> ConnectorSyncScheduleEntity:
        self._schedules[schedule.id] = schedule
        return schedule

    def get_schedule(self, schedule_id: str) -> ConnectorSyncScheduleEntity | None:
        return self._schedules.get(schedule_id)

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
        schedules = list(self._schedules.values())
        if connector_instance_id:
            schedules = [s for s in schedules if s.connector_instance_id == connector_instance_id]
        if is_active is not None:
            schedules = [s for s in schedules if s.is_active == is_active]
        return schedules[offset : offset + limit]

    def update_schedule(
        self,
        schedule_id: str,
        *,
        is_active: bool | None = None,
        next_run_at: str | None = None,
        last_run_at: str | None = None,
        last_job_id: str | None = None,
    ) -> ConnectorSyncScheduleEntity | None:
        schedule = self._schedules.get(schedule_id)
        if schedule is None:
            return None
        kwargs: dict[str, Any] = {"updated_at": datetime.now(UTC).isoformat()}
        if is_active is not None:
            kwargs["is_active"] = is_active
        if next_run_at is not None:
            kwargs["next_run_at"] = next_run_at
        if last_run_at is not None:
            kwargs["last_run_at"] = last_run_at
        if last_job_id is not None:
            kwargs["last_job_id"] = last_job_id
        self._schedules[schedule_id] = schedule.model_copy(update=kwargs)
        return self._schedules[schedule_id]

    def delete_schedule(self, schedule_id: str) -> bool:
        return self._schedules.pop(schedule_id, None) is not None

    def list_due_schedules(self) -> list[ConnectorSyncScheduleEntity]:
        now = datetime.now(UTC)
        due = []
        for s in self._schedules.values():
            if not s.is_active:
                continue
            if s.next_run_at and datetime.fromisoformat(s.next_run_at) <= now:
                due.append(s)
        return due


class _FakeInstanceRepository:
    def __init__(self) -> None:
        self._instances: dict[str, ConnectorInstanceEntity] = {}

    def upsert_instance(self, instance: ConnectorInstanceEntity) -> ConnectorInstanceEntity:
        self._instances[instance.id] = instance
        return instance

    def get_instance(self, instance_id: str) -> ConnectorInstanceEntity | None:
        return self._instances.get(instance_id)

    def list_instances(
        self,
        *,
        provider: str | None = None,
        workspace_id: str | None = None,
        tenant_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ConnectorInstanceEntity]:
        return list(self._instances.values())


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def _make_instance(id: str = "ci-001", provider: str = "postgresql") -> ConnectorInstanceEntity:
    now = datetime.now(UTC).isoformat()
    return ConnectorInstanceEntity(
        id=id,
        provider=provider,
        display_name=f"{provider} instance",
        workspace_id="ws-001",
        tenant_id="tn-001",
        configuration={"provider": provider},
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def orchestrator() -> ConnectorSyncOrchestrator:
    job_repo = _FakeJobRepository()
    schedule_repo = _FakeScheduleRepository()
    instance_repo = _FakeInstanceRepository()
    instance = _make_instance()
    instance_repo.upsert_instance(instance)
    connector_services: dict[str, MagicMock] = {
        "postgresql": MagicMock(),
    }
    return ConnectorSyncOrchestrator(
        job_repo=job_repo,
        schedule_repo=schedule_repo,
        instance_repo=instance_repo,
        connector_services=connector_services,
    )


def test_create_sync_job(orchestrator: ConnectorSyncOrchestrator) -> None:
    view = orchestrator.create_sync_job(
        connector_instance_id="ci-001",
        kind="full_sync",
        trigger="manual",
    )
    assert view.status == "pending"
    assert view.provider == "postgresql"
    assert view.kind == "full_sync"
    assert view.trigger == "manual"


def test_create_sync_job_instance_not_found(orchestrator: ConnectorSyncOrchestrator) -> None:
    with pytest.raises(ValueError, match="not found"):
        orchestrator.create_sync_job(
            connector_instance_id="nonexistent",
        )


def test_get_sync_job(orchestrator: ConnectorSyncOrchestrator) -> None:
    created = orchestrator.create_sync_job(
        connector_instance_id="ci-001",
    )
    fetched = orchestrator.get_sync_job(created.jobId)
    assert fetched is not None
    assert fetched.jobId == created.jobId


def test_get_sync_job_not_found(orchestrator: ConnectorSyncOrchestrator) -> None:
    assert orchestrator.get_sync_job("nonexistent") is None


def test_list_sync_jobs(orchestrator: ConnectorSyncOrchestrator) -> None:
    orchestrator.create_sync_job(connector_instance_id="ci-001")
    orchestrator.create_sync_job(connector_instance_id="ci-001")
    jobs = orchestrator.list_sync_jobs(
        connector_instance_id="ci-001",
    )
    assert len(jobs) == 2


def test_cancel_sync_job(orchestrator: ConnectorSyncOrchestrator) -> None:
    created = orchestrator.create_sync_job(
        connector_instance_id="ci-001",
    )
    cancelled = orchestrator.cancel_sync_job(created.jobId)
    assert cancelled.status == "cancelled"


def test_cancel_sync_job_already_completed(orchestrator: ConnectorSyncOrchestrator) -> None:
    # Can't cancel a completed job
    created = orchestrator.create_sync_job(connector_instance_id="ci-001")
    # Manually set to completed
    job_repo = orchestrator._job_repo
    job_repo.update_status(created.jobId, "completed")
    with pytest.raises(ValueError, match="cannot cancel"):
        orchestrator.cancel_sync_job(created.jobId)


def test_create_sync_schedule(orchestrator: ConnectorSyncOrchestrator) -> None:
    view = orchestrator.create_sync_schedule(
        connector_instance_id="ci-001",
        frequency="day",
        interval_count=2,
    )
    assert view.frequency == "day"
    assert view.intervalCount == 2
    assert view.isActive is True


def test_list_sync_schedules(orchestrator: ConnectorSyncOrchestrator) -> None:
    orchestrator.create_sync_schedule(connector_instance_id="ci-001", frequency="hour")
    orchestrator.create_sync_schedule(connector_instance_id="ci-001", frequency="day")
    schedules = orchestrator.list_sync_schedules(connector_instance_id="ci-001")
    assert len(schedules) == 2


def test_delete_sync_schedule(orchestrator: ConnectorSyncOrchestrator) -> None:
    created = orchestrator.create_sync_schedule(connector_instance_id="ci-001")
    assert orchestrator.delete_sync_schedule(created.id) is True
    assert orchestrator.delete_sync_schedule(created.id) is False


def test_check_staleness_no_jobs(orchestrator: ConnectorSyncOrchestrator) -> None:
    instance = _make_instance()
    result = orchestrator.check_staleness(instance)
    assert result["stale"] is True
    assert result["reason"] == "no_successful_sync"


def test_check_staleness_recent(orchestrator: ConnectorSyncOrchestrator) -> None:
    instance = _make_instance()
    # Create a completed job
    job = ConnectorSyncJobEntity(
        id="sj-recent",
        connector_instance_id=instance.id,
        provider=instance.provider,
        status="completed",
        completed_at=datetime.now(UTC).isoformat(),
        created_at=datetime.now(UTC).isoformat(),
        updated_at=datetime.now(UTC).isoformat(),
    )
    orchestrator._job_repo.create_job(job)
    result = orchestrator.check_staleness(instance)
    assert result["stale"] is False
    assert result["reason"] == "ok"


def test_retry_policy_defaults() -> None:
    policy = ConnectorRetryPolicyEntity()
    assert policy.max_retries == 3
    assert policy.should_retry(0, "connection") is True
    assert policy.should_retry(3, "connection") is False


def test_asset_checksum_deterministic(orchestrator: ConnectorSyncOrchestrator) -> None:
    metadata = {"col_count": 10, "row_count": 100}
    cs1 = orchestrator.compute_asset_checksum("table1", metadata)
    cs2 = orchestrator.compute_asset_checksum("table1", metadata)
    assert cs1 == cs2
    # Different metadata -> different checksum
    cs3 = orchestrator.compute_asset_checksum("table1", {"col_count": 10})
    assert cs1 != cs3
