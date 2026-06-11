from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from fastapi import HTTPException

from app.application.services.exception_reason_taxonomy import normalize_exception_reason_code
from app.domain.entities import ExceptionRecordCreateEntity
from app.domain.entities import GxExecutionRunEntity
from app.domain.entities import build_exception_record_create_entity
from app.domain.entities.gx_execution_run import build_gx_execution_contract_entity
from app.domain.entities.gx_execution_run import build_gx_execution_diagnostic_entities
from app.domain.entities.gx_execution_run import build_gx_execution_result_item_entities
from app.domain.entities.gx_execution_run import build_gx_execution_result_summary_entity
from app.domain.interfaces import ExceptionFactRepository
from app.domain.interfaces import ExceptionReasonAnalyticsProjectionRepository
from app.application.services.exception_fact_validation import exception_fact_validation_service


def _entity_payload(entity: Any) -> dict[str, Any]:
    if entity is None:
        return {}
    if hasattr(entity, "model_dump"):
        payload = entity.model_dump(by_alias=True, exclude_none=True)
        return payload if isinstance(payload, dict) else {}
    if isinstance(entity, dict):
        return dict(entity)
    return {}


def _read_payload_string(payload: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = payload.get(key)
        normalized = str(value or "").strip()
        if normalized:
            return normalized
    return None


def _read_payload_int(payload: dict[str, Any], *keys: str) -> int | None:
    for key in keys:
        value = payload.get(key)
        if value in (None, ""):
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return None


def _to_exception_record_payload(record: ExceptionRecordCreateEntity | Mapping[str, Any]) -> dict[str, Any]:
    exception_record = build_exception_record_create_entity(record)
    ops_metadata = dict(exception_record.opsMetadata)
    if exception_record.failureClass and not str(ops_metadata.get("failure_class") or "").strip():
        ops_metadata["failure_class"] = exception_record.failureClass

    payload = {
        "id": exception_record.id,
        "data_object_version_id": exception_record.dataObjectVersionId,
        "execution_run_id": exception_record.executionRunId,
        "rule_id": exception_record.ruleId,
        "record_identifier_type": exception_record.recordIdentifierType,
        "record_identifier_value": exception_record.recordIdentifierValue,
        "reason_code": exception_record.reasonCode,
        "reason_text": exception_record.reasonText,
        "ops_metadata": ops_metadata,
        "detected_at": exception_record.detectedAt,
    }
    if exception_record.failureClass:
        payload["failure_class"] = exception_record.failureClass
    return payload


def _extract_run_execution_contract(execution_context: GxExecutionRunEntity):
    return build_gx_execution_contract_entity(execution_context.executionContract)


def _build_violation_lineage_metadata(execution_context: GxExecutionRunEntity) -> dict[str, Any]:
    execution_contract = _extract_run_execution_contract(execution_context)
    execution_contract_payload = _entity_payload(execution_contract)
    handoff_payload = _entity_payload(execution_context.handoffPayload)
    delivery_snapshot = execution_context.handoffPayload.deliverySnapshot if execution_context.handoffPayload is not None else None
    delivery_snapshot_payload = _entity_payload(delivery_snapshot)
    traceability = execution_contract.traceability if execution_contract is not None else None

    validation_artifact_id = (
        str(execution_context.suiteId or "").strip()
        or str(traceability.gxSuiteId or "").strip()
        or _read_payload_string(handoff_payload, "validation_artifact_id")
    )
    validation_artifact_version = (
        execution_context.suiteVersion
        if execution_context.suiteVersion not in (None, "")
        else traceability.gxSuiteVersion
    )
    if validation_artifact_version in (None, ""):
        validation_artifact_version = _read_payload_int(handoff_payload, "validation_artifact_version")

    execution_plan_id = _read_payload_string(
        handoff_payload,
        "execution_plan_id",
        "run_plan_id",
    ) or _read_payload_string(
        execution_contract_payload,
        "execution_plan_id",
        "run_plan_id",
    )
    execution_plan_version_id = _read_payload_string(
        handoff_payload,
        "execution_plan_version_id",
        "run_plan_version_id",
    ) or _read_payload_string(
        execution_contract_payload,
        "execution_plan_version_id",
        "run_plan_version_id",
    )

    lineage = {
        "suite_id": validation_artifact_id or None,
        "suite_version": validation_artifact_version,
        "validation_artifact_id": validation_artifact_id or None,
        "validation_artifact_version": validation_artifact_version,
        "rule_version_id": str(execution_context.ruleVersionId or "").strip() or None,
        "correlation_id": str(execution_context.correlationId or "").strip() or None,
        "engine_type": str(execution_context.engineType or "").strip() or None,
        "engine_target": str(execution_context.engineTarget or "").strip() or None,
        "execution_shape": str(execution_context.executionShape or "").strip() or None,
        "execution_plan_id": execution_plan_id,
        "execution_plan_version_id": execution_plan_version_id,
        "delivery_id": (
            str(execution_contract.resolvedDataDeliveryId or "").strip()
            if execution_contract is not None
            else None
        )
        or (
            str(delivery_snapshot.resolvedDataDeliveryId or "").strip()
            if delivery_snapshot is not None
            else None
        )
        or _read_payload_string(execution_contract_payload, "resolved_data_delivery_id")
        or _read_payload_string(delivery_snapshot_payload, "resolved_data_delivery_id"),
        "delivery_location": (
            str(execution_contract.resolvedDeliveryLocation or "").strip()
            if execution_contract is not None
            else None
        )
        or (
            str(delivery_snapshot.resolvedDeliveryLocation or "").strip()
            if delivery_snapshot is not None
            else None
        )
        or _read_payload_string(execution_contract_payload, "resolved_delivery_location")
        or _read_payload_string(delivery_snapshot_payload, "resolved_delivery_location"),
        "delivery_resolution_mode": (
            str(execution_contract.deliveryResolutionMode or "").strip()
            if execution_contract is not None
            else None
        )
        or (
            str(delivery_snapshot.deliveryResolutionMode or "").strip()
            if delivery_snapshot is not None
            else None
        )
        or _read_payload_string(execution_contract_payload, "delivery_resolution_mode")
        or _read_payload_string(delivery_snapshot_payload, "delivery_resolution_mode"),
        "artifact_key": (
            str(traceability.artifactKey or "").strip()
            if traceability is not None
            else None
        )
        or _read_payload_string(execution_contract_payload, "artifact_key"),
    }
    return {key: value for key, value in lineage.items() if value is not None}


def resolve_record_identifier(native_failure: Any, execution_context: GxExecutionRunEntity | None = None) -> dict[str, str | None]:
    primary_key = str(getattr(native_failure, "dataPrimaryKey", None) or "").strip()
    if primary_key:
        return {
            "record_identifier_type": "primary_key",
            "record_identifier_value": primary_key,
        }

    row_identifier = str(getattr(native_failure, "rowIdentifier", None) or "").strip()
    if row_identifier:
        return {
            "record_identifier_type": "business_key",
            "record_identifier_value": row_identifier,
        }

    return {
        "record_identifier_type": None,
        "record_identifier_value": None,
    }


def _resolve_dataset_level_record_identifier(
    *,
    record_identifier_type: str | None,
    record_identifier_value: str | None,
    data_object_version_id: str,
    targets: Sequence[str],
) -> tuple[str | None, str | None]:
    if record_identifier_type and record_identifier_value:
        return record_identifier_type, record_identifier_value
    if data_object_version_id:
        return "data_object_version", data_object_version_id
    if len(targets) == 1:
        return "data_object_version", targets[0]
    return record_identifier_type, record_identifier_value


def normalize_reason(native_failure: Any, run_result: Any | None = None) -> dict[str, str | None]:
    raw_reason_code = (
        str(getattr(native_failure, "expectationType", None) or "").strip()
        or str(getattr(native_failure, "reason", None) or "").strip()
        or str(getattr(run_result, "failureCode", None) or "").strip()
        or None
    )
    reason_text = (
        str(getattr(native_failure, "message", None) or "").strip()
        or str(getattr(native_failure, "reason", None) or "").strip()
        or str(getattr(run_result, "failureMessage", None) or "").strip()
        or str(getattr(native_failure, "expectationType", None) or "").strip()
        or str(getattr(run_result, "failureCode", None) or "").strip()
        or None
    )
    failure_class = (
        str(getattr(native_failure, "reason", None) or "").strip()
        or str(getattr(run_result, "failureCode", None) or "").strip()
        or raw_reason_code
    )
    reason_code = normalize_exception_reason_code(
        raw_reason_code,
        engine_type="gx",
        reason_text=reason_text,
        failure_class=failure_class,
    )
    return {
        "reason_code": reason_code,
        "reason_text": reason_text,
        "failure_class": failure_class or None,
    }


def extract_exception_fact_target_ids(*, run_result: Any, execution_context: GxExecutionRunEntity) -> list[str]:
    target_ids: list[str] = []
    diagnostics = build_gx_execution_diagnostic_entities(getattr(run_result, "diagnostics", None))
    result_summary = build_gx_execution_result_summary_entity(getattr(run_result, "resultSummary", None))

    def add_candidate(value: Any) -> None:
        normalized = str(value or "").strip()
        if normalized and normalized not in target_ids:
            target_ids.append(normalized)

    for diagnostic in diagnostics:
        add_candidate(diagnostic.dataObjectVersionId)

    if target_ids:
        return target_ids

    for result in build_gx_execution_result_item_entities(result_summary):
        add_candidate(result.dataObjectVersionId)

    if target_ids:
        return target_ids

    execution_contract = _extract_run_execution_contract(execution_context)
    traceability = execution_contract.traceability if execution_contract is not None else None
    add_candidate(traceability.dataObjectVersionId if traceability is not None else None)
    return target_ids


def collect_exception_facts(*, run_result: Any, execution_context: GxExecutionRunEntity) -> list[ExceptionRecordCreateEntity]:
    diagnostics = build_gx_execution_diagnostic_entities(getattr(run_result, "diagnostics", None))
    if not diagnostics:
        return []

    exception_fact_validation_service.require_exception_fact_collection_support(execution_context=execution_context)

    suite_id = str(execution_context.suiteId or "").strip()
    suite_version = execution_context.suiteVersion
    rule_id = str(execution_context.ruleId or "").strip()
    rule_version_id = str(execution_context.ruleVersionId or "").strip()
    correlation_id = str(execution_context.correlationId or "").strip()
    if not suite_id or suite_version in (None, "") or not rule_id or not rule_version_id or not correlation_id:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "violation_persistence_unavailable",
                "message": "GX execution run is missing required metadata for violation persistence",
                "run_id": execution_context.id,
            },
        )

    targets = extract_exception_fact_target_ids(run_result=run_result, execution_context=execution_context)
    if not targets:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "violation_persistence_unavailable",
                "message": "Unable to resolve a data object version id for GX violation persistence",
                "run_id": execution_context.id,
            },
        )

    base_ops_metadata = _build_violation_lineage_metadata(execution_context)
    violation_batch: list[ExceptionRecordCreateEntity] = []

    for index, diagnostic in enumerate(diagnostics):
        data_object_version_id = str(diagnostic.dataObjectVersionId or "").strip()
        record_identifier = resolve_record_identifier(diagnostic, execution_context)
        record_identifier_type = record_identifier["record_identifier_type"]
        record_identifier_value = record_identifier["record_identifier_value"]
        normalized_reason = normalize_reason(diagnostic, run_result=run_result)
        reason_code = normalized_reason["reason_code"]
        reason_text = normalized_reason["reason_text"]
        failure_class = normalized_reason["failure_class"]

        if not data_object_version_id:
            if len(targets) == 1:
                data_object_version_id = targets[0]
            else:
                raise HTTPException(
                    status_code=503,
                    detail={
                        "error": "violation_persistence_unavailable",
                        "message": "Diagnostic is missing data object version id",
                        "run_id": execution_context.id,
                        "diagnostic_index": index,
                    },
                )
        record_identifier_type, record_identifier_value = _resolve_dataset_level_record_identifier(
            record_identifier_type=record_identifier_type,
            record_identifier_value=record_identifier_value,
            data_object_version_id=data_object_version_id,
            targets=targets,
        )
        if not record_identifier_type or not record_identifier_value:
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "violation_persistence_unavailable",
                    "message": "Diagnostic is missing record identifier",
                    "run_id": execution_context.id,
                    "diagnostic_index": index,
                },
            )
        if not reason_code or not reason_text:
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "violation_persistence_unavailable",
                    "message": "Diagnostic is missing normalized failure reason",
                    "run_id": execution_context.id,
                    "diagnostic_index": index,
                },
            )

        ops_metadata = dict(base_ops_metadata)
        ops_metadata["failure_class"] = failure_class
        ops_metadata["reason_code"] = reason_code
        ops_metadata["reason_text"] = reason_text
        expectation_type = str(getattr(diagnostic, "expectationType", None) or "").strip()
        if expectation_type:
            ops_metadata["expectation_type"] = expectation_type

        violation_batch.append(
            ExceptionRecordCreateEntity(
                id=None,
                dataObjectVersionId=data_object_version_id,
                executionRunId=execution_context.id,
                ruleId=rule_id,
                recordIdentifierType=record_identifier_type,
                recordIdentifierValue=record_identifier_value,
                reasonCode=reason_code,
                reasonText=reason_text,
                failureClass=failure_class,
                opsMetadata=ops_metadata,
                detectedAt=str(
                    diagnostic.detectedAt
                    or getattr(run_result, "completedAt", None)
                    or getattr(run_result, "startedAt", None)
                    or execution_context.completedAt
                    or execution_context.startedAt
                    or execution_context.updatedAt
                    or ""
                ).strip() or None,
            )
        )

    return violation_batch


async def emit_exception_fact_batch(
    *,
    violation_batch: Sequence[ExceptionRecordCreateEntity | Mapping[str, Any]],
    settings_provider: Callable[[], Any],
    violation_repository: ExceptionFactRepository,
    exception_storage_builder: Callable[..., Any],
    projection_repository: ExceptionReasonAnalyticsProjectionRepository | None = None,
) -> int:
    if not violation_batch:
        return 0

    exception_storage_service = exception_storage_builder(
        settings=settings_provider(),
        violation_repository=violation_repository,
    )
    created = 0
    for start_index in range(0, len(violation_batch), 1000):
        batch = violation_batch[start_index : start_index + 1000]
        batch_records = [build_exception_record_create_entity(item) for item in batch]
        persisted_count = await exception_storage_service.persist_violations([
            _to_exception_record_payload(record) for record in batch_records
        ])
        exception_fact_validation_service.validate_exception_fact_persistence_result(
            expected_count=len(batch_records),
            persisted_count=persisted_count,
            run_id=str(batch_records[0].executionRunId or "") if batch_records else "",
        )
        if projection_repository is not None:
            await projection_repository.persist_exception_records(batch_records)
        created += persisted_count
    return created
