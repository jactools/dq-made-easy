from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
import json
import logging
import os
from typing import Any
from urllib.parse import quote
from uuid import uuid4

from opentelemetry import propagate

from fastapi import HTTPException

from app.core.runtime_queues import resolve_profiling_queue_key as _resolve_runtime_profiling_queue_key
from app.core.otel_metrics import record_async_queue_event
from app.core.telemetry import traced_span
from app.domain.entities import SuggestionProfilingRequestEntity
from app.domain.entities.profiling_request import ProfilingRequest
from app.domain.interfaces import ProfilingRepository

try:
    import redis.asyncio as aioredis
except Exception:
    aioredis = None

try:
    import redis as redis_sync
except Exception:
    redis_sync = None


class ProfilingEnqueueServiceError(Exception):
    def __init__(self, public_detail: str, *, status_code: int = 503) -> None:
        super().__init__(public_detail)
        self.public_detail = public_detail
        self.status_code = status_code


class ProfilingRequestPersistenceError(ProfilingEnqueueServiceError):
    def __init__(self) -> None:
        super().__init__("Failed to persist profiling request")


class ProfilingRedisPushError(ProfilingEnqueueServiceError):
    def __init__(self) -> None:
        super().__init__("Failed to enqueue job to Redis")


class ProfilingQueueNotConfiguredError(ProfilingEnqueueServiceError):
    def __init__(self) -> None:
        super().__init__("Profiling queue is not configured")


@dataclass(frozen=True)
class ProfilingEnqueueResult:
    enqueued: bool
    job_id: str


def _profiling_active_conflict_detail(
    *,
    data_source_id: str,
    active_request: SuggestionProfilingRequestEntity,
) -> dict[str, Any]:
    return {
        "error": "profiling_request_already_active",
        "message": "Profiling is already active for this data source",
        "data_source_id": data_source_id,
        "active_request_id": str(active_request.id or ""),
        "active_request_status": str(active_request.status or ""),
    }


def _resolve_queue_key() -> str:
    queue_key = _resolve_runtime_profiling_queue_key()
    if queue_key:
        return queue_key
    raise ProfilingQueueNotConfiguredError()


def _resolve_redis_url(settings: Any) -> str | None:
    explicit_url = os.environ.get("PROFILING_REDIS_URL") or os.environ.get("REDIS_URL")
    if explicit_url:
        return explicit_url

    redis_host = str(settings.redis_host or "").strip()
    if not redis_host:
        return None

    redis_port = int(settings.redis_port)
    redis_db = int(settings.redis_db)
    redis_password = settings.redis_password
    if redis_password:
        return f"redis://:{quote(redis_password, safe='')}@{redis_host}:{redis_port}/{redis_db}"
    return f"redis://{redis_host}:{redis_port}/{redis_db}"


def _inject_trace_headers(payload: dict[str, Any]) -> None:
    carrier = payload.get("headers") if isinstance(payload.get("headers"), dict) else {}
    propagate.inject(carrier)
    payload["headers"] = carrier


def _build_queue_payload(request_body: Any, correlation_id: str) -> dict[str, Any]:
    queue_payload = request_body.model_dump(mode="python", by_alias=False, exclude_none=True)
    queue_payload["job_id"] = request_body.job_id or str(uuid4())
    queue_payload["profiling_request_id"] = request_body.profiling_request_id or str(uuid4())
    queue_payload["correlation_id"] = request_body.correlation_id or correlation_id

    headers = queue_payload.get("headers")
    if not isinstance(headers, dict):
        queue_payload["headers"] = {}

    return queue_payload


async def enqueue_profiling_job(
    *,
    request_body: Any,
    profiling_repository: ProfilingRepository,
    settings: Any,
    correlation_id: str,
) -> ProfilingEnqueueResult:
    logger = logging.getLogger("app.application.services.profiling_enqueue")
    payload = _build_queue_payload(request_body, correlation_id)
    job_id = payload["job_id"]
    profiling_request_id = payload["profiling_request_id"]

    data_source_id = str(payload.get("data_source_id") or "").strip()
    if data_source_id:
        active_request = profiling_repository.find_active_profiling_request(data_source_id)
        if active_request is not None:
            raise HTTPException(status_code=409, detail=_profiling_active_conflict_detail(
                data_source_id=data_source_id,
                active_request=active_request,
            ))

    _inject_trace_headers(payload)

    try:
        profiling_req = ProfilingRequest(
            id=None,
            profiling_request_id=profiling_request_id,
            data_source_id=payload.get("data_source_id"),
            requested_by_user_id=payload.get("requested_by_user_id"),
            requested_at=datetime.now(UTC),
            started_at=None,
            completed_at=None,
            status="pending",
            error_message=None,
            job_id=job_id,
        )
        with traced_span(
            "profiling.enqueue.persist",
            profiling_request_id=profiling_request_id,
            job_id=job_id,
            correlation_id=correlation_id,
        ):
            profiling_repository.create_request(profiling_req)
        logger.info(
            "created profiling request",
            extra={
                "profiling_request_id": profiling_request_id,
                "job_id": job_id,
                "correlation_id": correlation_id,
            },
        )
    except Exception as exc:
        logger.exception(
            "failed to persist profiling request: %s",
            exc,
            extra={
                "profiling_request_id": profiling_request_id,
                "job_id": job_id,
                "correlation_id": correlation_id,
            },
        )
        record_async_queue_event(service="dq-api", queue_type="profiling", stage="enqueue", result="failure")
        raise ProfilingRequestPersistenceError() from exc

    queue_key = _resolve_queue_key()
    redis_url = _resolve_redis_url(settings)
    if not redis_url:
        logger.error(
            "Profiling queue is not configured",
            extra={"job_id": job_id, "correlation_id": correlation_id},
        )
        raise ProfilingQueueNotConfiguredError()

    pushed = False
    if aioredis is not None:
        try:
            client = aioredis.from_url(redis_url, decode_responses=True)
            with traced_span(
                "profiling.enqueue.redis_push",
                profiling_request_id=profiling_request_id,
                job_id=job_id,
                queue_key=queue_key,
                correlation_id=correlation_id,
            ):
                await client.lpush(queue_key, json.dumps(payload))
            await client.close()
            pushed = True
        except Exception as exc:  # pragma: no cover - runtime guard
            logger.exception("async redis push failed: %s", exc)

    if not pushed and redis_sync is not None:
        try:
            def _lpush_sync() -> int:
                client = redis_sync.from_url(redis_url, decode_responses=True)
                return client.lpush(queue_key, json.dumps(payload))

            with traced_span(
                "profiling.enqueue.redis_push",
                profiling_request_id=profiling_request_id,
                job_id=job_id,
                queue_key=queue_key,
                correlation_id=correlation_id,
            ):
                await asyncio.to_thread(_lpush_sync)
            pushed = True
        except Exception as exc:  # pragma: no cover - runtime guard
            logger.exception("sync redis push failed: %s", exc)

    if pushed:
        record_async_queue_event(service="dq-api", queue_type="profiling", stage="enqueue", result="success")
        logger.info(
            "enqueued job to redis",
            extra={"job_id": job_id, "queue_key": queue_key, "correlation_id": correlation_id},
        )
        return ProfilingEnqueueResult(enqueued=True, job_id=job_id)

    logger.error(
        "Failed to enqueue job to Redis",
        extra={"job_id": job_id, "queue_key": queue_key, "correlation_id": correlation_id},
    )
    record_async_queue_event(service="dq-api", queue_type="profiling", stage="enqueue", result="failure")
    try:
        profiling_repository.set_completed(
            profiling_request_id,
            success=False,
            error_message="Failed to enqueue job to Redis",
        )
    except Exception:
        logger.debug("failed to mark profiling request as completed after enqueue failure", exc_info=True)
    raise ProfilingRedisPushError()