from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
import io
import json
import math
import os
import textwrap
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, Request
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.core.runtime_queues import resolve_profiling_queue_key as _resolve_runtime_profiling_queue_key

try:
    import redis.asyncio as aioredis
except Exception:
    aioredis = None

try:
    import redis as redis_sync
except Exception:
    redis_sync = None

from app.api.presenters.testing import build_generated_data_test_proof_update_payload
from app.api.presenters.testing import build_batch_test_execution_context_payload
from app.api.presenters.testing import build_manual_test_proof_storage_payload
from app.api.presenters.testing import build_test_markdown_report
from app.api.presenters.testing import build_testing_scheduler_handoff_entity
from app.api.presenters.testing import merge_test_run_execution_context
from app.api.presenters.testing import render_test_proof_version_diff_section
from app.api.presenters.testing import serialize_rule_execution_context_payload
from app.api.v1 import test_data_materialization_support as _materialization_support
from app.api.v1 import test_data_queue_support as _test_data_queue_support
from app.api.v1.schemas import DataDeliveryNoteView
from app.api.v1.schemas.test_data_materialization_view import MaterializationCompletionBatchView
from app.api.v1.schemas.test_data_materialization_view import MaterializationDeliveryView
from app.api.v1.schemas.test_data_materialization_view import MaterializationTargetResultRequest
from app.api.v1.schemas.test_data_materialization_view import ReportTestDataMaterializationCompletionRequest
from app.api.v1.schemas.test_data_materialization_view import TestDataMaterializationCompletionView
from app.api.v1.schemas.test_data_materialization_view import TestDataMaterializationRequestView
from app.api.v1.schemas.test_data_queue_view import CreateQueuedTestDataRequest
from app.api.v1.schemas.test_data_queue_view import QueuedTestDataRequestView
from app.api.v1.schemas.test_data_queue_view import TestDataAttributeRequest
from app.application.services import test_data_materialization_service as _materialization_service
from app.application.services.test_data_queue_service import build_test_data_request_record as _service_build_test_data_request_record
from app.application.services.test_data_queue_service import enqueue_queued_test_data_request as _service_enqueue_queued_test_data_request
from app.application.services.test_data_queue_service import inject_queue_trace_headers as _service_inject_queue_trace_headers
from app.application.services.test_data_queue_service import read_test_data_request_record as _service_read_test_data_request_record
from app.application.services.test_data_queue_service import test_data_request_key as _service_test_data_request_key
from app.application.services.test_data_queue_service import wait_for_test_data_request_result as _service_wait_for_test_data_request_result
from app.application.services.test_data_queue_service import write_test_data_request_record as _service_write_test_data_request_record
from app.domain.entities import QueuedTestDataRequestRecordEntity
from app.domain.entities import RuleExecutionContextEntity
from app.domain.entities import TestDataMaterializationRecordEntity
from app.domain.interfaces.v1.data_catalog_repository import DataCatalogRepository

_TEST_DATA_MATERIALIZATION_JOB_TYPE = "test_data_materialization"
_TEST_DATA_MATERIALIZATION_REQUEST_TTL_SECONDS = 3600
_TEST_DATA_REQUEST_TTL_SECONDS = 3600
_TEST_DATA_REQUEST_POLL_INTERVAL_SECONDS = 0.5
_TEST_DATA_REQUEST_WAIT_TIMEOUT_SECONDS = 300.0


def _markdown_to_pdf_bytes(markdown_text: str) -> bytes:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    margin_x = 40
    margin_y = 40
    line_height = 14
    y = height - margin_y

    pdf.setFont("Helvetica", 10)

    for raw_line in markdown_text.splitlines():
        line = raw_line.rstrip()
        wrapped = textwrap.wrap(line, width=105) if line else [""]
        for part in wrapped:
            if y <= margin_y:
                pdf.showPage()
                pdf.setFont("Helvetica", 10)
                y = height - margin_y
            pdf.drawString(margin_x, y, part)
            y -= line_height

    pdf.save()
    buffer.seek(0)
    return buffer.getvalue()


def _build_scheduler_handoff_payload(
    request_id: str,
    execution_context: RuleExecutionContextEntity | dict[str, Any] | None,
    correlation_id: str,
) -> dict:
    return build_testing_scheduler_handoff_entity(
        request_id,
        execution_context,
        correlation_id,
    ).model_dump(mode="python")


def _paginate(rows: list[dict], page: int, limit: int) -> dict:
    safe_page = max(1, page)
    safe_limit = max(1, min(100, limit))
    offset = (safe_page - 1) * safe_limit
    total = len(rows)
    total_pages = math.ceil(total / safe_limit) if total else 0

    return {
        "data": rows[offset : offset + safe_limit],
        "pagination": {
            "total": total,
            "page": safe_page,
            "limit": safe_limit,
            "total_pages": total_pages,
            "has_next": safe_page < total_pages,
            "has_previous": safe_page > 1,
        },
    }


def _current_timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _require_queued_test_data_request_record(
    record: QueuedTestDataRequestRecordEntity | dict[str, Any],
) -> QueuedTestDataRequestRecordEntity:
    return _test_data_queue_support.require_queued_test_data_request_record(record)


def _queued_test_data_request_record_payload(
    record: QueuedTestDataRequestRecordEntity | dict[str, Any],
) -> dict[str, Any]:
    return _test_data_queue_support.queued_test_data_request_record_payload(record)


def _queued_test_data_request_field(
    record: QueuedTestDataRequestRecordEntity | dict[str, Any],
    field_name: str,
) -> Any:
    return _test_data_queue_support.queued_test_data_request_field(record, field_name)


def _require_test_data_materialization_record(
    record: TestDataMaterializationRecordEntity | dict[str, Any],
) -> TestDataMaterializationRecordEntity:
    return _materialization_support.require_test_data_materialization_record(record)


def _test_data_materialization_record_payload(
    record: TestDataMaterializationRecordEntity | dict[str, Any],
) -> dict[str, Any]:
    return _materialization_support.test_data_materialization_record_payload(record)


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


def _resolve_test_data_redis_url() -> str | None:
    return _materialization_support.resolve_test_data_redis_url()


def _resolve_test_data_materialization_queue_key() -> str:
    return _materialization_support.resolve_test_data_materialization_queue_key()


def _resolve_test_data_materialization_processing_queue_key(queue_key: str) -> str:
    return _materialization_support.resolve_test_data_materialization_processing_queue_key(queue_key)


def _resolve_test_data_output_prefix() -> str:
    return _materialization_support.resolve_test_data_output_prefix()


async def _redis_llen(redis_url: str, key: str) -> int:
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


def _test_data_materialization_request_key(request_id: str) -> str:
    return _materialization_support.test_data_materialization_request_key(request_id)


def _default_materialization_output_uri(
    *,
    output_prefix: str,
    version_id: str,
    output_format: str,
    sample_count: int,
    attribute_hash: str,
) -> str:
    return _materialization_support.default_materialization_output_uri(
        output_prefix=output_prefix,
        version_id=version_id,
        output_format=output_format,
        sample_count=sample_count,
        attribute_hash=attribute_hash,
    )


def _normalize_s3_uri(uri: str) -> str:
    return _materialization_support.normalize_s3_uri(uri)


def _parse_s3a_uri(uri: str) -> tuple[str, str]:
    return _materialization_service.parse_s3a_uri(uri)


def _matched_real_evidence_output_uri_terms(output_uri: str) -> list[str]:
    return _materialization_service.matched_real_evidence_output_uri_terms(output_uri)


def _ensure_synthetic_test_output_uri(
    *,
    output_uri: str,
    status_code: int,
    request_id: str | None = None,
    data_object_version_id: str | None = None,
    correlation_id: str | None = None,
) -> None:
    _materialization_support.ensure_synthetic_test_output_uri(
        output_uri=output_uri,
        status_code=status_code,
        request_id=request_id,
        data_object_version_id=data_object_version_id,
        correlation_id=correlation_id,
    )


def _resolve_optional_bool_env(name: str) -> bool | None:
    return _materialization_service.resolve_optional_bool_env(name)


def _derive_s3_ssl_enabled() -> bool:
    return _materialization_service.derive_s3_ssl_enabled()


def _build_s3_client() -> Any:
    return _materialization_support.build_s3_client()


def _s3_prefix_has_objects(*, output_uri: str) -> bool:
    return _materialization_service.s3_prefix_has_objects(output_uri=output_uri, build_s3_client_fn=_build_s3_client)


def _build_test_data_materialization_record(
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
        requested_at=_current_timestamp(),
        started_at=None,
        completed_at=None,
        error_message=None,
        correlation_id=correlation_id,
        queue_key=queue_key,
        processing_queue_key=processing_queue_key,
        selection=dict(selection) if isinstance(selection, dict) else None,
        result=None,
    )


def _resolve_materialization_storage_location(output_uri: str) -> str:
    return _materialization_support.resolve_materialization_storage_location(output_uri)


def _build_materialized_delivery_payload(
    *,
    request_id: str,
    record: TestDataMaterializationRecordEntity | dict[str, Any],
    row_count: int,
    output_uri: str,
    output_format: str,
    catalog_repository: DataCatalogRepository,
    reused_existing: bool = False,
) -> dict[str, Any]:
    record_entity = _require_test_data_materialization_record(record)
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

    delivered_at = _current_timestamp()
    correlation_id = str(record_entity.correlation_id or "").strip()
    return {
        "data_object_id": str(version_entity.data_object_id or ""),
        "data_object_version_id": version_id,
        "version": int(version_entity.version or 0),
        "delivered_at": delivered_at,
        "layer": "standardized",
        "storage_location": _resolve_materialization_storage_location(output_uri),
        "delivery_location": _normalize_s3_uri(output_uri),
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
            "output_uri": _normalize_s3_uri(output_uri),
            "sample_count": int(record_entity.sample_count or 0),
            "reused_existing": bool(reused_existing),
            "object_storage_classification": "synthetic_test",
            "evidence_classification": "synthetic_result",
            "selection": dict(record_entity.selection) if isinstance(record_entity.selection, dict) else None,
        },
    }


def _create_materialized_delivery_completion_from_record(
    *,
    request_id: str,
    record: TestDataMaterializationRecordEntity | dict[str, Any],
    row_count: int,
    output_uri: str,
    output_format: str,
    catalog_repository: DataCatalogRepository,
    reused_existing: bool = False,
) -> TestDataMaterializationCompletionView:
    record_entity = _require_test_data_materialization_record(record)
    delivery_payload = _build_materialized_delivery_payload(
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


def _expected_materialization_targets_from_record(
    record: TestDataMaterializationRecordEntity | dict[str, Any],
) -> list[dict[str, Any]]:
    return _materialization_support.expected_materialization_targets_from_record(record)


def _build_materialization_delivery_summary(
    *,
    deliveries: list[MaterializationDeliveryView],
    reused_existing: bool,
) -> dict[str, Any]:
    return _materialization_support.build_materialization_delivery_summary(
        deliveries=deliveries,
        reused_existing=reused_existing,
    )


def _build_materialization_result_from_deliveries(
    *,
    deliveries: list[MaterializationDeliveryView],
    request_output_uri: str,
    output_format: str,
    reused_existing: bool,
) -> dict[str, Any]:
    return _materialization_support.build_materialization_result_from_deliveries(
        deliveries=deliveries,
        request_output_uri=request_output_uri,
        output_format=output_format,
        reused_existing=reused_existing,
    )


def _create_materialized_delivery_completions_from_record(
    *,
    request_id: str,
    record: TestDataMaterializationRecordEntity | dict[str, Any],
    target_results: list[dict[str, Any]],
    catalog_repository: DataCatalogRepository,
    reused_existing: bool = False,
) -> MaterializationCompletionBatchView:
    record_entity = _require_test_data_materialization_record(record)
    deliveries: list[MaterializationDeliveryView] = []
    for target_result in target_results:
        version_id = str(target_result.get("data_object_version_id") or "").strip()
        target_record = record_entity.model_copy(update={"data_object_version_id": version_id})
        completion = _create_materialized_delivery_completion_from_record(
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
                output_uri=_normalize_s3_uri(str(target_result.get("output_uri") or "").strip()),
                output_format=str(target_result.get("output_format") or "").strip().lower(),
                data_delivery_id=completion.data_delivery_id,
                delivery_note=completion.delivery_note,
            )
        )

    first = deliveries[0] if len(deliveries) == 1 else None
    return MaterializationCompletionBatchView(
        request_id=request_id,
        data_deliveries=deliveries,
        delivery_summary=_build_materialization_delivery_summary(
            deliveries=deliveries,
            reused_existing=reused_existing,
        ),
        data_delivery_id=first.data_delivery_id if first is not None else None,
        delivery_note=first.delivery_note if first is not None else None,
    )


async def _register_materialized_delivery_completion(
    *,
    request_id: str,
    payload: ReportTestDataMaterializationCompletionRequest,
    catalog_repository: DataCatalogRepository,
) -> TestDataMaterializationCompletionView:
    return await _materialization_service.register_materialized_delivery_completion(
        request_id=request_id,
        payload=payload,
        catalog_repository=catalog_repository,
        resolve_redis_url=_resolve_test_data_redis_url,
        read_record=_read_test_data_materialization_record,
        require_record=_require_test_data_materialization_record,
        normalize_s3_uri_fn=_normalize_s3_uri,
        ensure_synthetic_output_uri_fn=_ensure_synthetic_test_output_uri,
        create_completions_from_record=_create_materialized_delivery_completions_from_record,
        build_completion_response=lambda delivery: TestDataMaterializationCompletionView(
            data_delivery_id=delivery.data_delivery_id,
            delivery_note=delivery.delivery_note,
        ),
    )


async def _register_materialized_delivery_completions(
    *,
    request_id: str,
    target_results: list[MaterializationTargetResultRequest],
    catalog_repository: DataCatalogRepository,
) -> MaterializationCompletionBatchView:
    return await _materialization_service.register_materialized_delivery_completions(
        request_id=request_id,
        target_results=target_results,
        catalog_repository=catalog_repository,
        resolve_redis_url=_resolve_test_data_redis_url,
        read_record=_read_test_data_materialization_record,
        require_record=_require_test_data_materialization_record,
        expected_targets_from_record=_expected_materialization_targets_from_record,
        normalize_s3_uri_fn=_normalize_s3_uri,
        ensure_synthetic_output_uri_fn=_ensure_synthetic_test_output_uri,
        create_completions_from_record=_create_materialized_delivery_completions_from_record,
    )


async def _write_test_data_materialization_record(
    redis_url: str,
    record: TestDataMaterializationRecordEntity | dict[str, Any],
) -> None:
    await _materialization_service.write_test_data_materialization_record(
        redis_url,
        record,
        _TEST_DATA_MATERIALIZATION_REQUEST_TTL_SECONDS,
        _test_data_materialization_request_key,
        _test_data_materialization_record_payload,
        _redis_set_json,
    )


async def _read_test_data_materialization_record(
    redis_url: str,
    request_id: str,
) -> TestDataMaterializationRecordEntity | None:
    return await _materialization_service.read_test_data_materialization_record(
        redis_url,
        request_id,
        _test_data_materialization_request_key,
        _require_test_data_materialization_record,
        _redis_get_json,
    )


async def _enqueue_test_data_materialization_request(
    *,
    request: Request,
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
        request_headers=request.headers,
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
        resolve_redis_url=_resolve_test_data_redis_url,
        resolve_queue_key=_resolve_test_data_materialization_queue_key,
        resolve_processing_queue_key=_resolve_test_data_materialization_processing_queue_key,
        redis_llen=_redis_llen,
        s3_prefix_has_objects_fn=_s3_prefix_has_objects,
        build_attribute_payloads_fn=_build_attribute_payloads,
        resolve_output_prefix=_resolve_test_data_output_prefix,
        default_output_uri=_default_materialization_output_uri,
        ensure_synthetic_output_uri_fn=_ensure_synthetic_test_output_uri,
        normalize_s3_uri_fn=_normalize_s3_uri,
        build_record=_build_test_data_materialization_record,
        create_completions_from_record=_create_materialized_delivery_completions_from_record,
        build_result_from_deliveries=_build_materialization_result_from_deliveries,
        current_timestamp=_current_timestamp,
        write_record=lambda redis_url, record: _write_test_data_materialization_record(
            redis_url,
            _test_data_materialization_record_payload(record),
        ),
        push_queue=_redis_lpush,
        inject_queue_trace_headers=_inject_queue_trace_headers,
        queue_job_type=_TEST_DATA_MATERIALIZATION_JOB_TYPE,
    )


def _test_data_request_key(request_id: str) -> str:
    return _service_test_data_request_key(request_id)


def _build_mock_preview_attributes() -> list[dict[str, Any]]:
    return _test_data_queue_support.build_mock_preview_attributes()


def _build_attribute_payloads(attributes: list[Any]) -> list[dict[str, Any]]:
    return _materialization_support.build_attribute_payloads(attributes)


def _resolve_version_generation_payload(
    version_id: str,
    sample_count: int,
    catalog_repository: DataCatalogRepository,
) -> dict[str, Any]:
    return _test_data_queue_support.resolve_version_generation_payload(
        version_id,
        sample_count,
        catalog_repository,
    )


def _resolve_queued_test_data_request_payload(
    payload: CreateQueuedTestDataRequest,
    catalog_repository: DataCatalogRepository,
) -> dict[str, Any]:
    return _test_data_queue_support.resolve_queued_test_data_request_payload(payload, catalog_repository)


def _inject_queue_trace_headers(queue_payload: dict[str, Any]) -> None:
    _service_inject_queue_trace_headers(queue_payload)


def _build_test_data_request_record(
    *,
    request_id: str,
    job_id: str,
    correlation_id: str,
    request_payload: dict[str, Any],
) -> QueuedTestDataRequestRecordEntity:
    return _require_queued_test_data_request_record(
        _service_build_test_data_request_record(
            request_id=request_id,
            job_id=job_id,
            correlation_id=correlation_id,
            request_payload=request_payload,
            current_timestamp=_current_timestamp(),
        )
    )


async def _redis_set_json(redis_url: str, key: str, payload: dict[str, Any], ttl_seconds: int) -> None:
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


async def _redis_get_json(redis_url: str, key: str) -> dict[str, Any] | None:
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


async def _redis_lpush(redis_url: str, queue_key: str, payload: dict[str, Any]) -> None:
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


async def _write_test_data_request_record(
    redis_url: str,
    record: QueuedTestDataRequestRecordEntity | dict[str, Any],
) -> None:
    await _service_write_test_data_request_record(
        redis_url,
        _queued_test_data_request_record_payload(record),
        _TEST_DATA_REQUEST_TTL_SECONDS,
        _redis_set_json,
    )


async def _read_test_data_request_record(
    redis_url: str,
    request_id: str,
) -> QueuedTestDataRequestRecordEntity | None:
    payload = await _service_read_test_data_request_record(redis_url, request_id, _redis_get_json)
    if payload is None:
        return None
    return _require_queued_test_data_request_record(payload)


async def _enqueue_queued_test_data_request(
    *,
    request: Request,
    request_payload: dict[str, Any],
) -> QueuedTestDataRequestRecordEntity:
    redis_url = _resolve_test_data_redis_url()
    if not redis_url:
        raise HTTPException(status_code=503, detail="Test data queue is not configured")
    record = await _service_enqueue_queued_test_data_request(
        request_headers=request.headers,
        request_payload=request_payload,
        redis_url=redis_url,
        queue_key=_resolve_test_data_queue_key(),
        ttl_seconds=_TEST_DATA_REQUEST_TTL_SECONDS,
        current_timestamp=_current_timestamp(),
        find_active_request=_test_data_queue_support.find_active_queued_test_data_request,
        write_record=lambda url, record, ttl: _service_write_test_data_request_record(url, record, ttl, _redis_set_json),
        push_queue=_redis_lpush,
    )
    return _require_queued_test_data_request_record(record)


async def _wait_for_test_data_request_result(request_id: str) -> QueuedTestDataRequestRecordEntity:
    redis_url = _resolve_test_data_redis_url()
    if not redis_url:
        raise HTTPException(status_code=503, detail="Test data queue is not configured")
    record = await _service_wait_for_test_data_request_result(
        request_id=request_id,
        redis_url=redis_url,
        read_record=lambda url, rid: _service_read_test_data_request_record(url, rid, _redis_get_json),
        poll_interval_seconds=_TEST_DATA_REQUEST_POLL_INTERVAL_SECONDS,
        wait_timeout_seconds=_TEST_DATA_REQUEST_WAIT_TIMEOUT_SECONDS,
    )
    return _require_queued_test_data_request_record(record)


def _as_queued_test_data_request_view(
    record: QueuedTestDataRequestRecordEntity | dict[str, Any],
) -> QueuedTestDataRequestView:
    return QueuedTestDataRequestView.model_validate(_queued_test_data_request_record_payload(record))


def _as_test_data_materialization_request_view(
    record: TestDataMaterializationRecordEntity | dict[str, Any],
) -> TestDataMaterializationRequestView:
    return TestDataMaterializationRequestView.model_validate(_test_data_materialization_record_payload(record))


def _bind_queued_test_data_request_enqueuer(
    request: Request,
) -> Callable[[dict[str, Any]], Awaitable[QueuedTestDataRequestRecordEntity]]:
    async def _enqueue(request_payload: dict[str, Any]) -> QueuedTestDataRequestRecordEntity:
        return await _enqueue_queued_test_data_request(request=request, request_payload=request_payload)

    return _enqueue


def _bind_test_data_materialization_request_enqueuer(
    request: Request,
    catalog_repository: DataCatalogRepository,
) -> Callable[..., Awaitable[TestDataMaterializationRecordEntity]]:
    async def _enqueue(**kwargs: Any) -> TestDataMaterializationRecordEntity:
        return await _enqueue_test_data_materialization_request(
            request=request,
            catalog_repository=catalog_repository,
            **kwargs,
        )

    return _enqueue


def _bind_materialized_delivery_completion_registrar(
    catalog_repository: DataCatalogRepository,
) -> Callable[[str, ReportTestDataMaterializationCompletionRequest], Awaitable[TestDataMaterializationCompletionView]]:
    async def _register(
        request_id: str,
        payload: ReportTestDataMaterializationCompletionRequest,
    ) -> TestDataMaterializationCompletionView:
        return await _register_materialized_delivery_completion(
            request_id=request_id,
            payload=payload,
            catalog_repository=catalog_repository,
        )

    return _register

