from __future__ import annotations

from typing import Any

from pydantic import Field

from app.domain.entities.base import EntityModel


class ExceptionRecordCreateEntity(EntityModel):
    id: str | None = None
    dataObjectVersionId: str
    executionRunId: str
    ruleId: str
    recordIdentifierType: str
    recordIdentifierValue: str
    reasonCode: str
    reasonText: str
    failureClass: str | None = None
    detectedAt: str | None = None
    opsMetadata: dict[str, Any] = Field(default_factory=dict)


def build_exception_record_create_entity(payload: Any) -> ExceptionRecordCreateEntity:
    if isinstance(payload, ExceptionRecordCreateEntity):
        return payload
    if not isinstance(payload, dict):
        return ExceptionRecordCreateEntity.model_validate(payload)

    normalized_payload = {
        "id": payload.get("id") or payload.get("violation_id"),
        "dataObjectVersionId": payload.get("dataObjectVersionId") or payload.get("data_object_version_id"),
        "executionRunId": payload.get("executionRunId") or payload.get("execution_run_id"),
        "ruleId": payload.get("ruleId") or payload.get("rule_id"),
        "recordIdentifierType": payload.get("recordIdentifierType") or payload.get("record_identifier_type"),
        "recordIdentifierValue": payload.get("recordIdentifierValue") or payload.get("record_identifier_value"),
        "reasonCode": payload.get("reasonCode") or payload.get("reason_code"),
        "reasonText": payload.get("reasonText") or payload.get("reason_text"),
        "failureClass": payload.get("failureClass") or payload.get("failure_class"),
        "detectedAt": payload.get("detectedAt") or payload.get("detected_at"),
        "opsMetadata": dict(payload.get("opsMetadata") or payload.get("ops_metadata") or {}),
    }
    return ExceptionRecordCreateEntity.model_validate(normalized_payload)

