import json
import urllib.request

import pytest
from prometheus_client import generate_latest

from profiling_metrics import REGISTRY, record_failure, record_redis_failure, record_redis_request, record_request
from queue_worker import ProfilingRequestStatusReporter
from queue_worker import _handle_job
from queue_worker import _next_queue_item
from redis.exceptions import TimeoutError as RedisTimeoutError


class FakeStatusStore:
    def __init__(self) -> None:
        self.events = []

    def set_started(self, profiling_request_id: str, job_id: str, *, correlation_id: str | None = None) -> None:
        self.events.append(("started", profiling_request_id, job_id, correlation_id))

    def set_completed(
        self,
        profiling_request_id: str,
        success: bool,
        error_message: str | None = None,
        *,
        correlation_id: str | None = None,
    ) -> None:
        self.events.append(("completed", profiling_request_id, success, error_message, correlation_id))


@pytest.fixture
def status_store() -> FakeStatusStore:
    return FakeStatusStore()


def test_handle_job_marks_started_and_completed(monkeypatch, status_store):

    monkeypatch.setattr(
        "queue_worker.handle_etl_job",
        lambda data: {"artifactUri": "file:///tmp/artifact.json"},
    )

    _handle_job(
        {
            "profiling_request_id": "pr-1",
            "job_id": "job-1",
            "correlation_id": "corr-1",
            "payload": {},
        },
        status_store,
    )

    assert status_store.events == [
        ("started", "pr-1", "job-1", "corr-1"),
        ("completed", "pr-1", True, None, "corr-1"),
    ]


def test_handle_job_marks_failed_on_error(monkeypatch, status_store):

    def _raise(_data):
        raise RuntimeError("etl exploded")

    monkeypatch.setattr("queue_worker.handle_etl_job", _raise)

    try:
        _handle_job(
            {
                "profiling_request_id": "pr-2",
                "job_id": "job-2",
                "correlation_id": "corr-2",
                "payload": {},
            },
            status_store,
        )
        raise AssertionError("expected RuntimeError")
    except RuntimeError as exc:
        assert str(exc) == "etl exploded"

    assert status_store.events == [
        ("started", "pr-2", "job-2", "corr-2"),
        ("completed", "pr-2", False, "etl exploded", "corr-2"),
    ]


class FakeRedis:
    def __init__(self) -> None:
        self.values = {}

    def get(self, key: str):
        return self.values.get(key)

    def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.values[key] = value


def test_next_queue_item_returns_none_on_timeout() -> None:
    class _TimeoutRedis:
        def brpop(self, *args, **kwargs):
            raise RedisTimeoutError("timed out")

    assert _next_queue_item(_TimeoutRedis(), "queue", timeout=1) is None


def test_handle_job_dispatches_test_data_generation() -> None:
    redis_client = FakeRedis()
    redis_client.set(
        "test-data-request:tdr-1",
        json.dumps(
            {
                "request_id": "tdr-1",
                "job_id": "tdj-1",
                "status": "pending",
                "target_type": "mock_data_source",
                "target_id": "mock-preview-source",
                "sample_count": 2,
                "requested_at": "2026-04-05T12:00:00Z",
                "started_at": None,
                "completed_at": None,
                "error_message": None,
                "correlation_id": "corr-1",
                "result": None,
            }
        ),
    )

    result = _handle_job(
        {
            "type": "test_data_generation",
            "job_id": "tdj-1",
            "test_data_request_id": "tdr-1",
            "payload": {
                "target_type": "mock_data_source",
                "target_id": "mock-preview-source",
                "sample_count": 2,
                "attributes": [
                    {"name": "column_id", "type": "integer", "nullable": False},
                    {"name": "column_x", "type": "text", "nullable": True},
                ],
            },
        },
        None,
        redis_client,
    )

    assert result["sample_count"] == 2
    assert len(result["samples"]) == 2
    stored = json.loads(redis_client.get("test-data-request:tdr-1"))
    assert stored["status"] == "completed"
    assert stored["result"]["sample_count"] == 2


def test_handle_job_records_request_and_failure_metrics(monkeypatch, status_store):
    def _raise(_data):
        raise RuntimeError("etl exploded")

    monkeypatch.setattr("queue_worker.handle_etl_job", _raise)

    with pytest.raises(RuntimeError, match="etl exploded"):
        _handle_job(
            {
                "type": "profiling",
                "profiling_request_id": "pr-4",
                "job_id": "job-4",
                "payload": {},
            },
            status_store,
        )

    metrics_text = generate_latest(REGISTRY).decode("utf-8")
    assert 'dq_profiling_request_count_total{request_type="profiling",status="failure"}' in metrics_text
    assert 'dq_profiling_failure_count_total{failure_type="runtime_error",request_type="profiling"}' in metrics_text


def test_metric_helpers_record_redis_and_request_metrics() -> None:
    record_request("test_data_generation", "success")
    record_failure("test_data_generation", "ValueError")
    record_redis_request("get", "success")
    record_redis_failure("set", "ConnectionError")

    metrics_text = generate_latest(REGISTRY).decode("utf-8")
    assert 'dq_profiling_request_count_total{request_type="test_data_generation",status="success"}' in metrics_text
    assert 'dq_profiling_failure_count_total{failure_type="value_error",request_type="test_data_generation"}' in metrics_text
    assert 'dq_profiling_redis_request_count_total{operation_type="get",status="success"}' in metrics_text
    assert 'dq_profiling_redis_failure_count_total{failure_type="connection_error",operation_type="set"}' in metrics_text


def test_status_reporter_uses_gateway_prefix(monkeypatch) -> None:
    captured_urls: list[str] = []

    class _Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def _fake_urlopen(request: urllib.request.Request, timeout: int):
        captured_urls.append(request.full_url)
        return _Response()

    monkeypatch.setattr("queue_worker.urllib.request.urlopen", _fake_urlopen)

    reporter = ProfilingRequestStatusReporter("http://api:4010")
    reporter.set_started("pr-123", "job-123", correlation_id="corr-123")
    reporter.set_completed("pr-123", True, correlation_id="corr-123")

    assert captured_urls == [
        "http://api:4010/rulebuilder/v1/profiling/requests/pr-123/report",
        "http://api:4010/rulebuilder/v1/profiling/requests/pr-123/report",
    ]