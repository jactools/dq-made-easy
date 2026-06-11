from collections.abc import Sequence
from typing import Any

from app.api.v1.schemas.admin_view import AdminRoleView, AdminUserView, AdminUsersPageView, ExceptionFactAccessRequestView
from app.api.v1.schemas.common_view import IdResponseView
from app.domain.entities import AdminRoleEntity, AdminUserEntity, ExceptionFactAccessRequestEntity


def resolve_admin_users_view(payload: dict[str, Any]) -> AdminUsersPageView:
    return AdminUsersPageView.model_validate(payload)


def resolve_admin_user_view(entity: AdminUserEntity) -> AdminUserView:
    return AdminUserView.model_validate(entity)


def resolve_admin_roles_view(rows: Sequence[AdminRoleEntity]) -> list[AdminRoleView]:
    return [AdminRoleView.model_validate(row) for row in rows]


def resolve_exception_fact_access_request_view(entity: ExceptionFactAccessRequestEntity) -> ExceptionFactAccessRequestView:
    return ExceptionFactAccessRequestView.model_validate(
        {
            "id": entity.id,
            "requester_id": entity.requesterId,
            "workspace_id": entity.workspaceId,
            "role_id": entity.roleId,
            "status": entity.status,
            "requested_duration_minutes": entity.requestedDurationMinutes,
            "comments": entity.comments,
            "requested_at": entity.requestedAt,
            "reviewed_by": entity.reviewedBy,
            "reviewed_at": entity.reviewedAt,
            "expires_at": entity.expiresAt,
        }
    )


def resolve_id_response(entity_id: str) -> IdResponseView:
    return IdResponseView(id=entity_id)
