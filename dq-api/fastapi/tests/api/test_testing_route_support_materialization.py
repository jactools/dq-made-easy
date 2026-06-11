from __future__ import annotations

import asyncio
import builtins
import sys
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.v1 import testing_route_support as testing_support
from app.domain.entities.data_catalog import DataDeliveryNoteEntity


def _make_delivery_note_entity(*, delivery_id: str, output_uri: str, row_count: int = 5) -> DataDeliveryNoteEntity:
    return DataDeliveryNoteEntity(
        id=f"note-{delivery_id}",
        data_delivery_id=delivery_id,
        data_object_id="do-1",
        data_object_version_id="dov-1",
        version=7,
        delivered_at="2026-04-21T12:00:00Z",
        timestamp="2026-04-21T12:00:00Z",
        layer="standardized",
        storage_location="S3",
        delivery_location=output_uri,
        delivery_status="completed",
        delivery_format="parquet",
        record_count=row_count,
        size_bytes=0,
        attributes_count=2,
        ingestor_name="dq-engine-test-data-materialization-worker",
        ingestor_run_id="job-1",
        source_system="test_data_materialization",
        source_snapshot_id="req-1",
        metadata_json={"materialization_request_id": "req-1"},
    )


def test_resolve_test_data_queue_keys_and_output_prefix(monkeypatch) -> None:
    monkeypatch.setenv("PROFILING_QUEUE_KEY", "queue-a")
    assert testing_support._resolve_test_data_queue_key() == "queue-a"
    monkeypatch.delenv("PROFILING_QUEUE_KEY", raising=False)
    monkeypatch.setenv("DQ_PROFILING_QUEUE_KEY", "queue-b")
    assert testing_support._resolve_test_data_queue_key() == "queue-b"

    monkeypatch.delenv("DQ_PROFILING_QUEUE_KEY", raising=False)
    with pytest.raises(HTTPException) as queue_error:
        testing_support._resolve_test_data_queue_key()
    assert queue_error.value.status_code == 503

    monkeypatch.setenv("TEST_DATA_MATERIALIZATION_QUEUE_KEY", "mat-queue")
    assert testing_support._resolve_test_data_materialization_queue_key() == "mat-queue"

    monkeypatch.delenv("TEST_DATA_MATERIALIZATION_QUEUE_KEY", raising=False)
    monkeypatch.delenv("DQ_TEST_DATA_MATERIALIZATION_QUEUE_KEY", raising=False)
    with pytest.raises(HTTPException) as materialization_queue_error:
        testing_support._resolve_test_data_materialization_queue_key()
    assert materialization_queue_error.value.status_code == 503

    assert testing_support._resolve_test_data_materialization_processing_queue_key("base") == "base:processing"

    monkeypatch.setenv("DQ_TEST_DATA_OUTPUT_PREFIX", "s3a://dq-test-data")
    assert testing_support._resolve_test_data_output_prefix() == "s3a://dq-test-data"

    monkeypatch.delenv("DQ_TEST_DATA_OUTPUT_PREFIX", raising=False)
    with pytest.raises(HTTPException) as error:
        testing_support._resolve_test_data_output_prefix()
    assert error.value.status_code == 503


def test_redis_llen_prefers_aioredis(monkeypatch) -> None:
    class FakeClient:
        def __init__(self) -> None:
            self._closed = False

        async def llen(self, key):
            assert key == "test-key"
            return 5

        async def aclose(self):
            self._closed = True

    class FakeAioredis:
        @staticmethod
        def from_url(url, decode_responses=True):
            assert url == "redis://localhost:6379/0"
            assert decode_responses is True
            return FakeClient()

    monkeypatch.setattr(testing_support, "aioredis", FakeAioredis)
    monkeypatch.setattr(testing_support, "redis_sync", None)
    result = asyncio.run(testing_support._redis_llen("redis://localhost:6379/0", "test-key"))
    assert result == 5


def test_test_data_materialization_request_key() -> None:
    assert testing_support._test_data_materialization_request_key("abc") == "test-data-materialization-request:abc"


def test_materialization_s3_uri_and_env_helpers(monkeypatch) -> None:
    assert testing_support._normalize_s3_uri("s3://bucket/path") == "s3a://bucket/path"
    assert testing_support._normalize_s3_uri("/tmp/output.parquet") == "/tmp/output.parquet"
    assert testing_support._parse_s3a_uri("s3a://bucket") == ("bucket", "")
    assert testing_support._parse_s3a_uri("s3://bucket/path") == ("bucket", "path")

    with pytest.raises(HTTPException) as invalid_scheme:
        testing_support._parse_s3a_uri("file:///tmp/output.parquet")
    assert invalid_scheme.value.status_code == 422
    assert invalid_scheme.value.detail["error"] == "invalid_output_uri"

    with pytest.raises(HTTPException) as missing_bucket:
        testing_support._parse_s3a_uri("s3a://")
    assert missing_bucket.value.status_code == 422
    assert missing_bucket.value.detail["message"] == "output_uri must include a bucket name"

    monkeypatch.setenv("DQ_S3_SSL_ENABLED", "yes")
    assert testing_support._resolve_optional_bool_env("DQ_S3_SSL_ENABLED") is True
    assert testing_support._derive_s3_ssl_enabled() is True

    monkeypatch.setenv("DQ_S3_SSL_ENABLED", "off")
    assert testing_support._resolve_optional_bool_env("DQ_S3_SSL_ENABLED") is False
    assert testing_support._derive_s3_ssl_enabled() is False

    monkeypatch.setenv("DQ_S3_SSL_ENABLED", "")
    monkeypatch.setenv("DQ_S3_ENDPOINT", "https://aistor.example")
    assert testing_support._resolve_optional_bool_env("DQ_S3_SSL_ENABLED") is None
    assert testing_support._derive_s3_ssl_enabled() is True


def test_build_s3_client_validates_dependency_and_configuration(monkeypatch) -> None:
    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "boto3":
            raise ImportError("missing boto3")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(HTTPException) as error:
        testing_support._build_s3_client()
    assert error.value.status_code == 503
    assert error.value.detail["dependency"] == "boto3"


def test_build_s3_client_and_s3_prefix_checks_cover_success_and_fail_fast(monkeypatch) -> None:
    captured: dict[str, object] = {}
    fake_client = object()

    class FakeBoto3:
        @staticmethod
        def client(service_name: str, **kwargs):
            captured["service_name"] = service_name
            captured["kwargs"] = kwargs
            return fake_client

    monkeypatch.setitem(sys.modules, "boto3", FakeBoto3)
    for env_name in [
        "DQ_S3_ENDPOINT",
        "AWS_ENDPOINT_URL",
        "DQ_S3_ACCESS_KEY",
        "AWS_ACCESS_KEY_ID",
        "DQ_S3_SECRET_KEY",
        "AWS_SECRET_ACCESS_KEY",
        "DQ_S3_REGION",
        "AWS_REGION",
        "AWS_DEFAULT_REGION",
        "DQ_S3_SSL_ENABLED",
    ]:
        monkeypatch.delenv(env_name, raising=False)

    with pytest.raises(HTTPException) as missing_endpoint:
        testing_support._build_s3_client()
    assert missing_endpoint.value.status_code == 503
    assert missing_endpoint.value.detail["error"] == "s3_not_configured"

    monkeypatch.setenv("DQ_S3_ENDPOINT", "https://aistor.example")
    with pytest.raises(HTTPException) as missing_creds:
        testing_support._build_s3_client()
    assert missing_creds.value.status_code == 503
    assert missing_creds.value.detail["error"] == "s3_not_configured"

    monkeypatch.setenv("DQ_S3_ACCESS_KEY", "access")
    monkeypatch.setenv("DQ_S3_SECRET_KEY", "secret")
    monkeypatch.setenv("DQ_S3_REGION", "eu-west-1")
    monkeypatch.setenv("DQ_S3_SSL_ENABLED", "yes")
    assert testing_support._build_s3_client() is fake_client
    assert captured["service_name"] == "s3"
    assert captured["kwargs"] == {
        "endpoint_url": "https://aistor.example",
        "aws_access_key_id": "access",
        "aws_secret_access_key": "secret",
        "region_name": "eu-west-1",
        "verify": True,
    }

    class ListObjectsClient:
        def __init__(self, response=None, error: Exception | None = None) -> None:
            self._response = response or {}
            self._error = error

        def list_objects_v2(self, **kwargs):
            captured["list_kwargs"] = kwargs
            if self._error is not None:
                raise self._error
            return self._response

    monkeypatch.setattr(testing_support, "_build_s3_client", lambda: ListObjectsClient({"Contents": [{"Key": "file.parquet"}]}))
    assert testing_support._s3_prefix_has_objects(output_uri="s3://bucket/prefix") is True
    assert captured["list_kwargs"] == {"Bucket": "bucket", "Prefix": "prefix/", "MaxKeys": 1}

    monkeypatch.setattr(testing_support, "_build_s3_client", lambda: ListObjectsClient({}))
    assert testing_support._s3_prefix_has_objects(output_uri="s3a://bucket/prefix") is False

    http_error = HTTPException(status_code=422, detail="bad-output")
    monkeypatch.setattr(testing_support, "_build_s3_client", lambda: ListObjectsClient(error=http_error))
    with pytest.raises(HTTPException) as raised_http_error:
        testing_support._s3_prefix_has_objects(output_uri="s3a://bucket/prefix")
    assert raised_http_error.value is http_error

    monkeypatch.setattr(testing_support, "_build_s3_client", lambda: ListObjectsClient(error=RuntimeError("s3 down")))
    with pytest.raises(HTTPException) as backend_error:
        testing_support._s3_prefix_has_objects(output_uri="s3a://bucket/prefix")
    assert backend_error.value.status_code == 503
    assert backend_error.value.detail["error"] == "test_data_output_check_failed"


def test_materialization_record_and_delivery_helpers(monkeypatch) -> None:
    monkeypatch.setattr(testing_support, "_current_timestamp", lambda: "2026-04-21T12:00:00Z")

    record = testing_support._build_test_data_materialization_record(
        request_id="req-1",
        job_id="job-1",
        correlation_id="corr-1",
        request_payload={
            "data_object_version_id": "dov-1",
            "sample_count": 5,
            "output_format": "PARQUET",
            "output_uri": "s3://bucket/path",
        },
        queue_key="queue-1",
        processing_queue_key="queue-1:processing",
        selection={"resolved": {"targets": []}},
        request_contract="catalog_materialization_v1",
        target_data_object_version_ids=["dov-1", " ", "dov-2"],
    )
    assert record.requested_at == "2026-04-21T12:00:00Z"
    assert record.target_data_object_version_ids == ["dov-1", "dov-2"]
    assert testing_support._test_data_materialization_record_payload(record)["request_id"] == "req-1"
    assert testing_support._resolve_materialization_storage_location("/tmp/output.parquet") == "FILE"
    assert testing_support._resolve_materialization_storage_location("s3://bucket/path") == "S3"

    with pytest.raises(HTTPException) as invalid_record:
        testing_support._require_test_data_materialization_record({})
    assert invalid_record.value.status_code == 503
    assert invalid_record.value.detail["error"] == "invalid_test_data_materialization_record"

    class VersionRepo:
        def get_data_object_version(self, version_id: str):
            if version_id == "missing":
                return None
            return SimpleNamespace(data_object_id="do-1", version=7, attribute_count=2)

        def create_materialized_delivery_note(self, payload: dict):
            return _make_delivery_note_entity(
                delivery_id="del-1",
                output_uri=str(payload.get("delivery_location") or "s3a://bucket/path"),
                row_count=int(payload.get("record_count") or 0),
            )

    with pytest.raises(HTTPException) as missing_version:
        testing_support._build_materialized_delivery_payload(
            request_id="req-1",
            record={
                "request_id": "req-1",
                "job_id": "job-1",
                "status": "pending",
                "data_object_version_id": "missing",
                "sample_count": 5,
                "output_format": "parquet",
                "output_uri": "s3://bucket/path",
            },
            row_count=5,
            output_uri="s3://bucket/path",
            output_format="parquet",
            catalog_repository=VersionRepo(),
        )
    assert missing_version.value.status_code == 404

    delivery_payload = testing_support._build_materialized_delivery_payload(
        request_id="req-1",
        record=record,
        row_count=5,
        output_uri="s3://bucket/path",
        output_format="PARQUET",
        catalog_repository=VersionRepo(),
        reused_existing=True,
    )
    assert delivery_payload["storage_location"] == "S3"
    assert delivery_payload["delivery_location"] == "s3a://bucket/path"
    assert delivery_payload["metadata_json"]["reused_existing"] is True

    completion = testing_support._create_materialized_delivery_completion_from_record(
        request_id="req-1",
        record=record,
        row_count=5,
        output_uri="s3://bucket/path",
        output_format="parquet",
        catalog_repository=VersionRepo(),
    )
    assert completion.data_delivery_id == "del-1"
    assert completion.delivery_note.delivery_location == "s3a://bucket/path"

    class BrokenRepo(VersionRepo):
        def create_materialized_delivery_note(self, payload: dict):
            del payload
            raise RuntimeError("db unavailable")

    with pytest.raises(HTTPException) as persistence_error:
        testing_support._create_materialized_delivery_completion_from_record(
            request_id="req-1",
            record=record,
            row_count=5,
            output_uri="s3://bucket/path",
            output_format="parquet",
            catalog_repository=BrokenRepo(),
        )
    assert persistence_error.value.status_code == 503
    assert persistence_error.value.detail["error"] == "data_delivery_persistence_failed"


def test_materialization_target_and_result_helpers() -> None:
    record = {
        "request_id": "req-1",
        "job_id": "job-1",
        "status": "pending",
        "data_object_version_id": "dov-1",
        "target_data_object_version_ids": ["dov-1"],
        "sample_count": 5,
        "output_format": "parquet",
        "output_uri": "s3://bucket/request-output",
        "selection": {
            "resolved": {
                "targets": [
                    "bad",
                    {"data_object_version_id": "", "output_uri": "s3://bucket/ignored"},
                    {
                        "data_object_version_id": "dov-2",
                        "output_uri": "s3://bucket/target-output",
                        "output_format": "CSV",
                    },
                ]
            }
        },
    }
    assert testing_support._expected_materialization_targets_from_record(record) == [
        {
            "data_object_version_id": "dov-2",
            "output_uri": "s3a://bucket/target-output",
            "output_format": "csv",
        }
    ]

    fallback_targets = testing_support._expected_materialization_targets_from_record(
        {
            "request_id": "req-2",
            "job_id": "job-2",
            "status": "pending",
            "data_object_version_id": "dov-3",
            "sample_count": 5,
            "output_format": "PARQUET",
            "output_uri": "s3://bucket/fallback-output",
        }
    )
    assert fallback_targets == [
        {
            "data_object_version_id": "dov-3",
            "output_uri": "s3a://bucket/fallback-output",
            "output_format": "parquet",
        }
    ]

    delivery = testing_support.MaterializationDeliveryView.model_validate(
        {
            "data_object_version_id": "dov-1",
            "row_count": 5,
            "output_uri": "s3a://bucket/target-output",
            "output_format": "parquet",
            "data_delivery_id": "del-1",
            "delivery_note": _make_delivery_note_entity(delivery_id="del-1", output_uri="s3a://bucket/target-output").model_dump(),
        }
    )
    result = testing_support._build_materialization_result_from_deliveries(
        deliveries=[delivery],
        request_output_uri="s3://bucket/request-output",
        output_format="PARQUET",
        reused_existing=True,
    )
    assert result["data_delivery_id"] == "del-1"
    assert result["delivery_note"]["data_delivery_id"] == "del-1"
    assert result["delivery_summary"]["reused_existing"] is True

    class Repo:
        def get_data_object_version(self, version_id: str):
            del version_id
            return SimpleNamespace(data_object_id="do-1", version=7, attribute_count=2)

        def create_materialized_delivery_note(self, payload: dict):
            delivery_id = f"del-{payload['data_object_version_id']}"
            return _make_delivery_note_entity(
                delivery_id=delivery_id,
                output_uri=str(payload.get("delivery_location") or ""),
                row_count=int(payload.get("record_count") or 0),
            )

    batch = testing_support._create_materialized_delivery_completions_from_record(
        request_id="req-1",
        record={
            "request_id": "req-1",
            "job_id": "job-1",
            "status": "pending",
            "data_object_version_id": "dov-1",
            "sample_count": 5,
            "output_format": "parquet",
            "output_uri": "s3://bucket/request-output",
            "correlation_id": "corr-1",
        },
        target_results=[
            {
                "data_object_version_id": "dov-1",
                "row_count": 5,
                "output_uri": "s3://bucket/request-output",
                "output_format": "PARQUET",
            }
        ],
        catalog_repository=Repo(),
        reused_existing=False,
    )
    assert batch.data_delivery_id == "del-dov-1"
    assert batch.delivery_note is not None
    assert batch.delivery_summary["target_count"] == 1


@pytest.mark.anyio
async def test_materialization_registration_helpers_cover_fail_fast_and_success_paths(monkeypatch) -> None:
    delivery = testing_support.MaterializationDeliveryView.model_validate(
        {
            "data_object_version_id": "dov-1",
            "row_count": 5,
            "output_uri": "s3a://bucket/output",
            "output_format": "parquet",
            "data_delivery_id": "del-1",
            "delivery_note": _make_delivery_note_entity(delivery_id="del-1", output_uri="s3a://bucket/output").model_dump(),
        }
    )
    batch = testing_support.MaterializationCompletionBatchView.model_validate(
        {
            "request_id": "req-1",
            "data_deliveries": [delivery.model_dump()],
            "delivery_summary": {"target_count": 1},
            "data_delivery_id": "del-1",
            "delivery_note": delivery.delivery_note.model_dump(),
        }
    )

    payload = testing_support.ReportTestDataMaterializationCompletionRequest(
        row_count=5,
        output_uri="s3a://bucket/output",
        output_format="parquet",
    )

    monkeypatch.setattr(testing_support, "_resolve_test_data_redis_url", lambda: None)
    with pytest.raises(HTTPException) as queue_missing:
        await testing_support._register_materialized_delivery_completion(
            request_id="req-1",
            payload=payload,
            catalog_repository=SimpleNamespace(),
        )
    assert queue_missing.value.status_code == 503

    monkeypatch.setattr(testing_support, "_resolve_test_data_redis_url", lambda: "redis://example")

    async def _read_missing(*_args, **_kwargs):
        return None

    monkeypatch.setattr(testing_support, "_read_test_data_materialization_record", _read_missing)
    with pytest.raises(HTTPException) as missing_record:
        await testing_support._register_materialized_delivery_completion(
            request_id="req-404",
            payload=payload,
            catalog_repository=SimpleNamespace(),
        )
    assert missing_record.value.status_code == 404

    async def _read_record(_redis_url: str, _request_id: str) -> dict:
        return {
            "request_id": "req-1",
            "job_id": "job-1",
            "status": "pending",
            "data_object_version_id": "dov-1",
            "sample_count": 5,
            "output_format": "parquet",
            "output_uri": "s3a://bucket/output",
            "correlation_id": "corr-1",
            "selection": {
                "resolved": {
                    "targets": [
                        {"data_object_version_id": "dov-1", "output_uri": "s3a://bucket/output", "output_format": "parquet"},
                        {"data_object_version_id": "dov-2", "output_uri": "s3a://bucket/output-2", "output_format": "delta"},
                    ]
                }
            },
        }

    monkeypatch.setattr(testing_support, "_read_test_data_materialization_record", _read_record)

    with pytest.raises(HTTPException) as output_mismatch:
        await testing_support._register_materialized_delivery_completion(
            request_id="req-1",
            payload=testing_support.ReportTestDataMaterializationCompletionRequest(
                row_count=5,
                output_uri="s3a://bucket/other",
                output_format="parquet",
            ),
            catalog_repository=SimpleNamespace(),
        )
    assert output_mismatch.value.status_code == 409
    assert output_mismatch.value.detail["error"] == "materialization_output_mismatch"

    with pytest.raises(HTTPException) as format_mismatch:
        await testing_support._register_materialized_delivery_completion(
            request_id="req-1",
            payload=testing_support.ReportTestDataMaterializationCompletionRequest(
                row_count=5,
                output_uri="s3a://bucket/output",
                output_format="delta",
            ),
            catalog_repository=SimpleNamespace(),
        )
    assert format_mismatch.value.status_code == 409
    assert format_mismatch.value.detail["error"] == "materialization_format_mismatch"

    async def _read_real_evidence_record(_redis_url: str, _request_id: str) -> dict:
        return {
            "request_id": "req-1",
            "job_id": "job-1",
            "status": "pending",
            "data_object_version_id": "dov-1",
            "sample_count": 5,
            "output_format": "parquet",
            "output_uri": "s3a://dq-evidence/output",
            "correlation_id": "corr-1",
            "selection": {
                "resolved": {
                    "targets": [
                        {"data_object_version_id": "dov-1", "output_uri": "s3a://dq-evidence/output", "output_format": "parquet"},
                        {"data_object_version_id": "dov-2", "output_uri": "s3a://bucket/output-2", "output_format": "delta"},
                    ]
                }
            },
        }

    monkeypatch.setattr(testing_support, "_read_test_data_materialization_record", _read_real_evidence_record)

    with pytest.raises(HTTPException) as namespace_conflict:
        await testing_support._register_materialized_delivery_completion(
            request_id="req-1",
            payload=testing_support.ReportTestDataMaterializationCompletionRequest(
                row_count=5,
                output_uri="s3a://dq-evidence/output",
                output_format="parquet",
            ),
            catalog_repository=SimpleNamespace(),
        )
    assert namespace_conflict.value.status_code == 409
    assert namespace_conflict.value.detail["error"] == "synthetic_output_namespace_conflict"
    assert namespace_conflict.value.detail["matched_terms"] == ["evidence"]

    monkeypatch.setattr(testing_support, "_read_test_data_materialization_record", _read_record)
    captured_single: dict[str, object] = {}

    def _fake_create_single(**kwargs):
        captured_single.update(kwargs)
        return batch

    monkeypatch.setattr(testing_support, "_create_materialized_delivery_completions_from_record", _fake_create_single)
    single = await testing_support._register_materialized_delivery_completion(
        request_id="req-1",
        payload=payload,
        catalog_repository=SimpleNamespace(),
    )
    assert single.data_delivery_id == "del-1"
    assert captured_single["target_results"] == [
        {
            "data_object_version_id": "dov-1",
            "row_count": 5,
            "output_uri": "s3a://bucket/output",
            "output_format": "parquet",
        }
    ]

    monkeypatch.setattr(testing_support, "_resolve_test_data_redis_url", lambda: None)
    with pytest.raises(HTTPException) as batch_queue_missing:
        await testing_support._register_materialized_delivery_completions(
            request_id="req-1",
            target_results=[],
            catalog_repository=SimpleNamespace(),
        )
    assert batch_queue_missing.value.status_code == 503

    monkeypatch.setattr(testing_support, "_resolve_test_data_redis_url", lambda: "redis://example")
    monkeypatch.setattr(testing_support, "_read_test_data_materialization_record", _read_missing)
    with pytest.raises(HTTPException) as batch_missing_record:
        await testing_support._register_materialized_delivery_completions(
            request_id="req-404",
            target_results=[],
            catalog_repository=SimpleNamespace(),
        )
    assert batch_missing_record.value.status_code == 404

    monkeypatch.setattr(testing_support, "_read_test_data_materialization_record", _read_record)
    with pytest.raises(HTTPException) as target_mismatch:
        await testing_support._register_materialized_delivery_completions(
            request_id="req-1",
            target_results=[
                testing_support.MaterializationTargetResultRequest(
                    data_object_version_id="dov-1",
                    row_count=5,
                    output_uri="s3a://bucket/output",
                    output_format="parquet",
                )
            ],
            catalog_repository=SimpleNamespace(),
        )
    assert target_mismatch.value.status_code == 409
    assert target_mismatch.value.detail["error"] == "materialization_target_mismatch"

    with pytest.raises(HTTPException) as batch_output_mismatch:
        await testing_support._register_materialized_delivery_completions(
            request_id="req-1",
            target_results=[
                testing_support.MaterializationTargetResultRequest(
                    data_object_version_id="dov-1",
                    row_count=5,
                    output_uri="s3a://bucket/other",
                    output_format="parquet",
                ),
                testing_support.MaterializationTargetResultRequest(
                    data_object_version_id="dov-2",
                    row_count=6,
                    output_uri="s3a://bucket/output-2",
                    output_format="delta",
                ),
            ],
            catalog_repository=SimpleNamespace(),
        )
    assert batch_output_mismatch.value.status_code == 409
    assert batch_output_mismatch.value.detail["error"] == "materialization_output_mismatch"

    with pytest.raises(HTTPException) as batch_format_mismatch:
        await testing_support._register_materialized_delivery_completions(
            request_id="req-1",
            target_results=[
                testing_support.MaterializationTargetResultRequest(
                    data_object_version_id="dov-1",
                    row_count=5,
                    output_uri="s3a://bucket/output",
                    output_format="parquet",
                ),
                testing_support.MaterializationTargetResultRequest(
                    data_object_version_id="dov-2",
                    row_count=6,
                    output_uri="s3a://bucket/output-2",
                    output_format="parquet",
                ),
            ],
            catalog_repository=SimpleNamespace(),
        )
    assert batch_format_mismatch.value.status_code == 409
    assert batch_format_mismatch.value.detail["error"] == "materialization_format_mismatch"

    monkeypatch.setattr(testing_support, "_read_test_data_materialization_record", _read_real_evidence_record)

    with pytest.raises(HTTPException) as batch_namespace_conflict:
        await testing_support._register_materialized_delivery_completions(
            request_id="req-1",
            target_results=[
                testing_support.MaterializationTargetResultRequest(
                    data_object_version_id="dov-1",
                    row_count=5,
                    output_uri="s3a://dq-evidence/output",
                    output_format="parquet",
                ),
                testing_support.MaterializationTargetResultRequest(
                    data_object_version_id="dov-2",
                    row_count=6,
                    output_uri="s3a://bucket/output-2",
                    output_format="delta",
                ),
            ],
            catalog_repository=SimpleNamespace(),
        )
    assert batch_namespace_conflict.value.status_code == 409
    assert batch_namespace_conflict.value.detail["error"] == "synthetic_output_namespace_conflict"
    assert batch_namespace_conflict.value.detail["matched_terms"] == ["evidence"]

    monkeypatch.setattr(testing_support, "_read_test_data_materialization_record", _read_record)
    captured_batch: dict[str, object] = {}

    def _fake_create_batch(**kwargs):
        captured_batch.update(kwargs)
        return batch

    monkeypatch.setattr(testing_support, "_create_materialized_delivery_completions_from_record", _fake_create_batch)
    result_batch = await testing_support._register_materialized_delivery_completions(
        request_id="req-1",
        target_results=[
            testing_support.MaterializationTargetResultRequest(
                data_object_version_id="dov-1",
                row_count=5,
                output_uri="s3a://bucket/output",
                output_format="parquet",
            ),
            testing_support.MaterializationTargetResultRequest(
                data_object_version_id="dov-2",
                row_count=6,
                output_uri="s3a://bucket/output-2",
                output_format="delta",
            ),
        ],
        catalog_repository=SimpleNamespace(),
    )
    assert result_batch.data_delivery_id == "del-1"
    assert captured_batch["target_results"] == [
        {
            "data_object_version_id": "dov-1",
            "row_count": 5,
            "output_uri": "s3a://bucket/output",
            "output_format": "parquet",
        },
        {
            "data_object_version_id": "dov-2",
            "row_count": 6,
            "output_uri": "s3a://bucket/output-2",
            "output_format": "delta",
        },
    ]


@pytest.mark.anyio
async def test_materialization_record_wrappers_and_enqueue_fail_fast_paths(monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def _fake_set_json(redis_url: str, key: str, payload: dict, ttl_seconds: int) -> None:
        captured["set_json"] = (redis_url, key, payload, ttl_seconds)

    monkeypatch.setattr(testing_support, "_redis_set_json", _fake_set_json)
    await testing_support._write_test_data_materialization_record(
        "redis://example",
        {
            "request_id": "req-1",
            "job_id": "job-1",
            "status": "pending",
            "data_object_version_id": "dov-1",
            "sample_count": 5,
            "output_format": "parquet",
            "output_uri": "s3://bucket/output",
        },
    )
    assert captured["set_json"][1] == "test-data-materialization-request:req-1"

    async def _fake_get_none(_redis_url: str, _key: str):
        return None

    monkeypatch.setattr(testing_support, "_redis_get_json", _fake_get_none)
    assert await testing_support._read_test_data_materialization_record("redis://example", "req-none") is None

    async def _fake_get_valid(_redis_url: str, _key: str):
        return {
            "request_id": "req-2",
            "job_id": "job-2",
            "status": "pending",
            "data_object_version_id": "dov-2",
            "sample_count": 3,
            "output_format": "parquet",
            "output_uri": "s3://bucket/output-2",
        }

    monkeypatch.setattr(testing_support, "_redis_get_json", _fake_get_valid)
    entity = await testing_support._read_test_data_materialization_record("redis://example", "req-2")
    assert entity is not None
    assert entity.request_id == "req-2"

    request = SimpleNamespace(headers={})
    repo_without_attrs = SimpleNamespace(list_attributes_catalog=lambda _version_id: [])

    monkeypatch.setattr(testing_support, "_resolve_test_data_redis_url", lambda: None)
    with pytest.raises(HTTPException) as no_queue:
        await testing_support._enqueue_test_data_materialization_request(
            request=request,
            version_id="dov-1",
            sample_count=5,
            output_format="parquet",
            output_uri="s3://bucket/output",
            catalog_repository=repo_without_attrs,
        )
    assert no_queue.value.status_code == 503

    monkeypatch.setattr(testing_support, "_resolve_test_data_redis_url", lambda: "redis://example")
    monkeypatch.setattr(testing_support, "_resolve_test_data_materialization_queue_key", lambda: "queue")
    monkeypatch.setattr(testing_support, "_resolve_test_data_materialization_processing_queue_key", lambda queue_key: f"{queue_key}:processing")

    async def _raise_query_error(*_args, **_kwargs):
        raise RuntimeError("redis down")

    monkeypatch.setattr(testing_support, "_redis_llen", _raise_query_error)
    with pytest.raises(HTTPException) as query_error:
        await testing_support._enqueue_test_data_materialization_request(
            request=request,
            version_id="dov-1",
            sample_count=5,
            output_format="parquet",
            output_uri="s3://bucket/output",
            catalog_repository=repo_without_attrs,
        )
    assert query_error.value.status_code == 503

    async def _queue_full(_redis_url: str, queue_key: str) -> int:
        return 20 if queue_key == "queue" else 0

    monkeypatch.setattr(testing_support, "_redis_llen", _queue_full)
    with pytest.raises(HTTPException) as queue_limit:
        await testing_support._enqueue_test_data_materialization_request(
            request=request,
            version_id="dov-1",
            sample_count=5,
            output_format="parquet",
            output_uri="s3://bucket/output",
            catalog_repository=repo_without_attrs,
        )
    assert queue_limit.value.status_code == 429
    assert queue_limit.value.detail["error"] == "queue_limit_exceeded"

    async def _queue_ok(*_args, **_kwargs) -> int:
        return 0

    monkeypatch.setattr(testing_support, "_redis_llen", _queue_ok)
    with pytest.raises(HTTPException) as invalid_target:
        await testing_support._enqueue_test_data_materialization_request(
            request=request,
            version_id="dov-1",
            sample_count=5,
            output_format="parquet",
            output_uri="s3://bucket/output",
            catalog_repository=repo_without_attrs,
            targets=["bad", {"data_object_version_id": "dov-1"}],
        )
    assert invalid_target.value.status_code == 422
    assert invalid_target.value.detail["error"] == "invalid_materialization_target"

    with pytest.raises(HTTPException) as missing_attributes:
        await testing_support._enqueue_test_data_materialization_request(
            request=request,
            version_id="dov-1",
            sample_count=5,
            output_format="parquet",
            output_uri="s3://bucket/output",
            catalog_repository=repo_without_attrs,
        )
    assert missing_attributes.value.status_code == 422
    assert missing_attributes.value.detail["error"] == "missing_attributes"


@pytest.mark.anyio
async def test_enqueue_materialization_request_covers_selected_attributes_default_output_and_reuse(monkeypatch) -> None:
    request = SimpleNamespace(headers={"X-Correlation-ID": "corr-1"})
    captured_writes: list[dict[str, object]] = []
    captured_completion: dict[str, object] = {}

    class Repo:
        def list_attributes_catalog(self, _version_id: str):
            return [
                {"name": "email", "type": "text", "nullable": True, "format": "email", "is_primary_key": False},
                {"name": "status", "type": "text", "nullable": True, "format": "", "is_primary_key": False},
            ]

    monkeypatch.setattr(testing_support, "_resolve_test_data_redis_url", lambda: "redis://example")
    monkeypatch.setattr(testing_support, "_resolve_test_data_materialization_queue_key", lambda: "queue")
    monkeypatch.setattr(testing_support, "_resolve_test_data_materialization_processing_queue_key", lambda queue_key: f"{queue_key}:processing")

    async def _queue_ok(*_args, **_kwargs) -> int:
        return 0

    monkeypatch.setattr(testing_support, "_redis_llen", _queue_ok)
    monkeypatch.setattr(testing_support, "_resolve_test_data_output_prefix", lambda: "s3a://dq-test-data/generated")
    monkeypatch.setattr(testing_support, "_s3_prefix_has_objects", lambda **_kwargs: True)
    monkeypatch.setattr(testing_support, "_current_timestamp", lambda: "2026-04-21T12:00:00Z")
    monkeypatch.setattr(testing_support, "_inject_queue_trace_headers", lambda payload: payload["headers"].update({"traceparent": "tp-1"}))

    async def _fake_write(_redis_url: str, record: dict) -> None:
        captured_writes.append(record)

    monkeypatch.setattr(testing_support, "_write_test_data_materialization_record", _fake_write)

    completion_batch = testing_support.MaterializationCompletionBatchView.model_validate(
        {
            "request_id": "req-1",
            "data_deliveries": [
                {
                    "data_object_version_id": "dov-1",
                    "row_count": 0,
                    "output_uri": "s3a://dq-test-data/generated/data_object_version_id=dov-1/attr_hash=fixed/sample_count=5/format=parquet",
                    "output_format": "parquet",
                    "data_delivery_id": "del-1",
                    "delivery_note": _make_delivery_note_entity(
                        delivery_id="del-1",
                        output_uri="s3a://dq-test-data/generated/data_object_version_id=dov-1/attr_hash=fixed/sample_count=5/format=parquet",
                        row_count=0,
                    ).model_dump(),
                }
            ],
            "delivery_summary": {"target_count": 1, "data_delivery_count": 1, "total_row_count": 0, "reused_existing": True, "data_delivery_ids": ["del-1"]},
            "data_delivery_id": "del-1",
            "delivery_note": _make_delivery_note_entity(
                delivery_id="del-1",
                output_uri="s3a://dq-test-data/generated/data_object_version_id=dov-1/attr_hash=fixed/sample_count=5/format=parquet",
                row_count=0,
            ).model_dump(),
        }
    )

    def _fake_completion(**kwargs):
        captured_completion.update(kwargs)
        return completion_batch

    monkeypatch.setattr(testing_support, "_create_materialized_delivery_completions_from_record", _fake_completion)

    with pytest.raises(HTTPException) as unknown_attributes:
        await testing_support._enqueue_test_data_materialization_request(
            request=request,
            version_id="dov-1",
            sample_count=5,
            output_format="parquet",
            output_uri=None,
            selected_attribute_names=["missing"],
            catalog_repository=Repo(),
        )
    assert unknown_attributes.value.status_code == 422
    assert unknown_attributes.value.detail["error"] == "unknown_attributes"

    with pytest.raises(HTTPException) as namespace_conflict:
        await testing_support._enqueue_test_data_materialization_request(
            request=request,
            version_id="dov-1",
            sample_count=5,
            output_format="parquet",
            output_uri="s3a://dq-evidence/generated/data_object_version_id=dov-1/attr_hash=fixed/sample_count=5/format=parquet",
            selected_attribute_names=["email"],
            catalog_repository=Repo(),
        )
    assert namespace_conflict.value.status_code == 422
    assert namespace_conflict.value.detail["error"] == "synthetic_output_namespace_conflict"
    assert namespace_conflict.value.detail["matched_terms"] == ["evidence"]

    record = await testing_support._enqueue_test_data_materialization_request(
        request=request,
        version_id="dov-1",
        sample_count=5,
        output_format="parquet",
        output_uri=None,
        selected_attribute_names=["email"],
        catalog_repository=Repo(),
        selection={"selector_type": "data_object_version_id"},
        request_contract="catalog_materialization_v1",
    )
    assert record.status == "completed"
    assert record.result is not None
    assert record.result["reused_existing"] is True
    assert captured_completion["target_results"][0]["output_format"] == "parquet"
    assert captured_completion["target_results"][0]["data_object_version_id"] == "dov-1"
    assert captured_writes[-1]["status"] == "completed"
    assert str(record.output_uri).startswith("s3a://dq-test-data/generated/data_object_version_id=dov-1/")
