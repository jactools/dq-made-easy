"""Payload parsing, coercion, and engine normalization (Layer 3).

These helpers parse raw dispatch messages, coerce field values, and
normalize engine type strings. They are engine-agnostic and imported
by both shared execution and engine-specific dispatch modules.
"""

from __future__ import annotations

import json
from typing import Any

from dq_plan_execution_types import DqWorkerExecutionError


ENGINE_ALIASES = {
    "great_expectations": "gx",
    "great-expectations": "gx",
    "pyspark_native": "pyspark",
    "spark": "pyspark",
}


def normalize_execution_engine(engine_type: str | None) -> str:
    """Normalize an engine type string to its canonical form."""
    normalized = str(engine_type or "").strip().lower()
    return ENGINE_ALIASES.get(normalized, normalized)


def parse_dispatch_payload(raw: str) -> dict[str, Any]:
    """Parse and validate a raw dispatch payload (JSON)."""
    try:
        payload = json.loads(raw)
    except Exception as exc:
        raise DqWorkerExecutionError(
            "Execution dispatch message is not valid JSON",
            failure_code="DQ_DISPATCH_INVALID_JSON",
        ) from exc
    if not isinstance(payload, dict):
        raise DqWorkerExecutionError(
            "Execution dispatch message must be a JSON object",
            failure_code="DQ_DISPATCH_INVALID_JSON",
        )
    return payload


def coerce_str(payload: dict[str, Any], *keys: str) -> str:
    """Return the first truthy string value for the given keys."""
    for key in keys:
        value = payload.get(key)
        if value is None:
            continue
        text_value = str(value).strip()
        if text_value:
            return text_value
    return ""


def coerce_int(payload: dict[str, Any], *keys: str) -> int:
    """Return the first positive integer value for the given keys."""
    for key in keys:
        value = payload.get(key)
        if value is None:
            continue
        try:
            parsed = int(value)
            if parsed >= 1:
                return parsed
        except Exception:
            continue
    return 0
