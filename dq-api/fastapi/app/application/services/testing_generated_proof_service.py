from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi import HTTPException


def resolve_failure_message(detail: Any) -> str:
    if isinstance(detail, str):
        return detail
    if isinstance(detail, Mapping):
        return str(detail.get("message") or detail.get("error") or "Queued test data generation failed")
    return "Queued test data generation failed"


def serialize_test_proof(proof: Any, resolve_test_proof_views) -> dict[str, Any]:
    return resolve_test_proof_views([proof])[0].model_dump(mode="json", by_alias=True)


def persist_generated_data_test_proof(
    repository,
    *,
    rule_id: str,
    proof_id: str | None,
    status: str,
    execution_context: Any,
    message: str,
    build_proof_payload,
    requested_by_user_id: str | None = None,
    correlation_id: str | None = None,
    request_id: str | None = None,
    version_id: str | None = None,
    sample_count: int | None = None,
    semantic_matching: dict[str, Any] | None = None,
    data_object_id: str | None = None,
    data_object_name: str | None = None,
    version_name: int | str | None = None,
) -> Any:
    proof_payload = build_proof_payload(
        status=status,
        execution_context=execution_context,
        message=message,
        requested_by_user_id=requested_by_user_id,
        correlation_id=correlation_id,
        request_id=request_id,
        version_id=version_id,
        sample_count=sample_count,
        semantic_matching=semantic_matching,
        data_object_id=data_object_id,
        data_object_name=data_object_name,
        version_name=version_name,
    )
    try:
        return (
            repository.update_test_proof(proof_id, proof_payload, status=status)
            if proof_id
            else repository.create_test_proof(rule_id, proof_payload, status=status)
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Test proof '{proof_id}' not found") from exc