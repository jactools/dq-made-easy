from __future__ import annotations

import math
from typing import Any


def build_rules_page_payload(rows: list[dict[str, Any]], page: int, limit: int) -> dict[str, Any]:
    safe_page = max(1, page)
    safe_limit = max(1, min(100, limit))
    offset = (safe_page - 1) * safe_limit
    total = len(rows)
    total_pages = math.ceil(total / safe_limit) if total else 0

    return {
        "data": rows[offset : offset + safe_limit],
        "pagination": {
            "total": total,
            "page": safe_page,
            "limit": safe_limit,
            "total_pages": total_pages,
            "has_next": safe_page < total_pages,
            "has_previous": safe_page > 1,
        },
    }