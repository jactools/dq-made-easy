from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import uuid4


def _field(payload: Any, *names: str) -> Any:
    if isinstance(payload, Mapping):
        for name in names:
            if payload.get(name) is not None:
                return payload.get(name)
        return None
    for name in names:
        value = getattr(payload, name, None)
        if value is not None:
            return value
    return None


def resolve_profiling_enqueue_settings(app_settings: Any, default_settings: Any) -> Any:
    return app_settings if app_settings is not None else default_settings


def resolve_profiling_enqueue_correlation_id(
    request_payload: Any,
    current_correlation_id: str | None,
    request_headers: Mapping[str, Any] | None,
) -> tuple[str, bool]:
    body_correlation_id = str(_field(request_payload, "correlation_id", "correlationId") or "").strip()
    if body_correlation_id:
        return body_correlation_id, False

    current = str(current_correlation_id or "").strip()
    if current:
        return current, False

    headers = request_headers if isinstance(request_headers, Mapping) else {}
    header_correlation_id = str(headers.get("X-Correlation-ID") or headers.get("x-correlation-id") or "").strip()
    if header_correlation_id:
        return header_correlation_id, False

    return str(uuid4()), True


def build_profiling_enqueue_response_payload(result: Any) -> dict[str, Any]:
    return {
        "enqueued": bool(getattr(result, "enqueued", False)),
        "job_id": getattr(result, "job_id", None),
    }


def require_profiling_started_job_id(new_status: str, job_id: str | None) -> str | None:
    normalized_status = str(new_status or "").strip().lower()
    normalized_job_id = str(job_id or "").strip() or None
    if normalized_status == "started" and not normalized_job_id:
        raise ValueError("job_id is required when new_status is started")
    return normalized_job_id


def resolve_profiling_completion_success(new_status: str) -> bool:
    return str(new_status or "").strip().lower() == "completed"