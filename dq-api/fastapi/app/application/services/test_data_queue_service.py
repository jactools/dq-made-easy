from __future__ import annotations

import asyncio
import time
from typing import Any, Awaitable, Callable, Mapping
from uuid import uuid4

from fastapi import HTTPException
from opentelemetry import propagate

from app.core.otel_metrics import record_async_queue_event

FindActiveQueuedTestDataRequest = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any] | None]]


def inject_queue_trace_headers(queue_payload: dict[str, Any]) -> None:
    headers = queue_payload.get("headers") if isinstance(queue_payload.get("headers"), dict) else {}
    propagate.inject(headers)
    queue_payload["headers"] = headers


def build_test_data_request_record(
    *,
    request_id: str,
    job_id: str,
    correlation_id: str,
    request_payload: dict[str, Any],
    current_timestamp: str,
) -> dict[str, Any]:
    return {
        "request_id": request_id,
        "job_id": job_id,
        "business_key": correlation_id,
        "status": "pending",
        "target_type": request_payload["target_type"],
        "target_id": request_payload["target_id"],
        "sample_count": int(request_payload["sample_count"]),
        "requested_at": current_timestamp,
        "started_at": None,
        "completed_at": None,
        "error_message": None,
        "correlation_id": correlation_id,
        "result": None,
    }


def _active_test_data_request_conflict_detail(
    *,
    request_payload: dict[str, Any],
    active_request: dict[str, Any],
) -> dict[str, Any]:
    return {
        "error": "queued_test_data_request_already_active",
        "message": "Test data request is already active for this target",
        "target_type": request_payload["target_type"],
        "target_id": request_payload["target_id"],
        "active_request_id": str(active_request.get("request_id") or ""),
        "active_request_status": str(active_request.get("status") or ""),
    }


def test_data_request_key(request_id: str) -> str:
    return f"test-data-request:{request_id}"


async def write_test_data_request_record(
    redis_url: str,
    record: dict[str, Any],
    ttl_seconds: int,
    redis_set_json,
) -> None:
    await redis_set_json(redis_url, test_data_request_key(str(record["request_id"])), record, ttl_seconds)


async def read_test_data_request_record(
    redis_url: str,
    request_id: str,
    redis_get_json,
) -> dict[str, Any] | None:
    return await redis_get_json(redis_url, test_data_request_key(request_id))


async def enqueue_queued_test_data_request(
    *,
    request_headers: Mapping[str, str],
    request_payload: dict[str, Any],
    redis_url: str,
    queue_key: str,
    ttl_seconds: int,
    current_timestamp: str,
    write_record,
    push_queue,
    find_active_request: FindActiveQueuedTestDataRequest | None = None,
) -> dict[str, Any]:
    if find_active_request is not None:
        active_request = await find_active_request(redis_url, request_payload)
        if active_request is not None:
            raise HTTPException(
                status_code=409,
                detail=_active_test_data_request_conflict_detail(
                    request_payload=request_payload,
                    active_request=active_request,
                ),
            )

    request_id = f"tdr-{uuid4().hex[:12]}"
    job_id = f"tdj-{uuid4().hex[:12]}"
    correlation_id = request_headers.get("X-Correlation-ID") or f"corr-{uuid4().hex[:12]}"
    queue_payload = {
        "type": "test_data_generation",
        "job_id": job_id,
        "test_data_request_id": request_id,
        "correlation_id": correlation_id,
        "headers": {},
        "payload": request_payload,
    }
    inject_queue_trace_headers(queue_payload)

    record = build_test_data_request_record(
        request_id=request_id,
        job_id=job_id,
        correlation_id=correlation_id,
        request_payload=request_payload,
        current_timestamp=current_timestamp,
    )

    await write_record(redis_url, record, ttl_seconds)
    try:
        await push_queue(redis_url, queue_key, queue_payload)
    except Exception as exc:
        failed_record = dict(record)
        failed_record["status"] = "failed"
        failed_record["completed_at"] = current_timestamp
        failed_record["error_message"] = f"Failed to enqueue test data job: {exc}"
        await write_record(redis_url, failed_record, ttl_seconds)
        record_async_queue_event(service="dq-api", queue_type="profiling", stage="enqueue", result="failure")
        raise HTTPException(status_code=503, detail="Failed to enqueue test data job") from exc

    record_async_queue_event(service="dq-api", queue_type="profiling", stage="enqueue", result="success")
    return record


async def wait_for_test_data_request_result(
    *,
    request_id: str,
    redis_url: str,
    read_record,
    poll_interval_seconds: float,
    wait_timeout_seconds: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + wait_timeout_seconds
    while time.monotonic() < deadline:
        record = await read_record(redis_url, request_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"Test data request '{request_id}' not found")

        status = str(record.get("status") or "").lower()
        if status == "completed":
            return record
        if status == "failed":
            raise HTTPException(
                status_code=503,
                detail=str(record.get("error_message") or "Test data generation failed"),
            )
        await asyncio.sleep(poll_interval_seconds)

    raise HTTPException(status_code=504, detail="Timed out waiting for queued test data generation")