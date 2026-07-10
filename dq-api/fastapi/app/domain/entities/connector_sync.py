"""Connector sync jobs, schedules, retry policies, and incremental metadata."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import ConfigDict, Field

from app.domain.entities.base import EntityModel


# ---------------------------------------------------------------------------
# Job status / kind / trigger
# ---------------------------------------------------------------------------
ConnectorJobStatus = Literal[
    "pending",
    "running",
    "completed",
    "failed",
    "cancelled",
    "retrying",
]
ConnectorJobKind = Literal["full_sync", "incremental_sync", "health_check"]
ConnectorJobTrigger = Literal["manual", "scheduled", "webhook"]
ConnectorScheduleFrequency = Literal["minute", "hour", "day", "week", "cron"]


# ---------------------------------------------------------------------------
# Retry Policy
# ---------------------------------------------------------------------------
class ConnectorRetryPolicyEntity(EntityModel):
    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True,
        extra="forbid",
        frozen=True,
    )

    max_retries: int = 3
    initial_delay_seconds: float = 1.0
    max_delay_seconds: float = 60.0
    backoff_multiplier: float = 2.0
    retryable_error_kinds: tuple[str, ...] = Field(
        default_factory=lambda: ("connection", "discovery", "sync"),
    )

    def compute_delay(self, attempt: int) -> float:
        """Exponential backoff with jitter."""
        import random
        delay = self.initial_delay_seconds * (self.backoff_multiplier ** attempt)
        delay = min(delay, self.max_delay_seconds)
        return delay * (0.5 + random.random() * 0.5)

    def should_retry(self, attempt: int, error_kind: str) -> bool:
        return attempt < self.max_retries and error_kind in self.retryable_error_kinds


# ---------------------------------------------------------------------------
# Sync Job Entity
# ---------------------------------------------------------------------------
class ConnectorSyncJobEntity(EntityModel):
    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True,
        extra="forbid",
        frozen=True,
    )

    id: str
    connector_instance_id: str
    provider: str
    kind: ConnectorJobKind = "full_sync"
    trigger: ConnectorJobTrigger = "manual"
    status: ConnectorJobStatus = "pending"
    retry_count: int = 0
    max_retries: int = 3
    synced_count: int = 0
    added_count: int = 0
    updated_count: int = 0
    removed_count: int = 0
    error_code: str | None = None
    error_message: str | None = None
    error_details: dict[str, Any] = Field(default_factory=dict)
    result_snapshot: dict[str, Any] = Field(default_factory=dict)
    workspace_id: str | None = None
    tenant_id: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    created_at: str
    updated_at: str


# ---------------------------------------------------------------------------
# Sync Schedule Entity
# ---------------------------------------------------------------------------
class ConnectorSyncScheduleEntity(EntityModel):
    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True,
        extra="forbid",
        frozen=True,
    )

    id: str
    connector_instance_id: str
    provider: str
    frequency: ConnectorScheduleFrequency = "day"
    cron_expression: str | None = None
    interval_count: int = 1
    next_run_at: str | None = None
    last_run_at: str | None = None
    last_job_id: str | None = None
    is_active: bool = True
    timezone: str = "UTC"
    workspace_id: str | None = None
    tenant_id: str | None = None
    created_at: str
    updated_at: str


# ---------------------------------------------------------------------------
# Asset Snapshot (for incremental sync drift detection)
# ---------------------------------------------------------------------------
class ConnectorAssetSnapshotEntity(EntityModel):
    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True,
        extra="forbid",
        frozen=True,
    )

    connector_instance_id: str
    provider: str
    asset_identifier: str
    asset_kind: str
    asset_metadata: dict[str, Any] = Field(default_factory=dict)
    checksum: str | None = None
    last_synced_at: str | None = None
    created_at: str
    updated_at: str


# ---------------------------------------------------------------------------
# API response view
# ---------------------------------------------------------------------------
class ConnectorSyncJobView(EntityModel):
    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True,
        extra="forbid",
        frozen=True,
    )

    jobId: str
    connectorInstanceId: str
    provider: str
    kind: ConnectorJobKind
    trigger: ConnectorJobTrigger
    status: ConnectorJobStatus
    retryCount: int
    maxRetries: int
    syncedCount: int
    addedCount: int
    updatedCount: int
    removedCount: int
    errorCode: str | None = None
    errorMessage: str | None = None
    startedAt: str | None = None
    completedAt: str | None = None
    createdAt: str
    updatedAt: str


class ConnectorSyncScheduleView(EntityModel):
    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True,
        extra="forbid",
        frozen=True,
    )

    id: str
    connectorInstanceId: str
    provider: str
    frequency: ConnectorScheduleFrequency
    cronExpression: str | None = None
    intervalCount: int
    nextRunAt: str | None = None
    lastRunAt: str | None = None
    lastJobId: str | None = None
    isActive: bool
    timezone: str
    workspaceId: str | None = None
    tenantId: str | None = None
    createdAt: str
    updatedAt: str


__all__ = [
    "ConnectorJobKind",
    "ConnectorJobStatus",
    "ConnectorJobTrigger",
    "ConnectorScheduleFrequency",
    "ConnectorAssetSnapshotEntity",
    "ConnectorRetryPolicyEntity",
    "ConnectorSyncJobEntity",
    "ConnectorSyncJobView",
    "ConnectorSyncScheduleEntity",
    "ConnectorSyncScheduleView",
]
