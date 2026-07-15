"""Connector sync worker — processes pending sync jobs with retry/backoff.

This worker polls the connector_sync_jobs table for pending jobs,
executes the sync via the connector service, and updates job status.
It supports exponential backoff retries and incremental sync detection.
"""

from __future__ import annotations

import importlib
import json
import logging
import os
import time
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from dq_utils.logging_utils import configure_logging
from dq_utils.logging_utils import log_event

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_DEFAULT_POLL_INTERVAL_SECONDS = 10
_DEFAULT_MAX_RETRIES = 3
_DEFAULT_INITIAL_DELAY_SECONDS = 1.0
_DEFAULT_MAX_DELAY_SECONDS = 60.0
_DEFAULT_BACKOFF_MULTIPLIER = 2.0
_DEFAULT_STALE_JOB_SECONDS = 3600


def _load_config() -> dict[str, Any]:
    return {
        "database_url": os.getenv("PRIMARY_DATABASE_URL") or os.getenv("DATABASE_URL", ""),
        "poll_interval_seconds": int(os.getenv("CONNECTOR_SYNC_POLL_INTERVAL", _DEFAULT_POLL_INTERVAL_SECONDS)),
        "max_retries": int(os.getenv("CONNECTOR_SYNC_MAX_RETRIES", _DEFAULT_MAX_RETRIES)),
        "initial_delay_seconds": float(os.getenv("CONNECTOR_SYNC_INITIAL_DELAY", _DEFAULT_INITIAL_DELAY_SECONDS)),
        "max_delay_seconds": float(os.getenv("CONNECTOR_SYNC_MAX_DELAY", _DEFAULT_MAX_DELAY_SECONDS)),
        "backoff_multiplier": float(os.getenv("CONNECTOR_SYNC_BACKOFF_MULTIPLIER", _DEFAULT_BACKOFF_MULTIPLIER)),
        "stale_job_seconds": int(os.getenv("CONNECTOR_SYNC_STALE_JOB_SECONDS", _DEFAULT_STALE_JOB_SECONDS)),
        "log_level": os.getenv("DQ_LOG_LEVEL", "INFO"),
    }


# ---------------------------------------------------------------------------
# Retry policy
# ---------------------------------------------------------------------------

_RETRYABLE_KINDS = {"connection", "discovery", "sync", "timeout"}


def _compute_delay(attempt: int, config: dict[str, Any]) -> float:
    delay = config["initial_delay_seconds"] * (config["backoff_multiplier"] ** attempt)
    delay = min(delay, config["max_delay_seconds"])
    # Add jitter
    import random
    return delay * (0.5 + random.random() * 0.5)


# ---------------------------------------------------------------------------
# DB helpers (minimal, no ORM dependency)
# ---------------------------------------------------------------------------

def _get_db_connection(config: dict[str, Any]):
    import psycopg
    return psycopg.connect(config["database_url"])


def _claim_pending_job(cursor) -> dict[str, Any] | None:
    cursor.execute("""
        UPDATE connector_sync_jobs
        SET status = 'running',
            updated_at = NOW()
        WHERE id = (
            SELECT id FROM connector_sync_jobs
            WHERE status = 'pending'
            ORDER BY created_at ASC
            LIMIT 1
        )
        RETURNING *
    """)
    row = cursor.fetchone()
    if row is None:
        return None
    keys = [desc[0] for desc in cursor.description]
    return dict(zip(keys, row))


def _update_job_status(
    cursor,
    job_id: str,
    status: str,
    *,
    error_code: str | None = None,
    error_message: str | None = None,
    synced_count: int | None = None,
    added_count: int | None = None,
    updated_count: int | None = None,
    removed_count: int | None = None,
    result_snapshot: dict | None = None,
) -> None:
    sets = ["status = %s", "updated_at = NOW()"]
    params: list[Any] = [status]
    if error_code is not None:
        sets.append("error_code = %s")
        params.append(error_code)
    if error_message is not None:
        sets.append("error_message = %s")
        params.append(error_message)
    if synced_count is not None:
        sets.append("synced_count = %s")
        params.append(synced_count)
    if added_count is not None:
        sets.append("added_count = %s")
        params.append(added_count)
    if updated_count is not None:
        sets.append("updated_count = %s")
        params.append(updated_count)
    if removed_count is not None:
        sets.append("removed_count = %s")
        params.append(removed_count)
    if result_snapshot is not None:
        sets.append("result_snapshot = %s")
        params.append(json.dumps(result_snapshot, default=str))
    params.append(job_id)
    cursor.execute(
        f"UPDATE connector_sync_jobs SET {', '.join(sets)} WHERE id = %s",
        params,
    )


def _get_job_by_id(cursor, job_id: str) -> dict[str, Any] | None:
    cursor.execute("SELECT * FROM connector_sync_jobs WHERE id = %s", (job_id,))
    row = cursor.fetchone()
    if row is None:
        return None
    keys = [desc[0] for desc in cursor.description]
    return dict(zip(keys, row))


def _get_connector_instance(cursor, instance_id: str) -> dict[str, Any] | None:
    cursor.execute(
        "SELECT * FROM connector_instances WHERE id = %s",
        (instance_id,),
    )
    row = cursor.fetchone()
    if row is None:
        return None
    keys = [desc[0] for desc in cursor.description]
    return dict(zip(keys, row))


# ---------------------------------------------------------------------------
# Connector loader
# ---------------------------------------------------------------------------

def _load_connector(provider: str) -> Any:
    """Load connector class from the dq-api package."""
    provider_map = {
        "postgresql": "app.application.services.postgresql_connector:PostgreSQLConnector",
        "sql_server": "app.application.services.sql_server_connector:SqlServerConnector",
        "azure_adls": "app.application.services.azure_adls_connector:AzureAdlsConnector",
        "s3_blob": "app.application.services.s3_blob_connector:S3BlobConnector",
        "external_api": "app.application.services.external_api_connector:ExternalApiConnector",
    }
    path = provider_map.get(provider)
    if not path:
        raise ValueError(f"unknown provider: {provider}")
    module_path, class_name = path.rsplit(".", 1)
    module = importlib.import_module(module_path)
    return getattr(module, class_name)()


# ---------------------------------------------------------------------------
# Sync execution
# ---------------------------------------------------------------------------

def _execute_sync(job: dict[str, Any], cursor) -> dict[str, Any]:
    """Execute the sync for the connector instance and return results."""
    instance = _get_connector_instance(cursor, job["connector_instance_id"])
    if instance is None:
        raise ValueError(f"connector instance {job['connector_instance_id']} not found")

    provider = job["provider"]
    configuration = instance.get("configuration_json") or {}

    connector = _load_connector(provider)

    # Build configuration entity from stored JSON
    from app.domain.entities.connector import ConnectorSecureConfigurationEntity
    config_entity = ConnectorSecureConfigurationEntity.model_validate({
        **configuration,
        "provider": provider,
    })

    # Run sync
    result = connector.sync(config_entity)

    if result.errors:
        error_kind = result.errors[0].kind if result.errors else "unknown"
        raise ConnectionError(
            f"sync failed: {error_kind}",
            {"kind": error_kind},
        )

    return {
        "synced_count": result.synced_count,
        "added_count": result.added_count or 0,
        "updated_count": result.updated_count or 0,
        "removed_count": result.removed_count or 0,
    }


def _classify_error(exc: Exception) -> tuple[str, str]:
    """Classify an exception into error_code and error_kind."""
    if isinstance(exc, (ConnectionError, TimeoutError)):
        return "connection", "connection"
    if isinstance(exc, PermissionError):
        return "authentication", "authentication"
    if "authentication" in str(exc).lower():
        return "authentication", "authentication"
    if "discovery" in str(exc).lower():
        return "discovery", "discovery"
    return "sync", "sync"


# ---------------------------------------------------------------------------
# Main worker loop
# ---------------------------------------------------------------------------

def run_worker_forever() -> None:
    """Main worker loop — poll for pending jobs and process them."""
    config = _load_config()
    configure_logging(config["log_level"])
    logger = logging.getLogger(__name__)

    log_event(
        logger,
        "connector_sync_worker.start",
        component="connector-sync-worker",
        pollInterval=config["poll_interval_seconds"],
        maxRetries=config["max_retries"],
    )

    consecutive_empty_polls = 0
    max_empty_polls = 60  # ~10 minutes at default interval

    while True:
        try:
            conn = _get_db_connection(config)
            conn.autocommit = False
            cursor = conn.cursor()

            job = _claim_pending_job(cursor)
            if job is None:
                conn.rollback()
                cursor.close()
                conn.close()
                consecutive_empty_polls += 1
                if consecutive_empty_polls > max_empty_polls:
                    # Reset counter periodically
                    consecutive_empty_polls = 0
                time.sleep(config["poll_interval_seconds"])
                continue

            consecutive_empty_polls = 0
            log_event(
                logger,
                "connector_sync_worker.job_claimed",
                component="connector-sync-worker",
                jobId=job["id"],
                provider=job["provider"],
                connectorInstanceId=job["connector_instance_id"],
            )

            try:
                result = _execute_sync(job, cursor)
                _update_job_status(
                    cursor,
                    job["id"],
                    "completed",
                    synced_count=result["synced_count"],
                    added_count=result["added_count"],
                    updated_count=result["updated_count"],
                    removed_count=result["removed_count"],
                    result_snapshot=result,
                )
                conn.commit()
                log_event(
                    logger,
                    "connector_sync_worker.job_completed",
                    component="connector-sync-worker",
                    jobId=job["id"],
                    syncedCount=result["synced_count"],
                )

            except Exception as exc:
                error_code, error_kind = _classify_error(exc)
                retry_count = int(job.get("retry_count") or 0)
                max_retries = int(job.get("max_retries") or config["max_retries"])

                if retry_count < max_retries and error_kind in _RETRYABLE_KINDS:
                    # Retry with backoff
                    delay = _compute_delay(retry_count, config)
                    _update_job_status(
                        cursor,
                        job["id"],
                        "retrying",
                        error_code=error_code,
                        error_message=str(exc),
                    )
                    conn.commit()
                    log_event(
                        logger,
                        "connector_sync_worker.job_retrying",
                        component="connector-sync-worker",
                        jobId=job["id"],
                        retryCount=retry_count + 1,
                        maxRetries=max_retries,
                        delaySeconds=round(delay, 2),
                        level="warning",
                    )
                    time.sleep(delay)
                    # Reset to pending after delay
                    _update_job_status(cursor, job["id"], "pending")
                    conn.commit()
                else:
                    _update_job_status(
                        cursor,
                        job["id"],
                        "failed",
                        error_code=error_code,
                        error_message=str(exc),
                    )
                    conn.commit()
                    log_event(
                        logger,
                        "connector_sync_worker.job_failed",
                        component="connector-sync-worker",
                        jobId=job["id"],
                        errorCode=error_code,
                        errorMessage=str(exc),
                        level="error",
                    )

        except KeyboardInterrupt:
            raise
        except Exception as exc:
            log_event(
                logger,
                "connector_sync_worker.loop_error",
                component="connector-sync-worker",
                level="error",
                errorMessage=str(exc),
            )
            time.sleep(config["poll_interval_seconds"])
        finally:
            try:
                cursor.close()
                conn.close()
            except Exception:
                pass


if __name__ == "__main__":
    run_worker_forever()
