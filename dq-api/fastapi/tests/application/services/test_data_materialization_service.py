from __future__ import annotations

from types import ModuleType, SimpleNamespace

import pytest
from fastapi import HTTPException

from app.application.services import test_data_materialization_service as service


def test_resolve_test_data_redis_url_prefers_env_and_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROFILING_REDIS_URL", "redis://profiling")
    monkeypatch.setenv("REDIS_URL", "redis://legacy")
    assert service.resolve_test_data_redis_url(SimpleNamespace(redis_host="host", redis_port=6379, redis_db=0)) == "redis://profiling"

    monkeypatch.delenv("PROFILING_REDIS_URL", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)
    resolved = service.resolve_test_data_redis_url(
        SimpleNamespace(redis_host="host", redis_port=6380, redis_db=2, redis_password="p@ss word")
    )
    assert resolved == "redis://:p%40ss%20word@host:6380/2"
    assert service.resolve_test_data_redis_url(SimpleNamespace(redis_host="", redis_port=6380, redis_db=2)) is None


def test_queue_and_output_prefix_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service, "_resolve_runtime_materialization_queue_key", lambda: "materialization-queue")
    assert service.resolve_test_data_materialization_queue_key() == "materialization-queue"

    monkeypatch.setattr(service, "_resolve_runtime_materialization_queue_key", lambda: "")
    with pytest.raises(HTTPException) as excinfo:
        service.resolve_test_data_materialization_queue_key()
    assert excinfo.value.status_code == 503

    monkeypatch.setenv("TEST_DATA_MATERIALIZATION_PROCESSING_QUEUE_KEY", "processing-queue")
    assert service.resolve_test_data_materialization_processing_queue_key("materialization-queue") == "processing-queue"
    monkeypatch.delenv("TEST_DATA_MATERIALIZATION_PROCESSING_QUEUE_KEY", raising=False)
    assert service.resolve_test_data_materialization_processing_queue_key("materialization-queue") == "materialization-queue:processing"

    monkeypatch.setenv("DQ_TEST_DATA_OUTPUT_PREFIX", " s3a://dq-test-data/ ")
    assert service.resolve_test_data_output_prefix() == "s3a://dq-test-data"
    monkeypatch.delenv("DQ_TEST_DATA_OUTPUT_PREFIX", raising=False)
    with pytest.raises(HTTPException) as excinfo:
        service.resolve_test_data_output_prefix()
    assert excinfo.value.status_code == 503


def test_uri_helpers_and_synthetic_namespace_guard() -> None:
    assert service.default_materialization_output_uri(
        output_prefix="s3a://dq-test-data/",
        version_id="v1",
        output_format="PARQUET",
        sample_count=25,
        attribute_hash="",
    ) == "s3a://dq-test-data/data_object_version_id=v1/attr_hash=all/sample_count=25/format=parquet"

    assert service.normalize_s3_uri("s3://bucket/path/to/object") == "s3a://bucket/path/to/object"
    assert service.normalize_s3_uri("s3a://bucket/path/to/object") == "s3a://bucket/path/to/object"
    assert service.parse_s3a_uri("s3a://bucket/path/to/object") == ("bucket", "path/to/object")
    assert service.parse_s3a_uri("s3://bucket") == ("bucket", "")
    with pytest.raises(HTTPException) as excinfo:
        service.parse_s3a_uri("file:///tmp/path")
    assert excinfo.value.status_code == 422

    assert service.matched_real_evidence_output_uri_terms("s3a://bucket/production/compliance/report") == ["compliance", "production"]
    service.ensure_synthetic_test_output_uri(output_uri="s3a://bucket/synthetic/output", status_code=409)
    with pytest.raises(HTTPException) as excinfo:
        service.ensure_synthetic_test_output_uri(
            output_uri="s3a://bucket/compliance/report",
            status_code=409,
            request_id="req-1",
            data_object_version_id="dov-1",
            correlation_id="corr-1",
        )
    assert excinfo.value.status_code == 409
    assert excinfo.value.detail["matched_terms"] == ["compliance"]
    assert excinfo.value.detail["request_id"] == "req-1"
    assert excinfo.value.detail["data_object_version_id"] == "dov-1"
    assert excinfo.value.detail["correlation_id"] == "corr-1"


def test_bool_env_and_s3_client_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_BOOL", "yes")
    assert service.resolve_optional_bool_env("TEST_BOOL") is True
    monkeypatch.setenv("TEST_BOOL", "0")
    assert service.resolve_optional_bool_env("TEST_BOOL") is False
    monkeypatch.setenv("DQ_S3_SSL_ENABLED", "true")
    assert service.derive_s3_ssl_enabled() is True
    monkeypatch.delenv("DQ_S3_SSL_ENABLED", raising=False)
    monkeypatch.setenv("DQ_S3_ENDPOINT", "https://example")
    assert service.derive_s3_ssl_enabled() is True
    monkeypatch.setenv("DQ_S3_ENDPOINT", "http://example")
    assert service.derive_s3_ssl_enabled() is False

    fake_boto3 = ModuleType("boto3")
    captured: dict[str, object] = {}

    def _client(service_name: str, **kwargs: object) -> object:
        captured["service_name"] = service_name
        captured["kwargs"] = kwargs
        return SimpleNamespace(service_name=service_name, kwargs=kwargs)

    fake_boto3.client = _client  # type: ignore[attr-defined]
    monkeypatch.setitem(__import__("sys").modules, "boto3", fake_boto3)
    monkeypatch.setenv("DQ_S3_ENDPOINT", "https://example")
    monkeypatch.setenv("DQ_S3_ACCESS_KEY", "access")
    monkeypatch.setenv("DQ_S3_SECRET_KEY", "secret")
    client = service.build_s3_client()
    assert client.service_name == "s3"
    assert captured["kwargs"]["verify"] is True

    monkeypatch.delenv("DQ_S3_ENDPOINT", raising=False)
    with pytest.raises(HTTPException) as excinfo:
        service.build_s3_client()
    assert excinfo.value.status_code == 503


def test_build_attribute_payloads_and_record_helpers() -> None:
    class _ModelDumpAttribute:
        def model_dump(self, mode: str, by_alias: bool) -> dict[str, object]:
            del mode, by_alias
            return {"name": "id", "type": "integer", "nullable": False, "format": "uuid", "is_primary_key": True}

    namespace_attribute = SimpleNamespace(name="code", type="", nullable=True, format="text", isPrimaryKey=True)
    blank_attribute = {"name": "   ", "type": "text"}

    payloads = service.build_attribute_payloads([_ModelDumpAttribute(), namespace_attribute, blank_attribute])
    assert payloads == [
        {"name": "id", "type": "integer", "nullable": False, "format": "uuid", "is_primary_key": True},
        {"name": "code", "type": "text", "nullable": True, "format": "text", "is_primary_key": True},
    ]
    assert service.test_data_materialization_request_key("req-1") == "test-data-materialization-request:req-1"

    written: list[tuple[str, str, dict[str, object], int]] = []

    async def _redis_set_json(redis_url: str, key: str, payload: dict[str, object], ttl_seconds: int) -> None:
        written.append((redis_url, key, payload, ttl_seconds))

    async def _redis_get_json(redis_url: str, key: str) -> dict[str, object] | None:
        if key.endswith("req-1"):
            return {"request_id": "req-1", "value": 42}
        return None

    async def _write_and_read() -> None:
        await service.write_test_data_materialization_record(
            "redis://example",
            SimpleNamespace(request_id="req-1", value=42),
            60,
            service.test_data_materialization_request_key,
            lambda record: {"request_id": record.request_id, "value": record.value},
            _redis_set_json,
        )
        record = await service.read_test_data_materialization_record(
            "redis://example",
            "req-1",
            service.test_data_materialization_request_key,
            lambda payload: SimpleNamespace(**payload),
            _redis_get_json,
        )
        missing = await service.read_test_data_materialization_record(
            "redis://example",
            "req-2",
            service.test_data_materialization_request_key,
            lambda payload: SimpleNamespace(**payload),
            _redis_get_json,
        )
        assert record.request_id == "req-1"
        assert record.value == 42
        assert missing is None

    import asyncio

    asyncio.run(_write_and_read())
    assert written == [("redis://example", "test-data-materialization-request:req-1", {"request_id": "req-1", "value": 42}, 60)]


def test_s3_prefix_and_materialized_completion_helpers() -> None:
    class _Client:
        def __init__(self, payload: dict[str, object] | Exception) -> None:
            self.payload = payload

        def list_objects_v2(self, **kwargs: object) -> dict[str, object]:
            if isinstance(self.payload, Exception):
                raise self.payload
            return self.payload

    assert service.s3_prefix_has_objects(
        output_uri="s3a://bucket/path/to/folder",
        build_s3_client_fn=lambda: _Client({"Contents": [1]}),
    ) is True
    assert service.s3_prefix_has_objects(
        output_uri="s3a://bucket/path/to/folder",
        build_s3_client_fn=lambda: _Client({}),
    ) is False
    with pytest.raises(HTTPException) as excinfo:
        service.s3_prefix_has_objects(
            output_uri="s3a://bucket/path/to/folder",
            build_s3_client_fn=lambda: _Client(RuntimeError("boom")),
        )
    assert excinfo.value.status_code == 503

    async def _exercise_completion_helpers() -> None:
        record = SimpleNamespace(
            output_uri="s3://bucket/path",
            output_format="parquet",
            data_object_version_id="dov-1",
            correlation_id="corr-1",
        )

        async def _read_record(redis_url: str, request_id: str) -> SimpleNamespace:
            del redis_url, request_id
            return record

        async def _read_missing_record(redis_url: str, request_id: str) -> None:
            del redis_url, request_id
            return None

        with pytest.raises(HTTPException) as excinfo:
            await service.register_materialized_delivery_completion(
                request_id="req-1",
                payload=SimpleNamespace(output_uri="s3://bucket/other", output_format="parquet", row_count=1),
                catalog_repository=object(),
                resolve_redis_url=lambda: "redis://example",
                read_record=_read_record,
                require_record=lambda payload: payload,
                normalize_s3_uri_fn=service.normalize_s3_uri,
                ensure_synthetic_output_uri_fn=lambda **kwargs: None,
                create_completions_from_record=lambda **kwargs: None,
                build_completion_response=lambda result: result,
            )
        assert excinfo.value.status_code == 409

        result = await service.register_materialized_delivery_completion(
            request_id="req-1",
            payload=SimpleNamespace(output_uri="s3://bucket/path", output_format="parquet", row_count=1),
            catalog_repository=object(),
            resolve_redis_url=lambda: "redis://example",
            read_record=_read_record,
            require_record=lambda payload: payload,
            normalize_s3_uri_fn=service.normalize_s3_uri,
            ensure_synthetic_output_uri_fn=lambda **kwargs: None,
            create_completions_from_record=lambda **kwargs: SimpleNamespace(data_deliveries=[SimpleNamespace(id="delivery-1")]),
            build_completion_response=lambda completion: {"delivery_id": completion.id},
        )
        assert result == {"delivery_id": "delivery-1"}

        expected_targets = [{"data_object_version_id": "dov-1", "output_uri": "s3://bucket/path", "output_format": "parquet"}]
        with pytest.raises(HTTPException) as excinfo:
            await service.register_materialized_delivery_completions(
                request_id="req-1",
                target_results=[SimpleNamespace(data_object_version_id="dov-2", output_uri="s3://bucket/path", output_format="parquet", row_count=1)],
                catalog_repository=object(),
                resolve_redis_url=lambda: "redis://example",
                read_record=_read_record,
                require_record=lambda payload: payload,
                expected_targets_from_record=lambda record_entity: expected_targets,
                normalize_s3_uri_fn=service.normalize_s3_uri,
                ensure_synthetic_output_uri_fn=lambda **kwargs: None,
                create_completions_from_record=lambda **kwargs: None,
            )
        assert excinfo.value.status_code == 409

        completion = await service.register_materialized_delivery_completions(
            request_id="req-1",
            target_results=[SimpleNamespace(data_object_version_id="dov-1", output_uri="s3://bucket/path", output_format="parquet", row_count=1)],
            catalog_repository=object(),
            resolve_redis_url=lambda: "redis://example",
            read_record=_read_record,
            require_record=lambda payload: payload,
            expected_targets_from_record=lambda record_entity: expected_targets,
            normalize_s3_uri_fn=service.normalize_s3_uri,
            ensure_synthetic_output_uri_fn=lambda **kwargs: None,
            create_completions_from_record=lambda **kwargs: SimpleNamespace(data_deliveries=[SimpleNamespace(id="delivery-1")]),
        )
        assert completion.data_deliveries[0].id == "delivery-1"

    import asyncio

    asyncio.run(_exercise_completion_helpers())


def test_enqueue_test_data_materialization_request_guard_and_success_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    catalog_repository = SimpleNamespace(list_attributes_catalog=lambda version_id: [SimpleNamespace(name="id"), SimpleNamespace(name="code")])

    async def _redis_llen_ok(redis_url: str, queue_key: str) -> int:
        del redis_url, queue_key
        return 0

    async def _redis_llen_fail(redis_url: str, queue_key: str) -> int:
        del redis_url, queue_key
        raise RuntimeError("redis unavailable")

    async def _write_record(redis_url: str, record: object) -> None:
        del redis_url, record

    async def _push_queue(redis_url: str, queue_key: str, payload: dict[str, object]) -> None:
        del redis_url, queue_key, payload

    async def _push_queue_fail(redis_url: str, queue_key: str, payload: dict[str, object]) -> None:
        del redis_url, queue_key, payload
        raise RuntimeError("boom")

    class _MaterializationRecord(SimpleNamespace):
        def model_copy(self, update: dict[str, object]) -> SimpleNamespace:
            payload = dict(self.__dict__)
            payload.update(update)
            return _MaterializationRecord(**payload)

    def _build_record(**kwargs: object) -> _MaterializationRecord:
        return _MaterializationRecord(**kwargs, status="queued", started_at=None, completed_at=None, result=None)

    def _build_result_from_deliveries(**kwargs: object) -> dict[str, object]:
        return {"deliveries": kwargs["deliveries"], "reused_existing": kwargs["reused_existing"]}

    def _inject_queue_trace_headers(payload: dict[str, object]) -> None:
        payload.setdefault("headers", {})["X-Correlation-ID"] = payload["correlation_id"]

    with pytest.raises(HTTPException) as excinfo:
        import asyncio

        asyncio.run(
            service.enqueue_test_data_materialization_request(
                request_headers={},
                version_id="version-1",
                sample_count=5,
                output_format="parquet",
                output_uri=None,
                selected_attribute_names=None,
                refresh=False,
                catalog_repository=catalog_repository,
                selection=None,
                targets=None,
                request_contract=None,
                resolve_redis_url=lambda: None,
                resolve_queue_key=lambda: "queue",
                resolve_processing_queue_key=lambda queue_key: f"{queue_key}:processing",
                redis_llen=_redis_llen_ok,
                s3_prefix_has_objects_fn=lambda **kwargs: False,
                build_attribute_payloads_fn=service.build_attribute_payloads,
                resolve_output_prefix=lambda: "s3a://dq-test-data",
                default_output_uri=service.default_materialization_output_uri,
                ensure_synthetic_output_uri_fn=lambda **kwargs: None,
                normalize_s3_uri_fn=service.normalize_s3_uri,
                build_record=_build_record,
                create_completions_from_record=lambda **kwargs: SimpleNamespace(data_deliveries=[]),
                build_result_from_deliveries=_build_result_from_deliveries,
                current_timestamp=lambda: "2024-05-01T10:00:00+00:00",
                write_record=_write_record,
                push_queue=_push_queue,
                inject_queue_trace_headers=_inject_queue_trace_headers,
                queue_job_type="test-data-materialization",
            )
        )
    assert excinfo.value.status_code == 503

    with pytest.raises(HTTPException) as excinfo:
        asyncio.run(
            service.enqueue_test_data_materialization_request(
                request_headers={},
                version_id="version-1",
                sample_count=5,
                output_format="parquet",
                output_uri=None,
                selected_attribute_names=None,
                refresh=False,
                catalog_repository=catalog_repository,
                selection=None,
                targets=None,
                request_contract=None,
                resolve_redis_url=lambda: "redis://example",
                resolve_queue_key=lambda: "queue",
                resolve_processing_queue_key=lambda queue_key: f"{queue_key}:processing",
                redis_llen=_redis_llen_fail,
                s3_prefix_has_objects_fn=lambda **kwargs: False,
                build_attribute_payloads_fn=service.build_attribute_payloads,
                resolve_output_prefix=lambda: "s3a://dq-test-data",
                default_output_uri=service.default_materialization_output_uri,
                ensure_synthetic_output_uri_fn=lambda **kwargs: None,
                normalize_s3_uri_fn=service.normalize_s3_uri,
                build_record=_build_record,
                create_completions_from_record=lambda **kwargs: SimpleNamespace(data_deliveries=[]),
                build_result_from_deliveries=_build_result_from_deliveries,
                current_timestamp=lambda: "2024-05-01T10:00:00+00:00",
                write_record=_write_record,
                push_queue=_push_queue,
                inject_queue_trace_headers=_inject_queue_trace_headers,
                queue_job_type="test-data-materialization",
            )
        )
    assert excinfo.value.status_code == 503

    with pytest.raises(HTTPException) as excinfo:
        asyncio.run(
            service.enqueue_test_data_materialization_request(
                request_headers={"X-Correlation-ID": "corr-1"},
                version_id="version-1",
                sample_count=5,
                output_format="parquet",
                output_uri="s3://bucket/path",
                selected_attribute_names=None,
                refresh=False,
                catalog_repository=catalog_repository,
                selection=None,
                targets=[{"data_object_version_id": "dov-1", "output_uri": "s3://bucket/path", "output_format": "parquet", "attributes": []}],
                request_contract=None,
                resolve_redis_url=lambda: "redis://example",
                resolve_queue_key=lambda: "queue",
                resolve_processing_queue_key=lambda queue_key: f"{queue_key}:processing",
                redis_llen=_redis_llen_ok,
                s3_prefix_has_objects_fn=lambda **kwargs: False,
                build_attribute_payloads_fn=service.build_attribute_payloads,
                resolve_output_prefix=lambda: "s3a://dq-test-data",
                default_output_uri=service.default_materialization_output_uri,
                ensure_synthetic_output_uri_fn=lambda **kwargs: None,
                normalize_s3_uri_fn=service.normalize_s3_uri,
                build_record=_build_record,
                create_completions_from_record=lambda **kwargs: SimpleNamespace(data_deliveries=[]),
                build_result_from_deliveries=_build_result_from_deliveries,
                current_timestamp=lambda: "2024-05-01T10:00:00+00:00",
                write_record=_write_record,
                push_queue=_push_queue,
                inject_queue_trace_headers=_inject_queue_trace_headers,
                queue_job_type="test-data-materialization",
            )
        )
    assert excinfo.value.status_code == 422

    reused_writes: list[object] = []
    async def _write_record_reused(redis_url: str, record: object) -> None:
        del redis_url
        reused_writes.append(record)

    reused_record = asyncio.run(
        service.enqueue_test_data_materialization_request(
            request_headers={"X-Correlation-ID": "corr-1"},
            version_id="version-1",
            sample_count=5,
            output_format="parquet",
            output_uri=None,
            selected_attribute_names=None,
            refresh=False,
            catalog_repository=catalog_repository,
            selection={"scope": "all"},
            targets=None,
            request_contract="contract-1",
            resolve_redis_url=lambda: "redis://example",
            resolve_queue_key=lambda: "queue",
            resolve_processing_queue_key=lambda queue_key: f"{queue_key}:processing",
            redis_llen=_redis_llen_ok,
            s3_prefix_has_objects_fn=lambda **kwargs: True,
            build_attribute_payloads_fn=service.build_attribute_payloads,
            resolve_output_prefix=lambda: "s3a://dq-test-data",
            default_output_uri=service.default_materialization_output_uri,
            ensure_synthetic_output_uri_fn=lambda **kwargs: None,
            normalize_s3_uri_fn=service.normalize_s3_uri,
            build_record=_build_record,
            create_completions_from_record=lambda **kwargs: SimpleNamespace(data_deliveries=[SimpleNamespace(id="delivery-1")]),
            build_result_from_deliveries=_build_result_from_deliveries,
            current_timestamp=lambda: "2024-05-01T10:00:00+00:00",
            write_record=_write_record_reused,
            push_queue=_push_queue,
            inject_queue_trace_headers=_inject_queue_trace_headers,
            queue_job_type="test-data-materialization",
        )
    )
    assert reused_record.status == "completed"
    assert reused_record.result == {"deliveries": [SimpleNamespace(id="delivery-1")], "reused_existing": True}
    assert reused_writes and reused_writes[0].status == "completed"

    failed_writes: list[object] = []

    async def _write_record_failed(redis_url: str, record: object) -> None:
        del redis_url
        failed_writes.append(record)

    with pytest.raises(HTTPException) as excinfo:
        asyncio.run(
            service.enqueue_test_data_materialization_request(
                request_headers={"X-Correlation-ID": "corr-1"},
                version_id="version-1",
                sample_count=5,
                output_format="parquet",
                output_uri=None,
                selected_attribute_names=None,
                refresh=True,
                catalog_repository=catalog_repository,
                selection={"scope": "all"},
                targets=None,
                request_contract="contract-1",
                resolve_redis_url=lambda: "redis://example",
                resolve_queue_key=lambda: "queue",
                resolve_processing_queue_key=lambda queue_key: f"{queue_key}:processing",
                redis_llen=_redis_llen_ok,
                s3_prefix_has_objects_fn=lambda **kwargs: False,
                build_attribute_payloads_fn=service.build_attribute_payloads,
                resolve_output_prefix=lambda: "s3a://dq-test-data",
                default_output_uri=service.default_materialization_output_uri,
                ensure_synthetic_output_uri_fn=lambda **kwargs: None,
                normalize_s3_uri_fn=service.normalize_s3_uri,
                build_record=_build_record,
                create_completions_from_record=lambda **kwargs: SimpleNamespace(data_deliveries=[]),
                build_result_from_deliveries=_build_result_from_deliveries,
                current_timestamp=lambda: "2024-05-01T10:00:00+00:00",
                write_record=_write_record_failed,
                push_queue=_push_queue_fail,
                inject_queue_trace_headers=_inject_queue_trace_headers,
                queue_job_type="test-data-materialization",
            )
        )
    assert excinfo.value.status_code == 503
    assert failed_writes
