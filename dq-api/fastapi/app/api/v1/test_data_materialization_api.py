from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from app.api.presenters.data_catalog import build_catalog_materialization_targets
from app.api.presenters.data_catalog import resolve_catalog_materialization_selection
from app.api.v1 import test_data_materialization_support as _materialization_support
from app.api.v1.schemas.test_data_materialization_view import MaterializationCompletionBatchView
from app.api.v1.schemas.test_data_materialization_view import MaterializationTargetResultRequest
from app.api.v1.schemas.test_data_materialization_view import ReportTestDataMaterializationCompletionRequest
from app.api.v1.schemas.test_data_materialization_view import TestDataMaterializationCompletionView
from app.api.v1.schemas.test_data_materialization_view import TestDataMaterializationRequestView
from app.application.services import test_data_materialization_service as _materialization_service
from app.domain.entities import TestDataMaterializationRecordEntity
from app.domain.interfaces import DataCatalogRepository

_build_attribute_payloads = _materialization_support.build_attribute_payloads
_default_materialization_output_uri = _materialization_support.default_materialization_output_uri
_normalize_s3_uri = _materialization_support.normalize_s3_uri
_resolve_test_data_output_prefix = _materialization_support.resolve_test_data_output_prefix
_resolve_test_data_redis_url = _materialization_support.resolve_test_data_redis_url
_redis_llen = _materialization_support.redis_llen
_redis_lpush = _materialization_support.redis_lpush
_write_test_data_materialization_record = _materialization_support.write_test_data_materialization_record
_s3_prefix_has_objects = _materialization_support.s3_prefix_has_objects
_build_test_data_materialization_record = _materialization_support.build_test_data_materialization_record
_create_materialized_delivery_completions_from_record = _materialization_support.create_materialized_delivery_completions_from_record
_build_materialization_result_from_deliveries = _materialization_support.build_materialization_result_from_deliveries
_test_data_materialization_record_payload = _materialization_support.test_data_materialization_record_payload
_require_test_data_materialization_record = _materialization_support.require_test_data_materialization_record
_expected_materialization_targets_from_record = _materialization_support.expected_materialization_targets_from_record
_ensure_synthetic_test_output_uri = _materialization_support.ensure_synthetic_test_output_uri
_current_timestamp = _materialization_support.current_timestamp
_inject_queue_trace_headers = _materialization_support.inject_queue_trace_headers
_resolve_test_data_materialization_queue_key = _materialization_support.resolve_test_data_materialization_queue_key
_resolve_test_data_materialization_processing_queue_key = (
    _materialization_support.resolve_test_data_materialization_processing_queue_key
)
_test_data_materialization_request_key = _materialization_support.test_data_materialization_request_key


async def _read_test_data_materialization_record(
    redis_url: str,
    request_id: str,
) -> TestDataMaterializationRecordEntity | None:
    return await _materialization_service.read_test_data_materialization_record(
        redis_url,
        request_id,
        _test_data_materialization_request_key,
        _require_test_data_materialization_record,
        _materialization_support.redis_get_json,
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


async def _enqueue_test_data_materialization_request(
    *,
    request_headers: Any,
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
        queue_job_type="test_data_materialization",
    )


async def create_catalog_materialization_request(
    *,
    request_headers: Any,
    payload: Any,
    repository: DataCatalogRepository,
) -> TestDataMaterializationRequestView:
    resolved_targets, selection = resolve_catalog_materialization_selection(payload, repository)
    queue_targets, selection, request_output_uri = build_catalog_materialization_targets(
        payload=payload,
        resolved_targets=resolved_targets,
        selection=selection,
        repository=repository,
        build_attribute_payloads=_build_attribute_payloads,
        normalize_s3_uri=_normalize_s3_uri,
        resolve_test_data_output_prefix=_resolve_test_data_output_prefix,
        default_materialization_output_uri=_default_materialization_output_uri,
    )

    record = await _enqueue_test_data_materialization_request(
        request_headers=request_headers,
        version_id=str(queue_targets[0]["data_object_version_id"]),
        sample_count=int(payload.sample_count),
        output_format=str(payload.output_format),
        output_uri=request_output_uri,
        selected_attribute_names=[],
        refresh=bool(payload.refresh),
        catalog_repository=repository,
        selection=selection,
        targets=queue_targets,
        request_contract="catalog_materialization_v1",
    )
    return TestDataMaterializationRequestView.model_validate(record)


async def get_materialization_request_view(request_id: str) -> TestDataMaterializationRequestView:
    redis_url = _resolve_test_data_redis_url()
    if not redis_url:
        raise HTTPException(status_code=503, detail="Test data materialization queue is not configured")

    record = await _read_test_data_materialization_record(redis_url, request_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Test data materialization '{request_id}' not found")
    return TestDataMaterializationRequestView.model_validate(record)


async def report_materialization_request_completion(
    *,
    request_id: str,
    payload: Any,
    repository: DataCatalogRepository,
) -> MaterializationCompletionBatchView:
    target_results = list(payload.target_results or [])
    if not target_results:
        redis_url = _resolve_test_data_redis_url()
        if not redis_url:
            raise HTTPException(status_code=503, detail="Test data materialization queue is not configured")
        record = await _read_test_data_materialization_record(redis_url, request_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"Test data materialization '{request_id}' not found")
        target_results = [
            MaterializationTargetResultRequest(
                data_object_version_id=str(record.get("data_object_version_id") or "").strip(),
                row_count=int(payload.row_count or 0),
                output_uri=str(payload.output_uri or ""),
                output_format=str(payload.output_format or record.get("output_format") or "parquet"),
            )
        ]

    return await _register_materialized_delivery_completions(
        request_id=request_id,
        target_results=target_results,
        catalog_repository=repository,
    )