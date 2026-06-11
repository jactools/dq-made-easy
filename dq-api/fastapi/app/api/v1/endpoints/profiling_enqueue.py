from typing import Any, Dict

from datetime import UTC, datetime
import time

from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import ConfigDict, Field
from dq_domain_validation import ProfilingStatus
from app.schemas.pydantic_base import SnakeModel, to_snake_alias
import logging
import uuid
from app.api.presenters.profiling_enqueue import build_profiling_enqueue_response_payload
from app.api.presenters.profiling_enqueue import require_profiling_started_job_id
from app.api.presenters.profiling_enqueue import resolve_profiling_completion_success
from app.api.presenters.profiling_enqueue import resolve_profiling_enqueue_correlation_id
from app.api.presenters.profiling_enqueue import resolve_profiling_enqueue_settings
from app.application.services.profiling_enqueue_service import _build_queue_payload
from app.application.services.profiling_enqueue_service import _inject_trace_headers
from app.application.services.profiling_enqueue_service import _resolve_queue_key
from app.application.services.profiling_enqueue_service import _resolve_redis_url
from app.application.services.profiling_enqueue_service import enqueue_profiling_job
from app.application.services.profiling_enqueue_service import ProfilingEnqueueServiceError
from app.core.dependencies import get_profiling_repository
from app.domain.interfaces import ProfilingRepository
from app.core.config import Settings, get_settings
from app.core.api_metrics import api_metrics_store
from app.core.otel_metrics import record_request_metric
from app.core.request_context import get_correlation_id, set_correlation_id

router = APIRouter(tags=["profiling"])


class EnqueueResponse(SnakeModel):
    enqueued: bool
    job_id: Any | None = None


class EnqueueRequest(SnakeModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid", alias_generator=to_snake_alias)

    type: str | None = None
    payload: Dict[str, Any] = Field(default_factory=dict)
    headers: Dict[str, Any] = Field(default_factory=dict)
    job_id: str | None = None
    profiling_request_id: str | None = None
    data_source_id: str | None = None
    requested_by_user_id: str | None = None
    correlation_id: str | None = None


class ProfilingRequestReportRequest(SnakeModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid", alias_generator=to_snake_alias)

    new_status: ProfilingStatus
    job_id: str | None = None
    error_message: str | None = None


class ProfilingRequestReportResponse(SnakeModel):
    ok: bool


def _resolve_settings(request: Request) -> Settings:
    app_settings = getattr(getattr(request.app, "state", None), "settings", None)
    return resolve_profiling_enqueue_settings(app_settings, get_settings())


@router.post("/profiling/enqueue", response_model=EnqueueResponse)
async def enqueue_profiling(
    request: Request,
    request_body: EnqueueRequest,
    profiling_repository: ProfilingRepository = Depends(get_profiling_repository),
):
    """Enqueue a profiling job onto the Redis-backed worker queue."""
    logger = logging.getLogger("app.api.v1.profiling_enqueue")
    start_ts = time.time()

    settings = _resolve_settings(request)

    # Ensure we have a correlation id (reuse middleware/context if present)
    correlation_id, generated_correlation_id = resolve_profiling_enqueue_correlation_id(
        request_body,
        get_correlation_id(),
        request.headers,
    )
    if generated_correlation_id:
        set_correlation_id(correlation_id)

    try:
        result = await enqueue_profiling_job(
            request_body=request_body,
            profiling_repository=profiling_repository,
            settings=settings,
            correlation_id=correlation_id,
        )
    except ProfilingEnqueueServiceError as exc:
        duration_ms = (time.time() - start_ts) * 1000.0
        try:
            api_metrics_store.record(request.method, request.url.path, exc.status_code, duration_ms, error_detail=exc.public_detail)
        except Exception:
            logger.debug("api_metrics_store.record failed", exc_info=True)
        try:
            record_request_metric(method=request.method, path=request.url.path, operation="profiling_enqueue", status_code=exc.status_code, duration_ms=duration_ms)
        except Exception:
            logger.debug("record_request_metric failed", exc_info=True)
        raise HTTPException(status_code=exc.status_code, detail=exc.public_detail) from exc

    duration_ms = (time.time() - start_ts) * 1000.0
    try:
        api_metrics_store.record(request.method, request.url.path, 200, duration_ms)
    except Exception:
        logger.debug("api_metrics_store.record failed", exc_info=True)
    try:
        record_request_metric(method=request.method, path=request.url.path, operation="profiling_enqueue", status_code=200, duration_ms=duration_ms)
    except Exception:
        logger.debug("record_request_metric failed", exc_info=True)
    return build_profiling_enqueue_response_payload(result)


@router.post(
    "/profiling/requests/{profiling_request_id}/report",
    response_model=ProfilingRequestReportResponse,
    responses={
        200: {"description": "Profiling request status updated."},
        404: {"description": "Profiling request not found."},
    },
)
async def report_profiling_request_status(
    profiling_request_id: str,
    body: ProfilingRequestReportRequest,
    profiling_repository: ProfilingRepository = Depends(get_profiling_repository),
) -> ProfilingRequestReportResponse:
    logger = logging.getLogger("app.api.v1.profiling_report")

    if body.new_status == "started":
        try:
            job_id = require_profiling_started_job_id(body.new_status, body.job_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="job_id is required when new_status is started")
        assert job_id is not None
        try:
            profiling_repository.set_started(profiling_request_id, job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"profiling_request '{profiling_request_id}' not found") from exc
        except Exception as exc:
            logger.exception("failed to report profiling request started")
            raise HTTPException(status_code=503, detail="failed to update profiling request status") from exc

        return ProfilingRequestReportResponse(ok=True)

    # completed / failed
    success = resolve_profiling_completion_success(body.new_status)
    try:
        profiling_repository.set_completed(
            profiling_request_id,
            success=success,
            error_message=body.error_message,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"profiling_request '{profiling_request_id}' not found") from exc
    except Exception as exc:
        logger.exception("failed to report profiling request completion")
        raise HTTPException(status_code=503, detail="failed to update profiling request status") from exc

    return ProfilingRequestReportResponse(ok=True)
