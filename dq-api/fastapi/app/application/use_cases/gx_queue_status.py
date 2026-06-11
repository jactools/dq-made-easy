from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from fastapi import HTTPException

from app.application.services import gx_queue_service
from app.domain.entities.gx_execution_run import build_gx_dispatch_payload_entity
from app.domain.interfaces import GxExecutionRunRepository


ResolveRedisUrl = Callable[[], str | None]
FetchQueueStatus = Callable[[str, str, int], Awaitable[tuple[int, list[str]]]]


@dataclass(slots=True)
class GetGxExecutionQueueStatusQuery:
    run_id: str
    scan_limit: int = 500


@dataclass(slots=True)
class GxExecutionQueueStatusResult:
    run_id: str
    business_key: str
    correlation_id: str
    queue_key: str
    queue_message_id: str
    queue_length: int
    inspected_depth: int
    found: bool
    index_from_head: int | None
    index_from_tail: int | None
async def get_gx_execution_queue_status(
    query: GetGxExecutionQueueStatusQuery,
    repository: GxExecutionRunRepository,
    resolve_redis_url: ResolveRedisUrl,
    fetch_queue_status: FetchQueueStatus,
) -> GxExecutionQueueStatusResult:
    run = await repository.get_run(query.run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"GX execution run '{query.run_id}' not found")

    handoff = build_gx_dispatch_payload_entity(run.handoffPayload)
    if handoff is None:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "handoff_payload_missing",
                "message": "GX execution run does not have a queue handoff payload",
                "run_id": query.run_id,
            },
        )

    queue_key = str(handoff.queueKey or "").strip()
    queue_message_id = str(handoff.queueMessageId or "").strip()
    correlation_id = str(handoff.correlationId or "").strip()
    if not correlation_id:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "correlation_id_missing",
                "message": "GX execution run is missing correlation_id",
                "run_id": query.run_id,
            },
        )
    if not queue_key or not queue_message_id:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "queue_metadata_missing",
                "message": "GX execution run is missing queue_key or queue_message_id",
                "run_id": query.run_id,
            },
        )

    redis_url = resolve_redis_url()
    if not redis_url:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "dispatch_queue_unavailable",
                "message": "GX dispatch queue is not configured",
                "queue_key": queue_key,
                "run_id": query.run_id,
            },
        )

    try:
        queue_length, scanned_payloads = await fetch_queue_status(redis_url, queue_key, query.scan_limit)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "queue_status_failed",
                "message": "Unable to query GX dispatch queue status",
                "queue_key": queue_key,
                "run_id": query.run_id,
                "exception": exc.__class__.__name__,
            },
        ) from exc

    index_from_head = gx_queue_service.find_queue_message_index(scanned_payloads, queue_message_id)
    found = index_from_head is not None
    index_from_tail = max(queue_length - 1 - int(index_from_head), 0) if found else None

    return GxExecutionQueueStatusResult(
        run_id=query.run_id,
        business_key=correlation_id,
        correlation_id=correlation_id,
        queue_key=queue_key,
        queue_message_id=queue_message_id,
        queue_length=int(queue_length),
        inspected_depth=len(scanned_payloads),
        found=bool(found),
        index_from_head=index_from_head,
        index_from_tail=index_from_tail,
    )