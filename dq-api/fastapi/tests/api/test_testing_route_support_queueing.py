from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.v1 import testing_route_support as testing_support


def test_queued_test_data_payload_helpers_cover_attribute_resolution_paths() -> None:
    class DumpModel:
        def model_dump(self, mode: str = "python", by_alias: bool = False) -> dict[str, object]:
            assert mode == "python"
            assert by_alias is False
            return {
                "name": "status",
                "type": "text",
                "nullable": False,
                "format": "",
                "is_primary_key": False,
            }

    attrs = testing_support._build_attribute_payloads(
        [
            testing_support.TestDataAttributeRequest(name="id", type="integer", nullable=False, format="", isPrimaryKey=True),
            DumpModel(),
            SimpleNamespace(name="email", type="text", nullable=True, format="email", is_primary_key=False),
            {"name": "country", "type": "text", "nullable": True, "format": "", "isPrimaryKey": True},
            {"name": "   ", "type": "text"},
        ]
    )
    assert attrs == [
        {
            "name": "id",
            "type": "integer",
            "nullable": False,
            "format": "",
            "is_primary_key": True,
        },
        {
            "name": "status",
            "type": "text",
            "nullable": False,
            "format": "",
            "is_primary_key": False,
        },
        {
            "name": "email",
            "type": "text",
            "nullable": True,
            "format": "email",
            "is_primary_key": False,
        },
        {
            "name": "country",
            "type": "text",
            "nullable": True,
            "format": "",
            "is_primary_key": True,
        },
    ]

    class Repo:
        def list_data_object_versions(self):
            return [
                SimpleNamespace(id="dov-1", version=7, data_object_id="do-1"),
                SimpleNamespace(id="dov-2", version=8, data_object_id="do-missing"),
            ]

        def list_attributes_catalog(self, version_id: str):
            return [SimpleNamespace(name=f"attr-{version_id}", type="text", nullable=True, format="", is_primary_key=False)]

        def list_data_objects_catalog(self):
            return [SimpleNamespace(id="do-1", name="Customers")]

    resolved = testing_support._resolve_version_generation_payload("dov-1", 4, Repo())
    assert resolved["version_name"] == 7
    assert resolved["data_object_id"] == "do-1"
    assert resolved["data_object_name"] == "Customers"
    assert resolved["attributes"][0]["name"] == "attr-dov-1"

    unresolved = testing_support._resolve_version_generation_payload("dov-2", 5, Repo())
    assert unresolved["version_name"] == 8
    assert unresolved["data_object_name"] is None

    missing_version = testing_support._resolve_version_generation_payload("missing", 6, Repo())
    assert missing_version["version_name"] is None
    assert missing_version["data_object_id"] is None
    assert missing_version["data_object_name"] is None

    data_object_version_payload = testing_support._resolve_queued_test_data_request_payload(
        testing_support.CreateQueuedTestDataRequest(
            targetType="data_object_version",
            targetId="dov-1",
            sampleCount=3,
        ),
        Repo(),
    )
    assert data_object_version_payload["target_type"] == "data_object_version"
    assert data_object_version_payload["target_id"] == "dov-1"

    preview_payload = testing_support._resolve_queued_test_data_request_payload(
        testing_support.CreateQueuedTestDataRequest(
            targetType="mock_data_source",
            targetId="mock-preview-source",
            sampleCount=2,
            attributes=[],
        ),
        Repo(),
    )
    assert preview_payload["source_name"] == "Mock Data Source (Preview)"
    assert [item["name"] for item in preview_payload["attributes"]] == ["column_id", "column_x", "column_y"]

    custom_mock_payload = testing_support._resolve_queued_test_data_request_payload(
        testing_support.CreateQueuedTestDataRequest(
            targetType="mock_data_source",
            targetId="custom-source",
            sampleCount=2,
            sourceName="Custom Source",
            versionName="v2",
            dataObjectId="do-9",
            attributes=[testing_support.TestDataAttributeRequest(name="email", format="email")],
        ),
        Repo(),
    )
    assert custom_mock_payload["source_name"] == "Custom Source"
    assert custom_mock_payload["version_id"] is None
    assert custom_mock_payload["data_object_id"] == "do-9"
    assert custom_mock_payload["attributes"] == [
        {
            "name": "email",
            "type": "text",
            "nullable": True,
            "format": "email",
            "is_primary_key": False,
        }
    ]

    with pytest.raises(HTTPException) as missing_target:
        testing_support._resolve_queued_test_data_request_payload(
            testing_support.CreateQueuedTestDataRequest(targetType="", targetId="", sampleCount=1),
            Repo(),
        )
    assert missing_target.value.status_code == 400

    with pytest.raises(HTTPException) as unsupported_target:
        testing_support._resolve_queued_test_data_request_payload(
            testing_support.CreateQueuedTestDataRequest(targetType="csv_file", targetId="file-1", sampleCount=1),
            Repo(),
        )
    assert unsupported_target.value.status_code == 400
    assert "Unsupported test data target_type" in str(unsupported_target.value.detail)


def test_queued_test_data_wrapper_helpers_delegate_to_service_functions(monkeypatch) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setattr(testing_support, "_service_test_data_request_key", lambda request_id: f"svc:{request_id}")

    def _inject(payload: dict[str, object]) -> None:
        payload["traceparent"] = "tp-1"

    monkeypatch.setattr(testing_support, "_service_inject_queue_trace_headers", _inject)
    monkeypatch.setattr(testing_support, "_current_timestamp", lambda: "2026-04-21T12:34:56Z")

    def _build_record(**kwargs):
        captured.update(kwargs)
        return {"built": kwargs}

    monkeypatch.setattr(testing_support, "_service_build_test_data_request_record", _build_record)
    monkeypatch.setattr(testing_support, "_require_queued_test_data_request_record", lambda record: {"wrapped": record})

    assert testing_support._test_data_request_key("req-7") == "svc:req-7"

    queue_payload: dict[str, object] = {"headers": {}}
    testing_support._inject_queue_trace_headers(queue_payload)
    assert queue_payload["traceparent"] == "tp-1"

    record = testing_support._build_test_data_request_record(
        request_id="req-7",
        job_id="job-7",
        correlation_id="corr-7",
        request_payload={"target_type": "data_object_version", "target_id": "dov-7"},
    )
    assert captured == {
        "request_id": "req-7",
        "job_id": "job-7",
        "correlation_id": "corr-7",
        "request_payload": {"target_type": "data_object_version", "target_id": "dov-7"},
        "current_timestamp": "2026-04-21T12:34:56Z",
    }
    assert record == {"wrapped": {"built": captured}}


@pytest.mark.anyio
async def test_queued_test_data_redis_wrappers_cover_async_sync_and_missing_backend(monkeypatch) -> None:
    captured: dict[str, object] = {"close_count": 0}

    class AsyncClient:
        async def set(self, key: str, payload: str, ex: int) -> None:
            captured["async_set"] = (key, json.loads(payload), ex)

        async def get(self, key: str) -> str:
            captured["async_get"] = key
            return json.dumps({"request_id": "req-1"})

        async def lpush(self, queue_key: str, payload: str) -> None:
            captured["async_lpush"] = (queue_key, json.loads(payload))

        async def aclose(self) -> None:
            captured["close_count"] = int(captured["close_count"]) + 1

    monkeypatch.setattr(
        testing_support,
        "aioredis",
        SimpleNamespace(from_url=lambda redis_url, decode_responses=True: AsyncClient()),
    )
    monkeypatch.setattr(testing_support, "redis_sync", None)

    await testing_support._redis_set_json("redis://async", "key-1", {"ok": True}, 60)
    assert captured["async_set"] == ("key-1", {"ok": True}, 60)

    async_payload = await testing_support._redis_get_json("redis://async", "key-2")
    assert async_payload == {"request_id": "req-1"}
    assert captured["async_get"] == "key-2"

    await testing_support._redis_lpush("redis://async", "queue-1", {"job": "payload"})
    assert captured["async_lpush"] == ("queue-1", {"job": "payload"})
    assert captured["close_count"] == 3

    class SyncClient:
        def set(self, key: str, payload: str, ex: int) -> None:
            captured["sync_set"] = (key, json.loads(payload), ex)

        def get(self, key: str) -> str | None:
            captured["sync_get"] = key
            return None

        def lpush(self, queue_key: str, payload: str) -> None:
            captured["sync_lpush"] = (queue_key, json.loads(payload))

    async def _fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(testing_support, "aioredis", None)
    monkeypatch.setattr(
        testing_support,
        "redis_sync",
        SimpleNamespace(from_url=lambda redis_url, decode_responses=True: SyncClient()),
    )
    monkeypatch.setattr(testing_support.asyncio, "to_thread", _fake_to_thread)

    await testing_support._redis_set_json("redis://sync", "key-3", {"ok": "sync"}, 30)
    assert captured["sync_set"] == ("key-3", {"ok": "sync"}, 30)

    sync_payload = await testing_support._redis_get_json("redis://sync", "key-4")
    assert sync_payload is None
    assert captured["sync_get"] == "key-4"

    await testing_support._redis_lpush("redis://sync", "queue-2", {"job": "sync"})
    assert captured["sync_lpush"] == ("queue-2", {"job": "sync"})

    monkeypatch.setattr(testing_support, "redis_sync", None)
    with pytest.raises(HTTPException) as missing_set_backend:
        await testing_support._redis_set_json("redis://none", "key-5", {}, 10)
    assert missing_set_backend.value.status_code == 503

    with pytest.raises(HTTPException) as missing_get_backend:
        await testing_support._redis_get_json("redis://none", "key-6")
    assert missing_get_backend.value.status_code == 503

    with pytest.raises(HTTPException) as missing_push_backend:
        await testing_support._redis_lpush("redis://none", "queue-3", {})
    assert missing_push_backend.value.status_code == 503


@pytest.mark.anyio
async def test_queued_test_data_request_wrappers_delegate_and_fail_fast(monkeypatch) -> None:
    request = SimpleNamespace(headers={"X-Correlation-ID": "corr-1"})
    captured: dict[str, object] = {}

    monkeypatch.setattr(testing_support, "_resolve_test_data_redis_url", lambda: None)
    with pytest.raises(HTTPException) as enqueue_missing_queue:
        await testing_support._enqueue_queued_test_data_request(
            request=request,
            request_payload={"target_type": "data_object_version", "target_id": "dov-1", "sample_count": 2},
        )
    assert enqueue_missing_queue.value.status_code == 503

    with pytest.raises(HTTPException) as wait_missing_queue:
        await testing_support._wait_for_test_data_request_result("req-1")
    assert wait_missing_queue.value.status_code == 503

    monkeypatch.setattr(testing_support, "_resolve_test_data_redis_url", lambda: "redis://example")
    monkeypatch.setattr(testing_support, "_resolve_test_data_queue_key", lambda: "queue-key")
    monkeypatch.setattr(testing_support, "_current_timestamp", lambda: "2026-04-21T13:00:00Z")
    monkeypatch.setattr(testing_support, "_require_queued_test_data_request_record", lambda record: {"wrapped": record})
    monkeypatch.setattr(
        testing_support,
        "_queued_test_data_request_record_payload",
        lambda record: {
            "request_id": str(record.get("request_id") or "req-1"),
            "job_id": str(record.get("job_id") or "job-1"),
            "business_key": str(record.get("business_key") or "corr-1"),
            "status": str(record.get("status") or "pending"),
            "target_type": str(record.get("target_type") or "data_object_version"),
            "target_id": str(record.get("target_id") or "dov-1"),
            "sample_count": int(record.get("sample_count") or 2),
            "requested_at": str(record.get("requested_at") or "2026-04-21T13:00:00Z"),
            "correlation_id": str(record.get("correlation_id") or "corr-1"),
        },
    )

    async def _service_write(redis_url: str, record: dict, ttl_seconds: int, redis_set_json):
        captured["service_write"] = (redis_url, dict(record), ttl_seconds, redis_set_json)

    monkeypatch.setattr(testing_support, "_service_write_test_data_request_record", _service_write)

    await testing_support._write_test_data_request_record("redis://example", {"request_id": "req-write"})
    assert captured["service_write"][0] == "redis://example"
    assert captured["service_write"][1]["request_id"] == "req-write"
    assert captured["service_write"][3] is testing_support._redis_set_json

    async def _service_read_none(redis_url: str, request_id: str, redis_get_json):
        captured["service_read_none"] = (redis_url, request_id, redis_get_json)
        return None

    monkeypatch.setattr(testing_support, "_service_read_test_data_request_record", _service_read_none)
    assert await testing_support._read_test_data_request_record("redis://example", "req-none") is None
    assert captured["service_read_none"][2] is testing_support._redis_get_json

    async def _service_read_payload(redis_url: str, request_id: str, redis_get_json):
        captured["service_read_payload"] = (redis_url, request_id, redis_get_json)
        return {"request_id": request_id, "status": "completed"}

    monkeypatch.setattr(testing_support, "_service_read_test_data_request_record", _service_read_payload)
    read_record = await testing_support._read_test_data_request_record("redis://example", "req-read")
    assert read_record == {"wrapped": {"request_id": "req-read", "status": "completed"}}

    async def _service_enqueue(**kwargs):
        captured["enqueue"] = kwargs
        assert kwargs["find_active_request"] is testing_support._test_data_queue_support.find_active_queued_test_data_request
        await kwargs["write_record"]("redis://example", {"request_id": "req-enqueue"}, kwargs["ttl_seconds"])
        return {"request_id": "req-enqueue", "status": "pending"}

    monkeypatch.setattr(testing_support, "_service_enqueue_queued_test_data_request", _service_enqueue)
    enqueue_record = await testing_support._enqueue_queued_test_data_request(
        request=request,
        request_payload={"target_type": "data_object_version", "target_id": "dov-1", "sample_count": 2},
    )
    assert enqueue_record == {"wrapped": {"request_id": "req-enqueue", "status": "pending"}}
    assert captured["enqueue"]["request_headers"] == {"X-Correlation-ID": "corr-1"}
    assert captured["enqueue"]["queue_key"] == "queue-key"
    assert captured["enqueue"]["push_queue"] is testing_support._redis_lpush

    async def _service_wait(**kwargs):
        captured["wait"] = kwargs
        awaited = await kwargs["read_record"]("redis://example", "req-wait")
        captured["wait_read_result"] = awaited
        return {"request_id": "req-wait", "status": "completed"}

    monkeypatch.setattr(testing_support, "_service_wait_for_test_data_request_result", _service_wait)
    waited_record = await testing_support._wait_for_test_data_request_result("req-wait")
    assert waited_record == {"wrapped": {"request_id": "req-wait", "status": "completed"}}
    assert captured["wait"]["redis_url"] == "redis://example"
    assert captured["wait_read_result"] == {"request_id": "req-wait", "status": "completed"}

    view = testing_support._as_queued_test_data_request_view({"request_id": "req-view"})
    assert view.businessKey == "corr-1"
    assert view.correlationId == "corr-1"
    assert view.model_dump(by_alias=True)["business_key"] == "corr-1"
    assert view.status == "pending"
