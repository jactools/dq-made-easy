import logging
from typing import Any
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from datetime import datetime, timezone

from app.domain.comment_governance import is_comment_admin
from app.domain.status_governance import canonicalize_status, is_transition_allowed
from app.api.presenters.approvals import build_approvals_page_payload
from app.api.presenters.approvals import derive_approval_effective_status
from app.api.presenters.approvals import derive_approval_rule_status
from app.api.presenters.approvals import normalize_approval_request_type
from app.api.presenters.approvals import normalize_approval_string_list
from app.api.presenters.approvals import parse_approval_effective_at
from app.api.presenters.approvals import parse_approval_suite_repair
from app.api.presenters.approvals import reject_camel_case_approval_keys
from app.api.presenters.row_access import read_row_field
from app.api.v1.schemas import ApprovalAuditView, ApprovalsPageView, ApprovalView
from app.schemas.pydantic_base import SnakeModel
from app.application.resolvers import (
    resolve_approval_audit_view,
    resolve_approval_view,
    resolve_approvals_page_view,
)
from app.domain.entities import build_gx_artifact_envelope_entity
from app.domain.entities import build_gx_artifact_envelope_from_validation_artifact
from app.domain.entities import build_validation_artifact_envelope_from_gx_artifact
from app.core.dependencies import get_approvals_repository
from app.core.dependencies import get_rules_repository
from app.core.dependencies import get_validation_artifact_repository
from app.core.dependencies import get_validation_run_plan_repository
from app.core.log_event import log_event
from app.core.request_context import get_scopes
from app.domain.entities import build_rule_version_list_entity
from app.domain.interfaces import ApprovalsRepository, RulesRepository, ValidationArtifactRepository, ValidationRunPlanRepository

router = APIRouter(tags=["approvals"])
_log = logging.getLogger(__name__)


class ApprovalCommentRequest(SnakeModel):
    workspace_id: str
    comment: str
    comment_type: Literal["general", "note", "concern", "question"] = "general"


class ApprovalCommentLockRequest(SnakeModel):
    locked: bool


class ApprovalCommentEditRequest(SnakeModel):
    comment: str


def _approval_scopes() -> list[str]:
    return [str(scope).strip() for scope in get_scopes() if str(scope).strip()]


def _approval_is_admin() -> bool:
    return is_comment_admin(_approval_scopes())


def _approval_comment_lookup(approval: Any, comment_id: str) -> dict[str, Any] | None:
    thread = list(getattr(approval, "commentThread", None) or [])
    return next((entry for entry in thread if str(entry.get("id") or "") == str(comment_id)), None)


def _approval_comment_authorized_for_owner(comment: dict[str, Any] | None, actor_id: str, approval: Any) -> bool:
    if comment is None:
        return False
    if str(comment.get("author_id") or "").strip() == str(actor_id).strip():
        return True
    return _approval_is_admin()


def _approval_record_owner_id(approval: Any) -> str:
    return str(getattr(approval, "requesterId", None) or "").strip()


def _approval_get_current(repository: ApprovalsRepository, approval_id: str) -> Any:
    approvals = repository.list_approvals(None)
    approval = next((item for item in approvals if str(item.id or "") == str(approval_id)), None)
    if approval is None:
        raise HTTPException(status_code=404, detail="Not found")
    return approval


def _read_gx_payload_field(value: Any, field_name: str) -> Any:
    if isinstance(value, dict):
        return value.get(field_name)
    return getattr(value, field_name, None)


def _resolve_comment_author_name(request: Request, fallback: str | None = None) -> str:
    claims = getattr(request.state, "auth_claims", None)
    if isinstance(claims, dict):
        for key in ("name", "preferred_username", "email"):
            value = str(claims.get(key) or "").strip()
            if value:
                return value
    return str(fallback or "system").strip() or "system"


def _gx_payload_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return model_dump(mode="python", by_alias=False, exclude_none=True)
    return {}


def _coerce_gx_suite_from_validation_artifact(value: Any) -> Any:
    try:
        return build_gx_artifact_envelope_from_validation_artifact(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "unsupported_engine_type",
                "message": str(exc),
            },
        ) from exc


async def _find_rule_row(rule_id: str, rules_repository: RulesRepository) -> Any | None:
    rows = await rules_repository.list_rule_records(
        workspace=None,
        include_deleted=True,
        is_template=False,
        limit=500,
        offset=0,
    )
    return next((row for row in rows if str(read_row_field(row, "id") or "") == str(rule_id)), None)


@router.get("/approvals", response_model=ApprovalsPageView)
async def get_approvals(
    workspace: str | None = Query(default=None),
    business_key: str | None = Query(default=None, alias="businessKey"),
    request_type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    requester_id: str | None = Query(default=None),
    exclude_requester_id: str | None = Query(default=None),
    query: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    repository: ApprovalsRepository = Depends(get_approvals_repository),
) -> ApprovalsPageView:
    log_event(
        _log,
        "approvals.list.start",
        component="approvals-api",
        workspace=workspace,
        requestType=request_type,
        status=status,
        requesterId=requester_id,
        excludeRequesterId=exclude_requester_id,
        query=query,
    )
    rows = repository.list_approvals(
        workspace,
        business_key,
        request_type,
        status,
        requester_id,
        exclude_requester_id,
        query,
    )
    log_event(_log, "approvals.list.complete", component="approvals-api", resultCount=len(rows))
    return resolve_approvals_page_view(build_approvals_page_payload([row.model_dump() for row in rows], page, limit))


@router.get("/approvals/audit", response_model=list[ApprovalAuditView])
async def get_approvals_audit(
    repository: ApprovalsRepository = Depends(get_approvals_repository),
) -> list[ApprovalAuditView]:
    audit = repository.list_approval_audit()
    log_event(_log, "approvals.audit.complete", component="approvals-api", resultCount=len(audit))
    return resolve_approval_audit_view(audit)


@router.post("/approvals/{approval_id}/comments", response_model=ApprovalView)
async def append_approval_comment(
    approval_id: str,
    body: ApprovalCommentRequest,
    request: Request,
    repository: ApprovalsRepository = Depends(get_approvals_repository),
) -> ApprovalView:
    actor_id = getattr(request.state, "user_id", None)
    if not actor_id:
        log_event(_log, "approvals.comment.unauthenticated", level="warning", component="approvals-api")
        raise HTTPException(status_code=401, detail="Not authenticated")

    comment = str(body.comment or "").strip()
    if not comment:
        raise HTTPException(status_code=422, detail="comment must not be empty")

    workspace_id = str(body.workspace_id or "").strip()
    if not workspace_id:
        raise HTTPException(status_code=422, detail="workspace_id is required")

    approval = _approval_get_current(repository, approval_id)

    if bool(getattr(approval, "commentsLocked", False)):
        raise HTTPException(status_code=409, detail={"error": "comments_locked", "message": "Comments are locked for this approval"})

    approval_workspace_id = str(getattr(approval, "workspaceId", None) or "").strip()
    if approval_workspace_id and approval_workspace_id != workspace_id:
        raise HTTPException(status_code=409, detail="approval does not belong to the requested workspace")

    comment_id = str(uuid4())
    try:
        repository.append_audit_event(
            approval_id=approval_id,
            action="commented",
            actor_id=str(actor_id),
            details={
                "comment_id": comment_id,
                "comment": comment,
                "comment_type": body.comment_type,
                "state": "new",
                "author_id": str(actor_id),
                "author_name": _resolve_comment_author_name(request, fallback=str(actor_id)),
                "workspace_id": workspace_id,
            },
        )

        updated = _approval_get_current(repository, approval_id)
    except HTTPException:
        raise
    except Exception as error:
        _log.exception("approvals.comment.failed", extra={"approval_id": approval_id, "workspace_id": workspace_id})
        raise HTTPException(
            status_code=500,
            detail={
                "error": "approval_comment_failed",
                "message": str(error),
                "approval_id": approval_id,
                "workspace_id": workspace_id,
            },
        ) from error

    log_event(_log, "approvals.comment.complete", component="approvals-api", actorId=actor_id, approvalId=approval_id)
    return resolve_approval_view(updated)


@router.patch("/approvals/{approval_id}/comments-lock", response_model=ApprovalView)
async def update_approval_comments_lock(
    approval_id: str,
    body: ApprovalCommentLockRequest,
    request: Request,
    repository: ApprovalsRepository = Depends(get_approvals_repository),
) -> ApprovalView:
    actor_id = getattr(request.state, "user_id", None)
    if not actor_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    approval = _approval_get_current(repository, approval_id)
    owner_id = _approval_record_owner_id(approval)
    if owner_id and str(actor_id).strip() != owner_id and not _approval_is_admin():
        raise HTTPException(status_code=403, detail="Only the approval owner or an admin can lock comments")

    approval_locked = bool(getattr(approval, "commentsLocked", False))
    if body.locked == approval_locked:
        return resolve_approval_view(approval)

    repository.append_audit_event(
        approval_id=approval_id,
        action="comments_locked" if body.locked else "comments_unlocked",
        actor_id=str(actor_id),
        details={
            "comments_locked": body.locked,
            "actor_name": _resolve_comment_author_name(request, fallback=str(actor_id)),
        },
    )
    updated = _approval_get_current(repository, approval_id)
    return resolve_approval_view(updated)


@router.patch("/approvals/{approval_id}/comments/{comment_id}", response_model=ApprovalView)
async def update_approval_comment(
    approval_id: str,
    comment_id: str,
    body: ApprovalCommentEditRequest,
    request: Request,
    repository: ApprovalsRepository = Depends(get_approvals_repository),
) -> ApprovalView:
    actor_id = getattr(request.state, "user_id", None)
    if not actor_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    comment = _approval_comment_lookup(_approval_get_current(repository, approval_id), comment_id)
    if comment is None:
        raise HTTPException(status_code=404, detail="Not found")
    if bool(comment.get("removed")):
        raise HTTPException(status_code=409, detail="comment has been removed")
    if str(comment.get("author_id") or "").strip() != str(actor_id).strip():
        raise HTTPException(status_code=403, detail="Only the comment author can edit this comment")

    comment_text = str(body.comment or "").strip()
    if not comment_text:
        raise HTTPException(status_code=422, detail="comment must not be empty")

    repository.append_audit_event(
        approval_id=approval_id,
        action="comment_updated",
        actor_id=str(actor_id),
        details={
            "comment_id": comment_id,
            "comment": comment_text,
            "edited": True,
            "edited_at": _utc_now(),
            "edited_by": str(actor_id),
            "author_id": comment.get("author_id"),
            "author_name": comment.get("author_name"),
            "comment_type": comment.get("type"),
        },
    )
    updated = _approval_get_current(repository, approval_id)
    return resolve_approval_view(updated)


@router.delete("/approvals/{approval_id}/comments/{comment_id}", response_model=ApprovalView)
async def delete_approval_comment(
    approval_id: str,
    comment_id: str,
    request: Request,
    repository: ApprovalsRepository = Depends(get_approvals_repository),
) -> ApprovalView:
    actor_id = getattr(request.state, "user_id", None)
    if not actor_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    approval = _approval_get_current(repository, approval_id)
    comment = _approval_comment_lookup(approval, comment_id)
    if comment is None:
        raise HTTPException(status_code=404, detail="Not found")
    if str(comment.get("author_id") or "").strip() != str(actor_id).strip() and not _approval_is_admin():
        raise HTTPException(status_code=403, detail="Only the comment author or an admin can remove this comment")

    repository.append_audit_event(
        approval_id=approval_id,
        action="comment_deleted",
        actor_id=str(actor_id),
        details={
            "comment_id": comment_id,
            "removed": True,
            "removed_reason": "removed by author" if str(comment.get("author_id") or "").strip() == str(actor_id).strip() else "removed by admin",
            "author_id": comment.get("author_id"),
            "author_name": comment.get("author_name"),
            "comment_type": comment.get("type"),
        },
    )
    updated = _approval_get_current(repository, approval_id)
    return resolve_approval_view(updated)


@router.post("/approvals/{approval_id}/comments/{comment_id}/resolve", response_model=ApprovalView)
async def resolve_approval_comment(
    approval_id: str,
    comment_id: str,
    request: Request,
    repository: ApprovalsRepository = Depends(get_approvals_repository),
) -> ApprovalView:
    actor_id = getattr(request.state, "user_id", None)
    if not actor_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    approval = _approval_get_current(repository, approval_id)
    comment = _approval_comment_lookup(approval, comment_id)
    if comment is None:
        raise HTTPException(status_code=404, detail="Not found")
    if str(comment.get("author_id") or "").strip() != str(actor_id).strip():
        raise HTTPException(status_code=403, detail="Only the comment author can resolve this comment")

    repository.append_audit_event(
        approval_id=approval_id,
        action="comment_resolved",
        actor_id=str(actor_id),
        details={
            "comment_id": comment_id,
            "resolved_at": _utc_now(),
            "resolved_by": str(actor_id),
            "author_id": comment.get("author_id"),
            "author_name": comment.get("author_name"),
            "comment_type": comment.get("type"),
        },
    )
    updated = _approval_get_current(repository, approval_id)
    return resolve_approval_view(updated)


@router.post("/approvals/{approval_id}/comments/{comment_id}/reopen", response_model=ApprovalView)
async def reopen_approval_comment(
    approval_id: str,
    comment_id: str,
    request: Request,
    repository: ApprovalsRepository = Depends(get_approvals_repository),
) -> ApprovalView:
    actor_id = getattr(request.state, "user_id", None)
    if not actor_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    approval = _approval_get_current(repository, approval_id)
    comment = _approval_comment_lookup(approval, comment_id)
    if comment is None:
        raise HTTPException(status_code=404, detail="Not found")
    if str(comment.get("author_id") or "").strip() != str(actor_id).strip():
        raise HTTPException(status_code=403, detail="Only the comment author can reopen this comment")

    repository.append_audit_event(
        approval_id=approval_id,
        action="comment_reopened",
        actor_id=str(actor_id),
        details={
            "comment_id": comment_id,
            "reopened_at": _utc_now(),
            "reopened_by": str(actor_id),
            "author_id": comment.get("author_id"),
            "author_name": comment.get("author_name"),
            "comment_type": comment.get("type"),
        },
    )
    updated = _approval_get_current(repository, approval_id)
    return resolve_approval_view(updated)


@router.post("/approvals/{approval_id}/comments/{comment_id}/acknowledge", response_model=ApprovalView)
async def acknowledge_approval_comment(
    approval_id: str,
    comment_id: str,
    request: Request,
    repository: ApprovalsRepository = Depends(get_approvals_repository),
) -> ApprovalView:
    actor_id = getattr(request.state, "user_id", None)
    if not actor_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    approval = _approval_get_current(repository, approval_id)
    owner_id = _approval_record_owner_id(approval)
    if owner_id and str(actor_id).strip() != owner_id and not _approval_is_admin():
        raise HTTPException(status_code=403, detail="Only the approval owner or an admin can acknowledge comments")

    comment = _approval_comment_lookup(approval, comment_id)
    if comment is None:
        raise HTTPException(status_code=404, detail="Not found")

    repository.append_audit_event(
        approval_id=approval_id,
        action="comment_acknowledged",
        actor_id=str(actor_id),
        details={
            "comment_id": comment_id,
            "acknowledged_at": _utc_now(),
            "acknowledged_by": str(actor_id),
            "author_id": comment.get("author_id"),
            "author_name": comment.get("author_name"),
            "comment_type": comment.get("type"),
        },
    )
    updated = _approval_get_current(repository, approval_id)
    return resolve_approval_view(updated)


@router.post("/approvals/{approval_id}/comments/{comment_id}/vote-up", response_model=ApprovalView)
async def vote_up_approval_comment(
    approval_id: str,
    comment_id: str,
    request: Request,
    repository: ApprovalsRepository = Depends(get_approvals_repository),
) -> ApprovalView:
    actor_id = getattr(request.state, "user_id", None)
    if not actor_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    approval = _approval_get_current(repository, approval_id)
    comment = _approval_comment_lookup(approval, comment_id)
    if comment is None:
        raise HTTPException(status_code=404, detail="Not found")
    if bool(comment.get("removed")):
        raise HTTPException(status_code=409, detail="comment has been removed")

    repository.append_audit_event(
        approval_id=approval_id,
        action="comment_voted_up",
        actor_id=str(actor_id),
        details={
            "comment_id": comment_id,
            "vote_count": int(comment.get("vote_count") or 0) + 1,
            "author_id": comment.get("author_id"),
            "author_name": comment.get("author_name"),
            "comment_type": comment.get("type"),
        },
    )
    updated = _approval_get_current(repository, approval_id)
    return resolve_approval_view(updated)


def _utc_now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


@router.post("/approvals", response_model=ApprovalView)
async def create_approval(
    payload: dict[str, Any],
    request: Request,
    repository: ApprovalsRepository = Depends(get_approvals_repository),
    rules_repository: RulesRepository = Depends(get_rules_repository),
) -> ApprovalView:
    actor_id = getattr(request.state, "user_id", None)
    reject_camel_case_approval_keys(payload, "Approval creation payload")

    effective_at, _ = parse_approval_effective_at(payload)
    rule_id = str(payload.get("rule_id") or "").strip()
    gx_run_plan_id = str(payload.get("gx_run_plan_id") or "").strip()
    gx_run_plan_version_id = str(payload.get("gx_run_plan_version_id") or "").strip()
    if not rule_id:
        if not gx_run_plan_id:
            raise HTTPException(status_code=422, detail="rule_id or gx_run_plan_id is required")
        if not gx_run_plan_version_id:
            raise HTTPException(status_code=422, detail="gx_run_plan_version_id is required when gx_run_plan_id is provided")
    request_type = normalize_approval_request_type(payload.get("request_type"))
    effective_status = derive_approval_effective_status(request_type)
    workspace = str(payload.get("workspace_id") or "default").strip() or "default"
    comments = str(payload.get("comments") or "").strip() or None
    current_rule_status: str | None = None
    existing_approvals = repository.list_approvals(None)
    suite_repair: dict[str, Any] | None = None

    if request_type == "gx_suite_repair":
        suite_repair = parse_approval_suite_repair(payload)
        if any(
            str(item.ruleId or "").strip() == rule_id
            and canonicalize_status(entity="approval", status=item.status) == "pending"
            and normalize_approval_request_type(getattr(item, "requestType", None)) == "gx_suite_repair"
            for item in existing_approvals
        ):
            raise HTTPException(status_code=409, detail="A pending gx_suite_repair already exists for this rule")

    if rule_id:
        rule_row = await _find_rule_row(rule_id, rules_repository)
        if rule_row is not None:
            current_rule_status = derive_approval_rule_status(
                rule_row,
                [item for item in existing_approvals if str(item.ruleId or "") == rule_id],
                status_canonicalizer=canonicalize_status,
            )
            if request_type == "deactivation":
                if current_rule_status != "activated":
                    raise HTTPException(
                        status_code=409,
                        detail=f"Transition '{current_rule_status}' -> 'deactivated' is not allowed",
                    )
            elif request_type == "gx_suite_repair":
                if current_rule_status != "activated":
                    raise HTTPException(
                        status_code=409,
                        detail="gx_suite_repair requires the rule to be activated",
                    )
            else:
                granted_scopes = [str(scope).strip() for scope in get_scopes() if str(scope).strip()]
                if not is_transition_allowed(
                    entity="rule",
                    from_status=current_rule_status,
                    to_status="pending-approval",
                    granted_scopes=granted_scopes,
                ):
                    raise HTTPException(
                        status_code=409,
                        detail=f"Transition '{current_rule_status}' -> 'pending-approval' is not allowed",
                    )

    created = repository.create_approval(
        {
            "rule_id": rule_id,
            "gx_run_plan_id": gx_run_plan_id or None,
            "gx_run_plan_version_id": gx_run_plan_version_id or None,
            "effective_status": effective_status,
            "request_type": request_type,
            "workspace_id": workspace,
            "comments": comments,
            "effective_at": effective_at,
            "suite_repair": suite_repair,
            "status": str(payload.get("status") or "pending").strip() or "pending",
        },
        actor_id,
    )

    if rule_id and current_rule_status is not None and request_type not in {"deactivation", "gx_suite_repair"}:
        await rules_repository.record_rule_status_transition(
            rule_id,
            current_rule_status,
            "pending-approval",
            actor_id,
            reason="Approval requested",
        )

    log_event(_log, "approvals.create.complete", component="approvals-api", actorId=actor_id)
    return resolve_approval_view(created)


@router.put("/approvals/{approval_id}", response_model=ApprovalView)
async def update_approval(
    approval_id: str,
    payload: dict[str, Any],
    request: Request,
    repository: ApprovalsRepository = Depends(get_approvals_repository),
    rules_repository: RulesRepository = Depends(get_rules_repository),
    validation_run_plan_repository: ValidationRunPlanRepository = Depends(get_validation_run_plan_repository),
    validation_artifact_repository: ValidationArtifactRepository = Depends(get_validation_artifact_repository),
) -> ApprovalView:
    actor_id = getattr(request.state, "user_id", None)
    if not actor_id:
        log_event(_log, "approvals.update.unauthenticated", level="warning", component="approvals-api")
        raise HTTPException(status_code=401, detail="Not authenticated")

    reject_camel_case_approval_keys(payload, "Approval update payload")

    if "effective_at" in payload:
        raise HTTPException(status_code=409, detail="effective_at cannot be modified after creation")

    requested_status = canonicalize_status(entity="approval", status=str(payload.get("status") or ""))
    approvals = repository.list_approvals(None)
    existing_approval = next((item for item in approvals if str(item.id or "") == str(approval_id)), None)
    if existing_approval is None:
        log_event(_log, "approvals.update.not_found", level="warning", component="approvals-api", actorId=actor_id)
        raise HTTPException(status_code=404, detail="Not found")

    current_rule_status: str | None = None
    rule_id = str(existing_approval.ruleId or "").strip()
    effective_status = str(getattr(existing_approval, "effectiveStatus", None) or "").strip() or None
    gx_run_plan_id = str(getattr(existing_approval, "gxRunPlanId", None) or "").strip()
    gx_run_plan_version_id = str(getattr(existing_approval, "gxRunPlanVersionId", None) or "").strip()
    if requested_status:
        current_approval_status = canonicalize_status(entity="approval", status=existing_approval.status)
        request_type = normalize_approval_request_type(getattr(existing_approval, "requestType", None))
        granted_scopes = [str(scope).strip() for scope in get_scopes() if str(scope).strip()]
        if current_approval_status != requested_status and not is_transition_allowed(
            entity="approval",
            from_status=current_approval_status,
            to_status=requested_status,
            granted_scopes=granted_scopes,
        ):
            raise HTTPException(
                status_code=409,
                detail=f"Transition '{current_approval_status}' -> '{requested_status}' is not allowed",
            )

        rule_id = str(existing_approval.ruleId or "").strip()
        if rule_id and requested_status in {"approved", "rejected"}:
            rule_row = await _find_rule_row(rule_id, rules_repository)
            if rule_row is not None:
                current_rule_status = derive_approval_rule_status(
                    rule_row,
                    [item for item in approvals if str(item.ruleId or "") == rule_id],
                    status_canonicalizer=canonicalize_status,
                )
                if request_type == "gx_suite_repair":
                    if requested_status == "approved" and current_rule_status != "activated":
                        raise HTTPException(
                            status_code=409,
                            detail="gx_suite_repair can only be approved while the rule is activated",
                        )
                elif request_type == "deactivation":
                    if requested_status == "approved" and current_rule_status != "deactivated" and not is_transition_allowed(
                        entity="rule",
                        from_status=current_rule_status,
                        to_status="deactivated",
                        granted_scopes=granted_scopes,
                    ):
                        raise HTTPException(
                            status_code=409,
                            detail=f"Transition '{current_rule_status}' -> 'deactivated' is not allowed",
                        )
                elif current_rule_status != requested_status and not is_transition_allowed(
                    entity="rule",
                    from_status=current_rule_status,
                    to_status=requested_status,
                    granted_scopes=granted_scopes,
                ):
                    raise HTTPException(
                        status_code=409,
                        detail=f"Transition '{current_rule_status}' -> '{requested_status}' is not allowed",
                    )

        if gx_run_plan_id and gx_run_plan_version_id:
            request_type = normalize_approval_request_type(getattr(existing_approval, "requestType", None))
            current_plan = await validation_run_plan_repository.get_plan(gx_run_plan_id)
            if current_plan is None:
                raise HTTPException(status_code=404, detail=f"GX run plan '{gx_run_plan_id}' not found")

            current_version = next(
                (
                    item
                    for item in (_read_gx_payload_field(current_plan, "versions") or [])
                    if str(_read_gx_payload_field(item, "runPlanVersionId") or "") == gx_run_plan_version_id
                ),
                None,
            )
            if current_version is None:
                raise HTTPException(status_code=404, detail=f"GX run plan version '{gx_run_plan_version_id}' not found")

            current_gx_state = str(_read_gx_payload_field(current_version, "governanceState") or "")
            if requested_status == "approved":
                if request_type == "activation":
                    if current_gx_state != "activation-requested":
                        raise HTTPException(
                            status_code=409,
                            detail=f"Transition '{current_gx_state}' -> 'approved_pending_activation' is not allowed",
                        )
                    await validation_run_plan_repository.transition_plan_version(
                        run_plan_id=gx_run_plan_id,
                        run_plan_version_id=gx_run_plan_version_id,
                        target_state="approved_pending_activation",
                        updated_by=actor_id,
                    )
                elif request_type == "deactivation":
                    if current_gx_state != "deactivation-requested":
                        raise HTTPException(
                            status_code=409,
                            detail=f"Transition '{current_gx_state}' -> 'deactivated' is not allowed",
                        )
                    await validation_run_plan_repository.deactivate_plan(
                        run_plan_id=gx_run_plan_id,
                        run_plan_version_id=gx_run_plan_version_id,
                        deactivated_by=actor_id,
                    )
            elif requested_status == "rejected":
                if request_type == "activation":
                    if current_gx_state != "activation-requested":
                        raise HTTPException(
                            status_code=409,
                            detail=f"Transition '{current_gx_state}' -> 'inactive' is not allowed",
                        )
                    await validation_run_plan_repository.transition_plan_version(
                        run_plan_id=gx_run_plan_id,
                        run_plan_version_id=gx_run_plan_version_id,
                        target_state="inactive",
                        updated_by=actor_id,
                    )
                elif request_type == "deactivation":
                    if current_gx_state != "deactivation-requested":
                        raise HTTPException(
                            status_code=409,
                            detail=f"Transition '{current_gx_state}' -> 'active' is not allowed",
                        )
                    await validation_run_plan_repository.transition_plan_version(
                        run_plan_id=gx_run_plan_id,
                        run_plan_version_id=gx_run_plan_version_id,
                        target_state="active",
                        updated_by=actor_id,
                    )

    async def _execute_gx_suite_repair(*, approval_id: str, rule_id: str, actor_id: str) -> None:
        from app.application.services import compile_rule_to_intermediate_model
        from app.application.services import build_gx_expectations_for_rule
        from app.application.services import build_gx_row_condition_meta_from_intermediate_model
        from app.application.services import GxExpectationBuildError

        audit = repository.list_approval_audit()
        created = next(
            (
                item
                for item in audit
                if str(getattr(item, "approvalId", "") or "") == str(approval_id)
                and str(getattr(item, "action", "") or "") == "created"
            ),
            None,
        )
        created_details = getattr(created, "details", None) if created is not None else None
        if not isinstance(created_details, dict):
            raise HTTPException(status_code=500, detail="Approval audit details unavailable")

        suite_repair = created_details.get("suite_repair")
        if not isinstance(suite_repair, dict):
            raise HTTPException(status_code=422, detail="suite_repair details missing for gx_suite_repair")

        data_object_id = str(suite_repair.get("data_object_id") or "").strip() or None
        dataset_id = str(suite_repair.get("dataset_id") or "").strip() or None
        data_product_id = str(suite_repair.get("data_product_id") or "").strip() or None
        data_object_version_ids = normalize_approval_string_list(suite_repair.get("data_object_version_ids"))
        primary_key_fields = normalize_approval_string_list(suite_repair.get("primary_key_fields"))

        if not any((data_object_id, dataset_id, data_product_id)):
            raise HTTPException(status_code=422, detail="suite_repair missing assignment scope")
        if not data_object_version_ids:
            raise HTTPException(status_code=422, detail="suite_repair.data_object_version_ids must not be empty")

        versions_payload = build_rule_version_list_entity(
            await rules_repository.list_rule_versions(rule_id, limit=1, offset=0)
        )
        versions = versions_payload.versions if versions_payload is not None else []
        current_version = next((v for v in versions if bool(v.isCurrentVersion)), versions[0] if versions else None)
        rule_version_id = str(current_version.id or "").strip() if current_version is not None else ""
        if not rule_version_id:
            raise HTTPException(status_code=409, detail="Rule has no current version")

        entity = await rules_repository.get_rule_by_id(rule_id)
        if entity is None:
            raise HTTPException(status_code=404, detail=f"Rule '{rule_id}' not found")

        intermediate_model = compile_rule_to_intermediate_model(
            rule_id=rule_id,
            rule_version_id=rule_version_id,
            filter_expression=(getattr(entity, "expression", "") or "").strip(),
        )

        if not bool(intermediate_model.get("compilable", True)):
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "rule_not_compilable",
                    "message": "Rule cannot be compiled; repair suite aborted",
                    "rule_id": rule_id,
                    "rule_version_id": rule_version_id,
                },
            )

        try:
            expectations = build_gx_expectations_for_rule(
                rule=entity,
                intermediate_model=intermediate_model,
                rule_id=rule_id,
                artifact_key=str(intermediate_model.get("artifactKey") or ""),
            )
        except GxExpectationBuildError as exc:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "gx_expectations_build_failed",
                    "message": str(exc),
                    "rule_id": rule_id,
                    "rule_version_id": rule_version_id,
                },
            ) from exc

        if not expectations:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "gx_expectations_empty",
                    "message": "GX expectation translation produced no expectations",
                    "rule_id": rule_id,
                    "rule_version_id": rule_version_id,
                },
            )

        suite_id = f"gx_{rule_id}"
        history = await validation_artifact_repository.list_artifact_status_history(
            artifact_id=suite_id,
            artifact_version=None,
        )
        max_version = 0
        for entry in history:
            try:
                max_version = max(
                    max_version,
                    int(
                        _read_gx_payload_field(entry, "validationArtifactVersion")
                        or _read_gx_payload_field(entry, "suiteVersion")
                        or 0
                    ),
                )
            except (TypeError, ValueError):
                continue
        suite_version = (max_version + 1) if max_version > 0 else 1

        now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        filter_payload = intermediate_model.get("filter") if isinstance(intermediate_model, dict) else None
        source_rule_expression = ""
        compiled_expression = ""
        if isinstance(filter_payload, dict):
            source_rule_expression = str(filter_payload.get("source") or "").strip()
            compiled_expression = str(filter_payload.get("normalized") or "").strip()
        if not source_rule_expression:
            source_rule_expression = str(getattr(entity, "expression", "") or "").strip()
        execution_contract = {
            "engineTarget": "pyspark",
            "executionShape": "single_object",
            "traceability": {
                "ruleId": rule_id,
                "ruleVersionId": rule_version_id,
                "gxSuiteId": suite_id,
                "gxSuiteVersion": suite_version,
                "dataObjectVersionId": (data_object_version_ids[0] if len(data_object_version_ids) == 1 else None),
                "sourceRuleExpression": source_rule_expression or None,
                "compiledExpression": compiled_expression or None,
                "artifactKey": str(intermediate_model.get("artifactKey") or "").strip() or None,
            },
        }

        assignment_scope = {
            "dataObjectId": data_object_id,
            "datasetId": dataset_id,
            "dataProductId": data_product_id,
        }
        if not any(str(value or "").strip() for value in assignment_scope.values()):
            raise ValueError("GX suite envelope is invalid")

        resolved_target_ids = [str(value).strip() for value in data_object_version_ids if str(value).strip()]
        if not resolved_target_ids:
            raise ValueError("GX suite envelope is invalid")

        envelope = build_gx_artifact_envelope_entity(
            {
                "suiteId": suite_id,
                "suiteVersion": suite_version,
                "artifactVersion": "v1",
                "assignmentScope": assignment_scope,
                "resolvedExecutionScope": {
                    "dataObjectVersionIds": resolved_target_ids,
                },
                "gxSuite": {
                    "expectation_suite_name": f"dq_{rule_id}_v{suite_version}",
                    "expectations": [dict(expectation) for expectation in expectations],
                    "meta": {
                        "ruleId": rule_id,
                        "compilerVersion": intermediate_model.get("compilerVersion"),
                        "artifactKey": intermediate_model.get("artifactKey"),
                        "intermediateModel": intermediate_model,
                        "gxRowCondition": build_gx_row_condition_meta_from_intermediate_model(intermediate_model),
                        "repair": True,
                        "repairApprovalId": approval_id,
                    },
                },
                "compiledFrom": {
                    "ruleIds": [rule_id],
                    "compilerVersion": str(intermediate_model.get("compilerVersion") or "unknown"),
                    "generatedAt": now_iso,
                },
                "executionHints": {
                    "recommendedEngine": "pyspark",
                    "primaryKeyFields": list(primary_key_fields),
                },
                "executionContract": execution_contract,
                "savedBy": actor_id,
                "sourcePipeline": "rule-approvals",
            }
        )

        await validation_artifact_repository.save_artifact(
            envelope=build_validation_artifact_envelope_from_gx_artifact(envelope),
            status="active",
            saved_by=actor_id,
            source_pipeline="rule-approvals",
        )

        repository.append_audit_event(
            approval_id=approval_id,
            action="gx_suite.repair.completed",
            actor_id=actor_id,
            details={
                "rule_id": rule_id,
                "suite_id": suite_id,
                "suite_version": suite_version,
                "data_object_id": data_object_id,
                "dataset_id": dataset_id,
                "data_product_id": data_product_id,
                "data_object_version_ids": list(data_object_version_ids),
            },
        )

    try:
        effective_at = getattr(existing_approval, "effectiveAt", None)
        if requested_status == "approved":
            request_type = normalize_approval_request_type(getattr(existing_approval, "requestType", None))
            if request_type == "deactivation" and effective_at:
                try:
                    parsed_effective_at = datetime.fromisoformat(str(effective_at).replace("Z", "+00:00"))
                except Exception:
                    raise HTTPException(status_code=422, detail="effective_at must be a valid RFC3339 timestamp")

                if parsed_effective_at.tzinfo is None or parsed_effective_at.tzinfo.utcoffset(parsed_effective_at) is None:
                    raise HTTPException(status_code=422, detail="effective_at must include a timezone offset")

                if parsed_effective_at > datetime.now(timezone.utc):
                    raise HTTPException(
                        status_code=503,
                        detail={
                            "error": "downstream_unavailable",
                            "service": "lifecycle-scheduler",
                            "message": "lifecycle-scheduler is unavailable",
                        },
                    )

            if request_type == "gx_suite_repair" and rule_id:
                await _execute_gx_suite_repair(approval_id=approval_id, rule_id=rule_id, actor_id=actor_id)

            if rule_id and request_type == "deactivation" and effective_status not in {None, "deactivated"}:
                raise HTTPException(
                    status_code=409,
                    detail=f"Approval effective status '{effective_status}' does not match request type '{request_type}'",
                )

        updated = repository.update_approval(approval_id, payload, actor_id)
    except PermissionError as error:
        log_event(_log, "approvals.update.forbidden", level="warning", component="approvals-api", actorId=actor_id)
        raise HTTPException(status_code=403, detail=str(error)) from error

    if updated is None:
        log_event(_log, "approvals.update.not_found", level="warning", component="approvals-api", actorId=actor_id)
        raise HTTPException(status_code=404, detail="Not found")

    request_type = normalize_approval_request_type(getattr(existing_approval, "requestType", None))
    if rule_id and current_rule_status is not None and requested_status in {"approved", "rejected"} and request_type not in {"deactivation", "gx_suite_repair"}:
        await rules_repository.record_rule_status_transition(
            rule_id,
            current_rule_status,
            requested_status,
            actor_id,
            reason="Approval reviewed",
        )

    if requested_status == "approved":
        request_type = normalize_approval_request_type(getattr(updated, "requestType", None) or getattr(existing_approval, "requestType", None))
        rule_id = str(getattr(updated, "ruleId", None) or getattr(existing_approval, "ruleId", None) or "").strip()
        if request_type == "deactivation" and rule_id:
            effective_status = str(
                getattr(updated, "effectiveStatus", None)
                or getattr(existing_approval, "effectiveStatus", None)
                or derive_approval_effective_status(request_type)
                or ""
            ).strip() or None
            if effective_status != "deactivated":
                raise HTTPException(
                    status_code=409,
                    detail=f"Approval effective status '{effective_status}' does not match request type '{request_type}'",
                )
            await rules_repository.deactivate_rule(rule_id)

            suites = await validation_artifact_repository.list_artifacts_for_rule(
                rule_id=rule_id,
                status="active",
                latest_only=True,
            )
            if suites:
                all_rules = await rules_repository.list_rule_records(
                    workspace=None,
                    include_deleted=True,
                    is_template=False,
                    limit=500,
                    offset=0,
                )
                rule_entity = await rules_repository.get_rule_by_id(rule_id)
                rule_owner_id = str(getattr(rule_entity, "created_by_user_id", "") or "").strip() if rule_entity is not None else ""
                deactivation_requester_id = str(getattr(existing_approval, "requesterId", None) or "").strip()
                activated_by_id = {
                    str(read_row_field(r, "id") or ""): bool(read_row_field(r, "active"))
                    and not bool(read_row_field(r, "removed"))
                    and not bool(read_row_field(r, "removed_at"))
                    and not bool(read_row_field(r, "deleted_on"))
                    for r in all_rules
                    if str(read_row_field(r, "id") or "").strip()
                }

                now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

                for suite in suites:
                    typed_suite = _coerce_gx_suite_from_validation_artifact(suite)
                    suite_id = str(_read_gx_payload_field(typed_suite, "suiteId") or "").strip()
                    if not suite_id:
                        continue

                    history = await validation_artifact_repository.list_artifact_status_history(
                        artifact_id=suite_id,
                        artifact_version=None,
                    )
                    max_version = 0
                    for entry in history:
                        try:
                            max_version = max(
                                max_version,
                                int(
                                    _read_gx_payload_field(entry, "validationArtifactVersion")
                                    or _read_gx_payload_field(entry, "suiteVersion")
                                    or 0
                                ),
                            )
                        except (TypeError, ValueError):
                            continue
                    current_suite_version = int(_read_gx_payload_field(typed_suite, "suiteVersion") or 0)
                    next_version = (max_version + 1) if max_version > 0 else (current_suite_version + 1)

                    suite_payload = _gx_payload_dict(typed_suite)
                    compiled_from = suite_payload.get("compiledFrom") if isinstance(suite_payload.get("compiledFrom"), dict) else {}
                    current_rule_ids_raw = compiled_from.get("ruleIds") if isinstance(compiled_from.get("ruleIds"), list) else []
                    current_rule_ids = [str(item).strip() for item in current_rule_ids_raw if str(item).strip()]

                    remaining_rule_ids = [
                        rid
                        for rid in current_rule_ids
                        if rid != rule_id and activated_by_id.get(rid) is True
                    ]

                    if not remaining_rule_ids:
                        log_event(
                            _log,
                            "gx.suite.reversion.skipped_empty",
                            level="warning",
                            component="approvals-api",
                            suiteId=suite_id,
                            deactivatedRuleId=rule_id,
                        )
                        await validation_artifact_repository.patch_artifact_status(
                            artifact_id=suite_id,
                            new_status="disabled",
                            artifact_version=current_suite_version or None,
                            changed_by=actor_id,
                            reason=f"Rule '{rule_id}' deactivated; no remaining activated rules",
                        )

                        new_suite = dict(suite_payload)
                        new_suite["suiteVersion"] = int(next_version)

                        new_compiled_from = dict(compiled_from)
                        new_compiled_from["ruleIds"] = []
                        new_compiled_from["generatedAt"] = now_iso
                        new_suite["compiledFrom"] = new_compiled_from

                        gx_suite = new_suite.get("gxSuite")
                        if isinstance(gx_suite, dict):
                            gx_suite = dict(gx_suite)
                            meta = gx_suite.get("meta")
                            gx_suite["meta"] = {**(meta if isinstance(meta, dict) else {}), "suiteEmpty": True, "suiteEmptyReason": "rule_deactivated"}
                            name = gx_suite.get("expectation_suite_name")
                            if isinstance(name, str) and name.endswith(f"_v{current_suite_version}"):
                                gx_suite["expectation_suite_name"] = name.rsplit("_v", 1)[0] + f"_v{next_version}"
                            new_suite["gxSuite"] = gx_suite

                        new_suite["executionContract"] = None

                        log_event(
                            _log,
                            "gx.suite.reversion.empty.register",
                            level="warning",
                            component="approvals-api",
                            suiteId=suite_id,
                            fromSuiteVersion=current_suite_version,
                            toSuiteVersion=int(next_version),
                            deactivatedRuleId=rule_id,
                        )

                        await validation_artifact_repository.save_artifact(
                            envelope=build_validation_artifact_envelope_from_gx_artifact(
                                build_gx_artifact_envelope_entity(new_suite)
                            ),
                            status="disabled",
                            saved_by=actor_id,
                            source_pipeline="rule-lifecycle",
                        )

                        repository.append_audit_event(
                            approval_id=approval_id,
                            action="gx_suite.empty.registered",
                            actor_id=actor_id,
                            details={
                                "rule_id": rule_id,
                                "suite_id": suite_id,
                                "from_suite_version": current_suite_version,
                                "to_suite_version": int(next_version),
                                "status": "disabled",
                            },
                        )

                        if not rule_owner_id or not deactivation_requester_id:
                            repository.append_audit_event(
                                approval_id=approval_id,
                                action="notification.gx_suite_empty.missing_recipient",
                                actor_id=actor_id,
                                details={
                                    "rule_id": rule_id,
                                    "suite_id": suite_id,
                                    "suite_version": int(next_version),
                                    "rule_owner_id": rule_owner_id or None,
                                    "deactivation_requester_id": deactivation_requester_id or None,
                                },
                            )
                        else:
                            message = (
                                f"GX suite '{suite_id}' became empty after deactivation of rule '{rule_id}'. "
                                f"A disabled suite version {int(next_version)} was registered."
                            )
                            recipients = []
                            recipients.append(rule_owner_id)
                            if deactivation_requester_id != rule_owner_id:
                                recipients.append(deactivation_requester_id)

                            for recipient_id in recipients:
                                repository.append_audit_event(
                                    approval_id=approval_id,
                                    action="notification.gx_suite_empty",
                                    actor_id=recipient_id,
                                    details={
                                        "message": message,
                                        "recipient_id": recipient_id,
                                        "sender_id": actor_id,
                                        "rule_id": rule_id,
                                        "suite_id": suite_id,
                                        "suite_version": int(next_version),
                                        "severity": "warning",
                                    },
                                )

                        log_event(
                            _log,
                            "gx.suite.reversion.empty.registered",
                            component="approvals-api",
                            suiteId=suite_id,
                            suiteVersion=int(next_version),
                        )
                        continue

                    new_suite = dict(suite_payload)
                    new_suite["suiteVersion"] = int(next_version)

                    new_compiled_from = dict(compiled_from)
                    new_compiled_from["ruleIds"] = list(remaining_rule_ids)
                    new_compiled_from["generatedAt"] = now_iso
                    new_suite["compiledFrom"] = new_compiled_from

                    gx_suite = new_suite.get("gxSuite")
                    if isinstance(gx_suite, dict):
                        name = gx_suite.get("expectation_suite_name")
                        if isinstance(name, str) and name.endswith(f"_v{current_suite_version}"):
                            gx_suite = dict(gx_suite)
                            gx_suite["expectation_suite_name"] = name.rsplit("_v", 1)[0] + f"_v{next_version}"
                            new_suite["gxSuite"] = gx_suite

                    execution_contract = new_suite.get("executionContract")
                    if isinstance(execution_contract, dict):
                        traceability = execution_contract.get("traceability")
                        trace_rule_id = str(traceability.get("ruleId") or "") if isinstance(traceability, dict) else ""
                        if trace_rule_id and trace_rule_id in remaining_rule_ids:
                            execution_contract = dict(execution_contract)
                            traceability = dict(traceability) if isinstance(traceability, dict) else {}
                            traceability["gxSuiteVersion"] = int(next_version)
                            execution_contract["traceability"] = traceability
                            new_suite["executionContract"] = execution_contract
                        else:
                            new_suite["executionContract"] = None

                    log_event(
                        _log,
                        "gx.suite.reversion.start",
                        component="approvals-api",
                        suiteId=suite_id,
                        fromSuiteVersion=current_suite_version,
                        toSuiteVersion=int(next_version),
                        deactivatedRuleId=rule_id,
                        remainingRuleCount=len(remaining_rule_ids),
                    )

                    await validation_artifact_repository.save_artifact(
                        envelope=build_validation_artifact_envelope_from_gx_artifact(
                            build_gx_artifact_envelope_entity(new_suite)
                        ),
                        status="active",
                        saved_by=actor_id,
                        source_pipeline="rule-lifecycle",
                    )

                    repository.append_audit_event(
                        approval_id=approval_id,
                        action="gx_suite.reversion.completed",
                        actor_id=actor_id,
                        details={
                            "rule_id": rule_id,
                            "suite_id": suite_id,
                            "from_suite_version": current_suite_version,
                            "to_suite_version": int(next_version),
                            "remaining_rule_ids": list(remaining_rule_ids),
                            "remaining_rule_count": len(remaining_rule_ids),
                            "status": "active",
                        },
                    )

                    log_event(
                        _log,
                        "gx.suite.reversion.complete",
                        component="approvals-api",
                        suiteId=suite_id,
                        suiteVersion=int(next_version),
                        remainingRuleCount=len(remaining_rule_ids),
                    )

    log_event(_log, "approvals.update.complete", component="approvals-api", actorId=actor_id)
    return resolve_approval_view(updated)


@router.delete("/approvals/{approval_id}", response_model=ApprovalView)
async def delete_approval(
    approval_id: str,
    request: Request,
    repository: ApprovalsRepository = Depends(get_approvals_repository),
) -> ApprovalView:
    actor_id = getattr(request.state, "user_id", None)
    if not actor_id:
        log_event(_log, "approvals.delete.unauthenticated", level="warning", component="approvals-api")
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        deleted = repository.delete_approval(approval_id, actor_id)
    except PermissionError as error:
        log_event(_log, "approvals.delete.forbidden", level="warning", component="approvals-api", actorId=actor_id)
        raise HTTPException(status_code=403, detail=str(error)) from error

    if deleted is None:
        log_event(_log, "approvals.delete.not_found", level="warning", component="approvals-api", actorId=actor_id)
        raise HTTPException(status_code=404, detail="Not found")
    log_event(_log, "approvals.delete.complete", component="approvals-api", actorId=actor_id)
    return resolve_approval_view(deleted)