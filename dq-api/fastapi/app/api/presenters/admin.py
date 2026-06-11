from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from app.api.presenters.row_access import read_row_field
from app.domain.user_names import compose_user_display_name


def derive_admin_rule_status_from_row(row: Any) -> str:
    if bool(read_row_field(row, "removed")) or bool(read_row_field(row, "removed_at")) or bool(read_row_field(row, "deleted_on")):
        return "removed"
    if bool(read_row_field(row, "active")):
        return "activated"
    status = str(read_row_field(row, "last_approval_status") or "").strip().lower().replace("_", "-")
    return status or "draft"


def _serialize_admin_user(user: Any) -> dict[str, Any]:
    model_dump = getattr(user, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump()
        if isinstance(dumped, Mapping):
            return dict(dumped)
    if isinstance(user, Mapping):
        return dict(user)
    return {
        "id": str(getattr(user, "id", "") or ""),
        "first_name": str(getattr(user, "first_name", "") or ""),
        "last_name": str(getattr(user, "last_name", "") or ""),
        "email": str(getattr(user, "email", "") or ""),
        "roles": list(getattr(user, "roles", []) or []),
        "workspaces": list(getattr(user, "workspaces", []) or []),
    }


def filter_admin_users(users: Sequence[Any], q: str | None, sort: str | None, order: str | None) -> list[Any]:
    result = list(users)
    filter_value = (q or "").strip().lower()
    if filter_value:
        result = [
            user
            for user in result
            if filter_value
            in " ".join(
                [
                    str(getattr(user, "id", "") or ""),
                    compose_user_display_name(
                        getattr(user, "first_name", ""),
                        getattr(user, "last_name", ""),
                        fallback=getattr(user, "email", "") or getattr(user, "id", ""),
                    ),
                    str(getattr(user, "email", "") or ""),
                    *[str(role) for role in getattr(user, "roles", [])],
                    *[str(workspace) for workspace in getattr(user, "workspaces", [])],
                ]
            ).lower()
        ]

    if (sort or "").lower() == "name":
        reverse = (order or "asc").lower() == "desc"
        result = sorted(
            result,
            key=lambda user: compose_user_display_name(
                getattr(user, "first_name", ""),
                getattr(user, "last_name", ""),
                fallback=getattr(user, "email", "") or getattr(user, "id", ""),
            ),
            reverse=reverse,
        )

    return result


def build_admin_users_page_payload(users: Sequence[Any], page: int, limit: int) -> dict[str, Any]:
    safe_page = max(1, page)
    safe_limit = max(1, min(100, limit))
    offset = (safe_page - 1) * safe_limit
    serialized_users = [_serialize_admin_user(user) for user in users]
    total = len(serialized_users)
    total_pages = math.ceil(total / safe_limit) if total else 0

    return {
        "data": serialized_users[offset : offset + safe_limit],
        "pagination": {
            "total": total,
            "page": safe_page,
            "limit": safe_limit,
            "total_pages": total_pages,
            "has_next": safe_page < total_pages,
            "has_previous": safe_page > 1,
        },
    }