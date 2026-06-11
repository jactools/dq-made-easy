from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
import logging
import os
from typing import Any
from typing import Mapping
from uuid import uuid4

from opentelemetry import propagate

from app.core.otel_metrics import record_natural_language_draft_request_event
from app.core.otel_metrics import record_suggestions_redis_failure
from app.core.otel_metrics import record_suggestions_redis_request
from app.core.runtime_queues import resolve_natural_language_draft_queue_key as _resolve_runtime_natural_language_draft_queue_key
from app.domain.entities import NaturalLanguageDraftRequestEntity
from app.domain.interfaces.v1.suggestions_repository import SuggestionsRepository

try:
    import redis.asyncio as aioredis
except Exception:
    aioredis = None

try:
    import redis as redis_sync
except Exception:
    redis_sync = None


NATURAL_LANGUAGE_DRAFT_REQUEST_TTL_SECONDS = 24 * 60 * 60
NATURAL_LANGUAGE_DRAFT_EVENT_STREAM_MAXLEN = 100


class NaturalLanguageDraftEnqueueServiceError(Exception):
    def __init__(self, public_detail: str, *, status_code: int = 503) -> None:
        super().__init__(public_detail)
        self.public_detail = public_detail
        self.status_code = status_code


class NaturalLanguageDraftRequestPersistenceError(NaturalLanguageDraftEnqueueServiceError):
    def __init__(self) -> None:
        super().__init__("Failed to persist natural-language draft request")


class NaturalLanguageDraftRedisPushError(NaturalLanguageDraftEnqueueServiceError):
    def __init__(self) -> None:
        super().__init__("Failed to enqueue draft request to Redis")


class NaturalLanguageDraftQueueNotConfiguredError(NaturalLanguageDraftEnqueueServiceError):
    def __init__(self) -> None:
        super().__init__("Natural-language draft queue is not configured")


@dataclass(frozen=True)
class NaturalLanguageDraftEnqueueResult:
    enqueued: bool
    request_id: str


def _resolve_queue_key() -> str:
    queue_key = _resolve_runtime_natural_language_draft_queue_key()
    if queue_key:
        return queue_key
    raise NaturalLanguageDraftQueueNotConfiguredError()


def _resolve_redis_url(settings: Any) -> str | None:
    explicit_url = os.environ.get("NATURAL_LANGUAGE_DRAFT_REDIS_URL") or os.environ.get("REDIS_URL")
    if explicit_url:
        return explicit_url

    redis_host = str(getattr(settings, "redis_host", "") or "").strip()
    if not redis_host:
        return None

    redis_port = int(getattr(settings, "redis_port", 6379))
    redis_db = int(getattr(settings, "redis_db", 0))
    redis_password = getattr(settings, "redis_password", None)
    if redis_password:
        from urllib.parse import quote

        return f"redis://:{quote(str(redis_password), safe='')}@{redis_host}:{redis_port}/{redis_db}"
    return f"redis://{redis_host}:{redis_port}/{redis_db}"


def _request_key(request_id: str) -> str:
    return f"natural-language-draft-request:{request_id}"


def request_event_stream_key(request_id: str) -> str:
    return f"natural-language-draft-request-events:{request_id}"


def _inject_trace_headers(payload: dict[str, Any]) -> None:
    carrier = payload.get("headers") if isinstance(payload.get("headers"), dict) else {}
    propagate.inject(carrier)
    payload["headers"] = carrier


def _build_queue_payload(
    request_body: Any,
    correlation_id: str,
    *,
    requested_by_user_id: str,
    accessible_workspace_ids: set[str],
    selected_attribute_ids: list[str] | None = None,
) -> dict[str, Any]:
    queue_payload = request_body.model_dump(mode="python", by_alias=True, exclude_none=True)
    queue_payload["job_id"] = str(uuid4())
    queue_payload["request_id"] = str(uuid4())
    queue_payload["correlation_id"] = correlation_id
    queue_payload["requested_by_user_id"] = str(requested_by_user_id or "").strip()
    queue_payload["accessible_workspace_ids"] = sorted({str(item).strip() for item in accessible_workspace_ids if str(item).strip()})
    queue_payload["selected_attribute_ids"] = [str(item).strip() for item in (selected_attribute_ids if selected_attribute_ids is not None else list(queue_payload.get("selected_attribute_ids") or [])) if str(item).strip()]
    queue_payload.setdefault("status", "pending")
    headers = queue_payload.get("headers")
    if not isinstance(headers, dict):
        queue_payload["headers"] = {}
    return queue_payload


def _current_timestamp() -> str:
    return datetime.now(UTC).isoformat()


def _build_request_record(payload: dict[str, Any]) -> dict[str, Any]:
    selected_attribute_ids = [str(item).strip() for item in list(payload.get("selected_attribute_ids") or []) if str(item).strip()]
    analysis_type = str(payload.get("analysis_type") or ("draft" if selected_attribute_ids else "preview")).strip().lower() or "preview"
    record = {
        "request_id": str(payload.get("request_id") or "").strip(),
        "job_id": str(payload.get("job_id") or "").strip(),
        "requested_by_user_id": str(payload.get("requested_by_user_id") or "").strip() or None,
        "current_workspace_id": str(payload.get("current_workspace_id") or "").strip(),
        "search_scope": str(payload.get("search_scope") or "current").strip(),
        "analysis_provider": str(payload.get("analysis_provider") or "llm").strip().lower() or "llm",
        "analysis_type": analysis_type,
        "prompt": str(payload.get("prompt") or "").strip(),
        "selected_attribute_ids": selected_attribute_ids,
        "accessible_workspace_ids": sorted({str(item).strip() for item in list(payload.get("accessible_workspace_ids") or []) if str(item).strip()}),
        "status": str(payload.get("status") or "pending").strip().lower() or "pending",
        "requested_at": payload.get("requested_at") or _current_timestamp(),
        "started_at": payload.get("started_at"),
        "completed_at": payload.get("completed_at"),
        "error_message": payload.get("error_message"),
        "suggestion_id": payload.get("suggestion_id"),
        "result": payload.get("result"),
        "correlation_id": payload.get("correlation_id"),
        "headers": dict(payload.get("headers") or {}),
    }
    for extra_key in ("version_id", "task_payload", "auto_import"):
        if extra_key in payload:
            record[extra_key] = payload.get(extra_key)
    return record


def build_request_status_event_payload(record: Mapping[str, Any]) -> dict[str, Any]:
    status = str(record.get("status") or "pending").strip().lower() or "pending"
    changed_at = record.get("completed_at") or record.get("started_at") or record.get("requested_at") or _current_timestamp()
    request_payload = {
        "request_id": str(record.get("request_id") or "").strip(),
        "current_workspace_id": str(record.get("current_workspace_id") or "").strip(),
        "version_id": record.get("version_id"),
        "selected_attribute_ids": list(record.get("selected_attribute_ids") or []),
        "prompt": str(record.get("prompt") or ""),
        "requested_by_user_id": record.get("requested_by_user_id"),
        "requested_at": record.get("requested_at"),
        "started_at": record.get("started_at"),
        "completed_at": record.get("completed_at"),
        "status": status,
        "error_message": record.get("error_message"),
        "analysis_type": str(record.get("analysis_type") or "preview"),
        "analysis_provider": str(record.get("analysis_provider") or "llm"),
        "auto_import": bool(record.get("auto_import")),
        "task_payload": dict(record.get("task_payload") or {}),
        "result": record.get("result"),
    }
    return {
        "request_id": request_payload["request_id"],
        "status": status,
        "changed_at": changed_at,
        "error_message": record.get("error_message"),
        "request": request_payload,
    }


def _publish_request_status_event(redis_client: Any, record: Mapping[str, Any], *, event_name: str = "status_changed") -> str:
    request_id = str(record.get("request_id") or "").strip()
    if not request_id:
        raise NaturalLanguageDraftRedisPushError()
    try:
        event_id = redis_client.xadd(
            request_event_stream_key(request_id),
            {
                "event": event_name,
                "data": json.dumps(build_request_status_event_payload(record), sort_keys=True),
            },
            maxlen=NATURAL_LANGUAGE_DRAFT_EVENT_STREAM_MAXLEN,
            approximate=True,
        )
    except Exception as exc:
        record_suggestions_redis_failure(operation_type="xadd", failure_type=exc.__class__.__name__)
        raise

    record_suggestions_redis_request(operation_type="xadd", status="success")
    return str(event_id)


def _store_request_record(redis_client: Any, record: dict[str, Any]) -> None:
    try:
        redis_client.set(
            _request_key(str(record["request_id"])),
            json.dumps(record),
            ex=NATURAL_LANGUAGE_DRAFT_REQUEST_TTL_SECONDS,
        )
    except Exception as exc:
        record_suggestions_redis_failure(operation_type="set", failure_type=exc.__class__.__name__)
        raise

    record_suggestions_redis_request(operation_type="set", status="success")


def load_request_record(redis_client: Any, request_id: str) -> dict[str, Any] | None:
    try:
        raw = redis_client.get(_request_key(request_id))
    except Exception as exc:
        record_suggestions_redis_failure(operation_type="get", failure_type=exc.__class__.__name__)
        raise

    record_suggestions_redis_request(operation_type="get", status="success")
    return json.loads(raw) if raw else None


def load_request_record_from_settings(settings: Any, request_id: str) -> dict[str, Any] | None:
    redis_url = _resolve_redis_url(settings)
    if not redis_url or redis_sync is None:
        raise NaturalLanguageDraftQueueNotConfiguredError()

    client = redis_sync.from_url(redis_url, decode_responses=True)
    return load_request_record(client, request_id)


def save_request_record_to_settings(settings: Any, record: dict[str, Any]) -> None:
    redis_url = _resolve_redis_url(settings)
    if not redis_url or redis_sync is None:
        raise NaturalLanguageDraftQueueNotConfiguredError()

    client = redis_sync.from_url(redis_url, decode_responses=True)
    _store_request_record(client, record)


def mark_request_started(redis_client: Any, *, request_id: str, job_id: str) -> dict[str, Any] | None:
    record = load_request_record(redis_client, request_id)
    if record is None:
        return None
    record["status"] = "started"
    record["job_id"] = job_id
    record["started_at"] = record.get("started_at") or _current_timestamp()
    record["error_message"] = None
    _store_request_record(redis_client, record)
    _publish_request_status_event(redis_client, record)
    return record


def mark_request_completed(
    redis_client: Any,
    *,
    request_id: str,
    success: bool,
    error_message: str | None = None,
    suggestion_id: str | None = None,
    result: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    record = load_request_record(redis_client, request_id)
    if record is None:
        return None
    record["status"] = "completed" if success else "failed"
    record["completed_at"] = _current_timestamp()
    record["error_message"] = error_message
    record["suggestion_id"] = suggestion_id
    record["result"] = result
    _store_request_record(redis_client, record)
    _publish_request_status_event(redis_client, record)
    return record


async def open_request_event_stream_client(settings: Any) -> Any:
    redis_url = _resolve_redis_url(settings)
    if not redis_url or aioredis is None:
        raise NaturalLanguageDraftQueueNotConfiguredError()
    return aioredis.from_url(redis_url, decode_responses=True)


async def read_request_status_events(
    redis_client: Any,
    *,
    request_id: str,
    last_event_id: str,
    block_ms: int = 30000,
    count: int = 10,
) -> list[tuple[str, dict[str, str]]]:
    try:
        streams = await redis_client.xread(
            {request_event_stream_key(request_id): last_event_id},
            block=block_ms,
            count=count,
        )
    except Exception as exc:
        record_suggestions_redis_failure(operation_type="xread", failure_type=exc.__class__.__name__)
        raise

    record_suggestions_redis_request(operation_type="xread", status="success")
    events: list[tuple[str, dict[str, str]]] = []
    for _, entries in streams or []:
        for event_id, fields in entries:
            events.append((str(event_id), dict(fields or {})))
    return events


async def enqueue_natural_language_draft_job(
    *,
    request_body: Any,
    settings: Any,
    suggestions_repository: SuggestionsRepository,
    correlation_id: str,
    requested_by_user_id: str,
    accessible_workspace_ids: set[str],
    selected_attribute_ids: list[str] | None = None,
) -> NaturalLanguageDraftEnqueueResult:
    logger = logging.getLogger("app.application.services.natural_language_draft_enqueue")
    payload = _build_queue_payload(
        request_body,
        correlation_id,
        requested_by_user_id=requested_by_user_id,
        accessible_workspace_ids=accessible_workspace_ids,
        selected_attribute_ids=selected_attribute_ids,
    )
    request_id = payload["request_id"]
    job_id = payload["job_id"]
    analysis_provider = str(payload.get("analysis_provider") or "llm").strip().lower() or "llm"

    _inject_trace_headers(payload)

    record = _build_request_record(payload)
    try:
        suggestions_repository.record_natural_language_request(
            request=NaturalLanguageDraftRequestEntity.model_validate(record)
        )
    except Exception as exc:
        logger.exception(
            "failed to persist natural-language draft request",
            extra={"request_id": request_id, "job_id": job_id, "correlation_id": correlation_id},
        )
        record_natural_language_draft_request_event(
            stage="enqueue",
            result="failure",
            analysis_provider=analysis_provider,
            error_code="request_persistence_failed",
        )
        raise NaturalLanguageDraftRequestPersistenceError() from exc

    try:
        queue_key = _resolve_queue_key()
        redis_url = _resolve_redis_url(settings)
        if not redis_url:
            raise NaturalLanguageDraftQueueNotConfiguredError()
        if aioredis is None:
            raise NaturalLanguageDraftRedisPushError()

        client = aioredis.from_url(redis_url, decode_responses=True)
        try:
            try:
                await client.set(_request_key(request_id), json.dumps(record), ex=NATURAL_LANGUAGE_DRAFT_REQUEST_TTL_SECONDS)
            except Exception as exc:
                record_suggestions_redis_failure(operation_type="set", failure_type=exc.__class__.__name__)
                raise
            record_suggestions_redis_request(operation_type="set", status="success")

            try:
                await client.lpush(queue_key, json.dumps(payload))
            except Exception as exc:
                record_suggestions_redis_failure(operation_type="lpush", failure_type=exc.__class__.__name__)
                raise
            record_suggestions_redis_request(operation_type="lpush", status="success")
        finally:
            await client.aclose()
    except NaturalLanguageDraftQueueNotConfiguredError as exc:
        logger.error(
            "Natural-language draft queue is not configured",
            extra={"request_id": request_id, "job_id": job_id, "correlation_id": correlation_id},
        )
        try:
            suggestions_repository.update_natural_language_request(
                request_id=request_id,
                status="failed",
                job_id=job_id,
                completed_at=_current_timestamp(),
                error_message=exc.public_detail,
            )
        except Exception:
            logger.exception(
                "failed to update natural-language request after queue misconfiguration",
                extra={"request_id": request_id, "job_id": job_id, "correlation_id": correlation_id},
            )
        record_natural_language_draft_request_event(
            stage="enqueue",
            result="failure",
            analysis_provider=analysis_provider,
            error_code="queue_not_configured",
        )
        raise exc
    except NaturalLanguageDraftRedisPushError as exc:
        logger.error(
            "Natural-language draft Redis push is unavailable",
            extra={"request_id": request_id, "job_id": job_id, "correlation_id": correlation_id},
        )
        try:
            suggestions_repository.update_natural_language_request(
                request_id=request_id,
                status="failed",
                job_id=job_id,
                completed_at=_current_timestamp(),
                error_message=exc.public_detail,
            )
        except Exception:
            logger.exception(
                "failed to update natural-language request after Redis push failure",
                extra={"request_id": request_id, "job_id": job_id, "correlation_id": correlation_id},
            )
        record_natural_language_draft_request_event(
            stage="enqueue",
            result="failure",
            analysis_provider=analysis_provider,
            error_code="redis_push_failed",
        )
        raise exc
    except Exception as exc:
        logger.exception(
            "failed to enqueue natural-language draft request",
            extra={"request_id": request_id, "job_id": job_id, "correlation_id": correlation_id},
        )
        try:
            suggestions_repository.update_natural_language_request(
                request_id=request_id,
                status="failed",
                job_id=job_id,
                completed_at=_current_timestamp(),
                error_message=str(exc),
            )
        except Exception:
            logger.exception(
                "failed to update natural-language request after enqueue failure",
                extra={"request_id": request_id, "job_id": job_id, "correlation_id": correlation_id},
            )
        record_natural_language_draft_request_event(
            stage="enqueue",
            result="failure",
            analysis_provider=analysis_provider,
            error_code="redis_push_failed",
        )
        raise NaturalLanguageDraftRedisPushError() from exc

    record_natural_language_draft_request_event(
        stage="enqueue",
        result="success",
        analysis_provider=analysis_provider,
    )
    logger.info(
        "enqueued natural-language draft request",
        extra={"request_id": request_id, "job_id": job_id, "correlation_id": correlation_id},
    )
    return NaturalLanguageDraftEnqueueResult(enqueued=True, request_id=request_id)