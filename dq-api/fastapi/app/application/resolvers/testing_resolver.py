from collections.abc import Sequence
from typing import Any

from app.api.v1.schemas.testing_view import (
    BatchTestRequestView,
    BatchTestRequestsPageView,
    BatchTestRunResultView,
    StoreTestProofResultView,
    TestDataPayloadView,
    TestProofView,
    TestRunResultView,
)
from app.domain.entities import (
    BatchTestRequestEntity,
    BatchTestRunResultEntity,
    StoreTestProofResultEntity,
    TestDataPayloadEntity,
    TestProofEntity,
    TestRunResultEntity,
)


def _resolve_execution_context(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    execution_context = payload.get("executionContext")
    if isinstance(execution_context, dict):
        return execution_context
    execution_context = payload.get("execution_context")
    if isinstance(execution_context, dict):
        return execution_context
    return None


def _with_derived_execution_context(payload: dict[str, Any]) -> dict[str, Any]:
    next_payload = dict(payload)
    execution_context = _resolve_execution_context(next_payload)
    if execution_context is None:
        proof_data = next_payload.get("proofData")
        if isinstance(proof_data, dict):
            execution_context = _resolve_execution_context(proof_data)
    if execution_context is not None:
        next_payload["executionContext"] = execution_context
    return next_payload


def _entity_to_payload(entity: Any) -> dict[str, Any]:
    if hasattr(entity, "model_dump"):
        return entity.model_dump()
    if isinstance(entity, dict):
        return dict(entity)
    return dict(entity or {})


def resolve_batch_test_requests_page_view(payload: dict[str, Any]) -> BatchTestRequestsPageView:
    return BatchTestRequestsPageView.model_validate(payload)


def resolve_batch_test_request_view(entity: BatchTestRequestEntity | None) -> BatchTestRequestView | None:
    return BatchTestRequestView.model_validate(entity) if entity is not None else None


def resolve_batch_test_request_list_view(rows: Sequence[BatchTestRequestEntity]) -> list[BatchTestRequestView]:
    return [BatchTestRequestView.model_validate(row) for row in rows]


def resolve_batch_test_run_result_view(entity: BatchTestRunResultEntity) -> BatchTestRunResultView:
    return BatchTestRunResultView.model_validate(_with_derived_execution_context(_entity_to_payload(entity)))


def resolve_test_data_payload_view(entity: TestDataPayloadEntity) -> TestDataPayloadView:
    return TestDataPayloadView.model_validate(entity)


def resolve_test_run_result_view(entity: TestRunResultEntity) -> TestRunResultView:
    return TestRunResultView.model_validate(_with_derived_execution_context(_entity_to_payload(entity)))


def resolve_store_test_proof_result_view(entity: StoreTestProofResultEntity) -> StoreTestProofResultView:
    return StoreTestProofResultView.model_validate(_with_derived_execution_context(_entity_to_payload(entity)))


def resolve_test_proofs_view(rows: Sequence[TestProofEntity]) -> list[TestProofView]:
    return [TestProofView.model_validate(_with_derived_execution_context(_entity_to_payload(row))) for row in rows]
