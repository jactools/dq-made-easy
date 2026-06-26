from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def build_summary(*, expectations: list[dict[str, Any]], passed: int, failed: int) -> dict[str, Any]:
    return {
        "started_at": utc_now_iso(),
        "completed_at": utc_now_iso(),
        "expectation_count": int(len(expectations)),
        "passed_expectation_count": int(passed),
        "failed_expectation_count": int(failed),
    }


def add_row_identifiers(diagnostics: list[dict[str, Any]], *, row_identifier: str | None) -> list[dict[str, Any]]:
    if not row_identifier:
        return diagnostics
    for diagnostic in diagnostics:
        if "row_identifier" not in diagnostic:
            diagnostic["row_identifier"] = row_identifier
        if "data_primary_key" not in diagnostic:
            diagnostic["data_primary_key"] = row_identifier
    return diagnostics
