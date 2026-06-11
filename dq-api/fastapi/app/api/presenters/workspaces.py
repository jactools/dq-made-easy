from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any


def _serialize_workspace_row(row: Any) -> dict[str, Any]:
    if isinstance(row, Mapping):
        return dict(row)
    model_dump = getattr(row, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump()
        if isinstance(dumped, Mapping):
            return dict(dumped)
    return {
        "id": str(getattr(row, "id", "") or ""),
        "name": str(getattr(row, "name", "") or ""),
        "description": str(getattr(row, "description", "") or ""),
    }


def build_workspaces_page_payload(rows: Sequence[Any], page: int, limit: int) -> dict[str, Any]:
    safe_page = max(1, page)
    safe_limit = max(1, min(100, limit))
    serialized_rows = [_serialize_workspace_row(row) for row in rows]
    offset = (safe_page - 1) * safe_limit
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