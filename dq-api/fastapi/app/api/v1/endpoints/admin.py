import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.api.presenters.admin import build_admin_users_page_payload
from app.api.presenters.admin import derive_admin_rule_status_from_row
from app.api.presenters.admin import filter_admin_users
from app.api.presenters.row_access import read_row_field
from app.api.v1.schemas import AdminRoleView, AdminUserView, AdminUsersPageView, ExceptionFactAccessRequestView, IdResponseView
from app.application.resolvers import (
    resolve_admin_roles_view,
    resolve_admin_user_view,
    resolve_admin_users_view,
    resolve_exception_fact_access_request_view,
    resolve_id_response,
)
from app.core.dependencies import get_app_config_repository
from app.core.dependencies import get_admin_repository
from app.core.dependencies import get_rules_repository
from app.core.log_event import log_event
from app.core.request_context import get_scopes
from app.core.telemetry import set_span_attributes, traced_span
from app.domain.status_governance import is_transition_allowed
from app.domain.interfaces import AppConfigRepository
from app.domain.interfaces import AdminRepository
from app.domain.interfaces import RulesRepository

router = APIRouter(tags=["admin"])
_log = logging.getLogger(__name__)


def _admin_rule_status_from_row(row: Any) -> str:
    return derive_admin_rule_status_from_row(row)


def _paginate(rows: list[Any], page: int, limit: int) -> dict[str, Any]:
    return build_admin_users_page_payload(rows, page, limit)


def _has_workspace_role(current_user: Any, workspace_id: str, role_name: str) -> bool:
    # Check workspace-scoped roles first
    for workspace_role in list(getattr(current_user, "workspace_roles", []) or []):
        if str(getattr(workspace_role, "workspace_id", None) or "").strip() != workspace_id:
            continue
        if str(getattr(workspace_role, "role", None) or "").strip() == role_name:
            return True
    
    # Also allow global roles (e.g., a global "admin" role applies to all workspaces)
    for workspace_role in list(getattr(current_user, "workspace_roles", []) or []):
        if str(getattr(workspace_role, "workspace_id", None) or "").strip() != "global":
            continue
        if str(getattr(workspace_role, "role", None) or "").strip() == role_name:
            return True
    
    return False


def _has_any_non_exception_role(current_user: Any, workspace_id: str) -> bool:
    for workspace_role in list(getattr(current_user, "workspace_roles", []) or []):
        if str(getattr(workspace_role, "workspace_id", None) or "").strip() != workspace_id:
            continue
        role_name = str(getattr(workspace_role, "role", None) or "").strip()
        if role_name and not role_name.startswith("exception-fact-"):
            return True
    return False


@router.get("/users", response_model=AdminUsersPageView)
async def get_users(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    q: str | None = Query(default=None),
    sort: str | None = Query(default=None),
    order: str | None = Query(default=None),
    repository: AdminRepository = Depends(get_admin_repository),
) -> AdminUsersPageView:
    log_event(_log, "admin.users.list.start", component="admin-api", query=q)
    rows = repository.list_users()
    result = filter_admin_users(rows, q, sort, order)

    log_event(_log, "admin.users.list.complete", component="admin-api", resultCount=len(result))
    return resolve_admin_users_view(_paginate(result, page, limit))


@router.get("/exception-fact-access-requests", response_model=list[ExceptionFactAccessRequestView])
async def list_exception_fact_access_requests(
    request: Request,
    workspace_id: str | None = Query(default=None, alias="workspaceId"),
    requester_id: str | None = Query(default=None, alias="requesterId"),
    status: str | None = Query(default=None),
    repository: AdminRepository = Depends(get_admin_repository),
    config_repository: AppConfigRepository = Depends(get_app_config_repository),
) -> list[ExceptionFactAccessRequestView]:
    current_user = repository.get_current_user(getattr(request.state, "user_id", None), getattr(request.state, "auth_claims", None))
    if current_user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    if workspace_id and not _has_workspace_role(current_user, workspace_id, "admin"):
        if requester_id is not None and str(requester_id).strip() == str(current_user.id):
            pass
        else:
            raise HTTPException(status_code=403, detail={"error": "exception_fact_access_denied", "message": "Workspace admin access is required to list requests for this workspace", "workspace_id": workspace_id})

    if workspace_id is None and requester_id is None and not any(
        str(getattr(role, "role", None) or "").strip() == "admin"
        for role in list(getattr(current_user, "workspace_roles", []) or [])
    ):
        requester_id = str(current_user.id)

    config = config_repository.get_app_config()
    requests = repository.list_exception_fact_access_requests(
        workspace_id=workspace_id,
        requester_id=requester_id,
        status=status,
        request_timeout_minutes=max(1, int(config.exceptionFactJitRequestTimeoutMinutes)),
    )
    return [resolve_exception_fact_access_request_view(item) for item in requests]


@router.post("/exception-fact-access-requests", response_model=ExceptionFactAccessRequestView)
async def create_exception_fact_access_request(
    request: Request,
    payload: dict[str, Any],
    repository: AdminRepository = Depends(get_admin_repository),
    config_repository: AppConfigRepository = Depends(get_app_config_repository),
) -> ExceptionFactAccessRequestView:
    current_user = repository.get_current_user(getattr(request.state, "user_id", None), getattr(request.state, "auth_claims", None))
    if current_user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    workspace_id = str(payload.get("workspace_id") or payload.get("workspaceId") or "").strip()
    role_id = str(payload.get("role_id") or payload.get("roleId") or "").strip()
    if not workspace_id:
        raise HTTPException(status_code=422, detail="workspace_id is required")
    if role_id not in {"exception-fact-reader", "exception-fact-investigator"}:
        raise HTTPException(status_code=422, detail="role_id must be exception-fact-reader or exception-fact-investigator")
    if not _has_any_non_exception_role(current_user, workspace_id):
        raise HTTPException(status_code=403, detail={"error": "exception_fact_access_denied", "message": "An existing workspace role is required before requesting JIT access", "workspace_id": workspace_id})

    config = config_repository.get_app_config()
    created = repository.create_exception_fact_access_request(
        {
            "workspace_id": workspace_id,
            "role_id": role_id,
            "requested_duration_minutes": payload.get("requested_duration_minutes") or payload.get("requestedDurationMinutes"),
            "comments": payload.get("comments"),
        },
        actor_id=str(current_user.id),
    )
    if int(created.requestedDurationMinutes or 0) > max(1, int(config.exceptionFactJitRoleMaxDurationMinutes)):
        log_event(_log, "admin.exception_fact_access_request.requested_duration_capped", component="admin-api", workspaceId=workspace_id)
    return resolve_exception_fact_access_request_view(created)


@router.put("/exception-fact-access-requests/{request_id}", response_model=ExceptionFactAccessRequestView)
async def update_exception_fact_access_request(
    request: Request,
    request_id: str,
    payload: dict[str, Any],
    repository: AdminRepository = Depends(get_admin_repository),
    config_repository: AppConfigRepository = Depends(get_app_config_repository),
) -> ExceptionFactAccessRequestView:
    current_user = repository.get_current_user(getattr(request.state, "user_id", None), getattr(request.state, "auth_claims", None))
    if current_user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    config = config_repository.get_app_config()
    existing = repository.list_exception_fact_access_requests(
        request_timeout_minutes=max(1, int(config.exceptionFactJitRequestTimeoutMinutes)),
    )
    request_row = next((item for item in existing if str(item.id or "") == str(request_id)), None)
    if request_row is None:
        raise HTTPException(status_code=404, detail="Not found")
    if not _has_workspace_role(current_user, request_row.workspaceId, "admin"):
        raise HTTPException(status_code=403, detail={"error": "exception_fact_access_denied", "message": "Workspace admin access is required to review this request", "workspace_id": request_row.workspaceId})

    try:
        updated = repository.update_exception_fact_access_request(
            request_id,
            payload,
            actor_id=str(current_user.id),
            max_duration_minutes=max(1, int(config.exceptionFactJitRoleMaxDurationMinutes)),
            request_timeout_minutes=max(1, int(config.exceptionFactJitRequestTimeoutMinutes)),
        )
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error

    if updated is None:
        raise HTTPException(status_code=404, detail="Not found")
    return resolve_exception_fact_access_request_view(updated)


@router.get("/roles", response_model=list[AdminRoleView])
async def get_roles(
    repository: AdminRepository = Depends(get_admin_repository),
) -> list[AdminRoleView]:
    roles = repository.list_roles()
    log_event(_log, "admin.roles.list.complete", component="admin-api", resultCount=len(roles))
    return resolve_admin_roles_view(roles)


@router.post("/roles", response_model=AdminRoleView)
async def create_role(
    payload: dict[str, Any],
    repository: AdminRepository = Depends(get_admin_repository),
) -> AdminRoleView:
    log_event(_log, "admin.role.create.start", component="admin-api", roleId=str(payload.get("id") or ""))
    try:
        created = repository.create_role(payload)
    except ValueError as error:
        log_event(_log, "admin.role.create.validation_error", level="warning", component="admin-api")
        raise HTTPException(status_code=400, detail=str(error)) from error
    log_event(_log, "admin.role.create.complete", component="admin-api", roleId=created.id)
    return AdminRoleView.model_validate(created)


@router.put("/roles/{role_id}", response_model=AdminRoleView)
async def update_role(
    role_id: str,
    payload: dict[str, Any],
    repository: AdminRepository = Depends(get_admin_repository),
) -> AdminRoleView:
    log_event(_log, "admin.role.update.start", component="admin-api", roleId=role_id)
    try:
        updated = repository.update_role(role_id, payload)
    except ValueError as error:
        log_event(_log, "admin.role.update.validation_error", level="warning", component="admin-api", roleId=role_id)
        raise HTTPException(status_code=400, detail=str(error)) from error

    if updated is None:
        log_event(_log, "admin.role.update.not_found", level="warning", component="admin-api", roleId=role_id)
        raise HTTPException(status_code=404, detail="Not found")

    log_event(_log, "admin.role.update.complete", component="admin-api", roleId=role_id)
    return AdminRoleView.model_validate(updated)


@router.put("/users/{user_id}", response_model=AdminUserView)
async def update_user(
    user_id: str,
    payload: dict[str, Any],
    repository: AdminRepository = Depends(get_admin_repository),
    config_repository: AppConfigRepository = Depends(get_app_config_repository),
) -> AdminUserView:
    log_event(_log, "admin.user.update.start", component="admin-api", userId=user_id)
    try:
        config = config_repository.get_app_config()
        updated = repository.update_user(
            user_id,
            payload,
            max(1, int(config.maxUsersPerWorkspace)),
        )
    except ValueError as error:
        log_event(_log, "admin.user.update.validation_error", level="warning", component="admin-api", userId=user_id)
        raise HTTPException(status_code=400, detail=str(error)) from error

    if updated is None:
        log_event(_log, "admin.user.update.not_found", level="warning", component="admin-api", userId=user_id)
        raise HTTPException(status_code=404, detail="Not found")
    log_event(_log, "admin.user.update.complete", component="admin-api", userId=user_id)
    return resolve_admin_user_view(updated)


@router.post("/users/{user_id}/reset-profile", response_model=IdResponseView)
async def reset_user_profile(
    user_id: str,
    repository: AdminRepository = Depends(get_admin_repository),
) -> IdResponseView:
    result = repository.reset_user_preferences(user_id, "profile")
    if result is None:
        log_event(_log, "admin.user.reset_profile.not_found", level="warning", component="admin-api", userId=user_id)
        raise HTTPException(status_code=404, detail="Not found")
    log_event(_log, "admin.user.reset_profile.complete", component="admin-api", userId=user_id)
    return resolve_id_response(result.id)


@router.post("/users/{user_id}/reset-settings", response_model=IdResponseView)
async def reset_user_settings(
    user_id: str,
    repository: AdminRepository = Depends(get_admin_repository),
) -> IdResponseView:
    result = repository.reset_user_preferences(user_id, "settings")
    if result is None:
        log_event(_log, "admin.user.reset_settings.not_found", level="warning", component="admin-api", userId=user_id)
        raise HTTPException(status_code=404, detail="Not found")
    log_event(_log, "admin.user.reset_settings.complete", component="admin-api", userId=user_id)
    return resolve_id_response(result.id)


@router.get("/me", response_model=AdminUserView)
async def get_me(
    request: Request,
    repository: AdminRepository = Depends(get_admin_repository),
) -> AdminUserView:
    with traced_span("admin.me.get", endpoint_group="admin", operation="get_me") as span:
        result = repository.get_current_user(
            getattr(request.state, "user_id", None),
            getattr(request.state, "auth_claims", None),
        )
        if result is None:
            set_span_attributes(span, user_authenticated=False)
            log_event(_log, "admin.me.get.unauthenticated", level="warning", component="admin-api")
            raise HTTPException(status_code=401, detail="Not authenticated")
        set_span_attributes(span, user_authenticated=True, user_id=str(result.id))
        log_event(_log, "admin.me.get.complete", component="admin-api", userId=str(result.id))
        return resolve_admin_user_view(result)


@router.put("/me", response_model=AdminUserView)
async def update_me(
    payload: dict[str, Any],
    request: Request,
    repository: AdminRepository = Depends(get_admin_repository),
) -> AdminUserView:
    with traced_span("admin.me.update", endpoint_group="admin", operation="update_me") as span:
        result = repository.update_current_user(
            getattr(request.state, "user_id", None),
            getattr(request.state, "auth_claims", None),
            payload,
        )
        if result is None:
            set_span_attributes(span, user_authenticated=False)
            log_event(_log, "admin.me.update.unauthenticated", level="warning", component="admin-api")
            raise HTTPException(status_code=401, detail="Not authenticated")
        set_span_attributes(span, user_authenticated=True, user_id=str(result.id), payload_keys=sorted(payload.keys()))
        log_event(_log, "admin.me.update.complete", component="admin-api", userId=str(result.id))
        return resolve_admin_user_view(result)


@router.post("/rules/{rule_id}/recover")
async def recover_removed_rule(
    rule_id: str,
    request: Request,
    repository: RulesRepository = Depends(get_rules_repository),
) -> dict[str, Any]:
    actor_id = getattr(request.state, "user_id", None) or "user-admin"

    rows = await repository.list_rule_records(
        workspace=None,
        include_deleted=True,
        is_template=False,
        limit=500,
        offset=0,
    )
    current_row = next((row for row in rows if str(read_row_field(row, "id") or "") == str(rule_id)), None)
    if current_row is None:
        raise HTTPException(status_code=404, detail=f"Rule '{rule_id}' not found")

    current_status = _admin_rule_status_from_row(current_row)
    scopes = [str(scope).strip() for scope in get_scopes() if str(scope).strip()]
    if not is_transition_allowed(
        entity="rule",
        from_status=current_status,
        to_status="recovered",
        granted_scopes=scopes,
    ):
        raise HTTPException(
            status_code=409,
            detail=f"Transition '{current_status}' -> 'recovered' is not allowed",
        )

    try:
        payload = await repository.recover_rule(rule_id, recovered_by=str(actor_id))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    if payload is None:
        raise HTTPException(status_code=404, detail=f"Rule '{rule_id}' not found")
    return payload