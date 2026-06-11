from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.api.presenters.notifications import build_notification_entities
from app.api.v1.schemas import NotificationView
from app.core.dependencies import get_approvals_repository
from app.core.request_context import get_user_id
from app.domain.interfaces import ApprovalsRepository
from dq_domain_validation import NotificationType

router = APIRouter(tags=["notifications"])
_log = logging.getLogger(__name__)


@router.get("/notifications", response_model=list[NotificationView])
async def list_notifications(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    action: str | None = None,
    notification_type: NotificationType = "gx_suite_empty",
    repository: ApprovalsRepository = Depends(get_approvals_repository),
) -> list[NotificationView]:
    user_id = str(getattr(request.state, "user_id", None) or get_user_id() or "").strip()
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    effective_action = str(action or f"notification.{notification_type}").strip()
    notifications = build_notification_entities(
        repository.list_approval_audit(),
        user_id,
        action=effective_action,
        notification_type=notification_type,
    )
    return [NotificationView.model_validate(item) for item in notifications[offset : offset + limit]]
