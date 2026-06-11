from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import Request
from fastapi.responses import Response, StreamingResponse

TERMINAL_STATUSES = {"completed", "failed", "cancelled", "succeeded"}

LoadStatusPayload = Callable[[], Awaitable[dict[str, Any]]]


def is_terminal_status(status: Any) -> bool:
    return str(status or "").strip().lower() in TERMINAL_STATUSES


def status_from_payload(payload: dict[str, Any]) -> str:
    request_payload = payload.get("request") if isinstance(payload.get("request"), dict) else {}
    return str(request_payload.get("status") or payload.get("status") or "").strip().lower()


def sse_frame(*, event_name: str, payload: dict[str, Any], event_id: str | None = None) -> str:
    lines: list[str] = []
    if event_id:
        lines.append(f"id: {event_id}")
    lines.append(f"event: {event_name}")
    lines.append(f"data: {json.dumps(payload, separators=(',', ':'), sort_keys=True)}")
    lines.append("")
    return "\n".join(lines) + "\n"


def terminal_snapshot_response(payload: dict[str, Any]) -> Response:
    return Response(
        content=sse_frame(event_name="snapshot", payload=payload),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


async def iter_status_snapshots(
    *,
    request: Request,
    initial_payload: dict[str, Any],
    load_payload: LoadStatusPayload,
    poll_interval_seconds: float,
):
    last_status = status_from_payload(initial_payload)
    yield sse_frame(event_name="snapshot", payload=initial_payload)
    if is_terminal_status(last_status):
        return

    while True:
        if await request.is_disconnected():
            return
        await asyncio.sleep(poll_interval_seconds)
        payload = await load_payload()
        status = status_from_payload(payload)
        if status != last_status or is_terminal_status(status):
            yield sse_frame(event_name="status_changed", payload=payload)
            last_status = status
        else:
            yield ": keepalive\n\n"
        if is_terminal_status(status):
            return


def status_event_stream_response(
    *,
    request: Request,
    initial_payload: dict[str, Any],
    load_payload: LoadStatusPayload,
    poll_interval_seconds: float,
) -> Response:
    if is_terminal_status(status_from_payload(initial_payload)):
        return terminal_snapshot_response(initial_payload)

    return StreamingResponse(
        iter_status_snapshots(
            request=request,
            initial_payload=initial_payload,
            load_payload=load_payload,
            poll_interval_seconds=poll_interval_seconds,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
