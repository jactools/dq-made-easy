from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.application.services import test_data_queue_service as service


@pytest.mark.anyio
async def test_enqueue_queued_test_data_request_builds_record_and_queue_payload() -> None:
    writes: list[tuple[str, dict, int]] = []
    pushes: list[tuple[str, str, dict]] = []

    async def _write_record(redis_url: str, record: dict, ttl_seconds: int) -> None:
        writes.append((redis_url, dict(record), ttl_seconds))

    async def _push_queue(redis_url: str, queue_key: str, payload: dict) -> None:
        pushes.append((redis_url, queue_key, dict(payload)))

    record = await service.enqueue_queued_test_data_request(
        request_headers={"X-Correlation-ID": "corr-123"},
        request_payload={"target_type": "data_object_version", "target_id": "dov-1", "sample_count": 2},
        redis_url="redis://queue",
        queue_key="queue-key",
        ttl_seconds=300,
        current_timestamp="2026-04-20T16:30:00Z",
        write_record=_write_record,
        push_queue=_push_queue,
    )

    assert record["request_id"].startswith("tdr-")
    assert record["job_id"].startswith("tdj-")
    assert record["correlation_id"] == "corr-123"
    assert len(writes) == 1
    assert writes[0][2] == 300
    assert len(pushes) == 1
    assert pushes[0][1] == "queue-key"
    assert pushes[0][2]["type"] == "test_data_generation"
    assert pushes[0][2]["payload"]["target_id"] == "dov-1"


@pytest.mark.anyio
async def test_enqueue_queued_test_data_request_rejects_active_request() -> None:
    writes: list[dict] = []

    async def _write_record(_redis_url: str, record: dict, _ttl_seconds: int) -> None:
        writes.append(dict(record))

    async def _push_queue(_redis_url: str, _queue_key: str, _payload: dict) -> None:
        raise AssertionError("push should not be called")

    async def _find_active_request(_redis_url: str, request_payload: dict) -> dict | None:
        return {
            "request_id": "tdr-active-1",
            "status": "pending",
            "target_type": request_payload["target_type"],
            "target_id": request_payload["target_id"],
        }

    with pytest.raises(HTTPException) as exc_info:
        await service.enqueue_queued_test_data_request(
            request_headers={"X-Correlation-ID": "corr-123"},
            request_payload={"target_type": "data_object_version", "target_id": "dov-1", "sample_count": 2},
            redis_url="redis://queue",
            queue_key="queue-key",
            ttl_seconds=300,
            current_timestamp="2026-04-20T16:30:00Z",
            write_record=_write_record,
            push_queue=_push_queue,
            find_active_request=_find_active_request,
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["error"] == "queued_test_data_request_already_active"
    assert exc_info.value.detail["target_id"] == "dov-1"
    assert writes == []


@pytest.mark.anyio
async def test_enqueue_queued_test_data_request_marks_failed_record_on_push_error() -> None:
    writes: list[dict] = []

    async def _write_record(_redis_url: str, record: dict, _ttl_seconds: int) -> None:
        writes.append(dict(record))

    async def _push_queue(_redis_url: str, _queue_key: str, _payload: dict) -> None:
        raise RuntimeError("redis down")

    with pytest.raises(HTTPException) as exc_info:
        await service.enqueue_queued_test_data_request(
            request_headers={},
            request_payload={"target_type": "data_object_version", "target_id": "dov-1", "sample_count": 2},
            redis_url="redis://queue",
            queue_key="queue-key",
            ttl_seconds=300,
            current_timestamp="2026-04-20T16:31:00Z",
            write_record=_write_record,
            push_queue=_push_queue,
        )

    assert exc_info.value.status_code == 503
    assert len(writes) == 2
    assert writes[-1]["status"] == "failed"
    assert writes[-1]["completed_at"] == "2026-04-20T16:31:00Z"
    assert "redis down" in str(writes[-1]["error_message"])


@pytest.mark.anyio
async def test_wait_for_test_data_request_result_returns_completed_record() -> None:
    calls = 0

    async def _read_record(_redis_url: str, _request_id: str) -> dict:
        nonlocal calls
        calls += 1
        if calls == 1:
            return {"status": "pending"}
        return {"status": "completed", "result": {"samples": []}}

    record = await service.wait_for_test_data_request_result(
        request_id="tdr-1",
        redis_url="redis://queue",
        read_record=_read_record,
        poll_interval_seconds=0,
        wait_timeout_seconds=1,
    )

    assert record["status"] == "completed"


@pytest.mark.anyio
async def test_wait_for_test_data_request_result_raises_for_failed_record() -> None:
    async def _read_record(_redis_url: str, _request_id: str) -> dict:
        return {"status": "failed", "error_message": "boom"}

    with pytest.raises(HTTPException) as exc_info:
        await service.wait_for_test_data_request_result(
            request_id="tdr-2",
            redis_url="redis://queue",
            read_record=_read_record,
            poll_interval_seconds=0,
            wait_timeout_seconds=1,
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "boom"