from __future__ import annotations

from collections.abc import Mapping
from collections.abc import Sequence
from typing import Any

from pydantic import Field

from app.domain.comment_governance import COMMENT_STATE_NEW
from app.domain.comment_governance import coerce_bool
from app.domain.comment_governance import coerce_int
from app.domain.comment_governance import first_non_empty_text
from app.domain.comment_governance import merge_comment_event
from app.domain.comment_governance import normalize_comment_state
from app.domain.entities.base import EntityModel


class ApprovalEntity(EntityModel):
    id: str
    businessKey: str | None = None
    ruleId: str
    effectiveStatus: str | None = None
    gxRunPlanId: str | None = None
    gxRunPlanVersionId: str | None = None
    status: str
    requesterId: str | None = None
    workspaceId: str = "default"
    requestType: str = "activation"
    effectiveAt: str | None = None
    comments: str | None = None
    commentThread: list[dict[str, Any]] = Field(default_factory=list)
    commentsLocked: bool = False
    removedCommentCount: int = 0
    requestedAt: str | None = None
    reviewedBy: str | None = None
    reviewedAt: str | None = None


class ApprovalAuditEntity(EntityModel):
    id: str
    approvalId: str
    action: str
    actorId: str | None = None
    timestamp: str
    details: dict[str, Any] = Field(default_factory=dict)


def _normalize_comment_text(details: Mapping[str, Any], *names: str) -> str | None:
    for name in names:
        value = details.get(name)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _normalize_comment_record(details: Mapping[str, Any], row: ApprovalAuditEntity) -> dict[str, Any] | None:
    action = str(row.action or "").strip()
    if action not in {
        "created",
        "approved",
        "rejected",
        "commented",
        "comment_updated",
        "comment_deleted",
        "comment_resolved",
        "comment_reopened",
        "comment_acknowledged",
        "comment_voted_up",
        "comment_locked",
        "comment_unlocked",
    }:
        return None

    comment_id = first_non_empty_text(details.get("comment_id"), details.get("commentId"), row.id)
    comment_text = _normalize_comment_text(details, "comment", "comments", "content")
    author_id = first_non_empty_text(details.get("author_id"), details.get("authorId"), row.actorId)
    author_name = _normalize_comment_text(details, "author_name", "authorName", "requester_name", "requesterName")
    state = normalize_comment_state(details.get("state")) if details.get("state") is not None else COMMENT_STATE_NEW
    created_at = first_non_empty_text(details.get("created_at"), details.get("createdAt"), row.timestamp) or ""

    if comment_text is None and action not in {"comment_deleted", "comment_locked", "comment_unlocked"}:
        return None

    return {
        "id": comment_id or str(row.id or ""),
        "author_id": author_id,
        "author_name": author_name or author_id or "system",
        "content": comment_text or "",
        "type": _normalize_comment_text(details, "comment_type", "commentType") or ("note" if action in {"created", "approved", "rejected"} else "general"),
        "created_at": created_at,
        "state": state,
        "locked": coerce_bool(details.get("locked")),
        "removed": coerce_bool(details.get("removed")),
        "removed_at": first_non_empty_text(details.get("removed_at"), details.get("removedAt")),
        "removed_by": first_non_empty_text(details.get("removed_by"), details.get("removedBy")),
        "removed_reason": first_non_empty_text(details.get("removed_reason"), details.get("removedReason")),
        "edited": coerce_bool(details.get("edited")),
        "edited_at": first_non_empty_text(details.get("edited_at"), details.get("editedAt")),
        "edited_by": first_non_empty_text(details.get("edited_by"), details.get("editedBy")),
        "edit_count": coerce_int(details.get("edit_count"), 0),
        "vote_count": coerce_int(details.get("vote_count"), 0),
        "resolved_at": first_non_empty_text(details.get("resolved_at"), details.get("resolvedAt")),
        "resolved_by": first_non_empty_text(details.get("resolved_by"), details.get("resolvedBy")),
        "reopened_at": first_non_empty_text(details.get("reopened_at"), details.get("reopenedAt")),
        "reopened_by": first_non_empty_text(details.get("reopened_by"), details.get("reopenedBy")),
        "acknowledged_at": first_non_empty_text(details.get("acknowledged_at"), details.get("acknowledgedAt")),
        "acknowledged_by": first_non_empty_text(details.get("acknowledged_by"), details.get("acknowledgedBy")),
        "locked_at": first_non_empty_text(details.get("locked_at"), details.get("lockedAt")),
        "locked_by": first_non_empty_text(details.get("locked_by"), details.get("lockedBy")),
    }


def build_approval_comment_thread(audit_rows: Sequence[ApprovalAuditEntity]) -> list[dict[str, Any]]:
    entries_by_id: dict[str, dict[str, Any]] = {}

    for row in sorted(audit_rows, key=lambda item: (str(item.timestamp or ""), str(item.id or ""))):
        action = str(row.action or "").strip()
        if action in {"comments_locked", "comments_unlocked"}:
            continue

        details = row.details if isinstance(row.details, Mapping) else {}
        normalized = _normalize_comment_record(details, row)
        if normalized is None:
            continue

        comment_id = str(normalized["id"])
        entries_by_id[comment_id] = merge_comment_event(
            entries_by_id.get(comment_id, normalized),
            dict(details),
            action=action,
            timestamp=str(row.timestamp or ""),
            actor_id=str(row.actorId or "").strip() or None,
        )

    return sorted(entries_by_id.values(), key=lambda entry: (str(entry.get("created_at") or ""), str(entry.get("id") or "")))


def build_approval_comment_governance(audit_rows: Sequence[ApprovalAuditEntity]) -> dict[str, Any]:
    comments_locked = False
    removed_comment_count = 0

    for row in sorted(audit_rows, key=lambda item: (str(item.timestamp or ""), str(item.id or ""))):
        action = str(row.action or "").strip()
        details = row.details if isinstance(row.details, Mapping) else {}
        if action == "comments_locked":
            comments_locked = True
        elif action == "comments_unlocked":
            comments_locked = False
        elif action == "comment_deleted" and coerce_bool(details.get("removed")):
            removed_comment_count += 1

    return {
        "commentsLocked": comments_locked,
        "removedCommentCount": removed_comment_count,
    }


def build_approval_audit_entity(payload: Any) -> ApprovalAuditEntity:
    def _field(*names: str) -> Any:
        if isinstance(payload, Mapping):
            for name in names:
                if payload.get(name) is not None:
                    return payload.get(name)
            return None
        for name in names:
            value = getattr(payload, name, None)
            if value is not None:
                return value
        return None

    if isinstance(payload, ApprovalAuditEntity):
        return payload

    details = _field("details")
    return ApprovalAuditEntity(
        id=str(_field("id") or ""),
        approvalId=str(_field("approvalId", "approval_id") or ""),
        action=str(_field("action") or ""),
        actorId=(str(_field("actorId", "actor_id")) if _field("actorId", "actor_id") is not None else None),
        timestamp=str(_field("timestamp") or ""),
        details=dict(details) if isinstance(details, Mapping) else {},
    )


def build_approval_entity(payload: Any) -> ApprovalEntity:
    def _field(*names: str) -> Any:
        if isinstance(payload, Mapping):
            for name in names:
                if payload.get(name) is not None:
                    return payload.get(name)
            return None
        for name in names:
            value = getattr(payload, name, None)
            if value is not None:
                return value
        return None

    if isinstance(payload, ApprovalEntity):
        return payload

    return ApprovalEntity(
        id=str(_field("id") or ""),
        businessKey=(str(_field("businessKey", "business_key")) if _field("businessKey", "business_key") is not None else None),
        ruleId=str(_field("ruleId", "rule_id") or ""),
        effectiveStatus=(
            str(_field("effectiveStatus", "effective_status"))
            if _field("effectiveStatus", "effective_status") is not None
            else None
        ),
        gxRunPlanId=(
            str(_field("gxRunPlanId", "gx_run_plan_id"))
            if _field("gxRunPlanId", "gx_run_plan_id") is not None
            else None
        ),
        gxRunPlanVersionId=(
            str(_field("gxRunPlanVersionId", "gx_run_plan_version_id"))
            if _field("gxRunPlanVersionId", "gx_run_plan_version_id") is not None
            else None
        ),
        status=str(_field("status") or ""),
        requesterId=(str(_field("requesterId", "requester_id")) if _field("requesterId", "requester_id") is not None else None),
        workspaceId=str(_field("workspaceId", "workspace_id") or "default"),
        requestType=str(_field("requestType", "request_type") or "activation"),
        effectiveAt=(str(_field("effectiveAt", "effective_at")) if _field("effectiveAt", "effective_at") is not None else None),
        comments=(str(_field("comments")) if _field("comments") is not None else None),
        commentThread=list(_field("commentThread", "comment_thread") or []),
        requestedAt=(str(_field("requestedAt", "requested_at")) if _field("requestedAt", "requested_at") is not None else None),
        reviewedBy=(str(_field("reviewedBy", "reviewed_by")) if _field("reviewedBy", "reviewed_by") is not None else None),
        reviewedAt=(str(_field("reviewedAt", "reviewed_at")) if _field("reviewedAt", "reviewed_at") is not None else None),
    )
