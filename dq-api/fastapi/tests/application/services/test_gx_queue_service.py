from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException

import app.application.services.gx_queue_service as queue_service


class _Logger:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def exception(self, message: str) -> None:
        self.messages.append(message)


@pytest.fixture
def logger() -> _Logger:
    return _Logger()


def test_resolve_redis_url_prefers_explicit_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GX_EXECUTION_REDIS_URL", "redis://gx-env:6379/0")
    monkeypatch.setenv("REDIS_URL", "redis://fallback:6379/0")

    url = queue_service.resolve_redis_url(
        SimpleNamespace(redis_host="redis", redis_port=6379, redis_db=3, redis_password=None)
    )

    assert url == "redis://gx-env:6379/0"


def test_resolve_redis_url_builds_from_settings_with_password_encoding(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GX_EXECUTION_REDIS_URL", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)

    url = queue_service.resolve_redis_url(
        SimpleNamespace(redis_host="redis.local", redis_port=6380, redis_db=2, redis_password="p@ss word")
    )

    assert url == "redis://:p%40ss%20word@redis.local:6380/2"


def test_resolve_redis_url_returns_none_when_host_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GX_EXECUTION_REDIS_URL", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)

    assert queue_service.resolve_redis_url(
        SimpleNamespace(redis_host="", redis_port=6379, redis_db=0, redis_password=None)
    ) is None


@pytest.mark.anyio
async def test_redis_lpush_uses_async_client_and_closes(logger: _Logger) -> None:
    client = SimpleNamespace(lpush=AsyncMock(), aclose=AsyncMock())
    async_module = SimpleNamespace(from_url=Mock(return_value=client))

    await queue_service.redis_lpush(
        "redis://queue",
        "queue:key",
        {"run_id": "run-1"},
        async_redis_module=async_module,
        sync_redis_module=None,
        logger=logger,
    )

    async_module.from_url.assert_called_once_with("redis://queue", decode_responses=True)
    client.lpush.assert_awaited_once()
    client.aclose.assert_awaited_once()
    assert logger.messages == []


@pytest.mark.anyio
async def test_redis_lpush_falls_back_to_sync_when_async_fails(
    monkeypatch: pytest.MonkeyPatch,
    logger: _Logger,
) -> None:
    async_client = SimpleNamespace(lpush=AsyncMock(side_effect=RuntimeError("async down")), aclose=AsyncMock())
    async_module = SimpleNamespace(from_url=Mock(return_value=async_client))

    sync_client = SimpleNamespace(lpush=Mock())
    sync_module = SimpleNamespace(from_url=Mock(return_value=sync_client))

    async def _direct_to_thread(fn, *args, **kwargs):
        del args, kwargs
        return fn()

    monkeypatch.setattr(queue_service.asyncio, "to_thread", _direct_to_thread)

    await queue_service.redis_lpush(
        "redis://queue",
        "queue:key",
        {"run_id": "run-2"},
        async_redis_module=async_module,
        sync_redis_module=sync_module,
        logger=logger,
    )

    assert sync_module.from_url.call_count == 1
    assert sync_client.lpush.call_count == 1
    assert any("async GX dispatch redis push failed" in message for message in logger.messages)


@pytest.mark.anyio
async def test_redis_lpush_raises_when_no_backends(logger: _Logger) -> None:
    with pytest.raises(RuntimeError, match="Unable to push GX dispatch payload to Redis"):
        await queue_service.redis_lpush(
            "redis://queue",
            "queue:key",
            {"run_id": "run-3"},
            async_redis_module=None,
            sync_redis_module=None,
            logger=logger,
        )


@pytest.mark.anyio
async def test_assert_worker_heartbeat_maps_redis_errors_to_http_exception(
    monkeypatch: pytest.MonkeyPatch,
    logger: _Logger,
) -> None:
    async def _raise(*args, **kwargs):
        del args, kwargs
        raise RuntimeError("redis unavailable")

    monkeypatch.setattr(queue_service, "redis_get", _raise)

    with pytest.raises(HTTPException) as error:
        await queue_service.assert_worker_heartbeat(
            "redis://queue",
            queue_key="queue:key",
            heartbeat_key="heartbeat:key",
            expected_ttl_seconds=120,
            unavailable_error="dispatch_worker_unavailable",
            unavailable_message="worker missing",
            status_failed_error="dispatch_worker_status_failed",
            status_failed_message="status check failed",
            async_redis_module=None,
            sync_redis_module=None,
            logger=logger,
        )

    assert error.value.status_code == 503
    assert error.value.detail["error"] == "dispatch_worker_status_failed"


@pytest.mark.anyio
async def test_assert_worker_heartbeat_requires_non_empty_payload(
    monkeypatch: pytest.MonkeyPatch,
    logger: _Logger,
) -> None:
    async def _empty(*args, **kwargs):
        del args, kwargs
        return ""

    monkeypatch.setattr(queue_service, "redis_get", _empty)

    with pytest.raises(HTTPException) as error:
        await queue_service.assert_worker_heartbeat(
            "redis://queue",
            queue_key="queue:key",
            heartbeat_key="heartbeat:key",
            expected_ttl_seconds=90,
            unavailable_error="dispatch_worker_unavailable",
            unavailable_message="worker heartbeat missing",
            status_failed_error="dispatch_worker_status_failed",
            status_failed_message="status check failed",
            async_redis_module=None,
            sync_redis_module=None,
            logger=logger,
        )

    assert error.value.status_code == 503
    assert error.value.detail["error"] == "dispatch_worker_unavailable"
    assert error.value.detail["expected_heartbeat_ttl_seconds"] == 90


def test_find_queue_message_index_uses_queue_message_id_and_run_id_fallback() -> None:
    payloads = [
        "not-json",
        '{"queue_message_id": "msg-1"}',
        '{"run_id": "run-2"}',
    ]

    assert queue_service.find_queue_message_index(payloads, "msg-1") == 1
    assert queue_service.find_queue_message_index(payloads, "run-2") == 2
    assert queue_service.find_queue_message_index(payloads, "unknown") is None
    assert queue_service.find_queue_message_index(payloads, "") is None