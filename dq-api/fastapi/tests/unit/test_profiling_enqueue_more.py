from __future__ import annotations

import os
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints import profiling_enqueue as profiling
from app.application.services import profiling_enqueue_service


def test_resolve_queue_key_precedence(monkeypatch) -> None:
    monkeypatch.setenv("PROFILING_QUEUE_KEY", "primary")
    assert profiling._resolve_queue_key() == "primary"

    monkeypatch.delenv("PROFILING_QUEUE_KEY", raising=False)
    monkeypatch.setenv("DQ_PROFILING_QUEUE_KEY", "secondary")
    assert profiling._resolve_queue_key() == "secondary"

    monkeypatch.delenv("DQ_PROFILING_QUEUE_KEY", raising=False)
    monkeypatch.delenv("DQ_PROFILING_LOCAL_QUEUE", raising=False)
    with pytest.raises(profiling_enqueue_service.ProfilingQueueNotConfiguredError):
        profiling._resolve_queue_key()


def test_resolve_redis_url_from_env_and_settings(monkeypatch) -> None:
    monkeypatch.setenv("PROFILING_REDIS_URL", "redis://env-host:6379/0")
    settings = SimpleNamespace(redis_host="host", redis_port=6379, redis_db=0, redis_password=None)
    assert profiling._resolve_redis_url(settings) == "redis://env-host:6379/0"

    monkeypatch.delenv("PROFILING_REDIS_URL", raising=False)
    monkeypatch.setenv("REDIS_URL", "redis://env2:6379/1")
    assert profiling._resolve_redis_url(settings) == "redis://env2:6379/1"

    monkeypatch.delenv("REDIS_URL", raising=False)
    settings.redis_host = "host2"
    settings.redis_port = 6380
    settings.redis_db = 3
    settings.redis_password = "secret"
    url = profiling._resolve_redis_url(settings)
    assert url == "redis://:secret@host2:6380/3"

    settings.redis_host = None
    assert profiling._resolve_redis_url(settings) is None


def test_inject_trace_headers_and_build_queue_payload() -> None:
    payload = {"headers": {"existing": "value"}}
    profiling._inject_trace_headers(payload)
    assert isinstance(payload["headers"], dict)

    request = profiling.EnqueueRequest(
        type="test",
        payload={"foo": "bar"},
        headers={},
        job_id=None,
        profiling_request_id=None,
        data_source_id=None,
        requested_by_user_id=None,
        correlation_id=None,
    )
    queue_payload = profiling._build_queue_payload(request, "corr-123")
    assert queue_payload["correlation_id"] == "corr-123"
    assert queue_payload["job_id"]
    assert queue_payload["profiling_request_id"]
    assert isinstance(queue_payload["headers"], dict)


@pytest.mark.anyio
async def test_enqueue_profiling_reports_no_queue(monkeypatch) -> None:
    class DummyRepo:
        def create_request(self, request):
            assert request.job_id

    class DummySettings:
        redis_host = None
        redis_port = 6379
        redis_db = 0
        redis_password = None

    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(settings=DummySettings())),
        headers={},
        method="POST",
        url=SimpleNamespace(path="/profiling/enqueue"),
        state=SimpleNamespace(),
    )

    monkeypatch.delenv("PROFILING_REDIS_URL", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setattr(profiling.api_metrics_store, "record", lambda *args, **kwargs: None)
    monkeypatch.setattr(profiling, "record_request_metric", lambda *args, **kwargs: None)

    with pytest.raises(HTTPException) as exc:
        await profiling.enqueue_profiling(
            request=request,
            request_body=profiling.EnqueueRequest(type="profiling"),
            profiling_repository=DummyRepo(),
        )

    assert exc.value.status_code == 503
    assert "Profiling queue is not configured" in str(exc.value.detail)


@pytest.mark.anyio
async def test_enqueue_profiling_service_error_still_surfaces_when_metrics_recording_fails(monkeypatch) -> None:
    class DummySettings:
        redis_host = "host"
        redis_port = 6379
        redis_db = 0
        redis_password = None

    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(settings=DummySettings())),
        headers={},
        method="POST",
        url=SimpleNamespace(path="/profiling/enqueue"),
        state=SimpleNamespace(),
    )

    async def fail_enqueue(**kwargs):
        raise profiling.ProfilingEnqueueServiceError("service failed", status_code=503)

    def fail_metrics(*args, **kwargs):
        raise RuntimeError("metrics down")

    monkeypatch.setattr(profiling, "enqueue_profiling_job", fail_enqueue)
    monkeypatch.setattr(profiling.api_metrics_store, "record", fail_metrics)
    monkeypatch.setattr(profiling, "record_request_metric", fail_metrics)

    with pytest.raises(HTTPException) as exc:
        await profiling.enqueue_profiling(
            request=request,
            request_body=profiling.EnqueueRequest(type="profiling"),
            profiling_repository=SimpleNamespace(),
        )

    assert exc.value.status_code == 503
    assert exc.value.detail == "service failed"


@pytest.mark.anyio
async def test_enqueue_profiling_success_still_returns_payload_when_metrics_recording_fails(monkeypatch) -> None:
    class DummySettings:
        redis_host = "host"
        redis_port = 6379
        redis_db = 0
        redis_password = None

    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(settings=DummySettings())),
        headers={},
        method="POST",
        url=SimpleNamespace(path="/profiling/enqueue"),
        state=SimpleNamespace(),
    )

    async def succeed_enqueue(**kwargs):
        return SimpleNamespace(enqueued=True, job_id="job-metrics")

    def fail_metrics(*args, **kwargs):
        raise RuntimeError("metrics down")

    monkeypatch.setattr(profiling, "enqueue_profiling_job", succeed_enqueue)
    monkeypatch.setattr(profiling.api_metrics_store, "record", fail_metrics)
    monkeypatch.setattr(profiling, "record_request_metric", fail_metrics)

    payload = await profiling.enqueue_profiling(
        request=request,
        request_body=profiling.EnqueueRequest(type="profiling"),
        profiling_repository=SimpleNamespace(),
    )

    assert payload == {"enqueued": True, "job_id": "job-metrics"}


@pytest.mark.anyio
async def test_report_profiling_request_status_started_paths() -> None:
    started_calls: list[tuple[str, str]] = []

    class Repo:
        def set_started(self, profiling_request_id: str, job_id: str) -> None:
            started_calls.append((profiling_request_id, job_id))

    response = await profiling.report_profiling_request_status(
        "req-started",
        profiling.ProfilingRequestReportRequest(new_status="started", job_id="job-1"),
        profiling_repository=Repo(),
    )

    assert response.ok is True
    assert started_calls == [("req-started", "job-1")]

    with pytest.raises(HTTPException) as missing_job:
        await profiling.report_profiling_request_status(
            "req-started",
            profiling.ProfilingRequestReportRequest(new_status="started"),
            profiling_repository=Repo(),
        )
    assert missing_job.value.status_code == 422
    assert missing_job.value.detail == "job_id is required when new_status is started"


@pytest.mark.anyio
async def test_report_profiling_request_status_started_failures() -> None:
    class MissingRepo:
        def set_started(self, profiling_request_id: str, job_id: str) -> None:
            raise KeyError(profiling_request_id)

    class BrokenRepo:
        def set_started(self, profiling_request_id: str, job_id: str) -> None:
            raise RuntimeError("db unavailable")

    with pytest.raises(HTTPException) as not_found:
        await profiling.report_profiling_request_status(
            "req-missing",
            profiling.ProfilingRequestReportRequest(new_status="started", job_id="job-2"),
            profiling_repository=MissingRepo(),
        )
    assert not_found.value.status_code == 404
    assert not_found.value.detail == "profiling_request 'req-missing' not found"

    with pytest.raises(HTTPException) as broken:
        await profiling.report_profiling_request_status(
            "req-broken",
            profiling.ProfilingRequestReportRequest(new_status="started", job_id="job-3"),
            profiling_repository=BrokenRepo(),
        )
    assert broken.value.status_code == 503
    assert broken.value.detail == "failed to update profiling request status"


@pytest.mark.anyio
async def test_report_profiling_request_status_completion_paths() -> None:
    completed_calls: list[tuple[str, bool, str | None]] = []

    class Repo:
        def set_completed(self, profiling_request_id: str, success: bool, error_message: str | None = None) -> None:
            completed_calls.append((profiling_request_id, success, error_message))

    response = await profiling.report_profiling_request_status(
        "req-completed",
        profiling.ProfilingRequestReportRequest(new_status="completed"),
        profiling_repository=Repo(),
    )
    assert response.ok is True

    failed_response = await profiling.report_profiling_request_status(
        "req-failed",
        profiling.ProfilingRequestReportRequest(new_status="failed", error_message="worker failed"),
        profiling_repository=Repo(),
    )
    assert failed_response.ok is True
    assert completed_calls == [
        ("req-completed", True, None),
        ("req-failed", False, "worker failed"),
    ]


@pytest.mark.anyio
async def test_report_profiling_request_status_completion_failures() -> None:
    class MissingRepo:
        def set_completed(self, profiling_request_id: str, success: bool, error_message: str | None = None) -> None:
            raise KeyError(profiling_request_id)

    class BrokenRepo:
        def set_completed(self, profiling_request_id: str, success: bool, error_message: str | None = None) -> None:
            raise RuntimeError("db unavailable")

    with pytest.raises(HTTPException) as not_found:
        await profiling.report_profiling_request_status(
            "req-missing",
            profiling.ProfilingRequestReportRequest(new_status="completed"),
            profiling_repository=MissingRepo(),
        )
    assert not_found.value.status_code == 404
    assert not_found.value.detail == "profiling_request 'req-missing' not found"

    with pytest.raises(HTTPException) as broken:
        await profiling.report_profiling_request_status(
            "req-broken",
            profiling.ProfilingRequestReportRequest(new_status="failed", error_message="worker failed"),
            profiling_repository=BrokenRepo(),
        )
    assert broken.value.status_code == 503
    assert broken.value.detail == "failed to update profiling request status"
