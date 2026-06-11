from __future__ import annotations

import asyncio
import json
import os
from typing import Any
from urllib.parse import quote

from fastapi import HTTPException

from app.core.config import Settings
from app.domain.entities.gx_execution_run import build_gx_dispatch_payload_entity

try:
    import redis.asyncio as aioredis
except Exception:
    aioredis = None

try:
    import redis as redis_sync
except Exception:
    redis_sync = None


def resolve_redis_url(settings: Settings) -> str | None:
    explicit_url = os.environ.get("GX_EXECUTION_REDIS_URL") or os.environ.get("REDIS_URL")
    if explicit_url:
        return explicit_url

    redis_host = str(settings.redis_host or "").strip()
    if not redis_host:
        return None

    redis_port = int(settings.redis_port)
    redis_db = int(settings.redis_db)
    redis_password = settings.redis_password
    if redis_password:
        return f"redis://:{quote(redis_password, safe='')}@{redis_host}:{redis_port}/{redis_db}"
    return f"redis://{redis_host}:{redis_port}/{redis_db}"


async def redis_get(
    redis_url: str,
    key: str,
    *,
    async_redis_module,
    sync_redis_module,
    logger,
) -> str | None:
    if async_redis_module is not None:
        try:
            client = async_redis_module.from_url(redis_url, decode_responses=True)
            try:
                return await client.get(key)
            finally:
                close_method = getattr(client, "aclose", None) or getattr(client, "close", None)
                if close_method is not None:
                    result = close_method()
                    if asyncio.iscoroutine(result):
                        await result
        except Exception:
            logger.exception("async GX dispatch redis get failed")

    if sync_redis_module is not None:
        try:
            def _get_sync() -> str | None:
                client = sync_redis_module.from_url(redis_url, decode_responses=True)
                return client.get(key)

            return await asyncio.to_thread(_get_sync)
        except Exception:
            logger.exception("sync GX dispatch redis get failed")

    raise RuntimeError("Unable to read GX dispatch state from Redis")


async def redis_lpush(
    redis_url: str,
    queue_key: str,
    payload: dict[str, Any],
    *,
    async_redis_module,
    sync_redis_module,
    logger,
) -> None:
    serialized = json.dumps(payload)
    if async_redis_module is not None:
        try:
            client = async_redis_module.from_url(redis_url, decode_responses=True)
            try:
                await client.lpush(queue_key, serialized)
            finally:
                close_method = getattr(client, "aclose", None) or getattr(client, "close", None)
                if close_method is not None:
                    result = close_method()
                    if asyncio.iscoroutine(result):
                        await result
            return
        except Exception:
            logger.exception("async GX dispatch redis push failed")

    if sync_redis_module is not None:
        try:
            def _lpush_sync() -> None:
                client = sync_redis_module.from_url(redis_url, decode_responses=True)
                client.lpush(queue_key, serialized)

            await asyncio.to_thread(_lpush_sync)
            return
        except Exception:
            logger.exception("sync GX dispatch redis push failed")

    raise RuntimeError("Unable to push GX dispatch payload to Redis")


async def redis_queue_status(
    redis_url: str,
    queue_key: str,
    scan_limit: int,
    *,
    async_redis_module,
    sync_redis_module,
    logger,
) -> tuple[int, list[str]]:
    if scan_limit <= 0:
        scan_limit = 1

    if async_redis_module is not None:
        try:
            client = async_redis_module.from_url(redis_url, decode_responses=True)
            try:
                length = int(await client.llen(queue_key))
                if length <= 0:
                    return 0, []
                depth = min(length, int(scan_limit))
                payloads = await client.lrange(queue_key, 0, depth - 1)
                return length, list(payloads or [])
            finally:
                close_method = getattr(client, "aclose", None) or getattr(client, "close", None)
                if close_method is not None:
                    result = close_method()
                    if asyncio.iscoroutine(result):
                        await result
        except Exception:
            logger.exception("async GX dispatch redis queue status failed")

    if sync_redis_module is not None:
        try:
            def _status_sync() -> tuple[int, list[str]]:
                client = sync_redis_module.from_url(redis_url, decode_responses=True)
                length = int(client.llen(queue_key))
                if length <= 0:
                    return 0, []
                depth = min(length, int(scan_limit))
                payloads = client.lrange(queue_key, 0, depth - 1)
                return length, list(payloads or [])

            return await asyncio.to_thread(_status_sync)
        except Exception:
            logger.exception("sync GX dispatch redis queue status failed")

    raise RuntimeError("Unable to query GX dispatch payload queue status from Redis")


async def assert_worker_heartbeat(
    redis_url: str,
    *,
    queue_key: str,
    heartbeat_key: str,
    expected_ttl_seconds: int,
    unavailable_error: str,
    unavailable_message: str,
    status_failed_error: str,
    status_failed_message: str,
    async_redis_module,
    sync_redis_module,
    logger,
) -> None:
    try:
        heartbeat_payload = await redis_get(
            redis_url,
            heartbeat_key,
            async_redis_module=async_redis_module,
            sync_redis_module=sync_redis_module,
            logger=logger,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "error": status_failed_error,
                "message": status_failed_message,
                "queue_key": queue_key,
                "heartbeat_key": heartbeat_key,
                "exception": exc.__class__.__name__,
            },
        ) from exc

    if heartbeat_payload:
        return

    raise HTTPException(
        status_code=503,
        detail={
            "error": unavailable_error,
            "message": unavailable_message,
            "queue_key": queue_key,
            "heartbeat_key": heartbeat_key,
            "expected_heartbeat_ttl_seconds": expected_ttl_seconds,
        },
    )


def find_queue_message_index(payloads: list[str], queue_message_id: str) -> int | None:
    target = str(queue_message_id or "").strip()
    if not target:
        return None

    for idx, raw in enumerate(payloads):
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
        except Exception:
            continue
        queue_payload = build_gx_dispatch_payload_entity(parsed)
        if queue_payload is None:
            continue
        candidate = str(queue_payload.queueMessageId or queue_payload.runId or "").strip()
        if candidate and candidate == target:
            return idx

    return None