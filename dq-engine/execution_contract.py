from __future__ import annotations

import json
from pathlib import Path
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


def persist_execution_payload(target_dir: str | Path, payload: dict[str, Any], *, artifact_prefix: str) -> list[str]:
    output_path = Path(target_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    artifact_paths: list[str] = []

    execution_path = output_path / f"{artifact_prefix}_execution.json"
    execution_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    artifact_paths.append(str(execution_path))

    errors_payload = {
        "engine_type": payload.get("engine_type", artifact_prefix),
        "rule_id": payload.get("rule_id"),
        "error_count": payload.get("failed_count", 0),
        "storage_strategy": (payload.get("error_management") or {}).get("storage_strategy", "chunked"),
        "sampled_error_rows": (payload.get("error_management") or {}).get("sampled_error_rows", []),
        "execution_metadata": payload.get("execution_metadata", {}),
        "quarantine_artifact": payload.get("quarantine_artifact", {}),
        "observability_summary": payload.get("observability_summary", {}),
        "failure_code": payload.get("failure_code"),
        "failure_message": payload.get("failure_message"),
        "failed_check": payload.get("failed_check", {}),
        "failure_metrics": payload.get("failure_metrics", {}),
        "trace": payload.get("trace", {}),
    }

    errors_path = output_path / f"{artifact_prefix}_errors.json"
    errors_path.write_text(json.dumps(errors_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    artifact_paths.append(str(errors_path))

    return artifact_paths