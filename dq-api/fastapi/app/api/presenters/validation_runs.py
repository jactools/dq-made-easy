from __future__ import annotations

import csv
import io
import json
import math
from typing import Any

from app.domain.entities.validation_run import ValidationRunEntity, ValidationRunItemEntity


def build_validation_run_item_payload(item: ValidationRunItemEntity) -> dict[str, Any]:
    return {
        "id": item.id,
        "ruleId": item.rule_id,
        "ruleName": item.rule_name,
        "ruleVersionNumber": item.rule_version_number,
        "valid": item.valid,
        "errors": item.errors,
        "warnings": item.warnings,
        "diagnostics": list(item.diagnostics),
        "conflicts": list(item.conflicts),
    }


def build_validation_run_payload(run: ValidationRunEntity) -> dict[str, Any]:
    return {
        "id": run.id,
        "workspace": run.workspace,
        "triggeredBy": run.triggered_by,
        "runAt": run.run_at,
        "total": run.total,
        "validCount": run.valid_count,
        "invalidCount": run.invalid_count,
        "status": run.status,
        "items": [build_validation_run_item_payload(item) for item in run.validation_items],
    }


def build_validation_runs_page_payload(
    rows: list[dict[str, Any]],
    *,
    page: int,
    limit: int,
    total: int | None = None,
) -> dict[str, Any]:
    safe_page = max(1, page)
    safe_limit = max(1, min(100, limit))
    effective_total = len(rows) if total is None else int(max(0, total))
    offset = (safe_page - 1) * safe_limit
    total_pages = math.ceil(effective_total / safe_limit) if effective_total else 0
    page_rows = rows if total is not None else rows[offset : offset + safe_limit]
    return {
        "data": page_rows,
        "pagination": {
            "total": effective_total,
            "page": safe_page,
            "limit": safe_limit,
            "total_pages": total_pages,
            "has_next": safe_page < total_pages,
            "has_previous": safe_page > 1,
        },
    }


def build_validation_run_csv_export(*, run_id: str, serialized_run: dict[str, Any]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=["runId", "ruleId", "ruleName", "valid", "errors", "warnings"],
        extrasaction="ignore",
    )
    writer.writeheader()
    for item in serialized_run.get("items") or []:
        writer.writerow(
            {
                "runId": run_id,
                "ruleId": item.get("ruleId") or "",
                "ruleName": item.get("ruleName") or "",
                "valid": item.get("valid"),
                "errors": item.get("errors") or 0,
                "warnings": item.get("warnings") or 0,
            }
        )
    output.seek(0)
    return output.getvalue()


def build_validation_run_json_export(serialized_run: dict[str, Any]) -> str:
    return json.dumps(serialized_run, default=str, indent=2)