from __future__ import annotations

import asyncio
import gzip
import hashlib
import json
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, Protocol

from app.core.config import Settings
from app.domain.entities import GxExecutionViolationCreateEntity
from app.domain.interfaces import ExceptionFactRepository


_SUPPORTED_RECORD_IDENTIFIER_TYPES = frozenset({"primary_key", "business_key", "data_object_version"})


class ExceptionStorageError(RuntimeError):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


class ExceptionStorageBackend(Protocol):
    async def persist_violations(self, violations: Sequence[Mapping[str, Any]]) -> int:
        ...


class ExceptionStorageService(Protocol):
    async def persist_violations(self, violations: Sequence[Mapping[str, Any]]) -> int:
        ...


class RepositoryExceptionStorageBackend:
    def __init__(self, *, violation_repository: ExceptionFactRepository) -> None:
        self._violation_repository = violation_repository

    async def persist_violations(self, violations: Sequence[Mapping[str, Any]]) -> int:
        saved_rows = await self._violation_repository.save_violations(
            [_to_violation_create_entity(violation) for violation in violations]
        )
        return len(saved_rows)


class S3ExceptionStorageBackend:
    def __init__(
        self,
        *,
        bucket: str,
        prefix: str,
        endpoint: str,
        access_key: str,
        secret_key: str,
        region: str = "us-east-1",
        ssl_enabled: bool = True,
        client_factory: Any | None = None,
    ) -> None:
        self._bucket = str(bucket or "").strip()
        self._prefix = str(prefix or "").strip().strip("/")
        self._endpoint = str(endpoint or "").strip()
        self._access_key = str(access_key or "").strip()
        self._secret_key = str(secret_key or "").strip()
        self._region = str(region or "").strip() or "us-east-1"
        self._ssl_enabled = bool(ssl_enabled)
        self._client_factory = client_factory or self._build_s3_client
        self._client = self._client_factory()
        self._ensure_bucket_exists()

    @staticmethod
    def _build_s3_client_factory(
        endpoint: str,
        access_key: str,
        secret_key: str,
        region: str,
        ssl_enabled: bool,
    ) -> Any:
        try:
            import boto3
        except Exception as exc:  # pragma: no cover - environment dependent
            raise ExceptionStorageError(
                "Python package 'boto3' is required for S3 exception storage",
                status_code=503,
            ) from exc

        return boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
            verify=ssl_enabled,
        )

    def _build_s3_client(self) -> Any:
        if not self._bucket:
            raise ExceptionStorageError("GX exception storage requires GX_EXCEPTION_STORAGE_BUCKET")
        if not self._endpoint:
            raise ExceptionStorageError("GX exception storage requires GX_EXCEPTION_STORAGE_ENDPOINT")
        if not self._access_key or not self._secret_key:
            raise ExceptionStorageError(
                "GX exception storage requires GX_EXCEPTION_STORAGE_ACCESS_KEY and GX_EXCEPTION_STORAGE_SECRET_KEY",
                status_code=503,
            )
        return self._build_s3_client_factory(
            self._endpoint,
            self._access_key,
            self._secret_key,
            self._region,
            self._ssl_enabled,
        )

    def _ensure_bucket_exists(self) -> None:
        try:
            self._client.head_bucket(Bucket=self._bucket)
            return
        except Exception as exc:
            error_code = _client_error_code(exc)
            if error_code not in {"404", "NoSuchBucket", "NotFound"}:
                raise

        create_kwargs: dict[str, Any] = {"Bucket": self._bucket}
        if self._region != "us-east-1":
            create_kwargs["CreateBucketConfiguration"] = {"LocationConstraint": self._region}

        try:
            self._client.create_bucket(**create_kwargs)
        except Exception as exc:
            error_code = _client_error_code(exc)
            if error_code not in {"BucketAlreadyExists", "BucketAlreadyOwnedByYou"}:
                raise

    async def persist_violations(self, violations: Sequence[Mapping[str, Any]]) -> int:
        normalized_violations = [_as_normalized_violation_record(violation) for violation in violations]
        if not normalized_violations:
            return 0

        normalized_violations.sort(
            key=lambda item: (
                item["data_object_version_id"],
                item["execution_run_id"],
                item["rule_id"],
                item["record_identifier_value"],
                item["record_identifier_type"],
                item["reason_code"],
                item["reason_text"],
                item["detected_at"] or "",
                item["violation_id"],
            )
        )

        payload = {
            "storedAt": datetime.now(UTC).isoformat(),
            "schemaVersion": "v4",
            "violationCount": len(normalized_violations),
            "violations": [_to_object_storage_violation_payload(violation) for violation in normalized_violations],
        }
        canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        content_hash = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
        data_object_version_id = normalized_violations[0]["data_object_version_id"]
        execution_run_id = normalized_violations[0]["execution_run_id"]
        key_parts = [
            self._prefix or "gx-exceptions",
            f"data_object_version_id={data_object_version_id}",
            f"execution_run_id={execution_run_id}",
            f"violation-batch-{content_hash}.json.gz",
        ]
        object_key = "/".join(part for part in key_parts if part)
        compressed_body = gzip.compress(canonical_json.encode("utf-8"))

        await asyncio.to_thread(
            self._put_object,
            object_key,
            compressed_body,
            content_hash,
            data_object_version_id,
            execution_run_id,
        )
        return len(normalized_violations)

    def _put_object(
        self,
        object_key: str,
        compressed_body: bytes,
        content_hash: str,
        data_object_version_id: str,
        execution_run_id: str,
    ) -> None:
        self._client.put_object(
            Bucket=self._bucket,
            Key=object_key,
            Body=compressed_body,
            ContentType="application/json",
            ContentEncoding="gzip",
            Metadata={
                "content_sha256": content_hash,
                "storage_kind": "gx_violation_batch",
                "data_object_version_id": data_object_version_id,
                "execution_run_id": execution_run_id,
            },
        )


def build_exception_storage_service(
    *,
    settings: Settings,
    violation_repository: ExceptionFactRepository,
) -> ExceptionStorageService:
    backend_name = str(getattr(settings, "gx_exception_storage_backend", "s3") or "s3").strip().lower()

    if backend_name in {"repository", "db"}:
        return GxExceptionStorageService(backend=RepositoryExceptionStorageBackend(violation_repository=violation_repository))

    if backend_name == "s3":
        endpoint = str(getattr(settings, "gx_exception_storage_endpoint", "") or "").strip()
        bucket = str(getattr(settings, "gx_exception_storage_bucket", "dq-gx-exceptions") or "dq-gx-exceptions").strip() or "dq-gx-exceptions"
        access_key = str(getattr(settings, "gx_exception_storage_access_key", "") or "").strip()
        secret_key = str(getattr(settings, "gx_exception_storage_secret_key", "") or "").strip()
        region = str(getattr(settings, "gx_exception_storage_region", "us-east-1") or "us-east-1").strip() or "us-east-1"
        prefix = str(getattr(settings, "gx_exception_storage_prefix", "gx-exceptions") or "gx-exceptions").strip() or "gx-exceptions"
        ssl_enabled = bool(getattr(settings, "gx_exception_storage_ssl_enabled", True))

        backend = S3ExceptionStorageBackend(
            bucket=bucket,
            prefix=prefix,
            endpoint=endpoint,
            access_key=access_key,
            secret_key=secret_key,
            region=region,
            ssl_enabled=ssl_enabled,
        )
        return GxExceptionStorageService(backend=backend)

    raise ExceptionStorageError(
        f"Unsupported GX exception storage backend '{backend_name}'",
        status_code=400,
    )


class GxExceptionStorageService:
    def __init__(self, *, backend: ExceptionStorageBackend, batch_size: int = 1000) -> None:
        self._backend = backend
        self._batch_size = max(int(batch_size), 1)

    async def persist_violations(self, violations: Sequence[Mapping[str, Any]]) -> int:
        normalized_violations = [self._normalize_violation(violation) for violation in violations]
        if not normalized_violations:
            return 0

        normalized_violations.sort(
            key=lambda item: (
                item["data_object_version_id"],
                item["execution_run_id"],
                item["rule_id"],
                item["record_identifier_value"],
                item["record_identifier_type"],
                item["reason_code"],
                item["reason_text"],
                item["detected_at"] or "",
                item["violation_id"],
            )
        )

        grouped_violations: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for violation in normalized_violations:
            grouped_violations[(violation["data_object_version_id"], violation["execution_run_id"])].append(violation)

        persisted = 0
        for group_key in sorted(grouped_violations):
            group = grouped_violations[group_key]
            for start_index in range(0, len(group), self._batch_size):
                batch = group[start_index : start_index + self._batch_size]
                persisted += await self._backend.persist_violations(batch)
        return persisted

    @staticmethod
    def _normalize_violation(violation: Mapping[str, Any]) -> dict[str, Any]:
        return _normalize_violation_record(violation)


def _read_violation_string(violation: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        value = violation.get(key)
        normalized = str(value or "").strip()
        if normalized:
            return normalized
    return ""


def _build_identifier_hash(record_identifier_type: str, record_identifier_value: str) -> str:
    digest = hashlib.sha256(f"{record_identifier_type}:{record_identifier_value}".encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _read_violation_positive_int(violation: Mapping[str, Any], *keys: str) -> int:
    for key in keys:
        value = violation.get(key)
        if value in (None, ""):
            continue
        try:
            number = int(value)
        except (TypeError, ValueError) as exc:
            raise ExceptionStorageError(f"Violation record has invalid {key}") from exc
        if number < 1:
            raise ExceptionStorageError(f"Violation record has invalid {key}")
        return number
    raise ExceptionStorageError(f"Violation record is missing {keys[0]}")


def _client_error_code(exc: Exception) -> str:
    response = getattr(exc, "response", None)
    if isinstance(response, Mapping):
        error = response.get("Error")
        if isinstance(error, Mapping):
            return str(error.get("Code") or "").strip()
    return ""


def _normalize_violation_record(violation: Mapping[str, Any]) -> dict[str, Any]:
    data_object_version_id = _read_violation_string(violation, "data_object_version_id")
    execution_run_id = _read_violation_string(violation, "execution_run_id")
    record_identifier_type = _read_violation_string(violation, "record_identifier_type", "recordIdentifierType")
    record_identifier_value = _read_violation_string(violation, "record_identifier_value", "recordIdentifierValue")
    rule_id = _read_violation_string(violation, "rule_id")
    reason_code = _read_violation_string(violation, "reason_code", "reasonCode")
    reason_text = _read_violation_string(violation, "reason_text", "reasonText")
    detected_at = _read_violation_string(violation, "detected_at") or None

    if not data_object_version_id:
        raise ExceptionStorageError("Violation record is missing data_object_version_id")
    if not execution_run_id:
        raise ExceptionStorageError("Violation record is missing execution_run_id")
    if not record_identifier_type:
        raise ExceptionStorageError("Violation record is missing record_identifier_type")
    if record_identifier_type not in _SUPPORTED_RECORD_IDENTIFIER_TYPES:
        raise ExceptionStorageError(
            f"Violation record has unsupported record_identifier_type '{record_identifier_type}'"
        )
    if not record_identifier_value:
        raise ExceptionStorageError("Violation record is missing record_identifier_value")
    if not rule_id:
        raise ExceptionStorageError("Violation record is missing rule_id")
    if not reason_code:
        raise ExceptionStorageError("Violation record is missing reason_code")
    if not reason_text:
        raise ExceptionStorageError("Violation record is missing reason_text")

    raw_ops_metadata = violation.get("ops_metadata")
    ops_metadata = dict(raw_ops_metadata) if isinstance(raw_ops_metadata, Mapping) else {}
    validation_artifact_id = _read_violation_string(ops_metadata, "validation_artifact_id", "validationArtifactId")
    validation_artifact_version = _read_violation_positive_int(
        ops_metadata,
        "validation_artifact_version",
        "validationArtifactVersion",
    )
    rule_version_id = _read_violation_string(ops_metadata, "rule_version_id", "ruleVersionId")
    engine_type = _read_violation_string(ops_metadata, "engine_type", "engineType")
    if not validation_artifact_id:
        raise ExceptionStorageError("Violation record is missing validation_artifact_id")
    if not rule_version_id:
        raise ExceptionStorageError("Violation record is missing rule_version_id")
    if not engine_type:
        raise ExceptionStorageError("Violation record is missing engine_type")

    ops_metadata["record_identifier_type"] = record_identifier_type
    ops_metadata["record_identifier_value"] = record_identifier_value
    ops_metadata["reason_code"] = reason_code
    ops_metadata["reason_text"] = reason_text
    ops_metadata["validation_artifact_id"] = validation_artifact_id
    ops_metadata["validation_artifact_version"] = validation_artifact_version
    ops_metadata["rule_version_id"] = rule_version_id
    ops_metadata["engine_type"] = engine_type
    if not str(ops_metadata.get("failure_class") or "").strip():
        ops_metadata["failure_class"] = reason_code
    if not str(ops_metadata.get("identifier_hash") or "").strip():
        ops_metadata["identifier_hash"] = _build_identifier_hash(record_identifier_type, record_identifier_value)

    canonical_payload = {
        "dataObjectVersionId": data_object_version_id,
        "executionRunId": execution_run_id,
        "recordIdentifierType": record_identifier_type,
        "recordIdentifierValue": record_identifier_value,
        "ruleId": rule_id,
        "reasonCode": reason_code,
        "reasonText": reason_text,
        "detectedAt": detected_at,
    }
    canonical_json = json.dumps(canonical_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    violation_id = _read_violation_string(violation, "violation_id", "violationId")
    if not violation_id:
        violation_id = f"gx-violation-{hashlib.sha256(canonical_json.encode('utf-8')).hexdigest()[:32]}"

    return {
        "violation_id": violation_id,
        "data_object_version_id": data_object_version_id,
        "execution_run_id": execution_run_id,
        "record_identifier_type": record_identifier_type,
        "record_identifier_value": record_identifier_value,
        "rule_id": rule_id,
        "reason_code": reason_code,
        "reason_text": reason_text,
        "detected_at": detected_at,
        "ops_metadata": ops_metadata,
    }


def _as_normalized_violation_record(violation: Mapping[str, Any]) -> dict[str, Any]:
    if {
        "violation_id",
        "data_object_version_id",
        "execution_run_id",
        "record_identifier_type",
        "record_identifier_value",
        "rule_id",
        "reason_code",
        "reason_text",
        "ops_metadata",
    }.issubset(violation.keys()):
        normalized = dict(violation)
        normalized["ops_metadata"] = dict(violation.get("ops_metadata") or {})
        return normalized
    return _normalize_violation_record(violation)


def _to_violation_create_entity(violation: Mapping[str, Any]) -> GxExecutionViolationCreateEntity:
    normalized = _as_normalized_violation_record(violation)
    return GxExecutionViolationCreateEntity(
        id=normalized["violation_id"],
        dataObjectVersionId=normalized["data_object_version_id"],
        executionRunId=normalized["execution_run_id"],
        ruleId=normalized["rule_id"],
        dataPrimaryKey=normalized["record_identifier_value"],
        violationReason=normalized["reason_text"],
        opsMetadata=dict(normalized["ops_metadata"]),
        detectedAt=normalized["detected_at"],
    )


def _to_object_storage_violation_payload(violation: Mapping[str, Any]) -> dict[str, Any]:
    normalized = _as_normalized_violation_record(violation)
    ops_payload = {
        "dataObjectVersionId": normalized["data_object_version_id"],
        "executionRunId": normalized["execution_run_id"],
    }
    if normalized["detected_at"]:
        ops_payload["detectedAt"] = normalized["detected_at"]
    ops_metadata = dict(normalized["ops_metadata"])
    if ops_metadata.get("suite_id") is not None:
        ops_payload["suiteId"] = ops_metadata["suite_id"]
    if ops_metadata.get("suite_version") is not None:
        ops_payload["suiteVersion"] = ops_metadata["suite_version"]
    if ops_metadata.get("validation_artifact_id") is not None:
        ops_payload["validationArtifactId"] = ops_metadata["validation_artifact_id"]
    if ops_metadata.get("validation_artifact_version") is not None:
        ops_payload["validationArtifactVersion"] = ops_metadata["validation_artifact_version"]
    if ops_metadata.get("rule_version_id") is not None:
        ops_payload["ruleVersionId"] = ops_metadata["rule_version_id"]
    if ops_metadata.get("correlation_id") is not None:
        ops_payload["correlationId"] = ops_metadata["correlation_id"]
    if ops_metadata.get("engine_type") is not None:
        ops_payload["engineType"] = ops_metadata["engine_type"]
    if ops_metadata.get("engine_target") is not None:
        ops_payload["engineTarget"] = ops_metadata["engine_target"]
    if ops_metadata.get("execution_shape") is not None:
        ops_payload["executionShape"] = ops_metadata["execution_shape"]
    if ops_metadata.get("execution_plan_id") is not None:
        ops_payload["executionPlanId"] = ops_metadata["execution_plan_id"]
    if ops_metadata.get("execution_plan_version_id") is not None:
        ops_payload["executionPlanVersionId"] = ops_metadata["execution_plan_version_id"]
    if ops_metadata.get("delivery_id") is not None:
        ops_payload["deliveryId"] = ops_metadata["delivery_id"]
    if ops_metadata.get("delivery_location") is not None:
        ops_payload["deliveryLocation"] = ops_metadata["delivery_location"]
    if ops_metadata.get("delivery_resolution_mode") is not None:
        ops_payload["deliveryResolutionMode"] = ops_metadata["delivery_resolution_mode"]
    if ops_metadata.get("artifact_key") is not None:
        ops_payload["artifactKey"] = ops_metadata["artifact_key"]
    if ops_metadata.get("failure_class") is not None:
        ops_payload["failureClass"] = ops_metadata["failure_class"]
    if ops_metadata.get("identifier_hash") is not None:
        ops_payload["identifierHash"] = ops_metadata["identifier_hash"]
    if ops_metadata.get("identifier_fields") is not None:
        ops_payload["identifierFields"] = ops_metadata["identifier_fields"]

    return {
        "violationId": normalized["violation_id"],
        "violationFact": {
            "recordIdentifierType": normalized["record_identifier_type"],
            "recordIdentifierValue": normalized["record_identifier_value"],
            "ruleId": normalized["rule_id"],
            "reasonCode": normalized["reason_code"],
            "reasonText": normalized["reason_text"],
            "identifierHash": normalized["ops_metadata"].get("identifier_hash"),
        },
        "ops": ops_payload,
    }