"""Tests for connector sync domain entities."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

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


# ---------------------------------------------------------------------------
# Retry policy
# ---------------------------------------------------------------------------


def test_retry_policy_default_values() -> None:
    policy = ConnectorRetryPolicyEntity()
    assert policy.max_retries == 3
    assert policy.initial_delay_seconds == 1.0
    assert policy.max_delay_seconds == 60.0
    assert policy.backoff_multiplier == 2.0


def test_retry_policy_compute_delay_capped() -> None:
    policy = ConnectorRetryPolicyEntity()
    # Attempt 10 should hit max delay cap
    delay = policy.compute_delay(10)
    assert delay <= policy.max_delay_seconds


def test_retry_policy_should_retry_within_limit() -> None:
    policy = ConnectorRetryPolicyEntity()
    assert policy.should_retry(0, "connection") is True
    assert policy.should_retry(2, "sync") is True
    assert policy.should_retry(3, "connection") is False  # at max
    assert policy.should_retry(0, "unknown") is False  # not retryable


# ---------------------------------------------------------------------------
# Sync job entity
# ---------------------------------------------------------------------------


def test_sync_job_entity_creation() -> None:
    now = datetime.now(UTC).isoformat()
    job = ConnectorSyncJobEntity(
        id="sj-001",
        connector_instance_id="ci-001",
        provider="postgresql",
        kind="full_sync",
        trigger="manual",
        status="pending",
        created_at=now,
        updated_at=now,
    )
    assert job.id == "sj-001"
    assert job.provider == "postgresql"
    assert job.kind == "full_sync"
    assert job.status == "pending"
    assert job.retry_count == 0
    assert job.max_retries == 3


def test_sync_job_entity_defaults() -> None:
    now = datetime.now(UTC).isoformat()
    job = ConnectorSyncJobEntity(
        id="sj-002",
        connector_instance_id="ci-002",
        provider="sql_server",
        created_at=now,
        updated_at=now,
    )
    assert job.kind == "full_sync"
    assert job.trigger == "manual"
    assert job.status == "pending"


# ---------------------------------------------------------------------------
# Sync schedule entity
# ---------------------------------------------------------------------------


def test_sync_schedule_entity_creation() -> None:
    now = datetime.now(UTC).isoformat()
    schedule = ConnectorSyncScheduleEntity(
        id="ss-001",
        connector_instance_id="ci-001",
        provider="postgresql",
        frequency="day",
        interval_count=1,
        created_at=now,
        updated_at=now,
    )
    assert schedule.frequency == "day"
    assert schedule.interval_count == 1
    assert schedule.is_active is True
    assert schedule.timezone == "UTC"


def test_sync_schedule_cron_expression() -> None:
    now = datetime.now(UTC).isoformat()
    schedule = ConnectorSyncScheduleEntity(
        id="ss-002",
        connector_instance_id="ci-001",
        provider="postgresql",
        frequency="cron",
        cron_expression="0 2 * * *",
        created_at=now,
        updated_at=now,
    )
    assert schedule.frequency == "cron"
    assert schedule.cron_expression == "0 2 * * *"


# ---------------------------------------------------------------------------
# Asset snapshot entity
# ---------------------------------------------------------------------------


def test_asset_snapshot_entity_creation() -> None:
    now = datetime.now(UTC).isoformat()
    snapshot = ConnectorAssetSnapshotEntity(
        connector_instance_id="ci-001",
        provider="postgresql",
        asset_identifier="public.users",
        asset_kind="table",
        created_at=now,
        updated_at=now,
    )
    assert snapshot.asset_identifier == "public.users"
    assert snapshot.asset_kind == "table"


# ---------------------------------------------------------------------------
# Job view
# ---------------------------------------------------------------------------


def test_sync_job_view_from_entity() -> None:
    now = datetime.now(UTC).isoformat()
    job = ConnectorSyncJobEntity(
        id="sj-001",
        connector_instance_id="ci-001",
        provider="postgresql",
        kind="full_sync",
        trigger="manual",
        status="completed",
        synced_count=42,
        added_count=10,
        updated_count=20,
        removed_count=5,
        created_at=now,
        updated_at=now,
    )
    view = ConnectorSyncJobView(
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
        createdAt=job.created_at,
        updatedAt=job.updated_at,
    )
    assert view.jobId == "sj-001"
    assert view.syncedCount == 42
    assert view.status == "completed"


# ---------------------------------------------------------------------------
# Type literals
# ---------------------------------------------------------------------------


def test_job_status_literals() -> None:
    valid: list[ConnectorJobStatus] = [
        "pending",
        "running",
        "completed",
        "failed",
        "cancelled",
        "retrying",
    ]
    assert len(valid) == 6


def test_job_kind_literals() -> None:
    valid: list[ConnectorJobKind] = [
        "full_sync",
        "incremental_sync",
        "health_check",
    ]
    assert len(valid) == 3


def test_job_trigger_literals() -> None:
    valid: list[ConnectorJobTrigger] = [
        "manual",
        "scheduled",
        "webhook",
    ]
    assert len(valid) == 3
