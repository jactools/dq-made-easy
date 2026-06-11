from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.api.v1.endpoints.admin import _has_any_non_exception_role
from app.api.v1.schemas import ExceptionFactAccessRequestView
from app.application.resolvers import resolve_exception_fact_access_request_view
from app.core.dependencies import get_app_config_repository
from app.core.dependencies import get_admin_repository
from app.domain.interfaces import AdminRepository
from app.domain.interfaces import AppConfigRepository

router = APIRouter(tags=["governance"])


@router.get("/exception-fact-access-requests", response_model=list[ExceptionFactAccessRequestView])
async def list_my_exception_fact_access_requests(
    request: Request,
    status: str | None = Query(default=None),
    repository: AdminRepository = Depends(get_admin_repository),
    config_repository: AppConfigRepository = Depends(get_app_config_repository),
) -> list[ExceptionFactAccessRequestView]:
    current_user = repository.get_current_user(getattr(request.state, "user_id", None), getattr(request.state, "auth_claims", None))
    if current_user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    config = config_repository.get_app_config()
    requests = repository.list_exception_fact_access_requests(
        requester_id=str(current_user.id),
        status=status,
        request_timeout_minutes=max(1, int(config.exceptionFactJitRequestTimeoutMinutes)),
    )
    return [resolve_exception_fact_access_request_view(item) for item in requests]


@router.post("/exception-fact-access-requests", response_model=ExceptionFactAccessRequestView)
async def create_exception_fact_access_request(
    request: Request,
    payload: dict[str, Any],
    repository: AdminRepository = Depends(get_admin_repository),
) -> ExceptionFactAccessRequestView:
    current_user = repository.get_current_user(getattr(request.state, "user_id", None), getattr(request.state, "auth_claims", None))
    if current_user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    workspace_id = str(payload.get("workspace_id") or payload.get("workspaceId") or "").strip()
    role_id = str(payload.get("role_id") or payload.get("roleId") or "").strip()
    if not workspace_id:
        raise HTTPException(status_code=422, detail="workspace_id is required")
    if role_id not in {"exception-fact-reader", "exception-fact-investigator"}:
        raise HTTPException(
            status_code=422,
            detail="role_id must be exception-fact-reader or exception-fact-investigator",
        )
    if not _has_any_non_exception_role(current_user, workspace_id):
        raise HTTPException(
            status_code=403,
            detail={
                "error": "exception_fact_access_denied",
                "message": "An existing workspace role is required before requesting JIT access",
                "workspace_id": workspace_id,
            },
        )

    created = repository.create_exception_fact_access_request(
        {
            "workspace_id": workspace_id,
            "role_id": role_id,
            "requested_duration_minutes": payload.get("requested_duration_minutes") or payload.get("requestedDurationMinutes"),
            "comments": payload.get("comments"),
        },
        actor_id=str(current_user.id),
    )
    return resolve_exception_fact_access_request_view(created)
