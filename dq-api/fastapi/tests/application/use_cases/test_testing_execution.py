from __future__ import annotations

from types import SimpleNamespace

import pytest

from fastapi import HTTPException

from app.application.use_cases.testing_batch_requests import BatchTestRequestExecutionServices
from app.application.use_cases.testing_batch_requests import execute_batch_test_request
from app.application.use_cases.testing_batch_requests import RunBatchTestRequestCommand
from app.application.use_cases.testing_execution import execute_rule_with_data
from app.application.use_cases.testing_execution import ManualTestProofServices
from app.application.use_cases.testing_execution import RunRuleWithDataCommand
from app.application.use_cases.testing_execution import RuleWithDataExecutionServices
from app.application.use_cases.testing_execution import store_manual_test_proof
from app.application.use_cases.testing_execution import StoreManualTestProofCommand


@pytest.mark.anyio
async def test_execute_batch_test_request_adds_scheduler_handoff() -> None:
    async def _build_execution_context(rule_id: str):
        assert rule_id == "rule-1"
        return {"ruleVersionId": "rv-1", "handoffReady": True, "executionContract": {"engineTarget": "dq-engine"}}

    result = await execute_batch_test_request(
        command=RunBatchTestRequestCommand(request_id="batch-1"),
        services=BatchTestRequestExecutionServices(
            get_batch_test_request=lambda request_id: SimpleNamespace(
                id=request_id,
                ruleId="rule-1",
                executionCorrelationId="corr-1",
            ),
            build_execution_context=_build_execution_context,
            run_batch_test_request=lambda request_id: SimpleNamespace(id=request_id, status="running", model_dump=lambda: {"id": request_id, "status": "running"}),
            build_batch_test_execution_context_payload=lambda request_id, execution_context, correlation_id: (
                {
                    "ruleVersionId": execution_context["ruleVersionId"],
                    "correlationId": correlation_id,
                    "schedulerHandoff": {
                        "batchRequestId": request_id,
                        "executorTarget": "dq-engine",
                        "handoffStatus": "accepted",
                        "handoffReady": True,
                    },
                },
                {"executorTarget": "dq-engine"},
            ),
        ),
    )

    assert result.rule_id == "rule-1"
    assert result.response_payload["executionContext"]["schedulerHandoff"]["batchRequestId"] == "batch-1"


@pytest.mark.anyio
async def test_execute_rule_with_data_merges_execution_context() -> None:
    async def _build_execution_context(rule_id: str):
        assert rule_id == "rule-1"
        return {"compiledExpression": "email contains '@'", "ruleVersionId": "rv-1"}

    result = await execute_rule_with_data(
        command=RunRuleWithDataCommand(
            rule_id="rule-1",
            test_data=[{"email": "user@example.com"}],
            version_id_source="v1",
        ),
        services=RuleWithDataExecutionServices(
            build_execution_context=_build_execution_context,
            serialize_execution_context=lambda context: dict(context),
            run_rule_against_test_data=lambda rule_id, test_data, version_id_source, compiled_expression=None, semantic_config=None: SimpleNamespace(
                totalTests=len(test_data),
                model_dump=lambda: {
                    "ruleId": rule_id,
                    "testDataSource": version_id_source,
                    "totalTests": len(test_data),
                    "passedCount": 1,
                    "failedCount": 0,
                    "expression": compiled_expression,
                },
            ),
            merge_execution_context=lambda response_payload, execution_context, compiled_expression: {
                "ruleVersionId": execution_context["ruleVersionId"],
                "executedExpressionSource": "compiled-artifact",
                "compiledExpression": compiled_expression,
                "totalTests": response_payload["totalTests"],
            },
        ),
    )

    assert result.response_payload["executionContext"]["ruleVersionId"] == "rv-1"
    assert result.response_payload["executionContext"]["executedExpressionSource"] == "compiled-artifact"


@pytest.mark.anyio
async def test_store_manual_test_proof_allows_missing_compiler_artifact_for_manual_submission() -> None:
    captured: dict[str, object] = {}

    async def _resolve_current_rule_status(rule_id: str):
        assert rule_id == "rule-1"
        return "validated"

    async def _build_execution_context(_rule_id: str):
        raise HTTPException(
            status_code=409,
            detail={
                "error": "active_compiler_artifact_required",
                "message": "Validate the rule first.",
            },
        )

    def _build_execution_trace(**kwargs):
        captured["trace"] = kwargs
        return {"resultStatus": kwargs["status"]}

    def _build_manual_payload(payload, *, execution_context, requested_by_user_id, execution_trace):
        captured["payload"] = {
            "execution_context": execution_context,
            "requested_by_user_id": requested_by_user_id,
            "execution_trace": execution_trace,
            "payload": payload,
        }
        return {"proofData": {"executionTrace": execution_trace}, **payload}

    def _store_test_proof(rule_id: str, payload: dict[str, object]):
        captured["stored"] = (rule_id, payload)
        return {"proofId": "proof-1", "ruleId": rule_id, "proofData": payload.get("proofData", {})}

    async def _record_rule_tested_transition(rule_id: str, current_status: str, actor_id: str | None):
        captured["transition"] = (rule_id, current_status, actor_id)

    stored = await store_manual_test_proof(
        command=StoreManualTestProofCommand(
            rule_id="rule-1",
            payload={"coverage": 0.9, "recordsTestedCount": 10, "failuresFound": 0, "proofData": {}},
            passed=True,
            requested_by_user_id="user-1",
        ),
        services=ManualTestProofServices(
            resolve_current_rule_status=_resolve_current_rule_status,
            build_execution_context=_build_execution_context,
            build_execution_trace=_build_execution_trace,
            build_manual_test_proof_storage_payload=_build_manual_payload,
            store_test_proof=_store_test_proof,
            record_rule_tested_transition=_record_rule_tested_transition,
        ),
    )

    assert captured["trace"]["status"] == "passed"
    assert captured["payload"]["execution_context"] is None
    assert captured["transition"] == ("rule-1", "validated", "user-1")
    assert stored["proofId"] == "proof-1"