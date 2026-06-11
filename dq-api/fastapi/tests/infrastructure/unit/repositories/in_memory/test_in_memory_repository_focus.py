from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.infrastructure.repositories.in_memory_exception_reason_analytics_projection_repository import (
    InMemoryExceptionReasonAnalyticsProjectionRepository,
)
from app.infrastructure.repositories.in_memory_profiling_repository import InMemoryProfilingRepository
from app.infrastructure.repositories.in_memory_sessions_repository import InMemorySessionsRepository
from app.infrastructure.repositories.in_memory_validation_run_repository import InMemoryValidationRunRepository


def test_in_memory_sessions_repository_creates_touches_and_deletes_sessions() -> None:
    repository = InMemorySessionsRepository()

    repository.create_session("session-1", "user-1", access_token="a", id_token="i", refresh_token="r")
    created = repository.get_session("session-1")

    assert created is not None
    assert created.id == "session-1"
    assert created.user_id == "user-1"
    assert created.access_token == "a"

    previous_activity = created.last_activity
    repository.touch_session("session-1")
    touched = repository.get_session("session-1")

    assert touched is not None
    assert touched.last_activity >= previous_activity

    repository.delete_session("session-1")
    assert repository.get_session("session-1") is None


@pytest.mark.anyio
async def test_in_memory_validation_run_repository_saves_lists_and_gets_runs() -> None:
    repository = InMemoryValidationRunRepository()

    run = await repository.save_run(
        run_id="run-1",
        workspace="ws-1",
        triggered_by="user-1",
        run_at="2026-05-22T10:00:00Z",
        total=2,
        valid_count=1,
        invalid_count=1,
        status="completed",
        items=[
            {
                "id": "item-1",
                "ruleId": "rule-1",
                "ruleName": "Rule 1",
                "ruleVersionNumber": 3,
                "valid": True,
                "errors": 0,
                "warnings": 1,
                "diagnostics": [{"code": "DQ1_EMPTY_EXPRESSION"}],
                "conflicts": [{"field": "name"}],
            }
        ],
    )

    assert run.id == "run-1"
    assert run.validation_items[0].rule_id == "rule-1"

    listed = await repository.list_runs(workspace="ws-1", limit=10, offset=0)
    assert listed.total == 1
    assert listed.data[0].id == "run-1"

    fetched = await repository.get_run("run-1")
    assert fetched is not None
    assert fetched.id == "run-1"

    assert await repository.get_run("missing") is None


def test_in_memory_profiling_repository_tracks_state_transitions() -> None:
    repository = InMemoryProfilingRepository()

    request = SimpleNamespace(
        profiling_request_id=None,
        data_source_id="ds-1",
        requested_by_user_id="user-1",
        requested_at=datetime(2026, 5, 22, 10, 0, tzinfo=timezone.utc),
        status=None,
        job_id=None,
    )

    created = repository.create_request(request)
    assert created.profiling_request_id.startswith("pr-")
    assert created.status == "pending"

    repository.set_started(created.profiling_request_id, "job-1")
    started_row = repository._store[created.profiling_request_id]
    assert started_row["status"] == "started"
    assert started_row["job_id"] == "job-1"

    repository.set_completed(created.profiling_request_id, success=False, error_message="boom")
    completed_row = repository._store[created.profiling_request_id]
    assert completed_row["status"] == "failed"
    assert completed_row["error_message"] == "boom"

    with pytest.raises(KeyError):
        repository.set_started("missing", "job-2")
    with pytest.raises(KeyError):
        repository.set_completed("missing", success=True)


@pytest.mark.anyio
async def test_in_memory_exception_reason_analytics_projection_repository_persists_and_summarizes(monkeypatch: pytest.MonkeyPatch) -> None:
    repository = InMemoryExceptionReasonAnalyticsProjectionRepository()

    projection_rows = [
        {
            "id": "reason-1",
            "failed_record_count": 2,
            "record_identifier_values": ["A", "A", "B"],
            "execution_run_ids": ["run-1"],
        },
        {
            "id": "reason-1",
            "failed_record_count": 1,
            "record_identifier_values": ["B", "C"],
            "execution_run_ids": ["run-2"],
        },
    ]

    monkeypatch.setattr(
        "app.infrastructure.repositories.in_memory_exception_reason_analytics_projection_repository.build_reason_analytics_projection_rows",
        lambda exception_records: projection_rows,
    )
    monkeypatch.setattr(
        "app.infrastructure.repositories.in_memory_exception_reason_analytics_projection_repository.summarize_reason_analytics_projection_rows",
        lambda rows, **kwargs: SimpleNamespace(rows=list(rows), kwargs=kwargs),
    )

    persisted_count = await repository.persist_exception_records([SimpleNamespace(id="record-1")])
    assert persisted_count == 2

    stored = repository._rows["reason-1"]
    assert stored["failed_record_count"] == 3
    assert stored["record_identifier_values"] == ["A", "B", "C"]
    assert stored["execution_run_ids"] == ["run-1", "run-2"]

    summary = await repository.summarize_reason_analytics(
        data_object_version_ids=["dov-1"],
        execution_run_ids=["run-1"],
        reason_codes=["reason-1"],
    )
    assert summary.kwargs["data_object_version_ids"] == ["dov-1"]
    assert summary.kwargs["execution_run_ids"] == ["run-1"]
    assert summary.kwargs["reason_codes"] == ["reason-1"]
