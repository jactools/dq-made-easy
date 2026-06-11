from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response

from app.api.v1.async_status_events import status_event_stream_response
from app.application.services.profiling_request_service import ProfilingRequestService
from app.api.presenters.suggestions import build_data_source_not_found_payload
from app.api.presenters.suggestions import build_not_authenticated_payload
from app.api.presenters.suggestions import build_profiling_enqueue_failed_payload
from app.api.presenters.suggestions import build_profiling_rate_limit_payload
from app.api.presenters.suggestions import build_profiling_request_not_found_payload
from app.api.presenters.suggestions import build_profiling_request_status_payload
from app.api.presenters.suggestions import build_profiling_requests_payload
from app.api.presenters.suggestions import serialize_suggestion_entity
from app.core.dependencies import get_approvals_repository
from app.core.dependencies import get_profiling_repository
from app.core.request_context import get_user_id
from app.domain.interfaces import ApprovalsRepository
from app.domain.interfaces import ProfilingRepository
from app.domain.interfaces.profiling_repository import ProfilingDataSourceNotFoundError
from app.domain.interfaces.profiling_repository import ProfilingEnqueueFailedError
from app.domain.interfaces.profiling_repository import ProfilingRateLimitError
from app.domain.interfaces.profiling_repository import ProfilingRequestNotFoundError

router = APIRouter(tags=["profiling"])

_PROFILING_EVENT_POLL_INTERVAL_SECONDS = 2.0


def profiling_request_events_url(profiling_request_id: str) -> str:
    return f"/data-catalog/v1/profiling/requests/{profiling_request_id}/events"


def _profiling_request_event_payload(request: Any) -> dict[str, Any]:
    request_payload = build_profiling_request_status_payload(request)["request"]
    return {
        "request_id": str(request_payload.get("id") or request_payload.get("profiling_request_id") or "").strip(),
        "status": request_payload.get("status"),
        "request": request_payload,
    }


@router.post("/profiling/requests")
async def request_data_profiling(
    data_source_id: str = Query(min_length=1),
    workspace_id: str = Query(min_length=1),
    repository: ProfilingRepository = Depends(get_profiling_repository),
    approvals_repository: ApprovalsRepository = Depends(get_approvals_repository),
) -> JSONResponse:
    user_id = get_user_id()
    if not user_id:
        return JSONResponse(status_code=401, content=build_not_authenticated_payload())

    normalized_workspace_id = str(workspace_id or "").strip()
    if not normalized_workspace_id:
        raise HTTPException(status_code=400, detail="workspace_id is required for profiling requests")

    service = ProfilingRequestService(
        profiling_repository=repository,
        approvals_repository=approvals_repository,
    )

    try:
        result = service.request_profiling(
            user_id=user_id,
            data_source_id=data_source_id,
            workspace_id=normalized_workspace_id,
        )
    except ProfilingDataSourceNotFoundError:
        return JSONResponse(status_code=404, content=build_data_source_not_found_payload())
    except ProfilingRateLimitError as exc:
        return JSONResponse(
            status_code=429,
            content=build_profiling_rate_limit_payload(
                last_requested_at=exc.last_requested_at,
                minutes_remaining=exc.minutes_remaining,
            ),
        )
    except ProfilingEnqueueFailedError as exc:
        return JSONResponse(
            status_code=503,
            content=build_profiling_enqueue_failed_payload(profiling_request_id=exc.profiling_request_id),
        )
    content = serialize_suggestion_entity(result)
    content["events_url"] = profiling_request_events_url(str(result.profiling_request_id))
    return JSONResponse(status_code=200, content=content)


@router.get("/profiling/requests")
async def list_profiling_requests(
    data_source_id: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    repository: ProfilingRepository = Depends(get_profiling_repository),
    approvals_repository: ApprovalsRepository = Depends(get_approvals_repository),
) -> JSONResponse:
    user_id = get_user_id()
    if not user_id:
        return JSONResponse(status_code=401, content=build_not_authenticated_payload())

    service = ProfilingRequestService(
        profiling_repository=repository,
        approvals_repository=approvals_repository,
    )
    requests = service.list_profiling_requests(
        user_id=user_id,
        data_source_id=data_source_id,
        limit=limit,
    )
    return JSONResponse(status_code=200, content=build_profiling_requests_payload(requests))


@router.get("/profiling/requests/{profiling_request_id}/status")
async def get_profiling_request_status(
    profiling_request_id: str,
    repository: ProfilingRepository = Depends(get_profiling_repository),
    approvals_repository: ApprovalsRepository = Depends(get_approvals_repository),
) -> JSONResponse:
    service = ProfilingRequestService(
        profiling_repository=repository,
        approvals_repository=approvals_repository,
    )
    try:
        request = service.get_profiling_request_status(profiling_request_id)
    except ProfilingRequestNotFoundError:
        return JSONResponse(status_code=404, content=build_profiling_request_not_found_payload())
    return JSONResponse(status_code=200, content=build_profiling_request_status_payload(request))


@router.get("/profiling/requests/{profiling_request_id}/events", response_model=None)
async def stream_profiling_request_events(
    profiling_request_id: str,
    request: Request,
    repository: ProfilingRepository = Depends(get_profiling_repository),
    approvals_repository: ApprovalsRepository = Depends(get_approvals_repository),
) -> Response:
    service = ProfilingRequestService(
        profiling_repository=repository,
        approvals_repository=approvals_repository,
    )

    async def _load_payload() -> dict[str, Any]:
        try:
            request_record = service.get_profiling_request_status(profiling_request_id)
        except ProfilingRequestNotFoundError as exc:
            raise HTTPException(status_code=404, detail=build_profiling_request_not_found_payload()) from exc
        return _profiling_request_event_payload(request_record)

    initial_payload = await _load_payload()
    return status_event_stream_response(
        request=request,
        initial_payload=initial_payload,
        load_payload=_load_payload,
        poll_interval_seconds=_PROFILING_EVENT_POLL_INTERVAL_SECONDS,
    )