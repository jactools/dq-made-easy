from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException


@dataclass(slots=True)
class CreateQueuedTestDataRequestCommand:
    request_payload: dict[str, Any]


@dataclass(slots=True)
class GetQueuedTestDataRequestCommand:
    request_id: str


@dataclass(slots=True)
class CreateTestDataMaterializationCommand:
    version_id: str
    sample_count: int
    output_format: str
    output_uri: str | None = None
    selected_attribute_names: list[str] | None = None
    refresh: bool = False


@dataclass(slots=True)
class GetTestDataMaterializationCommand:
    request_id: str


@dataclass(slots=True)
class ReportTestDataMaterializationCompletionCommand:
    request_id: str
    payload: Any


ResolveRedisUrl = Callable[[], str | None]
ReadRecord = Callable[[str, str], Awaitable[Any | None]]
BuildViewPayload = Callable[[Any], Any]
EnqueueQueuedTestDataRequest = Callable[[dict[str, Any]], Awaitable[Any]]
EnqueueMaterializationRequest = Callable[..., Awaitable[Any]]
RegisterMaterializationCompletion = Callable[[str, Any], Awaitable[Any]]


async def create_queued_test_data_request(
    command: CreateQueuedTestDataRequestCommand,
    enqueue_queued_test_data_request: EnqueueQueuedTestDataRequest,
    build_view_payload: BuildViewPayload,
) -> Any:
    record = await enqueue_queued_test_data_request(command.request_payload)
    return build_view_payload(record)


async def get_queued_test_data_request(
    command: GetQueuedTestDataRequestCommand,
    resolve_redis_url: ResolveRedisUrl,
    read_record: ReadRecord,
    build_view_payload: BuildViewPayload,
) -> Any:
    redis_url = resolve_redis_url()
    if not redis_url:
        raise HTTPException(status_code=503, detail="Test data queue is not configured")
    record = await read_record(redis_url, command.request_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Test data request '{command.request_id}' not found")
    return build_view_payload(record)


async def create_test_data_materialization(
    command: CreateTestDataMaterializationCommand,
    enqueue_test_data_materialization_request: EnqueueMaterializationRequest,
    build_view_payload: BuildViewPayload,
) -> Any:
    version_id = str(command.version_id or "").strip()
    if not version_id:
        raise HTTPException(status_code=422, detail="data_object_version_id is required")

    record = await enqueue_test_data_materialization_request(
        version_id=version_id,
        sample_count=int(command.sample_count),
        output_format=str(command.output_format),
        output_uri=command.output_uri,
        selected_attribute_names=list(command.selected_attribute_names or []),
        refresh=bool(command.refresh),
    )
    return build_view_payload(record)


async def get_test_data_materialization(
    command: GetTestDataMaterializationCommand,
    resolve_redis_url: ResolveRedisUrl,
    read_record: ReadRecord,
    build_view_payload: BuildViewPayload,
) -> Any:
    redis_url = resolve_redis_url()
    if not redis_url:
        raise HTTPException(status_code=503, detail="Test data materialization queue is not configured")
    record = await read_record(redis_url, command.request_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Test data materialization '{command.request_id}' not found")
    return build_view_payload(record)


async def report_test_data_materialization_completion(
    command: ReportTestDataMaterializationCompletionCommand,
    register_completion: RegisterMaterializationCompletion,
) -> Any:
    return await register_completion(command.request_id, command.payload)