import json
from types import SimpleNamespace

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api.v1.endpoints import profiling_enqueue as profiling_enqueue_module
from app.application.services import profiling_enqueue_service
from app.core.dependencies import get_profiling_repository
from app.main import app


class FakeProfilingRepository:
    def __init__(self, should_fail_on_create: bool = False, active_request: SimpleNamespace | None = None) -> None:
        self.created_requests = []
        self.completed_calls = []
        self.should_fail_on_create = should_fail_on_create
        self.active_request = active_request

    def create_request(self, request):
        if self.should_fail_on_create:
            raise RuntimeError("persist failed")
        self.created_requests.append(request)
        return request

    def set_started(self, profiling_request_id: str, job_id: str) -> None:
        return None

    def set_completed(self, profiling_request_id: str, success: bool, error_message: str | None = None) -> None:
        self.completed_calls.append(
            {
                "profiling_request_id": profiling_request_id,
                "success": success,
                "error_message": error_message,
            }
        )

    def find_active_profiling_request(self, data_source_id: str):
        if self.active_request is None:
            return None
        if getattr(self.active_request, "data_source_id", None) != data_source_id:
            return None
        return self.active_request


class FakeAsyncRedisClient:
    def __init__(self, should_fail: bool = False) -> None:
        self.should_fail = should_fail
        self.lpush_calls = []

    async def lpush(self, key: str, payload: str) -> int:
        self.lpush_calls.append((key, payload))
        if self.should_fail:
            raise RuntimeError("redis down")
        return 1

    async def close(self) -> None:
        return None


def test_enqueue_pushes_snake_case_payload(monkeypatch):
    repository = FakeProfilingRepository()
    redis_client = FakeAsyncRedisClient()

    monkeypatch.setenv("PROFILING_REDIS_URL", "redis://profiling-test")
    monkeypatch.setenv("PROFILING_QUEUE_KEY", "profiling-test-queue")
    monkeypatch.setattr(
        profiling_enqueue_service,
        "aioredis",
        SimpleNamespace(from_url=lambda *args, **kwargs: redis_client),
    )
    monkeypatch.setattr(profiling_enqueue_service, "redis_sync", None)

    app.dependency_overrides[get_profiling_repository] = lambda: repository
    try:
        client = TestClient(app)
        response = client.post(
            "/api/rulebuilder/v1/profiling/enqueue",
            json={
                "job_id": "job-123",
                "profiling_request_id": "pr-123",
                "data_source_id": "ds-123",
                "requested_by_user_id": "user-123",
                "type": "etl",
                "payload": {
                    "sourceConfig": {
                        "inlineData": [],
                    }
                },
            },
            headers={"X-Correlation-ID": "corr-123"},
        )
    finally:
        app.dependency_overrides.pop(get_profiling_repository, None)

    assert response.status_code == 200
    assert response.json() == {"enqueued": True, "job_id": "job-123"}

    assert len(repository.created_requests) == 1
    created_request = repository.created_requests[0]
    assert created_request.profiling_request_id == "pr-123"
    assert created_request.data_source_id == "ds-123"
    assert created_request.requested_by_user_id == "user-123"
    assert created_request.job_id == "job-123"

    assert len(redis_client.lpush_calls) == 1
    queue_key, raw_payload = redis_client.lpush_calls[0]
    assert queue_key == "profiling-test-queue"

    queued_payload = json.loads(raw_payload)
    assert queued_payload["job_id"] == "job-123"
    assert queued_payload["profiling_request_id"] == "pr-123"
    assert queued_payload["correlation_id"] == "corr-123"
    assert queued_payload["data_source_id"] == "ds-123"
    assert queued_payload["requested_by_user_id"] == "user-123"
    assert queued_payload["type"] == "etl"
    assert queued_payload["payload"] == {"sourceConfig": {"inlineData": []}}
    assert isinstance(queued_payload["headers"], dict)
    assert "jobId" not in queued_payload
    assert "profilingRequestId" not in queued_payload
    assert "correlationId" not in queued_payload
    assert "dataSourceId" not in queued_payload
    assert "requestedByUserId" not in queued_payload


def test_enqueue_returns_503_when_redis_push_fails(monkeypatch):
    repository = FakeProfilingRepository()
    redis_client = FakeAsyncRedisClient(should_fail=True)

    monkeypatch.setenv("PROFILING_REDIS_URL", "redis://profiling-test")
    monkeypatch.setenv("PROFILING_QUEUE_KEY", "profiling-test-queue")
    monkeypatch.setattr(
        profiling_enqueue_service,
        "aioredis",
        SimpleNamespace(from_url=lambda *args, **kwargs: redis_client),
    )
    monkeypatch.setattr(profiling_enqueue_service, "redis_sync", None)

    app.dependency_overrides[get_profiling_repository] = lambda: repository
    try:
        client = TestClient(app)
        response = client.post(
            "/api/rulebuilder/v1/profiling/enqueue",
            json={
                "job_id": "job-503",
                "profiling_request_id": "pr-503",
                "type": "etl",
                "payload": {},
            },
        )
    finally:
        app.dependency_overrides.pop(get_profiling_repository, None)

    assert response.status_code == 503
    assert response.json()["detail"] == "Failed to enqueue job to Redis"
    assert repository.completed_calls == [
        {
            "profiling_request_id": "pr-503",
            "success": False,
            "error_message": "Failed to enqueue job to Redis",
        }
    ]


def test_enqueue_returns_503_when_persistence_fails(monkeypatch):
    repository = FakeProfilingRepository(should_fail_on_create=True)
    redis_client = FakeAsyncRedisClient()

    monkeypatch.setenv("PROFILING_REDIS_URL", "redis://profiling-test")
    monkeypatch.setenv("PROFILING_QUEUE_KEY", "profiling-test-queue")
    monkeypatch.setattr(
        profiling_enqueue_service,
        "aioredis",
        SimpleNamespace(from_url=lambda *args, **kwargs: redis_client),
    )
    monkeypatch.setattr(profiling_enqueue_service, "redis_sync", None)

    app.dependency_overrides[get_profiling_repository] = lambda: repository
    try:
        client = TestClient(app)
        response = client.post(
            "/api/rulebuilder/v1/profiling/enqueue",
            json={
                "job_id": "job-persist-fail",
                "profiling_request_id": "pr-persist-fail",
                "data_source_id": "ds-persist-fail",
                "requested_by_user_id": "user-persist-fail",
                "type": "etl",
                "payload": {},
            },
        )
    finally:
        app.dependency_overrides.pop(get_profiling_repository, None)

    assert response.status_code == 503
    assert response.json()["detail"] == "Failed to persist profiling request"
    assert redis_client.lpush_calls == []
    assert repository.completed_calls == []


def test_enqueue_returns_409_when_active_request_exists(monkeypatch):
    repository = FakeProfilingRepository(active_request=SimpleNamespace(id="pr-active", data_source_id="ds-123", status="pending"))
    redis_client = FakeAsyncRedisClient()

    monkeypatch.setenv("PROFILING_REDIS_URL", "redis://profiling-test")
    monkeypatch.setenv("PROFILING_QUEUE_KEY", "profiling-test-queue")
    monkeypatch.setattr(
        profiling_enqueue_service,
        "aioredis",
        SimpleNamespace(from_url=lambda *args, **kwargs: redis_client),
    )
    monkeypatch.setattr(profiling_enqueue_service, "redis_sync", None)

    app.dependency_overrides[get_profiling_repository] = lambda: repository
    try:
        client = TestClient(app)
        response = client.post(
            "/api/rulebuilder/v1/profiling/enqueue",
            json={
                "job_id": "job-active",
                "profiling_request_id": "pr-active",
                "data_source_id": "ds-123",
                "requested_by_user_id": "user-active",
                "type": "etl",
                "payload": {},
            },
        )
    finally:
        app.dependency_overrides.pop(get_profiling_repository, None)

    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "profiling_request_already_active"
    assert response.json()["detail"]["data_source_id"] == "ds-123"
    assert repository.created_requests == []
    assert redis_client.lpush_calls == []
