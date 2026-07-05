"""Shared execution contract helpers (Layer 1).

Provides execution metadata and observability summary builders used by
engine-specific adapters (Layer 5) and the orchestrator (Layer 3).

Persistence logic lives in `dq_plan_execution_persistence.py`.

Renamed from ``execution_contract.py`` for namespace consistency.
"""

from __future__ import annotations

from typing import Any


def build_execution_metadata(
    *,
    rule_id: Any,
    engine_type: str,
    runtime: str,
    started_at: str,
    completed_at: str,
    duration_ms: float,
    source_row_count: int,
    execution_name: str,
    guardrails: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metadata = {
        "rule_id": rule_id,
        "engine_type": engine_type,
        "runtime": runtime,
        "execution_name": execution_name,
        "source_row_count": source_row_count,
        "started_at": started_at,
        "completed_at": completed_at,
        "duration_ms": round(duration_ms, 3),
    }
    metadata["guardrails"] = guardrails or {}
    return metadata


def build_observability_summary(
    *,
    engine_type: str,
    result: str,
    passed_count: int,
    failed_count: int,
    rule_family: str,
    duration_ms: float | None,
    storage_kind: str | None,
    storage_uri: str | None,
) -> dict[str, Any]:
    return {
        "engine_type": engine_type,
        "result": result,
        "passed_count": passed_count,
        "failed_count": failed_count,
        "rule_family": rule_family,
        "duration_ms": duration_ms,
        "storage_kind": storage_kind,
        "storage_uri": storage_uri,
    }
