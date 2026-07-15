"""Execution artifact persistence (Layer 3.5).

Writes execution payloads and error artifacts to disk.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def persist_execution_payload(
    target_dir: str | Path,
    payload: dict[str, Any],
    *,
    artifact_prefix: str,
) -> list[str]:
    """Persist execution and error artifacts to disk."""
    output_path = Path(target_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    artifact_paths: list[str] = []

    execution_path = output_path / f"{artifact_prefix}_execution.json"
    execution_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    artifact_paths.append(str(execution_path))

    errors_payload = {
        "engine_type": payload.get("engine_type", artifact_prefix),
        "rule_id": payload.get("rule_id"),
        "error_count": payload.get("failed_count", 0),
        "storage_strategy": (payload.get("error_management") or {}).get(
            "storage_strategy", "chunked"
        ),
        "sampled_error_rows": (payload.get("error_management") or {}).get(
            "sampled_error_rows", []
        ),
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
    errors_path.write_text(
        json.dumps(errors_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    artifact_paths.append(str(errors_path))

    return artifact_paths
