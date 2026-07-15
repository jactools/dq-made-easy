"""Connector sync job, schedule and staleness endpoints (API-1 gap closure).

Background sync job management, periodic scheduling and staleness
health monitoring for connector instances.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.api.v1.endpoints.connectors import ConnectorOperationRequestView
from app.api.v1.endpoints.connectors import _connector_audit_details
from app.api.v1.endpoints.connectors import _normalized_provider
from app.api.v1.endpoints.connectors import _record_connector_audit_event
from app.api.v1.endpoints.connectors import _resolve_connector_instance
from app.core.dependencies import get_connector_audit_repository
from app.core.dependencies import get_connector_instance_repository
from app.core.dependencies import get_connector_sync_job_repository
from app.core.dependencies import get_connector_sync_schedule_repository
from app.domain.interfaces import ConnectorAuditRepository
from app.domain.interfaces import ConnectorInstanceRepository

router = APIRouter(tags=["connectors"])


# ---------------------------------------------------------------------------
# Sync job endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/connectors/{provider}/sync-jobs",
    responses={
        200: {"description": "Enqueue an async sync job and return the job record."},
        400: {"description": "The connector instance is invalid."},
        404: {"description": "The connector instance is not found."},
        503: {"description": "The connector sync repository is unavailable."},
    },
)
async def enqueue_connector_sync_job(
    provider: str,
    request: Request,
    body: ConnectorOperationRequestView,
    audit_repository: ConnectorAuditRepository = Depends(get_connector_audit_repository),
    instance_repository: ConnectorInstanceRepository = Depends(get_connector_instance_repository),
) -> dict[str, object]:
    """Enqueue a background sync job for the connector instance.

    Returns immediately with a pending job record. The worker processes
    the job asynchronously and updates its status in the database.
    """
    from app.domain.entities.connector_sync import ConnectorSyncJobEntity

    normalized_provider = _normalized_provider(provider)
    connector_instance_id = str(body.connector_instance_id or "").strip()
    if not connector_instance_id:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "connector_instance_id_required",
                "provider": normalized_provider,
                "message": "connector_instance_id is required for sync job enqueue",
            },
        )
    instance = _resolve_connector_instance(
        normalized_provider, connector_instance_id, instance_repository
    )
    if instance is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "connector_instance_not_found",
                "provider": normalized_provider,
                "message": f"Connector instance '{connector_instance_id}' not found",
            },
        )

    job_repo = get_connector_sync_job_repository()
    now = datetime.now(UTC).isoformat()
    job = ConnectorSyncJobEntity(
        id=f"sj-{uuid4().hex[:16]}",
        connector_instance_id=instance.id,
        provider=instance.provider,
        kind="full_sync",
        trigger="manual",
        status="pending",
        workspace_id=instance.workspace_id,
        tenant_id=instance.tenant_id,
        created_at=now,
        updated_at=now,
    )
    saved = job_repo.create_job(job)

    await _record_connector_audit_event(
        request=request,
        repository=audit_repository,
        action="connector_sync_enqueue",
        response_type="connector_sync_job",
        status_code=200,
        success=True,
        provider=instance.provider,
        connector_instance_id=instance.id,
        details=_connector_audit_details(
            provider=instance.provider,
            connector_instance_id=instance.id,
        ),
    )
    return {
        "jobId": saved.id,
        "connectorInstanceId": saved.connector_instance_id,
        "provider": saved.provider,
        "kind": saved.kind,
        "trigger": saved.trigger,
        "status": saved.status,
        "createdAt": saved.created_at,
    }


@router.get(
    "/connectors/sync-jobs/{job_id}",
    responses={
        200: {"description": "Return the sync job status."},
        404: {"description": "The sync job is not found."},
        503: {"description": "The connector sync repository is unavailable."},
    },
)
async def get_connector_sync_job(
    job_id: str,
) -> dict[str, object] | None:
    """Poll the status of a sync job."""
    job_repo = get_connector_sync_job_repository()
    job = job_repo.get_job(job_id)
    if job is None:
        return None
    return {
        "jobId": job.id,
        "connectorInstanceId": job.connector_instance_id,
        "provider": job.provider,
        "kind": job.kind,
        "trigger": job.trigger,
        "status": job.status,
        "retryCount": job.retry_count,
        "maxRetries": job.max_retries,
        "syncedCount": job.synced_count,
        "addedCount": job.added_count,
        "updatedCount": job.updated_count,
        "removedCount": job.removed_count,
        "errorCode": job.error_code,
        "errorMessage": job.error_message,
        "startedAt": job.started_at,
        "completedAt": job.completed_at,
        "createdAt": job.created_at,
        "updatedAt": job.updated_at,
    }


@router.get(
    "/connectors/sync-jobs",
    responses={
        200: {"description": "List sync jobs."},
        503: {"description": "The connector sync repository is unavailable."},
    },
)
async def list_connector_sync_jobs(
    connector_instance_id: str | None = Query(default=None),
    provider: str | None = Query(default=None),
    status: str | None = Query(default=None),
    workspace_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=0),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, object]]:
    """List sync jobs with optional filters."""
    job_repo = get_connector_sync_job_repository()
    jobs = job_repo.list_jobs(
        connector_instance_id=connector_instance_id,
        provider=provider,
        status=status,
        workspace_id=workspace_id,
        limit=limit,
        offset=offset,
    )
    return [
        {
            "jobId": j.id,
            "connectorInstanceId": j.connector_instance_id,
            "provider": j.provider,
            "kind": j.kind,
            "trigger": j.trigger,
            "status": j.status,
            "retryCount": j.retry_count,
            "syncedCount": j.synced_count,
            "addedCount": j.added_count,
            "updatedCount": j.updated_count,
            "removedCount": j.removed_count,
            "errorCode": j.error_code,
            "errorMessage": j.error_message,
            "startedAt": j.started_at,
            "completedAt": j.completed_at,
            "createdAt": j.created_at,
            "updatedAt": j.updated_at,
        }
        for j in jobs
    ]


@router.post(
    "/connectors/sync-jobs/{job_id}/cancel",
    responses={
        200: {"description": "Cancel the sync job."},
        400: {"description": "The job cannot be cancelled in its current state."},
        404: {"description": "The sync job is not found."},
    },
)
async def cancel_connector_sync_job(
    job_id: str,
) -> dict[str, object]:
    """Cancel a pending or retrying sync job."""
    job_repo = get_connector_sync_job_repository()
    job = job_repo.get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "job_not_found", "jobId": job_id},
        )
    if job.status not in ("pending", "retrying"):
        raise HTTPException(
            status_code=400,
            detail={
                "error": "cannot_cancel",
                "jobId": job_id,
                "status": job.status,
            },
        )
    updated = job_repo.update_status(job_id, "cancelled")
    if updated is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "job_not_found", "jobId": job_id},
        )
    return {
        "jobId": updated.id,
        "status": updated.status,
        "updatedAt": updated.updated_at,
    }


# ---------------------------------------------------------------------------
# Sync schedule endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/connectors/sync-schedules",
    responses={
        200: {"description": "Create a sync schedule."},
        400: {"description": "The schedule payload is invalid."},
        404: {"description": "The connector instance is not found."},
        503: {"description": "The connector sync repository is unavailable."},
    },
)
async def create_connector_sync_schedule(
    request: Request,
    body: ConnectorOperationRequestView,
    audit_repository: ConnectorAuditRepository = Depends(get_connector_audit_repository),
    instance_repository: ConnectorInstanceRepository = Depends(get_connector_instance_repository),
) -> dict[str, object]:
    """Create a periodic sync schedule for a connector instance."""
    from app.domain.entities.connector_sync import ConnectorSyncScheduleEntity

    provider = body.configuration.get("provider", "").strip().lower() or ""
    connector_instance_id = str(body.connector_instance_id or "").strip()
    if not connector_instance_id:
        raise HTTPException(
            status_code=400,
            detail={"error": "connector_instance_id_required"},
        )
    if not provider:
        raise HTTPException(status_code=400, detail={"error": "provider_required"})

    instance = _resolve_connector_instance(
        provider, connector_instance_id, instance_repository
    )
    if instance is None:
        raise HTTPException(status_code=404, detail={"error": "instance_not_found"})

    schedule_repo = get_connector_sync_schedule_repository()
    frequency = str(body.configuration.get("frequency", "day")).strip().lower()
    interval_count = int(body.configuration.get("interval_count", 1) or 1)
    cron_expression = body.configuration.get("cron_expression")
    timezone = str(body.configuration.get("timezone", "UTC")).strip()

    now = datetime.now(UTC)
    delta = timedelta(days=interval_count) if frequency == "day" else timedelta(hours=interval_count)
    schedule = ConnectorSyncScheduleEntity(
        id=f"ss-{uuid4().hex[:16]}",
        connector_instance_id=instance.id,
        provider=instance.provider,
        frequency=frequency,
        cron_expression=cron_expression,
        interval_count=interval_count,
        next_run_at=(now + delta).isoformat(),
        timezone=timezone,
        workspace_id=instance.workspace_id,
        tenant_id=instance.tenant_id,
        created_at=now.isoformat(),
        updated_at=now.isoformat(),
    )
    saved = schedule_repo.create_schedule(schedule)

    await _record_connector_audit_event(
        request=request,
        repository=audit_repository,
        action="connector_schedule_create",
        response_type="connector_sync_schedule",
        status_code=200,
        success=True,
        provider=instance.provider,
        connector_instance_id=instance.id,
        details=_connector_audit_details(
            provider=instance.provider,
            connector_instance_id=instance.id,
        ),
    )
    return {
        "id": saved.id,
        "connectorInstanceId": saved.connector_instance_id,
        "provider": saved.provider,
        "frequency": saved.frequency,
        "cronExpression": saved.cron_expression,
        "intervalCount": saved.interval_count,
        "nextRunAt": saved.next_run_at,
        "isActive": saved.is_active,
        "timezone": saved.timezone,
        "createdAt": saved.created_at,
    }


@router.get(
    "/connectors/sync-schedules",
    responses={
        200: {"description": "List sync schedules."},
        503: {"description": "The connector sync repository is unavailable."},
    },
)
async def list_connector_sync_schedules(
    connector_instance_id: str | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    limit: int = Query(default=100, ge=0),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, object]]:
    """List sync schedules for connector instances."""
    schedule_repo = get_connector_sync_schedule_repository()
    schedules = schedule_repo.list_schedules(
        connector_instance_id=connector_instance_id,
        is_active=is_active,
        limit=limit,
        offset=offset,
    )
    return [
        {
            "id": s.id,
            "connectorInstanceId": s.connector_instance_id,
            "provider": s.provider,
            "frequency": s.frequency,
            "cronExpression": s.cron_expression,
            "intervalCount": s.interval_count,
            "nextRunAt": s.next_run_at,
            "lastRunAt": s.last_run_at,
            "lastJobId": s.last_job_id,
            "isActive": s.is_active,
            "timezone": s.timezone,
            "createdAt": s.created_at,
            "updatedAt": s.updated_at,
        }
        for s in schedules
    ]


@router.delete(
    "/connectors/sync-schedules/{schedule_id}",
    responses={
        200: {"description": "Delete the sync schedule."},
        404: {"description": "The sync schedule is not found."},
    },
)
async def delete_connector_sync_schedule(
    schedule_id: str,
) -> dict[str, object]:
    """Delete a sync schedule."""
    schedule_repo = get_connector_sync_schedule_repository()
    deleted = schedule_repo.delete_schedule(schedule_id)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail={"error": "schedule_not_found"},
        )
    return {"scheduleId": schedule_id, "deleted": True}


# ---------------------------------------------------------------------------
# Staleness health endpoint
# ---------------------------------------------------------------------------


@router.get(
    "/connectors/{provider}/staleness",
    responses={
        200: {"description": "Return staleness status for the connector."},
        404: {"description": "The connector instance is not found."},
    },
)
async def check_connector_staleness(
    provider: str,
    connector_instance_id: str | None = Query(default=None),
    instance_repository: ConnectorInstanceRepository = Depends(get_connector_instance_repository),
) -> dict[str, object]:
    """Check if the last successful sync for a connector is stale."""
    normalized_provider = _normalized_provider(provider)
    instance = (
        _resolve_connector_instance(
            normalized_provider, connector_instance_id, instance_repository
        )
        if connector_instance_id
        else None
    )
    job_repo = get_connector_sync_job_repository()
    instance_id = instance.id if instance else None
    jobs = job_repo.list_jobs(
        connector_instance_id=instance_id,
        provider=normalized_provider if not instance_id else None,
        status="completed",
        limit=1,
        offset=0,
    )
    max_age_seconds = 86400  # 24 hours default

    if not jobs:
        return {
            "stale": True,
            "reason": "no_successful_sync",
            "lastSyncedAt": None,
            "ageSeconds": None,
            "maxAgeSeconds": max_age_seconds,
        }
    last_job = jobs[0]
    if last_job.completed_at:
        last_synced = datetime.fromisoformat(last_job.completed_at)
        age = (datetime.now(UTC) - last_synced).total_seconds()
        is_stale = age > max_age_seconds
        return {
            "stale": is_stale,
            "reason": "age_exceeded" if is_stale else "ok",
            "lastSyncedAt": last_job.completed_at,
            "ageSeconds": int(age),
            "maxAgeSeconds": max_age_seconds,
        }
    return {
        "stale": True,
        "reason": "no_timestamp",
        "lastSyncedAt": None,
        "ageSeconds": None,
        "maxAgeSeconds": max_age_seconds,
    }
