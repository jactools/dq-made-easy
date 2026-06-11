from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException

from dq_domain_validation import allowed_values

from app.api.presenters.row_access import read_row_field


_ALLOWED_REQUEST_TYPES = set(allowed_values("approval.request_type"))

_CAMEL_CASE_APPROVAL_KEYS = (
    "ruleId",
    "effectiveStatus",
    "gxRunPlanId",
    "gxRunPlanVersionId",
    "requestType",
    "workspaceId",
    "requesterId",
    "requestedAt",
    "effectiveAt",
    "reviewedBy",
    "reviewedAt",
)


def normalize_approval_request_type(value: Any) -> str:
    normalized = str(value or "activation").strip().lower().replace("-", "_")
    if not normalized:
        return "activation"
    if normalized in _ALLOWED_REQUEST_TYPES:
        return normalized
    raise HTTPException(
        status_code=422,
        detail=f"request_type must be one of {', '.join(sorted(_ALLOWED_REQUEST_TYPES))}",
    )


def normalize_approval_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise HTTPException(status_code=422, detail="suite_repair.data_object_version_ids must be a list")
    items: list[str] = []
    for entry in value:
        text = str(entry or "").strip()
        if text:
            items.append(text)
    return items


def parse_approval_suite_repair(payload: Mapping[str, Any]) -> dict[str, Any]:
    raw = payload.get("suite_repair")
    if raw is None:
        raise HTTPException(status_code=422, detail="suite_repair is required for gx_suite_repair")
    if not isinstance(raw, Mapping):
        raise HTTPException(status_code=422, detail="suite_repair must be an object")

    data_object_id = str(raw.get("data_object_id") or "").strip() or None
    dataset_id = str(raw.get("dataset_id") or "").strip() or None
    data_product_id = str(raw.get("data_product_id") or "").strip() or None
    data_object_version_ids = normalize_approval_string_list(raw.get("data_object_version_ids"))
    primary_key_fields = normalize_approval_string_list(raw.get("primary_key_fields"))

    if not any((data_object_id, dataset_id, data_product_id)):
        raise HTTPException(
            status_code=422,
            detail="suite_repair must include at least one of data_object_id, dataset_id, data_product_id",
        )
    if not data_object_version_ids:
        raise HTTPException(status_code=422, detail="suite_repair.data_object_version_ids must not be empty")

    return {
        "data_object_id": data_object_id,
        "dataset_id": dataset_id,
        "data_product_id": data_product_id,
        "data_object_version_ids": data_object_version_ids,
        "primary_key_fields": primary_key_fields,
    }


def reject_camel_case_approval_keys(payload: Mapping[str, Any], context: str) -> None:
    offending = [key for key in _CAMEL_CASE_APPROVAL_KEYS if key in payload]
    if offending:
        raise HTTPException(
            status_code=422,
            detail=f"{context} must use snake_case keys: {', '.join(offending)}",
        )


def derive_approval_effective_status(request_type: str) -> str | None:
    if request_type == "activation":
        return "activated"
    if request_type == "deactivation":
        return "deactivated"
    return None


def parse_approval_effective_at(payload: Mapping[str, Any]) -> tuple[str | None, datetime | None]:
    raw = payload.get("effective_at")
    if raw is None:
        return None, None

    text = str(raw).strip()
    if not text:
        return None, None

    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception as exc:
        raise HTTPException(status_code=422, detail="effective_at must be a valid RFC3339 timestamp") from exc

    if parsed.tzinfo is None or parsed.tzinfo.utcoffset(parsed) is None:
        raise HTTPException(status_code=422, detail="effective_at must include a timezone offset")

    normalized = parsed.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    return normalized, parsed


def build_approvals_page_payload(rows: Sequence[Mapping[str, Any]], page: int, limit: int) -> dict[str, Any]:
    safe_page = max(1, page)
    safe_limit = max(1, min(100, limit))
    offset = (safe_page - 1) * safe_limit
    serialized_rows = [dict(row) for row in rows]
    total = len(serialized_rows)
    total_pages = math.ceil(total / safe_limit) if total else 0

    return {
        "data": serialized_rows[offset : offset + safe_limit],
        "pagination": {
            "total": total,
            "page": safe_page,
            "limit": safe_limit,
            "total_pages": total_pages,
            "has_next": safe_page < total_pages,
            "has_previous": safe_page > 1,
        },
    }


def derive_approval_rule_status(
    rule_row: Any,
    approvals: Sequence[Any],
    *,
    status_canonicalizer: Callable[..., str | None],
) -> str:
    if rule_row:
        if bool(read_row_field(rule_row, "removed")) or bool(read_row_field(rule_row, "removed_at")) or bool(read_row_field(rule_row, "deleted_on")):
            return "removed"
        if bool(read_row_field(rule_row, "active")):
            return "activated"

        row_status = status_canonicalizer(entity="rule", status=read_row_field(rule_row, "last_approval_status"))
        if row_status in {"deactivated", "removed", "recovered"}:
            return row_status

    for approval in reversed(list(approvals)):
        status_value = status_canonicalizer(entity="rule", status=getattr(approval, "status", None))
        if status_value:
            return status_value

    if rule_row:
        last_approval_status = status_canonicalizer(entity="rule", status=read_row_field(rule_row, "last_approval_status"))
        if last_approval_status:
            return last_approval_status

    return "draft"