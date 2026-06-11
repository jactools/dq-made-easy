from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

import app.api.v1.testing_data_requests_api as requests_api
from app.api.v1.schemas.test_data_queue_view import CreateQueuedTestDataRequest


def test_resolve_test_data_queue_key_returns_runtime_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(requests_api, "_resolve_runtime_profiling_queue_key", lambda: "queue:test-data")

    assert requests_api._resolve_test_data_queue_key() == "queue:test-data"


def test_resolve_test_data_queue_key_fails_fast_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(requests_api, "_resolve_runtime_profiling_queue_key", lambda: None)

    with pytest.raises(HTTPException) as error:
        requests_api._resolve_test_data_queue_key()

    assert error.value.status_code == 503
    assert error.value.detail["error"] == "test_data_queue_not_configured"


def test_build_create_test_data_request_command_delegates_to_support(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = CreateQueuedTestDataRequest(targetType="mock_data_source", targetId="mock-preview-source", sampleCount=10)
    expected = {"target_type": "mock_data_source", "target_id": "mock-preview-source", "sample_count": 10}
    monkeypatch.setattr(
        requests_api._test_data_queue_support,
        "resolve_queued_test_data_request_payload",
        lambda p, catalog: (expected if (p is payload and catalog == "catalog") else {}),
    )

    command = requests_api.build_create_test_data_request_command(payload, "catalog")

    assert command.request_payload == expected


def test_build_create_test_data_materialization_command_maps_fields() -> None:
    payload = SimpleNamespace(
        data_object_version_id="dov-1",
        sample_count=25,
        output_format="parquet",
        output_uri="s3://bucket/output",
        selected_attribute_names=["a", "b"],
        refresh=True,
    )

    command = requests_api.build_create_test_data_materialization_command(payload)

    assert command.version_id == "dov-1"
    assert command.sample_count == 25
    assert command.output_format == "parquet"
    assert command.output_uri == "s3://bucket/output"
    assert command.selected_attribute_names == ["a", "b"]
    assert command.refresh is True


@pytest.mark.anyio
async def test_wait_for_test_data_request_result_fails_when_redis_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(requests_api, "resolve_test_data_redis_url", lambda: None)

    with pytest.raises(HTTPException) as error:
        await requests_api.wait_for_test_data_request_result("req-1")

    assert error.value.status_code == 503
    assert "Test data queue is not configured" in str(error.value.detail)


@pytest.mark.anyio
async def test_wait_for_test_data_request_result_returns_required_record(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(requests_api, "resolve_test_data_redis_url", lambda: "redis://queue")
    monkeypatch.setattr(
        requests_api,
        "_service_wait_for_test_data_request_result",
        AsyncMock(return_value={"request_id": "req-1", "status": "completed"}),
    )
    monkeypatch.setattr(
        requests_api._test_data_queue_support,
        "require_queued_test_data_request_record",
        lambda record: {"wrapped": record["request_id"]},
    )

    payload = await requests_api.wait_for_test_data_request_result("req-1")

    assert payload == {"wrapped": "req-1"}


@pytest.mark.anyio
async def test_bind_queued_test_data_request_enqueuer_calls_internal_enqueuer(monkeypatch: pytest.MonkeyPatch) -> None:
    internal = AsyncMock(return_value={"request_id": "req-1"})
    monkeypatch.setattr(requests_api, "_enqueue_queued_test_data_request", internal)

    request = SimpleNamespace(headers={"X-Correlation-ID": "corr-1"})
    enqueuer = requests_api.bind_queued_test_data_request_enqueuer(request)
    result = await enqueuer({"target_id": "dov-1"})

    assert result == {"request_id": "req-1"}
    internal.assert_awaited_once_with(request=request, request_payload={"target_id": "dov-1"})


@pytest.mark.anyio
async def test_bind_materialization_request_enqueuer_forwards_headers_and_kwargs(monkeypatch: pytest.MonkeyPatch) -> None:
    enqueue_materialization = AsyncMock(return_value={"request_id": "mat-1"})
    monkeypatch.setattr(requests_api._test_data_materialization_api, "_enqueue_test_data_materialization_request", enqueue_materialization)

    request = SimpleNamespace(headers={"X-Correlation-ID": "corr-2"})
    enqueuer = requests_api.bind_test_data_materialization_request_enqueuer(request, "catalog")
    result = await enqueuer(version_id="dov-9", sample_count=10, output_format="parquet")

    assert result == {"request_id": "mat-1"}
    enqueue_materialization.assert_awaited_once_with(
        request_headers={"X-Correlation-ID": "corr-2"},
        catalog_repository="catalog",
        version_id="dov-9",
        sample_count=10,
        output_format="parquet",
    )


@pytest.mark.anyio
async def test_read_test_data_request_record_handles_missing_and_present_records(monkeypatch: pytest.MonkeyPatch) -> None:
    read_mock = AsyncMock(side_effect=[None, {"request_id": "req-22", "status": "pending"}])
    monkeypatch.setattr(requests_api, "_service_read_test_data_request_record", read_mock)
    monkeypatch.setattr(
        requests_api._test_data_queue_support,
        "require_queued_test_data_request_record",
        lambda payload: {"required": payload["request_id"]},
    )

    missing = await requests_api.read_test_data_request_record("redis://queue", "req-missing")
    present = await requests_api.read_test_data_request_record("redis://queue", "req-22")

    assert missing is None
    assert present == {"required": "req-22"}
    assert read_mock.await_count == 2