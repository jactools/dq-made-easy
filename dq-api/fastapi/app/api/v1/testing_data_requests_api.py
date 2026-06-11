from __future__ import annotations

import os
from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import Response

from app.api.v1.async_status_events import status_event_stream_response
from app.core.runtime_queues import resolve_profiling_queue_key as _resolve_runtime_profiling_queue_key
from app.api.v1 import test_data_materialization_api as _test_data_materialization_api
from app.api.v1 import test_data_materialization_support as _materialization_support
from app.api.v1.schemas.test_data_materialization_view import ReportTestDataMaterializationCompletionRequest
from app.api.v1.schemas.test_data_materialization_view import TestDataMaterializationRequestView
from app.api.v1.schemas.test_data_queue_view import CreateQueuedTestDataRequest
from app.api.v1.schemas.test_data_queue_view import QueuedTestDataRequestView
from app.application.services import test_data_materialization_service as _materialization_service
from app.application.services.test_data_queue_service import enqueue_queued_test_data_request as _service_enqueue_queued_test_data_request
from app.application.services.test_data_queue_service import read_test_data_request_record as _service_read_test_data_request_record
from app.application.services.test_data_queue_service import wait_for_test_data_request_result as _service_wait_for_test_data_request_result
from app.application.services.test_data_queue_service import write_test_data_request_record as _service_write_test_data_request_record
from app.application.use_cases.testing_data_requests import create_queued_test_data_request as create_queued_test_data_request_use_case
from app.application.use_cases.testing_data_requests import CreateQueuedTestDataRequestCommand
from app.application.use_cases.testing_data_requests import create_test_data_materialization as create_test_data_materialization_use_case
from app.application.use_cases.testing_data_requests import CreateTestDataMaterializationCommand
from app.application.use_cases.testing_data_requests import get_queued_test_data_request as get_queued_test_data_request_use_case
from app.application.use_cases.testing_data_requests import GetQueuedTestDataRequestCommand
from app.application.use_cases.testing_data_requests import get_test_data_materialization as get_test_data_materialization_use_case
from app.application.use_cases.testing_data_requests import GetTestDataMaterializationCommand
from app.application.use_cases.testing_data_requests import report_test_data_materialization_completion as report_test_data_materialization_completion_use_case
from app.application.use_cases.testing_data_requests import ReportTestDataMaterializationCompletionCommand
from app.domain.interfaces.v1.data_catalog_repository import DataCatalogRepository
from app.api.v1 import test_data_queue_support as _test_data_queue_support


_TEST_DATA_REQUEST_TTL_SECONDS = 3600
_TEST_DATA_REQUEST_POLL_INTERVAL_SECONDS = 0.5
_TEST_DATA_REQUEST_WAIT_TIMEOUT_SECONDS = 300.0
_TEST_DATA_EVENT_POLL_INTERVAL_SECONDS = 1.0
_MATERIALIZATION_EVENT_POLL_INTERVAL_SECONDS = 2.0


def test_data_request_events_url(request_id: str) -> str:
    return f"/rulebuilder/v1/test-data/requests/{request_id}/events"


def test_data_materialization_events_url(request_id: str) -> str:
    return f"/rulebuilder/v1/test-data/materializations/{request_id}/events"


def _resolve_test_data_queue_key() -> str:
    queue_key = _resolve_runtime_profiling_queue_key()
    if queue_key:
        return queue_key
    raise HTTPException(
        status_code=503,
        detail={
            "error": "test_data_queue_not_configured",
            "message": "Test data queue is not configured",
            "env_vars": ["PROFILING_QUEUE_KEY", "DQ_PROFILING_QUEUE_KEY"],
        },
    )


async def _enqueue_queued_test_data_request(
    *,
    request: Request,
    request_payload: dict[str, Any],
) -> Any:
    redis_url = resolve_test_data_redis_url()
    if not redis_url:
        raise HTTPException(status_code=503, detail="Test data queue is not configured")

    record = await _service_enqueue_queued_test_data_request(
        request_headers=request.headers,
        request_payload=request_payload,
        redis_url=redis_url,
        queue_key=_resolve_test_data_queue_key(),
        ttl_seconds=_TEST_DATA_REQUEST_TTL_SECONDS,
        current_timestamp=_materialization_support.current_timestamp(),
        find_active_request=_test_data_queue_support.find_active_queued_test_data_request,
        write_record=lambda url, record, ttl: _service_write_test_data_request_record(
            url,
            record,
            ttl,
            _materialization_support.redis_set_json,
        ),
        push_queue=_materialization_support.redis_lpush,
    )
    return _test_data_queue_support.require_queued_test_data_request_record(record)


async def wait_for_test_data_request_result(request_id: str) -> Any:
    redis_url = resolve_test_data_redis_url()
    if not redis_url:
        raise HTTPException(status_code=503, detail="Test data queue is not configured")

    record = await _service_wait_for_test_data_request_result(
        request_id=request_id,
        redis_url=redis_url,
        read_record=lambda url, rid: _service_read_test_data_request_record(
            url,
            rid,
            _materialization_support.redis_get_json,
        ),
        poll_interval_seconds=_TEST_DATA_REQUEST_POLL_INTERVAL_SECONDS,
        wait_timeout_seconds=_TEST_DATA_REQUEST_WAIT_TIMEOUT_SECONDS,
    )
    return _test_data_queue_support.require_queued_test_data_request_record(record)


def build_create_test_data_request_command(
    payload: CreateQueuedTestDataRequest,
    catalog_repository: DataCatalogRepository,
) -> CreateQueuedTestDataRequestCommand:
    return CreateQueuedTestDataRequestCommand(
        request_payload=_test_data_queue_support.resolve_queued_test_data_request_payload(payload, catalog_repository)
    )


def build_get_test_data_request_command(request_id: str) -> GetQueuedTestDataRequestCommand:
    return GetQueuedTestDataRequestCommand(request_id=request_id)


def build_create_test_data_materialization_command(payload: Any) -> CreateTestDataMaterializationCommand:
    return CreateTestDataMaterializationCommand(
        version_id=str(payload.data_object_version_id or ""),
        sample_count=int(payload.sample_count),
        output_format=str(payload.output_format),
        output_uri=payload.output_uri,
        selected_attribute_names=list(payload.selected_attribute_names or []),
        refresh=bool(payload.refresh),
    )


def build_get_test_data_materialization_command(request_id: str) -> GetTestDataMaterializationCommand:
    return GetTestDataMaterializationCommand(request_id=request_id)


def build_report_test_data_materialization_completion_command(
    request_id: str,
    payload: ReportTestDataMaterializationCompletionRequest,
) -> ReportTestDataMaterializationCompletionCommand:
    return ReportTestDataMaterializationCompletionCommand(request_id=request_id, payload=payload)


def bind_queued_test_data_request_enqueuer(request: Request):
    async def _enqueue(request_payload: dict[str, Any]) -> Any:
        return await _enqueue_queued_test_data_request(request=request, request_payload=request_payload)

    return _enqueue


def bind_test_data_materialization_request_enqueuer(
    request: Request,
    catalog_repository: DataCatalogRepository,
):
    async def _enqueue(**kwargs: Any) -> Any:
        return await _test_data_materialization_api._enqueue_test_data_materialization_request(
            request_headers=request.headers,
            catalog_repository=catalog_repository,
            **kwargs,
        )

    return _enqueue


def bind_materialized_delivery_completion_registrar(catalog_repository: DataCatalogRepository):
    async def _register(
        request_id: str,
        payload: ReportTestDataMaterializationCompletionRequest,
    ) -> Any:
        return await _test_data_materialization_api._register_materialized_delivery_completion(
            request_id=request_id,
            payload=payload,
            catalog_repository=catalog_repository,
        )

    return _register


def queued_test_data_request_view_payload(payload: Any) -> Any:
    view_payload = _test_data_queue_support.queued_test_data_request_record_payload(payload)
    view_payload["events_url"] = test_data_request_events_url(str(view_payload["request_id"]))
    return QueuedTestDataRequestView.model_validate(
        view_payload
    )


def test_data_materialization_request_view_payload(payload: Any) -> Any:
    view_payload = _materialization_support.test_data_materialization_record_payload(payload)
    view_payload["events_url"] = test_data_materialization_events_url(str(view_payload["request_id"]))
    return TestDataMaterializationRequestView.model_validate(
        view_payload
    )


def _queued_test_data_event_payload(payload: Any) -> dict[str, Any]:
    view_payload = queued_test_data_request_view_payload(payload).model_dump(by_alias=True, mode="json")
    request_id = str(_test_data_queue_support.queued_test_data_request_field(payload, "request_id") or "").strip()
    return {
        "request_id": request_id,
        "status": view_payload.get("status"),
        "request": view_payload,
    }


def _test_data_materialization_event_payload(payload: Any) -> dict[str, Any]:
    view_payload = test_data_materialization_request_view_payload(payload).model_dump(by_alias=True, mode="json")
    return {
        "request_id": str(view_payload.get("request_id") or "").strip(),
        "status": view_payload.get("status"),
        "request": view_payload,
    }


def resolve_test_data_redis_url() -> str | None:
    return _materialization_support.resolve_test_data_redis_url()


async def read_test_data_request_record(redis_url: str, request_id: str) -> Any:
    payload = await _service_read_test_data_request_record(
        redis_url,
        request_id,
        _materialization_support.redis_get_json,
    )
    return _test_data_queue_support.require_queued_test_data_request_record(payload) if payload is not None else None


async def read_test_data_materialization_record(redis_url: str, request_id: str) -> Any:
    return await _materialization_service.read_test_data_materialization_record(
        redis_url,
        request_id,
        _materialization_support.test_data_materialization_request_key,
        _materialization_support.require_test_data_materialization_record,
        _materialization_support.redis_get_json,
    )


async def create_test_data_request(
    request: Request,
    payload: CreateQueuedTestDataRequest,
    catalog_repository: DataCatalogRepository,
) -> Any:
    return await create_queued_test_data_request_use_case(
        command=build_create_test_data_request_command(payload, catalog_repository),
        enqueue_queued_test_data_request=bind_queued_test_data_request_enqueuer(request),
        build_view_payload=queued_test_data_request_view_payload,
    )


async def get_test_data_request_view(request_id: str) -> Any:
    return await get_queued_test_data_request_use_case(
        command=build_get_test_data_request_command(request_id),
        resolve_redis_url=resolve_test_data_redis_url,
        read_record=read_test_data_request_record,
        build_view_payload=queued_test_data_request_view_payload,
    )


async def _load_test_data_request_event_payload(request_id: str) -> dict[str, Any]:
    redis_url = resolve_test_data_redis_url()
    if not redis_url:
        raise HTTPException(status_code=503, detail="Test data queue is not configured")
    record = await read_test_data_request_record(redis_url, request_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Test data request '{request_id}' not found")
    return _queued_test_data_event_payload(record)


async def stream_test_data_request_events(request_id: str, request: Request) -> Response:
    initial_payload = await _load_test_data_request_event_payload(request_id)

    async def _load_payload() -> dict[str, Any]:
        return await _load_test_data_request_event_payload(request_id)

    return status_event_stream_response(
        request=request,
        initial_payload=initial_payload,
        load_payload=_load_payload,
        poll_interval_seconds=_TEST_DATA_EVENT_POLL_INTERVAL_SECONDS,
    )


async def create_test_data_materialization(
    request: Request,
    payload: Any,
    catalog_repository: DataCatalogRepository,
) -> Any:
    return await create_test_data_materialization_use_case(
        command=build_create_test_data_materialization_command(payload),
        enqueue_test_data_materialization_request=bind_test_data_materialization_request_enqueuer(
            request,
            catalog_repository,
        ),
        build_view_payload=test_data_materialization_request_view_payload,
    )


async def get_test_data_materialization_view(request_id: str) -> Any:
    return await get_test_data_materialization_use_case(
        command=build_get_test_data_materialization_command(request_id),
        resolve_redis_url=resolve_test_data_redis_url,
        read_record=read_test_data_materialization_record,
        build_view_payload=test_data_materialization_request_view_payload,
    )


async def _load_test_data_materialization_event_payload(request_id: str) -> dict[str, Any]:
    redis_url = resolve_test_data_redis_url()
    if not redis_url:
        raise HTTPException(status_code=503, detail="Test data materialization queue is not configured")
    record = await read_test_data_materialization_record(redis_url, request_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Test data materialization '{request_id}' not found")
    return _test_data_materialization_event_payload(record)


async def stream_test_data_materialization_events(request_id: str, request: Request) -> Response:
    initial_payload = await _load_test_data_materialization_event_payload(request_id)

    async def _load_payload() -> dict[str, Any]:
        return await _load_test_data_materialization_event_payload(request_id)

    return status_event_stream_response(
        request=request,
        initial_payload=initial_payload,
        load_payload=_load_payload,
        poll_interval_seconds=_MATERIALIZATION_EVENT_POLL_INTERVAL_SECONDS,
    )


async def report_test_data_materialization_completion(
    request_id: str,
    payload: ReportTestDataMaterializationCompletionRequest,
    catalog_repository: DataCatalogRepository,
) -> Any:
    return await report_test_data_materialization_completion_use_case(
        command=build_report_test_data_materialization_completion_command(request_id, payload),
        register_completion=bind_materialized_delivery_completion_registrar(catalog_repository),
    )