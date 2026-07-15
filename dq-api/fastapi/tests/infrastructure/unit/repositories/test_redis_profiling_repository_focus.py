from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.domain.entities.profiling_request import ProfilingRequest
from app.infrastructure.repositories.redis_profiling_repository import RedisProfilingRepository


class _FakeRedisClient:
    def __init__(self) -> None:
        self.hashes: dict[str, dict[str, str]] = {}
        self.hset_calls: list[tuple[str, dict[str, str]]] = []

    def hset(self, key: str, mapping: dict[str, str]) -> None:
        self.hset_calls.append((key, dict(mapping)))
        self.hashes.setdefault(key, {}).update(mapping)

    def exists(self, key: str) -> bool:
        return key in self.hashes


def _install_fake_redis(monkeypatch: pytest.MonkeyPatch, client: _FakeRedisClient) -> None:
    monkeypatch.setattr("app.infrastructure.repositories.redis_profiling_repository.redis.Redis", lambda **kwargs: client)


def test_repository_initializes_tls_enabled_redis_client(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    client = _FakeRedisClient()

    def _fake_redis(**kwargs):
        captured.update(kwargs)
        return client

    monkeypatch.setattr("app.infrastructure.repositories.redis_profiling_repository.redis.Redis", _fake_redis)

    repository = RedisProfilingRepository(redis_host="example")

    assert repository._client is client
    assert captured["ssl"] is True
    assert captured["ssl_cert_reqs"] == "required"
    assert captured["ssl_check_hostname"] is True
    assert str(captured["ssl_ca_certs"]).endswith("internal-ca-bundle.pem")


def _request(*, status: str | None = None, job_id: str | None = None) -> ProfilingRequest:
    return ProfilingRequest(
        id=None,
        profiling_request_id="pr-1",
        data_source_id="ds-1",
        requested_by_user_id="user-1",
        requested_at=datetime(2024, 5, 1, 10, 0, tzinfo=timezone.utc),
        started_at=None,
        completed_at=None,
        status=status or "pending",
        error_message=None,
        job_id=job_id,
    )


def test_create_request_writes_expected_hash_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _FakeRedisClient()
    _install_fake_redis(monkeypatch, client)

    repository = RedisProfilingRepository(redis_host="example")
    request = _request(status=None, job_id="job-1")

    created = repository.create_request(request)

    assert created is request
    assert client.hset_calls == [
        (
            "profiling:pr-1",
            {
                "profiling_request_id": "pr-1",
                "data_source_id": "ds-1",
                "requested_by_user_id": "user-1",
                "requested_at": "2024-05-01T10:00:00+00:00",
                "started_at": "",
                "completed_at": "",
                "status": "pending",
                "error_message": "",
                "job_id": "job-1",
            },
        )
    ]


def test_set_started_updates_existing_hash(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _FakeRedisClient()
    client.hashes["profiling:pr-1"] = {"profiling_request_id": "pr-1"}
    _install_fake_redis(monkeypatch, client)

    repository = RedisProfilingRepository(redis_host="example")
    repository.set_started("pr-1", "job-2")

    assert client.hashes["profiling:pr-1"]["job_id"] == "job-2"
    assert client.hashes["profiling:pr-1"]["status"] == "started"
    assert client.hashes["profiling:pr-1"]["started_at"]


def test_set_started_raises_for_missing_hash(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _FakeRedisClient()
    _install_fake_redis(monkeypatch, client)

    repository = RedisProfilingRepository(redis_host="example")

    with pytest.raises(KeyError, match="profiling_request pr-1 not found"):
        repository.set_started("pr-1", "job-2")


def test_set_completed_updates_existing_hash_with_error_message(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _FakeRedisClient()
    client.hashes["profiling:pr-1"] = {"profiling_request_id": "pr-1"}
    _install_fake_redis(monkeypatch, client)

    repository = RedisProfilingRepository(redis_host="example")
    repository.set_completed("pr-1", success=False, error_message="boom")

    assert client.hashes["profiling:pr-1"]["status"] == "failed"
    assert client.hashes["profiling:pr-1"]["error_message"] == "boom"
    assert client.hashes["profiling:pr-1"]["completed_at"]


def test_set_completed_updates_existing_hash_without_error_message(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _FakeRedisClient()
    client.hashes["profiling:pr-1"] = {"profiling_request_id": "pr-1"}
    _install_fake_redis(monkeypatch, client)

    repository = RedisProfilingRepository(redis_host="example")
    repository.set_completed("pr-1", success=True)

    assert client.hashes["profiling:pr-1"]["status"] == "completed"
    assert "error_message" not in client.hashes["profiling:pr-1"]
    assert client.hashes["profiling:pr-1"]["completed_at"]


def test_set_completed_raises_for_missing_hash(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _FakeRedisClient()
    _install_fake_redis(monkeypatch, client)

    repository = RedisProfilingRepository(redis_host="example")

    with pytest.raises(KeyError, match="profiling_request pr-1 not found"):
        repository.set_completed("pr-1", success=True)
