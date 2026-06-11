import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.v1.schemas import AdminUserView
from app.application.resolvers import resolve_admin_user_view
from app.core.dependencies import get_admin_repository
from app.core.log_event import log_event
from app.core.telemetry import set_span_attributes, traced_span
from app.domain.interfaces import AdminRepository

router = APIRouter(tags=["user"])
_log = logging.getLogger(__name__)


@router.get("/me", response_model=AdminUserView)
async def get_me(
    request: Request,
    repository: AdminRepository = Depends(get_admin_repository),
) -> AdminUserView:
    with traced_span("user.me.get", endpoint_group="user", operation="get_me") as span:
        result = repository.get_current_user(
            getattr(request.state, "user_id", None),
            getattr(request.state, "auth_claims", None),
        )
        if result is None:
            set_span_attributes(span, user_authenticated=False)
            log_event(_log, "user.me.get.unauthenticated", level="warning", component="user-api")
            raise HTTPException(status_code=401, detail="Not authenticated")
        set_span_attributes(span, user_authenticated=True, user_id=str(result.id))
        log_event(_log, "user.me.get.complete", component="user-api", userId=str(result.id))
        return resolve_admin_user_view(result)


@router.put("/me", response_model=AdminUserView)
async def update_me(
    payload: dict[str, Any],
    request: Request,
    repository: AdminRepository = Depends(get_admin_repository),
) -> AdminUserView:
    with traced_span("user.me.update", endpoint_group="user", operation="update_me") as span:
        result = repository.update_current_user(
            getattr(request.state, "user_id", None),
            getattr(request.state, "auth_claims", None),
            payload,
        )
        if result is None:
            set_span_attributes(span, user_authenticated=False)
            log_event(_log, "user.me.update.unauthenticated", level="warning", component="user-api")
            raise HTTPException(status_code=401, detail="Not authenticated")
        set_span_attributes(span, user_authenticated=True, user_id=str(result.id), payload_keys=sorted(payload.keys()))
        log_event(_log, "user.me.update.complete", component="user-api", userId=str(result.id))
        return resolve_admin_user_view(result)
