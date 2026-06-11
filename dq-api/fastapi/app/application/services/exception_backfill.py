from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any
from typing import Mapping

from app.domain.entities import GxExecutionViolationCreateEntity


_SUPPORTED_RECORD_IDENTIFIER_TYPES = frozenset({"business_key", "primary_key"})


@dataclass(frozen=True)
class ExceptionBackfillDecision:
    status: str
    reason: str
    violation_id: str | None = None
    canonical_violation: dict[str, Any] | None = None
    updated_ops_metadata: dict[str, Any] | None = None


def _read_text(value: Any) -> str:
    return str(value or "").strip()


def _read_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _read_positive_int(value: Any) -> int | None:
    normalized = _read_text(value)
    if not normalized:
        return None
    try:
        parsed = int(normalized)
    except (TypeError, ValueError):
        return None
    if parsed < 1:
        return None
    return parsed


def _build_identifier_hash(record_identifier_type: str, record_identifier_value: str) -> str:
    digest = hashlib.sha256(
        f"{record_identifier_type}:{record_identifier_value}".encode("utf-8")
    ).hexdigest()
    return f"sha256:{digest}"


def normalize_legacy_reason_code(reason_text: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", _read_text(reason_text).lower()).strip("_")
    return normalized or "gx_violation"


def _build_violation_id(canonical_violation: Mapping[str, Any]) -> str:
    canonical_payload = {
        "dataObjectVersionId": canonical_violation["data_object_version_id"],
        "executionRunId": canonical_violation["execution_run_id"],
        "recordIdentifierType": canonical_violation["record_identifier_type"],
        "recordIdentifierValue": canonical_violation["record_identifier_value"],
        "ruleId": canonical_violation["rule_id"],
        "reasonCode": canonical_violation["reason_code"],
        "reasonText": canonical_violation["reason_text"],
        "detectedAt": canonical_violation["detected_at"],
    }
    canonical_json = json.dumps(canonical_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return f"gx-violation-{hashlib.sha256(canonical_json.encode('utf-8')).hexdigest()[:32]}"


def _build_canonical_ops_metadata(
    *,
    base_ops_metadata: Mapping[str, Any],
    data_primary_key: str,
    violation_reason: str,
) -> tuple[dict[str, Any] | None, str | None]:
    ops_metadata = dict(base_ops_metadata)
    record_identifier_type = _read_text(ops_metadata.get("record_identifier_type")) or "primary_key"
    if record_identifier_type not in _SUPPORTED_RECORD_IDENTIFIER_TYPES:
        return None, "unsupported_record_identifier_type"
    record_identifier_value = _read_text(ops_metadata.get("record_identifier_value")) or data_primary_key
    reason_text = _read_text(ops_metadata.get("reason_text")) or violation_reason
    reason_code = _read_text(ops_metadata.get("reason_code")) or normalize_legacy_reason_code(reason_text)
    validation_artifact_id = _read_text(ops_metadata.get("validation_artifact_id")) or _read_text(
        ops_metadata.get("suite_id")
    )
    validation_artifact_version = _read_positive_int(ops_metadata.get("validation_artifact_version"))
    if validation_artifact_version is None:
        validation_artifact_version = _read_positive_int(ops_metadata.get("suite_version"))
    rule_version_id = _read_text(ops_metadata.get("rule_version_id"))
    engine_type = _read_text(ops_metadata.get("engine_type")) or "gx"

    missing_fields: list[str] = []
    if not record_identifier_value:
        missing_fields.append("record_identifier_value")
    if not reason_text:
        missing_fields.append("reason_text")
    if not reason_code:
        missing_fields.append("reason_code")
    if not validation_artifact_id:
        missing_fields.append("validation_artifact_id")
    if validation_artifact_version is None:
        missing_fields.append("validation_artifact_version")
    if not rule_version_id:
        missing_fields.append("rule_version_id")
    if not engine_type:
        missing_fields.append("engine_type")
    if missing_fields:
        return None, ",".join(missing_fields)

    ops_metadata["engine_type"] = engine_type
    ops_metadata["record_identifier_type"] = record_identifier_type
    ops_metadata["record_identifier_value"] = record_identifier_value
    ops_metadata["reason_code"] = reason_code
    ops_metadata["reason_text"] = reason_text
    ops_metadata["validation_artifact_id"] = validation_artifact_id
    ops_metadata["validation_artifact_version"] = validation_artifact_version
    ops_metadata["rule_version_id"] = rule_version_id
    if not _read_text(ops_metadata.get("failure_class")):
        ops_metadata["failure_class"] = reason_code
    if not _read_text(ops_metadata.get("identifier_hash")):
        ops_metadata["identifier_hash"] = _build_identifier_hash(record_identifier_type, record_identifier_value)
    return ops_metadata, None


def build_repository_exception_backfill_decision(row: Mapping[str, Any]) -> ExceptionBackfillDecision:
    ops_metadata = _read_mapping(row.get("opsMetadata") or row.get("ops_metadata"))
    data_primary_key = _read_text(row.get("dataPrimaryKey") or row.get("data_primary_key"))
    violation_reason = _read_text(row.get("violationReason") or row.get("violation_reason"))
    canonical_ops_metadata, missing_reason = _build_canonical_ops_metadata(
        base_ops_metadata=ops_metadata,
        data_primary_key=data_primary_key,
        violation_reason=violation_reason,
    )
    if canonical_ops_metadata is None:
        return ExceptionBackfillDecision(status="skipped", reason=missing_reason or "not_backfillable")

    data_object_version_id = _read_text(row.get("dataObjectVersionId") or row.get("data_object_version_id"))
    execution_run_id = _read_text(row.get("executionRunId") or row.get("execution_run_id"))
    rule_id = _read_text(row.get("ruleId") or row.get("rule_id"))
    detected_at = row.get("detectedAt") or row.get("detected_at")
    detected_at_text = _read_text(detected_at)
    if not data_object_version_id or not execution_run_id or not rule_id or not detected_at_text:
        missing_fields: list[str] = []
        if not data_object_version_id:
            missing_fields.append("data_object_version_id")
        if not execution_run_id:
            missing_fields.append("execution_run_id")
        if not rule_id:
            missing_fields.append("rule_id")
        if not detected_at_text:
            missing_fields.append("detected_at")
        return ExceptionBackfillDecision(status="skipped", reason=",".join(missing_fields))

    canonical_violation = {
        "violation_id": _read_text(row.get("id")) or None,
        "data_object_version_id": data_object_version_id,
        "execution_run_id": execution_run_id,
        "record_identifier_type": canonical_ops_metadata["record_identifier_type"],
        "record_identifier_value": canonical_ops_metadata["record_identifier_value"],
        "rule_id": rule_id,
        "reason_code": canonical_ops_metadata["reason_code"],
        "reason_text": canonical_ops_metadata["reason_text"],
        "detected_at": detected_at_text,
        "ops_metadata": canonical_ops_metadata,
    }
    if canonical_violation["violation_id"] is None:
        canonical_violation["violation_id"] = _build_violation_id(canonical_violation)

    changed_keys = (
        "engine_type",
        "validation_artifact_id",
        "validation_artifact_version",
        "rule_version_id",
        "record_identifier_type",
        "record_identifier_value",
        "reason_code",
        "reason_text",
    )
    changed = any(canonical_ops_metadata.get(key) != ops_metadata.get(key) for key in changed_keys)
    return ExceptionBackfillDecision(
        status="backfilled" if changed else "noop",
        reason="canonicalized" if changed else "already_canonical",
        violation_id=canonical_violation["violation_id"],
        canonical_violation=canonical_violation,
        updated_ops_metadata=canonical_ops_metadata,
    )


def _object_storage_ops_to_metadata(ops_payload: Mapping[str, Any]) -> dict[str, Any]:
    mappings = {
        "suiteId": "suite_id",
        "suiteVersion": "suite_version",
        "validationArtifactId": "validation_artifact_id",
        "validationArtifactVersion": "validation_artifact_version",
        "ruleVersionId": "rule_version_id",
        "correlationId": "correlation_id",
        "engineType": "engine_type",
        "engineTarget": "engine_target",
        "executionShape": "execution_shape",
        "executionPlanId": "execution_plan_id",
        "executionPlanVersionId": "execution_plan_version_id",
        "deliveryId": "delivery_id",
        "deliveryLocation": "delivery_location",
        "deliveryResolutionMode": "delivery_resolution_mode",
        "artifactKey": "artifact_key",
        "failureClass": "failure_class",
        "datasetId": "dataset_id",
        "dataProductId": "data_product_id",
    }
    ops_metadata: dict[str, Any] = {}
    for source_key, target_key in mappings.items():
        if ops_payload.get(source_key) is not None:
            ops_metadata[target_key] = ops_payload[source_key]
    return ops_metadata


def build_object_storage_exception_backfill_decision(item: Mapping[str, Any]) -> ExceptionBackfillDecision:
    violation_fact = _read_mapping(item.get("violationFact") or item.get("violation_fact"))
    ops_payload = _read_mapping(item.get("ops"))
    ops_metadata = _object_storage_ops_to_metadata(ops_payload)

    if _read_text(violation_fact.get("recordIdentifierType")):
        ops_metadata["record_identifier_type"] = _read_text(violation_fact.get("recordIdentifierType"))
    elif _read_text(item.get("recordIdentifierType") or item.get("record_identifier_type")):
        ops_metadata["record_identifier_type"] = _read_text(
            item.get("recordIdentifierType") or item.get("record_identifier_type")
        )

    explicit_identifier_value = _read_text(violation_fact.get("recordIdentifierValue")) or _read_text(
        item.get("recordIdentifierValue") or item.get("record_identifier_value")
    )
    if explicit_identifier_value:
        ops_metadata["record_identifier_value"] = explicit_identifier_value

    explicit_reason_code = _read_text(violation_fact.get("reasonCode")) or _read_text(
        item.get("reasonCode") or item.get("reason_code")
    )
    explicit_reason_text = _read_text(violation_fact.get("reasonText")) or _read_text(
        item.get("reasonText") or item.get("reason_text")
    )
    if explicit_reason_code:
        ops_metadata["reason_code"] = explicit_reason_code
    if explicit_reason_text:
        ops_metadata["reason_text"] = explicit_reason_text

    row_identifier = _read_text(item.get("rowIdentifier") or item.get("row_identifier"))
    data_primary_key = explicit_identifier_value or _read_text(item.get("dataPrimaryKey") or item.get("data_primary_key"))
    if row_identifier and not data_primary_key:
        data_primary_key = row_identifier
        ops_metadata["record_identifier_type"] = "business_key"
        ops_metadata["record_identifier_value"] = row_identifier

    pseudo_row = {
        "id": _read_text(item.get("violationId") or item.get("violation_id") or item.get("id")),
        "dataObjectVersionId": _read_text(
            ops_payload.get("dataObjectVersionId")
            or item.get("dataObjectVersionId")
            or item.get("data_object_version_id")
        ),
        "executionRunId": _read_text(
            ops_payload.get("executionRunId")
            or item.get("executionRunId")
            or item.get("execution_run_id")
        ),
        "ruleId": _read_text(
            violation_fact.get("ruleId")
            or item.get("ruleId")
            or item.get("rule_id")
        ),
        "dataPrimaryKey": data_primary_key,
        "violationReason": explicit_reason_text or _read_text(
            item.get("violationReason") or item.get("violation_reason")
        ),
        "detectedAt": _read_text(ops_payload.get("detectedAt") or item.get("detectedAt") or item.get("detected_at")),
        "opsMetadata": ops_metadata,
    }
    return build_repository_exception_backfill_decision(pseudo_row)


def build_object_storage_exception_backfill_plan(
    payload: Mapping[str, Any],
) -> tuple[list[ExceptionBackfillDecision], bool]:
    violations = payload.get("violations")
    if not isinstance(violations, list):
        raise ValueError("Legacy GX exception payload is missing violations[]")
    decisions = [
        build_object_storage_exception_backfill_decision(item)
        for item in violations
        if isinstance(item, Mapping)
    ]
    schema_version = _read_text(payload.get("schemaVersion") or payload.get("schema_version"))
    requires_replay = schema_version != "v4" or any(decision.status == "backfilled" for decision in decisions)
    return decisions, requires_replay


def build_violation_create_entity(canonical_violation: Mapping[str, Any]) -> GxExecutionViolationCreateEntity:
    return GxExecutionViolationCreateEntity(
        id=_read_text(canonical_violation.get("violation_id")),
        dataObjectVersionId=_read_text(canonical_violation.get("data_object_version_id")),
        executionRunId=_read_text(canonical_violation.get("execution_run_id")),
        ruleId=_read_text(canonical_violation.get("rule_id")),
        dataPrimaryKey=_read_text(canonical_violation.get("record_identifier_value")),
        violationReason=_read_text(canonical_violation.get("reason_text")),
        opsMetadata=_read_mapping(canonical_violation.get("ops_metadata")),
        detectedAt=_read_text(canonical_violation.get("detected_at")) or None,
    )