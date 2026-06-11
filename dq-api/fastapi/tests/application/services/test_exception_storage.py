from __future__ import annotations

import asyncio
import hashlib
import gzip
import json
from typing import Any, Callable

import pytest

from app.application.services.exception_storage import GxExceptionStorageService
from app.application.services.exception_storage import ExceptionStorageError
from app.application.services.exception_storage import build_exception_storage_service
from app.application.services.exception_storage import S3ExceptionStorageBackend


class _FakeBucketMissingError(Exception):
    def __init__(self) -> None:
        super().__init__("NoSuchBucket")
        self.response = {"Error": {"Code": "NoSuchBucket"}}


class _FakeS3Client:
    def __init__(self) -> None:
        self.head_calls: list[dict[str, Any]] = []
        self.create_calls: list[dict[str, Any]] = []
        self.put_calls: list[dict[str, Any]] = []

    def head_bucket(self, **kwargs: Any) -> None:
        self.head_calls.append(kwargs)
        raise _FakeBucketMissingError()

    def create_bucket(self, **kwargs: Any) -> None:
        self.create_calls.append(kwargs)

    def put_object(self, **kwargs: Any) -> None:
        self.put_calls.append(kwargs)


@pytest.fixture
def s3_exception_storage_service_factory() -> Callable[[], tuple[GxExceptionStorageService, _FakeS3Client]]:
    def _create() -> tuple[GxExceptionStorageService, _FakeS3Client]:
        fake_client = _FakeS3Client()
        backend = S3ExceptionStorageBackend(
            bucket="dq-gx-exceptions",
            prefix="gx",
            endpoint="http://aistor:9000",
            access_key="access-key",
            secret_key="secret-key",
            ssl_enabled=False,
            client_factory=lambda: fake_client,
        )
        return GxExceptionStorageService(backend=backend, batch_size=10), fake_client

    return _create


def test_s3_exception_storage_backend_persists_canonical_batch(
    s3_exception_storage_service_factory: Callable[[], tuple[GxExceptionStorageService, _FakeS3Client]],
) -> None:
    service, fake_client = s3_exception_storage_service_factory()

    persisted = asyncio.run(
        service.persist_violations(
            [
                {
                    "data_object_version_id": "dov-1",
                    "execution_run_id": "run-1",
                    "rule_id": "rule_1",
                    "reason_code": "expect_column_values_to_not_be_null",
                    "reason_text": "customer_id must not be null",
                    "record_identifier_type": "business_key",
                    "record_identifier_value": "sales_order_number=SO-2",
                    "ops_metadata": {
                        "suite_id": "gx_suite_1",
                        "suite_version": 1,
                        "validation_artifact_id": "gx_suite_1",
                        "validation_artifact_version": 1,
                        "rule_version_id": "rule_version_1",
                        "correlation_id": "corr-1",
                        "engine_type": "gx",
                        "engine_target": "pyspark",
                        "execution_shape": "single_object",
                        "execution_plan_id": "run-plan-1",
                        "execution_plan_version_id": "run-plan-version-3",
                        "delivery_id": "delivery-1",
                        "delivery_location": "s3://deliveries/orders/2026-04-06",
                        "delivery_resolution_mode": "specific_delivery",
                        "artifact_key": "artifact_1",
                    },
                    "detected_at": "2026-04-06T12:01:00+00:00",
                },
                {
                    "data_object_version_id": "dov-1",
                    "execution_run_id": "run-1",
                    "rule_id": "rule_1",
                    "reason_code": "value_mismatch",
                    "reason_text": "customer_id differs from golden source",
                    "record_identifier_type": "primary_key",
                    "record_identifier_value": "row-1",
                    "ops_metadata": {
                        "suite_id": "gx_suite_1",
                        "suite_version": 1,
                        "validation_artifact_id": "gx_suite_1",
                        "validation_artifact_version": 1,
                        "rule_version_id": "rule_version_1",
                        "correlation_id": "corr-1",
                        "engine_type": "gx",
                        "engine_target": "pyspark",
                        "execution_shape": "single_object",
                        "execution_plan_id": "run-plan-1",
                        "execution_plan_version_id": "run-plan-version-3",
                        "delivery_id": "delivery-1",
                        "delivery_location": "s3://deliveries/orders/2026-04-06",
                        "delivery_resolution_mode": "specific_delivery",
                        "artifact_key": "artifact_1",
                    },
                    "detected_at": "2026-04-06T12:00:00+00:00",
                },
            ]
        )
    )

    assert persisted == 2
    assert len(fake_client.create_calls) == 1
    assert fake_client.create_calls[0]["Bucket"] == "dq-gx-exceptions"
    assert len(fake_client.put_calls) == 1
    put_call = fake_client.put_calls[0]
    assert put_call["Bucket"] == "dq-gx-exceptions"
    assert put_call["ContentEncoding"] == "gzip"
    assert put_call["Key"].startswith("gx/data_object_version_id=dov-1/execution_run_id=run-1/violation-batch-")

    payload = json.loads(gzip.decompress(put_call["Body"]).decode("utf-8"))
    assert payload["schemaVersion"] == "v4"
    assert payload["violationCount"] == 2
    assert [row["violationFact"]["recordIdentifierValue"] for row in payload["violations"]] == ["row-1", "sales_order_number=SO-2"]
    assert payload["violations"][0]["violationFact"]["recordIdentifierType"] == "primary_key"
    assert payload["violations"][1]["violationFact"]["recordIdentifierType"] == "business_key"
    assert payload["violations"][0]["violationFact"]["ruleId"] == "rule_1"
    assert payload["violations"][0]["violationFact"]["reasonCode"] == "value_mismatch"
    assert payload["violations"][0]["violationFact"]["reasonText"] == "customer_id differs from golden source"
    assert payload["violations"][0]["violationFact"]["identifierHash"] == (
        "sha256:"
        + hashlib.sha256("primary_key:row-1".encode("utf-8")).hexdigest()
    )
    assert payload["violations"][1]["violationFact"]["identifierHash"] == (
        "sha256:"
        + hashlib.sha256("business_key:sales_order_number=SO-2".encode("utf-8")).hexdigest()
    )
    assert payload["violations"][0]["ops"]["dataObjectVersionId"] == "dov-1"
    assert payload["violations"][0]["ops"]["suiteId"] == "gx_suite_1"
    assert payload["violations"][0]["ops"]["validationArtifactId"] == "gx_suite_1"
    assert payload["violations"][0]["ops"]["engineType"] == "gx"
    assert payload["violations"][0]["ops"]["executionPlanId"] == "run-plan-1"
    assert payload["violations"][0]["ops"]["deliveryId"] == "delivery-1"
    assert payload["violations"][0]["ops"]["artifactKey"] == "artifact_1"


def test_exception_storage_defaults_to_s3_backend(monkeypatch) -> None:
    fake_client = _FakeS3Client()

    class _Settings:
        gx_exception_storage_endpoint = "http://aistor:9000"
        gx_exception_storage_access_key = "access-key"
        gx_exception_storage_secret_key = "secret-key"

    monkeypatch.setattr(S3ExceptionStorageBackend, "_build_s3_client", lambda self: fake_client)

    service = build_exception_storage_service(settings=_Settings(), violation_repository=object())
    persisted = asyncio.run(
        service.persist_violations(
            [
                {
                    "data_object_version_id": "dov-1",
                    "execution_run_id": "run-1",
                    "rule_id": "rule_1",
                    "reason_code": "value_mismatch",
                    "reason_text": "customer_id differs from golden source",
                    "record_identifier_type": "primary_key",
                    "record_identifier_value": "row-1",
                    "ops_metadata": {
                        "suite_id": "gx_suite_1",
                        "suite_version": 1,
                        "validation_artifact_id": "gx_suite_1",
                        "validation_artifact_version": 1,
                        "rule_version_id": "rule_version_1",
                        "correlation_id": "corr-1",
                        "engine_type": "gx",
                        "execution_plan_id": "run-plan-1",
                        "delivery_id": "delivery-1",
                    },
                }
            ]
        )
    )

    assert persisted == 1
    assert fake_client.put_calls[0]["Bucket"] == "dq-gx-exceptions"


def test_exception_storage_requires_record_identifier_value(
    s3_exception_storage_service_factory: Callable[[], tuple[GxExceptionStorageService, _FakeS3Client]],
) -> None:
    service, _ = s3_exception_storage_service_factory()

    with pytest.raises(ExceptionStorageError, match="record_identifier_value"):
        asyncio.run(
            service.persist_violations(
                [
                    {
                        "data_object_version_id": "dov-1",
                        "execution_run_id": "run-1",
                        "rule_id": "rule_1",
                        "reason_code": "value_mismatch",
                        "reason_text": "customer_id differs from golden source",
                        "record_identifier_type": "primary_key",
                        "ops_metadata": {
                            "suite_id": "gx_suite_1",
                            "suite_version": 1,
                            "validation_artifact_id": "gx_suite_1",
                            "validation_artifact_version": 1,
                            "rule_version_id": "rule_version_1",
                            "correlation_id": "corr-1",
                            "engine_type": "gx",
                            "execution_plan_id": "run-plan-1",
                            "delivery_id": "delivery-1",
                        },
                    }
                ]
            )
        )


def test_exception_storage_requires_reason_code(
    s3_exception_storage_service_factory: Callable[[], tuple[GxExceptionStorageService, _FakeS3Client]],
) -> None:
    service, _ = s3_exception_storage_service_factory()

    with pytest.raises(ExceptionStorageError, match="reason_code"):
        asyncio.run(
            service.persist_violations(
                [
                    {
                        "data_object_version_id": "dov-1",
                        "execution_run_id": "run-1",
                        "rule_id": "rule_1",
                        "reason_text": "customer_id differs from golden source",
                        "record_identifier_type": "primary_key",
                        "record_identifier_value": "row-1",
                        "ops_metadata": {
                            "suite_id": "gx_suite_1",
                            "suite_version": 1,
                            "validation_artifact_id": "gx_suite_1",
                            "validation_artifact_version": 1,
                            "rule_version_id": "rule_version_1",
                            "correlation_id": "corr-1",
                            "engine_type": "gx",
                            "execution_plan_id": "run-plan-1",
                            "delivery_id": "delivery-1",
                        },
                    }
                ]
            )
        )


@pytest.mark.parametrize(
    ("missing_field", "expected_message"),
    [
        ("validation_artifact_id", "validation_artifact_id"),
        ("validation_artifact_version", "validation_artifact_version"),
        ("rule_version_id", "rule_version_id"),
        ("engine_type", "engine_type"),
    ],
)
def test_exception_storage_requires_canonical_lineage_fields(
    s3_exception_storage_service_factory: Callable[[], tuple[GxExceptionStorageService, _FakeS3Client]],
    missing_field: str,
    expected_message: str,
) -> None:
    service, _ = s3_exception_storage_service_factory()
    ops_metadata = {
        "suite_id": "gx_suite_1",
        "suite_version": 1,
        "validation_artifact_id": "gx_suite_1",
        "validation_artifact_version": 1,
        "rule_version_id": "rule_version_1",
        "correlation_id": "corr-1",
        "engine_type": "gx",
        "execution_plan_id": "run-plan-1",
        "delivery_id": "delivery-1",
    }
    ops_metadata.pop(missing_field)

    with pytest.raises(ExceptionStorageError, match=expected_message):
        asyncio.run(
            service.persist_violations(
                [
                    {
                        "data_object_version_id": "dov-1",
                        "execution_run_id": "run-1",
                        "rule_id": "rule_1",
                        "reason_code": "value_mismatch",
                        "reason_text": "customer_id differs from golden source",
                        "record_identifier_type": "primary_key",
                        "record_identifier_value": "row-1",
                        "ops_metadata": ops_metadata,
                    }
                ]
            )
        )