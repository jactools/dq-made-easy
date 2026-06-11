from __future__ import annotations

from typing import Any

from app.core.auth import has_required_scope


COMMENT_STATE_NEW = "new"
COMMENT_STATE_ACKNOWLEDGED_BY_OWNER = "acknowledged_by_owner"
COMMENT_STATE_VOTED_UP = "voted_up"
COMMENT_STATE_RESOLVED = "resolved"
COMMENT_STATE_REOPENED = "reopened"
COMMENT_STATE_LOCKED = "locked"

VALID_COMMENT_STATES = {
    COMMENT_STATE_NEW,
    COMMENT_STATE_ACKNOWLEDGED_BY_OWNER,
    COMMENT_STATE_VOTED_UP,
    COMMENT_STATE_RESOLVED,
    COMMENT_STATE_REOPENED,
    COMMENT_STATE_LOCKED,
}


def normalize_comment_state(value: object) -> str:
    normalized = str(value or "").strip().lower().replace("-", "_")
    return normalized if normalized in VALID_COMMENT_STATES else COMMENT_STATE_NEW


def is_comment_admin(granted_scopes: list[str]) -> bool:
    return has_required_scope(granted_scopes, ["dq:users:manage", "dq:workspace:manage", "dq:*"])


def build_comment_removed_placeholder() -> str:
    return "[removed]"


def first_non_empty_text(*values: object) -> str | None:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def coerce_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def coerce_int(value: object, default: int = 0) -> int:
    try:
        return int(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def merge_comment_event(entry: dict[str, Any], details: dict[str, Any], *, action: str, timestamp: str, actor_id: str | None) -> dict[str, Any]:
    updated = dict(entry)

    if action == "comment_updated":
        content = first_non_empty_text(details.get("comment"), details.get("content"))
        if content is not None:
            updated["content"] = content
        updated["edited"] = True
        updated["edited_at"] = timestamp
        updated["edited_by"] = actor_id or updated.get("edited_by")
        updated["edit_count"] = coerce_int(updated.get("edit_count"), 0) + 1

    elif action == "comment_deleted":
        updated["removed"] = True
        updated["removed_at"] = timestamp
        updated["removed_by"] = actor_id or updated.get("removed_by")
        removed_reason = first_non_empty_text(details.get("removed_reason"), details.get("reason"))
        if removed_reason is not None:
            updated["removed_reason"] = removed_reason
        updated["content"] = build_comment_removed_placeholder()

    elif action == "comment_resolved":
        updated["state"] = COMMENT_STATE_RESOLVED
        updated["resolved_at"] = timestamp
        updated["resolved_by"] = actor_id or updated.get("resolved_by")

    elif action == "comment_reopened":
        updated["state"] = COMMENT_STATE_REOPENED
        updated["reopened_at"] = timestamp
        updated["reopened_by"] = actor_id or updated.get("reopened_by")

    elif action == "comment_acknowledged":
        updated["state"] = COMMENT_STATE_ACKNOWLEDGED_BY_OWNER
        updated["acknowledged_at"] = timestamp
        updated["acknowledged_by"] = actor_id or updated.get("acknowledged_by")

    elif action == "comment_voted_up":
        updated["state"] = COMMENT_STATE_VOTED_UP
        updated["vote_count"] = coerce_int(updated.get("vote_count"), 0) + 1

    elif action == "comment_locked":
        updated["locked"] = True
        updated["state"] = COMMENT_STATE_LOCKED
        updated["locked_at"] = timestamp
        updated["locked_by"] = actor_id or updated.get("locked_by")

    elif action == "comment_unlocked":
        updated["locked"] = False
        updated["locked_at"] = None
        updated["locked_by"] = None
        if normalize_comment_state(updated.get("state")) == COMMENT_STATE_LOCKED:
            updated["state"] = COMMENT_STATE_REOPENED

    return updated