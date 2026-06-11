from __future__ import annotations

import pytest

from fastapi import HTTPException

from app.application.use_cases.testing_data_requests import create_queued_test_data_request
from app.application.use_cases.testing_data_requests import CreateQueuedTestDataRequestCommand
from app.application.use_cases.testing_data_requests import create_test_data_materialization
from app.application.use_cases.testing_data_requests import CreateTestDataMaterializationCommand
from app.application.use_cases.testing_data_requests import get_queued_test_data_request
from app.application.use_cases.testing_data_requests import GetQueuedTestDataRequestCommand
from app.application.use_cases.testing_data_requests import report_test_data_materialization_completion
from app.application.use_cases.testing_data_requests import ReportTestDataMaterializationCompletionCommand


@pytest.mark.anyio
async def test_create_queued_test_data_request_builds_view() -> None:
    result = await create_queued_test_data_request(
        command=CreateQueuedTestDataRequestCommand(request_payload={"target_id": "dov-1"}),
        enqueue_queued_test_data_request=lambda payload: _async_return({"request_id": "req-1", **payload}),
        build_view_payload=lambda record: {"id": record["request_id"], "target_id": record["target_id"]},
    )

    assert result == {"id": "req-1", "target_id": "dov-1"}


@pytest.mark.anyio
async def test_get_queued_test_data_request_fails_without_redis() -> None:
    with pytest.raises(HTTPException) as error:
        await get_queued_test_data_request(
            command=GetQueuedTestDataRequestCommand(request_id="req-1"),
            resolve_redis_url=lambda: None,
            read_record=lambda _redis_url, _request_id: _async_return(None),
            build_view_payload=lambda record: record,
        )
    assert error.value.status_code == 503


    @pytest.mark.anyio
    async def test_get_queued_test_data_request_returns_view() -> None:
        result = await get_queued_test_data_request(
            command=GetQueuedTestDataRequestCommand(request_id="req-1"),
            resolve_redis_url=lambda: "redis://stub",
            read_record=lambda _redis_url, _request_id: _async_return({"request_id": "req-1"}),
            build_view_payload=lambda record: {"id": record["request_id"]},
        )

        assert result == {"id": "req-1"}


    @pytest.mark.anyio
    async def test_get_test_data_materialization_handles_missing_record() -> None:
        with pytest.raises(HTTPException) as error:
            await get_test_data_materialization(
                command=GetTestDataMaterializationCommand(request_id="req-1"),
                resolve_redis_url=lambda: "redis://stub",
                read_record=lambda _redis_url, _request_id: _async_return(None),
                build_view_payload=lambda record: record,
            )

        assert error.value.status_code == 404


@pytest.mark.anyio
async def test_create_test_data_materialization_requires_version_id() -> None:
    with pytest.raises(HTTPException) as error:
        await create_test_data_materialization(
            command=CreateTestDataMaterializationCommand(version_id="", sample_count=5, output_format="parquet"),
            enqueue_test_data_materialization_request=lambda **kwargs: _async_return(kwargs),
            build_view_payload=lambda record: record,
        )
    assert error.value.status_code == 422


@pytest.mark.anyio
async def test_report_materialization_completion_delegates() -> None:
    result = await report_test_data_materialization_completion(
        command=ReportTestDataMaterializationCompletionCommand(request_id="req-1", payload={"row_count": 5}),
        register_completion=lambda request_id, payload: _async_return({"request_id": request_id, "payload": payload}),
    )

    assert result == {"request_id": "req-1", "payload": {"row_count": 5}}


async def _async_return(value):
    return value