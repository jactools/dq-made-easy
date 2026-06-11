import asyncio
import json
import os
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import HTTPException

try:
    import redis.asyncio as aioredis
except Exception:
    aioredis = None

try:
    import redis as redis_sync
except Exception:
    redis_sync = None

from app.api.v1.schemas import DataDeliveryNoteView
from app.api.v1.schemas.test_data_materialization_view import MaterializationCompletionBatchView
from app.api.v1.schemas.test_data_materialization_view import MaterializationDeliveryView
from app.api.v1.schemas.test_data_materialization_view import MaterializationTargetResultRequest
from app.api.v1.schemas.test_data_materialization_view import ReportTestDataMaterializationCompletionRequest
from app.api.v1.schemas.test_data_materialization_view import TestDataMaterializationCompletionView
from app.application.services import test_data_materialization_service as _materialization_service
from app.application.services.test_data_queue_service import inject_queue_trace_headers as _service_inject_queue_trace_headers
from app.core.config import get_settings
from app.domain.entities import TestDataMaterializationRecordEntity
from app.domain.entities import build_test_data_materialization_record_entity
from app.domain.interfaces.v1.data_catalog_repository import DataCatalogRepository

_TEST_DATA_MATERIALIZATION_JOB_TYPE = "test_data_materialization"
_TEST_DATA_MATERIALIZATION_REQUEST_TTL_SECONDS = 3600


def current_timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def resolve_test_data_redis_url() -> str | None:
    return _materialization_service.resolve_test_data_redis_url(get_settings())


def resolve_test_data_materialization_queue_key() -> str:
    return _materialization_service.resolve_test_data_materialization_queue_key()


def resolve_test_data_materialization_processing_queue_key(queue_key: str) -> str:
    return _materialization_service.resolve_test_data_materialization_processing_queue_key(queue_key)


def resolve_test_data_output_prefix() -> str:
    return _materialization_service.resolve_test_data_output_prefix()


def test_data_materialization_request_key(request_id: str) -> str:
    return _materialization_service.test_data_materialization_request_key(request_id)


def default_materialization_output_uri(
    *,
    output_prefix: str,
    version_id: str,
    output_format: str,
    sample_count: int,
    attribute_hash: str,
) -> str:
    return _materialization_service.default_materialization_output_uri(
        output_prefix=output_prefix,
        version_id=version_id,
        output_format=output_format,
        sample_count=sample_count,
        attribute_hash=attribute_hash,
    )


def normalize_s3_uri(uri: str) -> str:
    return _materialization_service.normalize_s3_uri(uri)


def ensure_synthetic_test_output_uri(
    *,
    output_uri: str,
    status_code: int,
    request_id: str | None = None,
    data_object_version_id: str | None = None,
    correlation_id: str | None = None,
) -> None:
    _materialization_service.ensure_synthetic_test_output_uri(
        output_uri=output_uri,
        status_code=status_code,
        request_id=request_id,
        data_object_version_id=data_object_version_id,
        correlation_id=correlation_id,
    )


def build_attribute_payloads(attributes: list[Any]) -> list[dict[str, Any]]:
    return _materialization_service.build_attribute_payloads(attributes)


def build_s3_client() -> Any:
    return _materialization_service.build_s3_client()


def s3_prefix_has_objects(*, output_uri: str) -> bool:
    return _materialization_service.s3_prefix_has_objects(output_uri=output_uri, build_s3_client_fn=build_s3_client)


def require_test_data_materialization_record(
    record: TestDataMaterializationRecordEntity | dict[str, Any],
) -> TestDataMaterializationRecordEntity:
    if isinstance(record, TestDataMaterializationRecordEntity):
        return record

    entity = build_test_data_materialization_record_entity(record)
    if entity is None:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "invalid_test_data_materialization_record",
                "message": "Stored test data materialization request record is invalid",
            },
        )
    return entity


def test_data_materialization_record_payload(
    record: TestDataMaterializationRecordEntity | dict[str, Any],
) -> dict[str, Any]:
    entity = require_test_data_materialization_record(record)
    return entity.model_dump(mode="python")


def build_test_data_materialization_record(
    *,
    request_id: str,
    job_id: str,
    correlation_id: str,
    request_payload: dict[str, Any],
    queue_key: str,
    processing_queue_key: str,
    selection: dict[str, Any] | None = None,
    request_contract: str | None = None,
    target_data_object_version_ids: list[str] | None = None,
) -> TestDataMaterializationRecordEntity:
    resolved_target_ids = [
        str(version_id or "").strip()
        for version_id in (target_data_object_version_ids or [request_payload["data_object_version_id"]])
        if str(version_id or "").strip()
    ]
    return TestDataMaterializationRecordEntity(
        request_id=request_id,
        job_id=job_id,
        request_contract=str(request_contract or "").strip() or None,
        status="pending",
        data_object_version_id=str(request_payload["data_object_version_id"]),
        target_data_object_version_ids=resolved_target_ids,
        sample_count=int(request_payload["sample_count"]),
        output_format=str(request_payload["output_format"]),
        output_uri=str(request_payload["output_uri"]),
        requested_at=current_timestamp(),
        started_at=None,
        completed_at=None,
        error_message=None,
        correlation_id=correlation_id,
        queue_key=queue_key,
        processing_queue_key=processing_queue_key,
        selection=dict(selection) if isinstance(selection, dict) else None,
        result=None,
    )


def resolve_materialization_storage_location(output_uri: str) -> str:
    normalized = normalize_s3_uri(output_uri)
    if normalized.startswith("s3a://"):
        return "S3"
    return "FILE"


def build_materialized_delivery_payload(
    *,
    request_id: str,
    record: TestDataMaterializationRecordEntity | dict[str, Any],
    row_count: int,
    output_uri: str,
    output_format: str,
    catalog_repository: DataCatalogRepository,
    reused_existing: bool = False,
) -> dict[str, Any]:
    record_entity = require_test_data_materialization_record(record)
    version_id = str(record_entity.data_object_version_id or "").strip()
    version_entity = catalog_repository.get_data_object_version(version_id)
    if version_entity is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "data_object_version_not_found",
                "message": f"Data object version '{version_id}' was not found",
                "data_object_version_id": version_id,
            },
        )

    delivered_at = current_timestamp()
    correlation_id = str(record_entity.correlation_id or "").strip()
    return {
        "data_object_id": str(version_entity.data_object_id or ""),
        "data_object_version_id": version_id,
        "version": int(version_entity.version or 0),
        "delivered_at": delivered_at,
        "layer": "standardized",
        "storage_location": resolve_materialization_storage_location(output_uri),
        "delivery_location": normalize_s3_uri(output_uri),
        "delivery_status": "completed",
        "delivery_format": str(output_format).strip().lower(),
        "record_count": int(row_count),
        "size_bytes": 0,
        "attributes_count": int(version_entity.attribute_count or 0),
        "ingestor_name": "dq-engine-test-data-materialization-worker",
        "ingestor_run_id": str(record_entity.job_id or "").strip() or None,
        "source_system": "test_data_materialization",
        "source_snapshot_id": request_id,
        "metadata_json": {
            "materialization_request_id": request_id,
            "job_id": str(record_entity.job_id or "").strip(),
            "correlation_id": correlation_id,
            "output_uri": normalize_s3_uri(output_uri),
            "sample_count": int(record_entity.sample_count or 0),
            "reused_existing": bool(reused_existing),
            "object_storage_classification": "synthetic_test",
            "evidence_classification": "synthetic_result",
            "selection": dict(record_entity.selection) if isinstance(record_entity.selection, dict) else None,
        },
    }


def create_materialized_delivery_completion_from_record(
    *,
    request_id: str,
    record: TestDataMaterializationRecordEntity | dict[str, Any],
    row_count: int,
    output_uri: str,
    output_format: str,
    catalog_repository: DataCatalogRepository,
    reused_existing: bool = False,
) -> TestDataMaterializationCompletionView:
    record_entity = require_test_data_materialization_record(record)
    delivery_payload = build_materialized_delivery_payload(
        request_id=request_id,
        record=record_entity,
        row_count=int(row_count),
        output_uri=output_uri,
        output_format=output_format,
        catalog_repository=catalog_repository,
        reused_existing=reused_existing,
    )
    try:
        note = catalog_repository.create_materialized_delivery_note(delivery_payload)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "data_delivery_persistence_failed",
                "message": "Failed to persist the materialized data delivery note",
                "request_id": request_id,
                "correlation_id": str(record_entity.correlation_id or "").strip() or None,
            },
        ) from exc

    return TestDataMaterializationCompletionView(
        data_delivery_id=str(note.data_delivery_id or ""),
        delivery_note=DataDeliveryNoteView.model_validate(note.model_dump()),
    )


def expected_materialization_targets_from_record(
    record: TestDataMaterializationRecordEntity | dict[str, Any],
) -> list[dict[str, Any]]:
    record_entity = require_test_data_materialization_record(record)
    selection = record_entity.selection if isinstance(record_entity.selection, dict) else {}
    resolved = selection.get("resolved") if isinstance(selection, dict) and isinstance(selection.get("resolved"), dict) else {}
    targets = resolved.get("targets") if isinstance(resolved, dict) else None
    if isinstance(targets, list) and targets:
        normalized_targets: list[dict[str, Any]] = []
        for target in targets:
            if not isinstance(target, dict):
                continue
            version_id = str(target.get("data_object_version_id") or "").strip()
            if not version_id:
                continue
            normalized_targets.append(
                {
                    "data_object_version_id": version_id,
                    "output_uri": normalize_s3_uri(str(target.get("output_uri") or "").strip()),
                    "output_format": str(target.get("output_format") or record_entity.output_format or "").strip().lower(),
                }
            )
        if normalized_targets:
            return normalized_targets

    return [
        {
            "data_object_version_id": str(record_entity.data_object_version_id or "").strip(),
            "output_uri": normalize_s3_uri(str(record_entity.output_uri or "").strip()),
            "output_format": str(record_entity.output_format or "").strip().lower(),
        }
    ]


def build_materialization_delivery_summary(
    *,
    deliveries: list[MaterializationDeliveryView],
    reused_existing: bool,
) -> dict[str, Any]:
    return {
        "target_count": len(deliveries),
        "data_delivery_count": len(deliveries),
        "total_row_count": sum(int(delivery.row_count) for delivery in deliveries),
        "reused_existing": bool(reused_existing),
        "data_delivery_ids": [delivery.data_delivery_id for delivery in deliveries],
        "delivery_locations": [
            str(delivery.delivery_note.delivery_location or delivery.output_uri or "").strip()
            for delivery in deliveries
            if str(delivery.delivery_note.delivery_location or delivery.output_uri or "").strip()
        ],
        "output_formats": sorted(
            {
                str(delivery.output_format or "").strip().lower()
                for delivery in deliveries
                if str(delivery.output_format or "").strip()
            }
        ),
        "object_storage_classifications": sorted(
            {
                str(delivery.delivery_note.object_storage_classification or "").strip()
                for delivery in deliveries
                if str(delivery.delivery_note.object_storage_classification or "").strip()
            }
        ),
        "evidence_classifications": sorted(
            {
                str(delivery.delivery_note.evidence_classification or "").strip()
                for delivery in deliveries
                if str(delivery.delivery_note.evidence_classification or "").strip()
            }
        ),
    }


def build_materialization_result_from_deliveries(
    *,
    deliveries: list[MaterializationDeliveryView],
    request_output_uri: str,
    output_format: str,
    reused_existing: bool,
) -> dict[str, Any]:
    target_results = [
        {
            "data_object_version_id": delivery.data_object_version_id,
            "row_count": int(delivery.row_count),
            "output_uri": delivery.output_uri,
            "output_format": delivery.output_format,
            "reused_existing": bool(reused_existing),
            "data_delivery_id": delivery.data_delivery_id,
            "delivery_note": delivery.delivery_note.model_dump(),
        }
        for delivery in deliveries
    ]

    result = {
        "row_count": sum(int(delivery.row_count) for delivery in deliveries),
        "output_uri": normalize_s3_uri(request_output_uri),
        "output_format": str(output_format or "").strip().lower(),
        "reused_existing": bool(reused_existing),
        "delivery_summary": build_materialization_delivery_summary(
            deliveries=deliveries,
            reused_existing=reused_existing,
        ),
        "target_results": target_results,
        "data_delivery_ids": [delivery.data_delivery_id for delivery in deliveries],
    }
    if len(deliveries) == 1:
        only = deliveries[0]
        result.update(
            {
                "row_count": int(only.row_count),
                "output_uri": only.output_uri,
                "output_format": only.output_format,
                "data_delivery_id": only.data_delivery_id,
                "delivery_note": only.delivery_note.model_dump(),
            }
        )
    return result


def create_materialized_delivery_completions_from_record(
    *,
    request_id: str,
    record: TestDataMaterializationRecordEntity | dict[str, Any],
    target_results: list[dict[str, Any]],
    catalog_repository: DataCatalogRepository,
    reused_existing: bool = False,
) -> MaterializationCompletionBatchView:
    record_entity = require_test_data_materialization_record(record)
    deliveries: list[MaterializationDeliveryView] = []
    for target_result in target_results:
        version_id = str(target_result.get("data_object_version_id") or "").strip()
        target_record = record_entity.model_copy(update={"data_object_version_id": version_id})
        completion = create_materialized_delivery_completion_from_record(
            request_id=request_id,
            record=target_record,
            row_count=int(target_result.get("row_count") or 0),
            output_uri=str(target_result.get("output_uri") or "").strip(),
            output_format=str(target_result.get("output_format") or "").strip().lower(),
            catalog_repository=catalog_repository,
            reused_existing=reused_existing,
        )
        deliveries.append(
            MaterializationDeliveryView(
                data_object_version_id=version_id,
                row_count=int(target_result.get("row_count") or 0),
                output_uri=normalize_s3_uri(str(target_result.get("output_uri") or "").strip()),
                output_format=str(target_result.get("output_format") or "").strip().lower(),
                data_delivery_id=completion.data_delivery_id,
                delivery_note=completion.delivery_note,
            )
        )

    first = deliveries[0] if len(deliveries) == 1 else None
    return MaterializationCompletionBatchView(
        request_id=request_id,
        data_deliveries=deliveries,
        delivery_summary=build_materialization_delivery_summary(
            deliveries=deliveries,
            reused_existing=reused_existing,
        ),
        data_delivery_id=first.data_delivery_id if first is not None else None,
        delivery_note=first.delivery_note if first is not None else None,
    )


async def redis_llen(redis_url: str, key: str) -> int:
    if aioredis is not None:
        client = aioredis.from_url(redis_url, decode_responses=True)
        try:
            return int(await client.llen(key))
        finally:
            close = getattr(client, "aclose", None) or getattr(client, "close", None)
            if close is not None:
                result = close()
                if asyncio.iscoroutine(result):
                    await result

    if redis_sync is not None:
        def _len() -> int:
            client = redis_sync.from_url(redis_url, decode_responses=True)
            return int(client.llen(key))

        return int(await asyncio.to_thread(_len))

    raise HTTPException(status_code=503, detail="Redis client is unavailable")


async def redis_set_json(redis_url: str, key: str, payload: dict[str, Any], ttl_seconds: int) -> None:
    if aioredis is not None:
        client = aioredis.from_url(redis_url, decode_responses=True)
        try:
            await client.set(key, json.dumps(payload), ex=ttl_seconds)
        finally:
            close = getattr(client, "aclose", None) or getattr(client, "close", None)
            if close is not None:
                result = close()
                if asyncio.iscoroutine(result):
                    await result
        return

    if redis_sync is not None:
        def _write() -> None:
            client = redis_sync.from_url(redis_url, decode_responses=True)
            client.set(key, json.dumps(payload), ex=ttl_seconds)

        await asyncio.to_thread(_write)
        return

    raise HTTPException(status_code=503, detail="Redis client is unavailable for test data queueing")


async def redis_get_json(redis_url: str, key: str) -> dict[str, Any] | None:
    if aioredis is not None:
        client = aioredis.from_url(redis_url, decode_responses=True)
        try:
            payload = await client.get(key)
        finally:
            close = getattr(client, "aclose", None) or getattr(client, "close", None)
            if close is not None:
                result = close()
                if asyncio.iscoroutine(result):
                    await result
        return json.loads(payload) if payload else None

    if redis_sync is not None:
        def _read() -> str | None:
            client = redis_sync.from_url(redis_url, decode_responses=True)
            return client.get(key)

        payload = await asyncio.to_thread(_read)
        return json.loads(payload) if payload else None

    raise HTTPException(status_code=503, detail="Redis client is unavailable for test data queueing")


async def redis_scan_json(redis_url: str, key_pattern: str) -> list[dict[str, Any]]:
    if aioredis is not None:
        client = aioredis.from_url(redis_url, decode_responses=True)
        try:
            records: list[dict[str, Any]] = []
            async for key in client.scan_iter(match=key_pattern):
                payload = await client.get(key)
                if payload:
                    records.append(json.loads(payload))
            return records
        finally:
            close = getattr(client, "aclose", None) or getattr(client, "close", None)
            if close is not None:
                result = close()
                if asyncio.iscoroutine(result):
                    await result

    if redis_sync is not None:
        def _scan() -> list[dict[str, Any]]:
            client = redis_sync.from_url(redis_url, decode_responses=True)
            records: list[dict[str, Any]] = []
            for key in client.scan_iter(match=key_pattern):
                payload = client.get(key)
                if payload:
                    records.append(json.loads(payload))
            return records

        return await asyncio.to_thread(_scan)

    raise HTTPException(status_code=503, detail="Redis client is unavailable for test data queueing")


async def redis_lpush(redis_url: str, queue_key: str, payload: dict[str, Any]) -> None:
    serialized = json.dumps(payload)
    if aioredis is not None:
        client = aioredis.from_url(redis_url, decode_responses=True)
        try:
            await client.lpush(queue_key, serialized)
        finally:
            close = getattr(client, "aclose", None) or getattr(client, "close", None)
            if close is not None:
                result = close()
                if asyncio.iscoroutine(result):
                    await result
        return

    if redis_sync is not None:
        def _push() -> None:
            client = redis_sync.from_url(redis_url, decode_responses=True)
            client.lpush(queue_key, serialized)

        await asyncio.to_thread(_push)
        return

    raise HTTPException(status_code=503, detail="Redis client is unavailable for test data queueing")


async def write_test_data_materialization_record(
    redis_url: str,
    record: TestDataMaterializationRecordEntity | dict[str, Any],
) -> None:
    await _materialization_service.write_test_data_materialization_record(
        redis_url,
        record,
        _TEST_DATA_MATERIALIZATION_REQUEST_TTL_SECONDS,
        test_data_materialization_request_key,
        test_data_materialization_record_payload,
        redis_set_json,
    )


async def read_test_data_materialization_record(
    redis_url: str,
    request_id: str,
) -> TestDataMaterializationRecordEntity | None:
    return await _materialization_service.read_test_data_materialization_record(
        redis_url,
        request_id,
        test_data_materialization_request_key,
        require_test_data_materialization_record,
        redis_get_json,
    )


def inject_queue_trace_headers(queue_payload: dict[str, Any]) -> None:
    _service_inject_queue_trace_headers(queue_payload)


async def register_materialized_delivery_completion(
    *,
    request_id: str,
    payload: ReportTestDataMaterializationCompletionRequest,
    catalog_repository: DataCatalogRepository,
) -> TestDataMaterializationCompletionView:
    return await _materialization_service.register_materialized_delivery_completion(
        request_id=request_id,
        payload=payload,
        catalog_repository=catalog_repository,
        resolve_redis_url=resolve_test_data_redis_url,
        read_record=read_test_data_materialization_record,
        require_record=require_test_data_materialization_record,
        normalize_s3_uri_fn=normalize_s3_uri,
        ensure_synthetic_output_uri_fn=ensure_synthetic_test_output_uri,
        create_completions_from_record=create_materialized_delivery_completions_from_record,
        build_completion_response=lambda delivery: TestDataMaterializationCompletionView(
            data_delivery_id=delivery.data_delivery_id,
            delivery_note=delivery.delivery_note,
        ),
    )


async def register_materialized_delivery_completions(
    *,
    request_id: str,
    target_results: list[MaterializationTargetResultRequest],
    catalog_repository: DataCatalogRepository,
) -> MaterializationCompletionBatchView:
    return await _materialization_service.register_materialized_delivery_completions(
        request_id=request_id,
        target_results=target_results,
        catalog_repository=catalog_repository,
        resolve_redis_url=resolve_test_data_redis_url,
        read_record=read_test_data_materialization_record,
        require_record=require_test_data_materialization_record,
        expected_targets_from_record=expected_materialization_targets_from_record,
        normalize_s3_uri_fn=normalize_s3_uri,
        ensure_synthetic_output_uri_fn=ensure_synthetic_test_output_uri,
        create_completions_from_record=create_materialized_delivery_completions_from_record,
    )


async def enqueue_test_data_materialization_request(
    *,
    request_headers: Mapping[str, str],
    version_id: str,
    sample_count: int,
    output_format: str,
    output_uri: str | None,
    selected_attribute_names: list[str] | None = None,
    refresh: bool = False,
    catalog_repository: DataCatalogRepository,
    selection: dict[str, Any] | None = None,
    targets: list[dict[str, Any]] | None = None,
    request_contract: str | None = None,
) -> TestDataMaterializationRecordEntity:
    return await _materialization_service.enqueue_test_data_materialization_request(
        request_headers=request_headers,
        version_id=version_id,
        sample_count=sample_count,
        output_format=output_format,
        output_uri=output_uri,
        selected_attribute_names=selected_attribute_names,
        refresh=refresh,
        catalog_repository=catalog_repository,
        selection=selection,
        targets=targets,
        request_contract=request_contract,
        resolve_redis_url=resolve_test_data_redis_url,
        resolve_queue_key=resolve_test_data_materialization_queue_key,
        resolve_processing_queue_key=resolve_test_data_materialization_processing_queue_key,
        redis_llen=redis_llen,
        s3_prefix_has_objects_fn=s3_prefix_has_objects,
        build_attribute_payloads_fn=build_attribute_payloads,
        resolve_output_prefix=resolve_test_data_output_prefix,
        default_output_uri=default_materialization_output_uri,
        ensure_synthetic_output_uri_fn=ensure_synthetic_test_output_uri,
        normalize_s3_uri_fn=normalize_s3_uri,
        build_record=build_test_data_materialization_record,
        create_completions_from_record=create_materialized_delivery_completions_from_record,
        build_result_from_deliveries=build_materialization_result_from_deliveries,
        current_timestamp=current_timestamp,
        write_record=lambda redis_url, record: write_test_data_materialization_record(
            redis_url,
            test_data_materialization_record_payload(record),
        ),
        push_queue=redis_lpush,
        inject_queue_trace_headers=inject_queue_trace_headers,
        queue_job_type=_TEST_DATA_MATERIALIZATION_JOB_TYPE,
    )