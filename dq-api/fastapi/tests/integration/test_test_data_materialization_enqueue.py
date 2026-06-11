from __future__ import annotations

import base64
import importlib
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit
from unittest.mock import patch

import pytest

from app.core.config import get_settings


@pytest.fixture
def _no_database(monkeypatch: pytest.MonkeyPatch) -> None:
    # Force dependency injection to use in-memory repositories.
    monkeypatch.setenv("DQ_DB_LOCAL_URL", "")
    monkeypatch.setenv("REQUIRE_DATABASE", "false")
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _materialization_queue_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_DATA_MATERIALIZATION_QUEUE_KEY", "dq-test-data:materialize")


class _SharedRedisClient:
    def __init__(self, store: dict[str, str]) -> None:
        self._store = store

    def get(self, key: str) -> str | None:
        return self._store.get(key)

    def set(self, key: str, value: str, ex: int | None = None) -> None:
        _ = ex
        self._store[key] = value


class _WorkerLoopRedisClient(_SharedRedisClient):
    def __init__(self, store: dict[str, str], queued_jobs: list[str]) -> None:
        super().__init__(store)
        self._queued_jobs = list(queued_jobs)
        self._processing_jobs: list[str] = []

    def brpoplpush(self, queue_key: str, processing_queue_key: str, timeout: int) -> str | None:
        _ = queue_key, processing_queue_key, timeout
        if self._queued_jobs:
            job = self._queued_jobs.pop(0)
            self._processing_jobs.append(job)
            return job
        raise KeyboardInterrupt()

    def lrem(self, queue_key: str, count: int, value: str) -> int:
        _ = queue_key, count
        try:
            self._processing_jobs.remove(value)
        except ValueError:
            return 0
        return 1


class _SharedRedisHarness:
    def __init__(self) -> None:
        self.records: dict[str, str] = {}
        self.queue_payloads: list[dict[str, object]] = []

    async def llen(self, _redis_url: str, key: str) -> int:
        _ = key
        return 0

    async def set_json(self, _redis_url: str, key: str, payload: dict, ttl_seconds: int) -> None:
        _ = ttl_seconds
        self.records[key] = json.dumps(payload)

    async def get_json(self, _redis_url: str, key: str) -> dict | None:
        raw = self.records.get(key)
        return json.loads(raw) if raw is not None else None

    async def lpush(self, _redis_url: str, queue_key: str, payload: dict) -> None:
        _ = queue_key
        self.queue_payloads.append(payload)

    def worker_client(self) -> _SharedRedisClient:
        return _SharedRedisClient(self.records)

    def worker_loop_client(self) -> _WorkerLoopRedisClient:
        return _WorkerLoopRedisClient(self.records, [json.dumps(payload) for payload in self.queue_payloads])


class _WorkerTokenProvider:
    def get_token(self, correlation_id: str | None = None) -> str:
        _ = correlation_id
        header = {"alg": "none", "typ": "JWT"}
        payload = {
            "sub": "worker-user",
            "preferred_username": "worker",
            "iss": os.environ.get("SSO_PUBLIC_ISSUER_URL", "http://keycloak.jac.dot:8080/realms/jaccloud"),
            "aud": ["dq-rules-ui"],
            "scope": "dq:rules:test dq:rules:write",
        }

        def _encode(value: dict[str, object]) -> str:
            return base64.urlsafe_b64encode(json.dumps(value).encode("utf-8")).decode("utf-8").rstrip("=")

        return f"{_encode(header)}.{_encode(payload)}.signature"


@pytest.fixture
def worker_module():
    repo_root = Path(__file__).resolve().parents[4]
    engine_dir = str(repo_root / "dq-engine")
    dq_utils_src = str(repo_root / "dq-utils" / "src")
    if dq_utils_src not in sys.path:
        sys.path.insert(0, dq_utils_src)
    if engine_dir not in sys.path:
        sys.path.insert(0, engine_dir)
    return importlib.import_module("test_data_materialization_worker")


@pytest.fixture
def override_materialization_repositories():
    from app.core.dependencies import get_data_catalog_repository
    from app.core.dependencies import get_gx_execution_run_repository
    from app.infrastructure.repositories.in_memory_data_catalog_repository import InMemoryDataCatalogRepository
    from app.infrastructure.repositories.in_memory_gx_execution_run_repository import InMemoryGxExecutionRunRepository
    from app.main import app

    def _apply(repository: InMemoryDataCatalogRepository | None = None):
        resolved_repository = repository or InMemoryDataCatalogRepository()
        app.dependency_overrides[get_data_catalog_repository] = lambda: resolved_repository
        app.dependency_overrides[get_gx_execution_run_repository] = lambda: InMemoryGxExecutionRunRepository()
        return resolved_repository

    yield _apply

    app.dependency_overrides.pop(get_data_catalog_repository, None)
    app.dependency_overrides.pop(get_gx_execution_run_repository, None)


def test_materialization_enqueue_returns_202_and_pushes_queue_payload(
    client,
    auth_headers,
    monkeypatch: pytest.MonkeyPatch,
    _no_database,
    override_materialization_repositories,
):
    from app.api.v1 import test_data_materialization_api as materialization_api_module

    override_materialization_repositories()
    monkeypatch.setenv("REDIS_URL", "redis://example:6379/0")

    captured: dict[str, object] = {}

    async def _fake_llen(_redis_url: str, key: str) -> int:
        captured.setdefault("llen_calls", []).append(key)
        return 0

    async def _fake_write(_redis_url: str, record: dict) -> None:
        captured["record"] = record

    async def _fake_lpush(_redis_url: str, queue_key: str, payload: dict) -> None:
        captured["queue_key"] = queue_key
        captured["queue_payload"] = payload

    monkeypatch.setattr(materialization_api_module, "_redis_llen", _fake_llen)
    monkeypatch.setattr(materialization_api_module, "_write_test_data_materialization_record", _fake_write)
    monkeypatch.setattr(materialization_api_module, "_redis_lpush", _fake_lpush)
    monkeypatch.setattr(materialization_api_module, "_s3_prefix_has_objects", lambda **kwargs: False)

    resp = client.post(
        "/api/rulebuilder/v1/test-data/materializations",
        headers=auth_headers("dq:rules:test", "dq:rules:write"),
        json={
            "data_object_version_id": "dov-1",
            "sample_count": 10,
            "output_format": "parquet",
            "output_uri": "s3a://dq-test-data/tests/dov-1",
        },
    )

    assert resp.status_code == 202
    body = resp.json()

    # Backend contract: snake_case.
    assert body["data_object_version_id"] == "dov-1"
    assert body["sample_count"] == 10
    assert body["output_format"] == "parquet"
    assert body["output_uri"].startswith("s3a://")
    assert body["status"] == "pending"

    assert captured["queue_key"]
    queue_payload = captured["queue_payload"]
    assert isinstance(queue_payload, dict)
    assert queue_payload["type"] == "test_data_materialization"
    assert queue_payload["payload"]["data_object_version_id"] == "dov-1"


def test_materialization_returns_429_when_queue_limit_exceeded(
    client,
    auth_headers,
    monkeypatch: pytest.MonkeyPatch,
    _no_database,
    override_materialization_repositories,
):
    from app.api.v1 import test_data_materialization_api as materialization_api_module

    override_materialization_repositories()
    monkeypatch.setenv("REDIS_URL", "redis://example:6379/0")
    monkeypatch.setenv("TEST_DATA_MATERIALIZATION_MAX_PENDING", "1")
    monkeypatch.setenv("TEST_DATA_MATERIALIZATION_MAX_IN_FLIGHT", "1")

    async def _fake_llen(_redis_url: str, key: str) -> int:
        # Simulate a saturated queue.
        return 1

    monkeypatch.setattr(materialization_api_module, "_redis_llen", _fake_llen)

    resp = client.post(
        "/api/rulebuilder/v1/test-data/materializations",
        headers=auth_headers("dq:rules:test", "dq:rules:write"),
        json={
            "data_object_version_id": "v1",
            "sample_count": 10,
            "output_format": "parquet",
            "output_uri": "s3a://dq-test-data/tests/v1",
        },
    )

    assert resp.status_code == 429
    detail = resp.json()["detail"]
    assert detail["error"] == "queue_limit_exceeded"


def test_catalog_materialization_dataset_batch_completion_creates_retrievable_notes(
    client,
    auth_headers,
    monkeypatch: pytest.MonkeyPatch,
    _no_database,
    override_materialization_repositories,
):
    from app.api.v1 import test_data_materialization_api as materialization_api_module
    from app.infrastructure.repositories.in_memory_data_catalog_repository import InMemoryDataCatalogRepository

    repository = override_materialization_repositories(InMemoryDataCatalogRepository())
    monkeypatch.setenv("REDIS_URL", "redis://example:6379/0")

    captured: dict[str, object] = {}

    async def _fake_llen(_redis_url: str, key: str) -> int:
        captured.setdefault("llen_calls", []).append(key)
        return 0

    async def _fake_set_json(_redis_url: str, key: str, payload: dict, ttl_seconds: int) -> None:
        captured["set_key"] = key
        captured["set_ttl"] = ttl_seconds
        captured["record"] = payload

    async def _fake_lpush(_redis_url: str, queue_key: str, payload: dict) -> None:
        captured["queue_key"] = queue_key
        captured["queue_payload"] = payload

    async def _fake_read(_redis_url: str, request_id: str) -> dict | None:
        record = captured.get("record")
        if isinstance(record, dict) and str(record.get("request_id") or "") == request_id:
            return record
        return None

    async def _fake_write(_redis_url: str, record: dict) -> None:
        captured["record"] = record

    monkeypatch.setattr(materialization_api_module, "_resolve_test_data_redis_url", lambda: "redis://example:6379/0")
    monkeypatch.setattr(materialization_api_module, "_redis_llen", _fake_llen)
    monkeypatch.setattr(materialization_api_module, "_redis_lpush", _fake_lpush)
    monkeypatch.setattr(materialization_api_module, "_write_test_data_materialization_record", _fake_write)
    monkeypatch.setattr(materialization_api_module, "_s3_prefix_has_objects", lambda **_kwargs: False)
    monkeypatch.setattr(materialization_api_module, "_read_test_data_materialization_record", _fake_read)

    try:
        create_response = client.post(
            "/api/data-catalog/v1/materialization-requests",
            headers=auth_headers("dq:rules:test", "dq:rules:write"),
            json={
                "data_set_id": "ds-1",
                "sample_count": 12,
                "output_format": "parquet",
                "output_uri": "s3a://dq-test-data/generated/catalog-integration-batch",
            },
        )

        assert create_response.status_code == 202
        create_payload = create_response.json()
        assert create_payload["request_contract"] == "catalog_materialization_v1"
        assert create_payload["target_data_object_version_ids"] == ["dov-3", "dov-23"]

        queue_payload = captured["queue_payload"]
        assert isinstance(queue_payload, dict)
        targets = queue_payload["payload"]["targets"]
        assert [target["data_object_version_id"] for target in targets] == ["dov-3", "dov-23"]

        request_id = create_payload["request_id"]
        completion_response = client.post(
            f"/api/data-catalog/v1/materialization-requests/{request_id}/complete",
            headers=auth_headers("dq:rules:test", "dq:rules:write"),
            json={
                "target_results": [
                    {
                        "data_object_version_id": target["data_object_version_id"],
                        "row_count": 12 + index,
                        "output_uri": target["output_uri"],
                        "output_format": target["output_format"],
                    }
                    for index, target in enumerate(targets)
                ]
            },
        )

        assert completion_response.status_code == 200
        completion_payload = completion_response.json()
        assert len(completion_payload["data_deliveries"]) == 2

        noted_versions: set[str] = set()
        for delivery in completion_payload["data_deliveries"]:
            delivery_id = delivery["data_delivery_id"]
            note_response = client.get(
                f"/api/data-catalog/v1/data-deliveries/{delivery_id}/note",
                headers=auth_headers("dq:rules:read"),
            )

            assert note_response.status_code == 200
            note_payload = note_response.json()
            assert note_payload["data_delivery_id"] == delivery_id
            assert note_payload["object_storage_classification"] == "synthetic_test"
            assert note_payload["evidence_classification"] == "synthetic_result"
            assert note_payload["metadata_json"]["materialization_request_id"] == request_id
            noted_versions.add(note_payload["data_object_version_id"])

        assert noted_versions == {"dov-3", "dov-23"}
    finally:
        pass


def test_catalog_materialization_worker_roundtrip_marks_request_completed(
    client,
    auth_headers,
    monkeypatch: pytest.MonkeyPatch,
    _no_database,
    worker_module,
    override_materialization_repositories,
):
    from app.api.v1 import test_data_materialization_api as materialization_api_module
    from app.infrastructure.repositories.in_memory_data_catalog_repository import InMemoryDataCatalogRepository

    repository = override_materialization_repositories(InMemoryDataCatalogRepository())
    monkeypatch.setenv("REDIS_URL", "redis://example:6379/0")

    shared_redis = _SharedRedisHarness()

    async def _catalog_read(_redis_url: str, request_id: str) -> dict | None:
        return await shared_redis.get_json(
            _redis_url,
            materialization_api_module._test_data_materialization_request_key(request_id),
        )

    async def _catalog_write(_redis_url: str, record: dict) -> None:
        key = materialization_api_module._test_data_materialization_request_key(str(record.get("request_id") or ""))
        shared_redis.records[key] = json.dumps(record)

    monkeypatch.setattr(materialization_api_module, "_resolve_test_data_redis_url", lambda: "redis://example:6379/0")
    monkeypatch.setattr(materialization_api_module, "_redis_llen", shared_redis.llen)
    monkeypatch.setattr(materialization_api_module, "_redis_lpush", shared_redis.lpush)
    monkeypatch.setattr(materialization_api_module, "_write_test_data_materialization_record", _catalog_write)
    monkeypatch.setattr(materialization_api_module, "_read_test_data_materialization_record", _catalog_read)
    monkeypatch.setattr(materialization_api_module, "_s3_prefix_has_objects", lambda **_kwargs: False)

    def _route_worker_request(*, method: str, url: str, headers: dict | None = None, json: dict | None = None, timeout: int | float | None = None):
        _ = timeout
        parsed = urlsplit(url)
        target = parsed.path or "/"
        if parsed.query:
            target = f"{target}?{parsed.query}"
        return client.request(method=method, url=target, headers=headers, json=json)

    worker_config = worker_module.WorkerConfig(
        redis_url="redis://example:6379/0",
        queue_key="dq-test-data:materialize",
        processing_queue_key="dq-test-data:materialize:processing",
        api_url="http://testserver",
        spark_master="local[*]",
        spark_ui_port=4040,
        output_prefix="s3a://dq-test-data",
        s3_endpoint="http://aistor:9000",
        s3_access_key="aistor",
        s3_secret_key="aistorpass",
        s3_region="eu-west-1",
        s3_path_style_access=True,
        s3_ssl_enabled=False,
        max_rows_per_request=5000,
        poll_timeout_seconds=5,
    )

    try:
        create_response = client.post(
            "/api/data-catalog/v1/materialization-requests",
            headers=auth_headers("dq:rules:test", "dq:rules:write"),
            json={
                "data_set_id": "ds-1",
                "sample_count": 12,
                "output_format": "parquet",
                "output_uri": "s3a://dq-test-data/generated/catalog-worker-roundtrip",
            },
        )

        assert create_response.status_code == 202
        create_payload = create_response.json()
        request_id = create_payload["request_id"]
        assert create_payload["status"] == "pending"
        assert create_payload["request_contract"] == "catalog_materialization_v1"
        assert create_payload["selection"]["selector_type"] == "data_set_id"
        assert len(shared_redis.queue_payloads) == 1

        with patch.object(worker_module, "_ensure_bucket_exists", return_value=None), patch.object(
            worker_module,
            "_create_spark_session",
            return_value=object(),
        ), patch.object(
            worker_module,
            "_build_rows",
            side_effect=[
                [{"id": 1}] * 12,
                [{"contact_id": "c-1"}] * 12,
            ],
        ), patch.object(
            worker_module,
            "_write_dataset",
            side_effect=[12, 9],
        ), patch.object(
            worker_module.requests,
            "request",
            side_effect=_route_worker_request,
        ):
            worker_module._process_job(
                worker_config,
                r=shared_redis.worker_client(),
                raw_job=json.dumps(shared_redis.queue_payloads[0]),
                token_provider=_WorkerTokenProvider(),
            )

        status_response = client.get(
            f"/api/data-catalog/v1/materialization-requests/{request_id}",
            headers=auth_headers("dq:rules:test", "dq:rules:write"),
        )

        assert status_response.status_code == 200
        status_payload = status_response.json()
        assert status_payload["status"] == "completed"
        assert status_payload["request_contract"] == "catalog_materialization_v1"
        assert status_payload["target_data_object_version_ids"] == ["dov-3", "dov-23"]
        assert status_payload["selection"]["selector_type"] == "data_set_id"
        assert status_payload["selection"]["resolved"]["target_count"] == 2
        assert status_payload["result"]["row_count"] == 21
        assert status_payload["result"]["output_uri"] == "s3a://dq-test-data/generated/catalog-worker-roundtrip"
        assert status_payload["result"]["delivery_summary"]["target_count"] == 2
        assert status_payload["result"]["delivery_summary"]["data_delivery_count"] == 2
        assert status_payload["result"]["delivery_summary"]["total_row_count"] == 21
        assert status_payload["result"]["delivery_summary"]["object_storage_classifications"] == ["synthetic_test"]
        assert status_payload["result"]["delivery_summary"]["evidence_classifications"] == ["synthetic_result"]
        assert status_payload["result"]["data_delivery_ids"]
        assert len(status_payload["result"]["data_delivery_ids"]) == 2
        assert len(status_payload["result"]["target_results"]) == 2

        for delivery_id in status_payload["result"]["data_delivery_ids"]:
            note_response = client.get(
                f"/api/data-catalog/v1/data-deliveries/{delivery_id}/note",
                headers=auth_headers("dq:rules:read"),
            )

            assert note_response.status_code == 200
            note_payload = note_response.json()
            assert note_payload["data_delivery_id"] == delivery_id
            assert note_payload["object_storage_classification"] == "synthetic_test"
            assert note_payload["evidence_classification"] == "synthetic_result"
            assert note_payload["metadata_json"]["materialization_request_id"] == request_id
    finally:
        pass


def test_catalog_materialization_reuse_roundtrip_marks_request_completed(
    client,
    auth_headers,
    monkeypatch: pytest.MonkeyPatch,
    _no_database,
    override_materialization_repositories,
):
    from app.api.v1 import test_data_materialization_api as materialization_api_module
    from app.infrastructure.repositories.in_memory_data_catalog_repository import InMemoryDataCatalogRepository

    repository = override_materialization_repositories(InMemoryDataCatalogRepository())
    monkeypatch.setenv("REDIS_URL", "redis://example:6379/0")

    shared_redis = _SharedRedisHarness()

    async def _catalog_read(_redis_url: str, request_id: str) -> dict | None:
        return await shared_redis.get_json(
            _redis_url,
            materialization_api_module._test_data_materialization_request_key(request_id),
        )

    async def _catalog_write(_redis_url: str, record: dict) -> None:
        key = materialization_api_module._test_data_materialization_request_key(str(record.get("request_id") or ""))
        shared_redis.records[key] = json.dumps(record)

    monkeypatch.setattr(materialization_api_module, "_resolve_test_data_redis_url", lambda: "redis://example:6379/0")
    monkeypatch.setattr(materialization_api_module, "_redis_llen", shared_redis.llen)
    monkeypatch.setattr(materialization_api_module, "_redis_lpush", shared_redis.lpush)
    monkeypatch.setattr(materialization_api_module, "_write_test_data_materialization_record", _catalog_write)
    monkeypatch.setattr(materialization_api_module, "_read_test_data_materialization_record", _catalog_read)
    monkeypatch.setattr(materialization_api_module, "_s3_prefix_has_objects", lambda **_kwargs: True)

    try:
        create_response = client.post(
            "/api/data-catalog/v1/materialization-requests",
            headers=auth_headers("dq:rules:test", "dq:rules:write"),
            json={
                "data_set_id": "ds-1",
                "sample_count": 12,
                "output_format": "parquet",
                "output_uri": "s3a://dq-test-data/generated/catalog-reuse-roundtrip",
            },
        )

        assert create_response.status_code == 202
        create_payload = create_response.json()
        request_id = create_payload["request_id"]
        assert create_payload["status"] == "completed"
        assert create_payload["request_contract"] == "catalog_materialization_v1"
        assert create_payload["target_data_object_version_ids"] == ["dov-3", "dov-23"]
        assert create_payload["selection"]["selector_type"] == "data_set_id"
        assert create_payload["result"]["reused_existing"] is True
        assert create_payload["result"]["row_count"] == 0
        assert create_payload["result"]["output_uri"] == "s3a://dq-test-data/generated/catalog-reuse-roundtrip"
        assert create_payload["result"]["delivery_summary"]["target_count"] == 2
        assert create_payload["result"]["delivery_summary"]["data_delivery_count"] == 2
        assert create_payload["result"]["delivery_summary"]["object_storage_classifications"] == ["synthetic_test"]
        assert create_payload["result"]["delivery_summary"]["evidence_classifications"] == ["synthetic_result"]
        assert len(create_payload["result"]["data_delivery_ids"]) == 2
        assert len(create_payload["result"]["target_results"]) == 2
        assert shared_redis.queue_payloads == []

        status_response = client.get(
            f"/api/data-catalog/v1/materialization-requests/{request_id}",
            headers=auth_headers("dq:rules:test", "dq:rules:write"),
        )

        assert status_response.status_code == 200
        status_payload = status_response.json()
        assert status_payload["status"] == "completed"
        assert status_payload["result"]["reused_existing"] is True
        assert status_payload["result"]["data_delivery_ids"] == create_payload["result"]["data_delivery_ids"]
        assert status_payload["result"]["delivery_summary"]["target_count"] == 2
        assert status_payload["selection"]["resolved"]["target_count"] == 2

        for target_result in status_payload["result"]["target_results"]:
            assert target_result["reused_existing"] is True
            assert target_result["row_count"] == 0
            assert target_result["data_delivery_id"] in status_payload["result"]["data_delivery_ids"]

        for delivery_id in status_payload["result"]["data_delivery_ids"]:
            note_response = client.get(
                f"/api/data-catalog/v1/data-deliveries/{delivery_id}/note",
                headers=auth_headers("dq:rules:read"),
            )

            assert note_response.status_code == 200
            note_payload = note_response.json()
            assert note_payload["data_delivery_id"] == delivery_id
            assert note_payload["object_storage_classification"] == "synthetic_test"
            assert note_payload["evidence_classification"] == "synthetic_result"
            assert note_payload["metadata_json"]["materialization_request_id"] == request_id
            assert note_payload["metadata_json"]["reused_existing"] is True
    finally:
        pass


def test_catalog_materialization_worker_storage_failure_marks_request_failed(
    client,
    auth_headers,
    monkeypatch: pytest.MonkeyPatch,
    _no_database,
    worker_module,
):
    from app.api.v1.endpoints import data_catalog as data_catalog_module
    from app.api.v1 import test_data_materialization_api as materialization_api_module
    from app.core.dependencies import get_data_catalog_repository
    from app.infrastructure.repositories.in_memory_data_catalog_repository import InMemoryDataCatalogRepository
    from app.main import app

    repository = InMemoryDataCatalogRepository()
    app.dependency_overrides[get_data_catalog_repository] = lambda: repository
    monkeypatch.setenv("REDIS_URL", "redis://example:6379/0")

    shared_redis = _SharedRedisHarness()

    async def _catalog_read(_redis_url: str, request_id: str) -> dict | None:
        return await shared_redis.get_json(
            _redis_url,
            materialization_api_module._test_data_materialization_request_key(request_id),
        )

    async def _catalog_write(_redis_url: str, record: dict) -> None:
        key = materialization_api_module._test_data_materialization_request_key(str(record.get("request_id") or ""))
        shared_redis.records[key] = json.dumps(record)

    monkeypatch.setattr(materialization_api_module, "_resolve_test_data_redis_url", lambda: "redis://example:6379/0")
    monkeypatch.setattr(materialization_api_module, "_redis_llen", shared_redis.llen)
    monkeypatch.setattr(materialization_api_module, "_redis_lpush", shared_redis.lpush)
    monkeypatch.setattr(materialization_api_module, "_write_test_data_materialization_record", _catalog_write)
    monkeypatch.setattr(materialization_api_module, "_read_test_data_materialization_record", _catalog_read)
    monkeypatch.setattr(materialization_api_module, "_s3_prefix_has_objects", lambda **_kwargs: False)

    worker_config = worker_module.WorkerConfig(
        redis_url="redis://example:6379/0",
        queue_key="dq-test-data:materialize",
        processing_queue_key="dq-test-data:materialize:processing",
        api_url="http://testserver",
        spark_master="local[*]",
        spark_ui_port=4040,
        output_prefix="s3a://dq-test-data",
        s3_endpoint="http://aistor:9000",
        s3_access_key="aistor",
        s3_secret_key="aistorpass",
        s3_region="eu-west-1",
        s3_path_style_access=True,
        s3_ssl_enabled=False,
        max_rows_per_request=5000,
        poll_timeout_seconds=5,
    )

    try:
        create_response = client.post(
            "/api/data-catalog/v1/materialization-requests",
            headers=auth_headers("dq:rules:test", "dq:rules:write"),
            json={
                "data_set_id": "ds-1",
                "sample_count": 12,
                "output_format": "parquet",
                "output_uri": "s3a://dq-test-data/generated/catalog-worker-storage-failure",
            },
        )

        assert create_response.status_code == 202
        create_payload = create_response.json()
        request_id = create_payload["request_id"]
        assert create_payload["status"] == "pending"
        assert len(shared_redis.queue_payloads) == 1

        with patch.object(worker_module, "_resolve_config", return_value=worker_config), patch.object(
            worker_module,
            "_build_token_provider",
            return_value=_WorkerTokenProvider(),
        ), patch.object(
            worker_module.redis,
            "from_url",
            return_value=shared_redis.worker_loop_client(),
        ), patch.object(
            worker_module,
            "_ensure_bucket_exists",
            return_value=None,
        ), patch.object(
            worker_module,
            "_create_spark_session",
            return_value=object(),
        ), patch.object(
            worker_module,
            "_build_rows",
            side_effect=[
                [{"id": 1}] * 12,
            ],
        ), patch.object(
            worker_module,
            "_write_dataset",
            side_effect=RuntimeError("Simulated storage failure"),
        ):
            with pytest.raises(KeyboardInterrupt):
                worker_module.run_worker_forever()

        status_response = client.get(
            f"/api/data-catalog/v1/materialization-requests/{request_id}",
            headers=auth_headers("dq:rules:test", "dq:rules:write"),
        )

        assert status_response.status_code == 200
        status_payload = status_response.json()
        assert status_payload["status"] == "failed"
        assert status_payload["request_contract"] == "catalog_materialization_v1"
        assert status_payload["selection"]["selector_type"] == "data_set_id"
        assert status_payload["selection"]["resolved"]["target_count"] == 2
        assert status_payload["completed_at"]
        assert status_payload["error_message"] == "Simulated storage failure"
        assert status_payload["result"] is None
    finally:
        app.dependency_overrides.pop(get_data_catalog_repository, None)


def test_catalog_materialization_worker_callback_failure_marks_request_failed(
    client,
    auth_headers,
    monkeypatch: pytest.MonkeyPatch,
    _no_database,
    worker_module,
):
    from app.api.v1.endpoints import data_catalog as data_catalog_module
    from app.api.v1 import test_data_materialization_api as materialization_api_module
    from app.core.dependencies import get_data_catalog_repository
    from app.infrastructure.repositories.in_memory_data_catalog_repository import InMemoryDataCatalogRepository
    from app.main import app

    repository = InMemoryDataCatalogRepository()
    app.dependency_overrides[get_data_catalog_repository] = lambda: repository
    monkeypatch.setenv("REDIS_URL", "redis://example:6379/0")

    shared_redis = _SharedRedisHarness()

    async def _catalog_read(_redis_url: str, request_id: str) -> dict | None:
        return await shared_redis.get_json(
            _redis_url,
            materialization_api_module._test_data_materialization_request_key(request_id),
        )

    async def _catalog_write(_redis_url: str, record: dict) -> None:
        key = materialization_api_module._test_data_materialization_request_key(str(record.get("request_id") or ""))
        shared_redis.records[key] = json.dumps(record)

    monkeypatch.setattr(materialization_api_module, "_resolve_test_data_redis_url", lambda: "redis://example:6379/0")
    monkeypatch.setattr(materialization_api_module, "_redis_llen", shared_redis.llen)
    monkeypatch.setattr(materialization_api_module, "_redis_lpush", shared_redis.lpush)
    monkeypatch.setattr(materialization_api_module, "_write_test_data_materialization_record", _catalog_write)
    monkeypatch.setattr(materialization_api_module, "_read_test_data_materialization_record", _catalog_read)
    monkeypatch.setattr(materialization_api_module, "_s3_prefix_has_objects", lambda **_kwargs: False)

    def _route_invalid_worker_callback(*, method: str, url: str, headers: dict | None = None, json: dict | None = None, timeout: int | float | None = None):
        _ = timeout
        parsed = urlsplit(url)
        target = parsed.path or "/"
        if parsed.query:
            target = f"{target}?{parsed.query}"
        invalid_json = json
        if target.endswith("/complete") and isinstance(json, dict):
            invalid_json = dict(json)
            target_results = list(invalid_json.get("target_results") or [])
            invalid_json["target_results"] = target_results[:1]
        return client.request(method=method, url=target, headers=headers, json=invalid_json)

    worker_config = worker_module.WorkerConfig(
        redis_url="redis://example:6379/0",
        queue_key="dq-test-data:materialize",
        processing_queue_key="dq-test-data:materialize:processing",
        api_url="http://testserver",
        spark_master="local[*]",
        spark_ui_port=4040,
        output_prefix="s3a://dq-test-data",
        s3_endpoint="http://aistor:9000",
        s3_access_key="aistor",
        s3_secret_key="aistorpass",
        s3_region="eu-west-1",
        s3_path_style_access=True,
        s3_ssl_enabled=False,
        max_rows_per_request=5000,
        poll_timeout_seconds=5,
    )

    try:
        create_response = client.post(
            "/api/data-catalog/v1/materialization-requests",
            headers=auth_headers("dq:rules:test", "dq:rules:write"),
            json={
                "data_set_id": "ds-1",
                "sample_count": 12,
                "output_format": "parquet",
                "output_uri": "s3a://dq-test-data/generated/catalog-worker-callback-failure",
            },
        )

        assert create_response.status_code == 202
        create_payload = create_response.json()
        request_id = create_payload["request_id"]
        assert create_payload["status"] == "pending"
        assert len(shared_redis.queue_payloads) == 1

        with patch.object(worker_module, "_resolve_config", return_value=worker_config), patch.object(
            worker_module,
            "_build_token_provider",
            return_value=_WorkerTokenProvider(),
        ), patch.object(
            worker_module.redis,
            "from_url",
            return_value=shared_redis.worker_loop_client(),
        ), patch.object(
            worker_module,
            "_ensure_bucket_exists",
            return_value=None,
        ), patch.object(
            worker_module,
            "_create_spark_session",
            return_value=object(),
        ), patch.object(
            worker_module,
            "_build_rows",
            side_effect=[
                [{"id": 1}] * 12,
                [{"contact_id": "c-1"}] * 12,
            ],
        ), patch.object(
            worker_module,
            "_write_dataset",
            side_effect=[12, 9],
        ), patch.object(
            worker_module.requests,
            "request",
            side_effect=_route_invalid_worker_callback,
        ):
            with pytest.raises(KeyboardInterrupt):
                worker_module.run_worker_forever()

        status_response = client.get(
            f"/api/data-catalog/v1/materialization-requests/{request_id}",
            headers=auth_headers("dq:rules:test", "dq:rules:write"),
        )

        assert status_response.status_code == 200
        status_payload = status_response.json()
        assert status_payload["status"] == "failed"
        assert status_payload["request_contract"] == "catalog_materialization_v1"
        assert status_payload["selection"]["selector_type"] == "data_set_id"
        assert status_payload["selection"]["resolved"]["target_count"] == 2
        assert status_payload["completed_at"]
        assert status_payload["error_message"] == (
            f"API request failed: POST /data-catalog/v1/materialization-requests/{request_id}/complete -> 409"
        )
        assert status_payload["result"] is None
    finally:
        app.dependency_overrides.pop(get_data_catalog_repository, None)
