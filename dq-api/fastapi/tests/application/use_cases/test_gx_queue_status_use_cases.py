from __future__ import annotations

import json

import pytest
from fastapi import HTTPException

from app.application.use_cases.gx_queue_status import get_gx_execution_queue_status
from app.application.use_cases.gx_queue_status import GetGxExecutionQueueStatusQuery
from app.domain.entities.gx_execution_run import build_gx_execution_run_entity


class _RunRepository:
    def __init__(self, run_payload: dict | None) -> None:
        self._run_payload = run_payload

    async def get_run(self, run_id: str):
        if self._run_payload is None or run_id != str(self._run_payload.get("id") or ""):
            return None
        return build_gx_execution_run_entity(self._run_payload)


@pytest.mark.anyio
async def test_get_gx_execution_queue_status_reports_position() -> None:
    repository = _RunRepository(
        {
            "id": "run-123",
            "status": "pending",
            "correlationId": "corr-run-123",
            "engineType": "gx",
            "engineTarget": "pyspark",
            "executionShape": "single_object",
            "submittedAt": "2026-04-10T08:00:00Z",
            "createdAt": "2026-04-10T08:00:00Z",
            "updatedAt": "2026-04-10T08:00:00Z",
            "handoffPayload": {
                "engine_type": "gx",
                "dispatch_mode": "queued",
                "executor_target": "dq-engine",
                "queue_key": "dq-gx:execution-dispatch",
                "queue_message_id": "run-123",
            },
        }
    )

    async def fetch_queue_status(redis_url: str, queue_key: str, scan_limit: int):
        assert redis_url == "redis://stub"
        assert queue_key == "dq-gx:execution-dispatch"
        assert scan_limit == 10
        return 3, [
            json.dumps({"queue_message_id": "run-999", "engine_type": "gx"}),
            json.dumps({"queue_message_id": "run-123", "engine_type": "gx"}),
            json.dumps({"queue_message_id": "run-888", "engine_type": "gx"}),
        ]

    result = await get_gx_execution_queue_status(
        query=GetGxExecutionQueueStatusQuery(run_id="run-123", scan_limit=10),
        repository=repository,
        resolve_redis_url=lambda: "redis://stub",
        fetch_queue_status=fetch_queue_status,
    )

    assert result.run_id == "run-123"
    assert result.queue_key == "dq-gx:execution-dispatch"
    assert result.queue_message_id == "run-123"
    assert result.queue_length == 3
    assert result.inspected_depth == 3
    assert result.found is True
    assert result.index_from_head == 1
    assert result.index_from_tail == 1


@pytest.mark.anyio
async def test_get_gx_execution_queue_status_fails_fast_without_redis_url() -> None:
    repository = _RunRepository(
        {
            "id": "run-123",
            "status": "pending",
            "correlationId": "corr-run-123",
            "engineType": "gx",
            "engineTarget": "pyspark",
            "executionShape": "single_object",
            "submittedAt": "2026-04-10T08:00:00Z",
            "createdAt": "2026-04-10T08:00:00Z",
            "updatedAt": "2026-04-10T08:00:00Z",
            "handoffPayload": {
                "engine_type": "gx",
                "dispatch_mode": "queued",
                "executor_target": "dq-engine",
                "queue_key": "dq-gx:execution-dispatch",
                "queue_message_id": "run-123",
            },
        }
    )

    async def fetch_queue_status(redis_url: str, queue_key: str, scan_limit: int):
        raise AssertionError("fetch_queue_status should not be called")

    with pytest.raises(HTTPException) as error:
        await get_gx_execution_queue_status(
            query=GetGxExecutionQueueStatusQuery(run_id="run-123", scan_limit=10),
            repository=repository,
            resolve_redis_url=lambda: None,
            fetch_queue_status=fetch_queue_status,
        )

    assert error.value.status_code == 503
    assert error.value.detail["error"] == "dispatch_queue_unavailable"