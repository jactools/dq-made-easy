from __future__ import annotations

from types import SimpleNamespace

from app.api.presenters.testing import (
    build_batch_test_execution_context_payload,
    build_generated_data_test_proof_payload,
    build_generated_data_test_proof_update_payload,
    build_manual_test_proof_storage_payload,
    build_test_execution_trace_entity,
    build_test_failure_analysis,
    build_test_markdown_report,
    build_testing_scheduler_handoff_entity,
    extract_test_selected_attributes,
    merge_test_run_execution_context,
    render_test_proof_version_diff_section,
)


def test_build_test_proof_execution_trace_and_generated_payload() -> None:
    execution_context = {
        "ruleVersionId": "rv-1",
        "ruleVersionNumber": 3,
        "artifactKey": "artifact-1",
        "compilerVersion": "dq-7.3.0",
        "compilerRevision": 1,
        "schemaVersion": "1",
    }

    trace = build_test_execution_trace_entity(
        status="passed",
        execution_context=execution_context,
        correlation_id="corr-1",
    ).model_dump(mode="python")
    assert trace["resultStatus"] == "passed"
    assert trace["ruleVersionId"] == "rv-1"
    assert trace["correlationId"] == "corr-1"

    proof = build_generated_data_test_proof_payload(
        status="failed",
        execution_context=execution_context,
        message="boom",
        requested_by_user_id="tester",
        correlation_id="corr-2",
        request_id="req-1",
        version_id="ver-1",
        sample_count=5,
        semantic_matching={"enabled": True},
        data_object_id="do-1",
        data_object_name="Data Object",
        version_name=7,
    )
    assert proof["status"] == "failed"
    assert proof["proofData"]["error"] == "boom"
    assert proof["proofData"]["executionContext"]["ruleVersionId"] == "rv-1"


def test_build_batch_execution_context_and_generated_updates() -> None:
    context_payload, scheduler_handoff = build_batch_test_execution_context_payload(
        request_id="req-1",
        execution_context={"executionContract": {"engineTarget": "dq-engine"}, "handoffReady": True},
        correlation_id="corr-1",
    )
    assert context_payload["correlationId"] == "corr-1"
    assert context_payload["schedulerHandoff"]["batchRequestId"] == "req-1"
    assert scheduler_handoff["executorTarget"] == "dq-engine"

    handoff = build_testing_scheduler_handoff_entity(
        request_id="req-1",
        execution_context={"executionContract": {"engineTarget": "dq-engine"}, "handoffReady": True},
        correlation_id="corr-1",
        handoff_id="handoff-1",
        submitted_at="2026-04-20T10:00:00Z",
    )
    assert handoff.batchRequestId == "req-1"
    assert handoff.executorTarget == "dq-engine"
    assert handoff.handoffReady is True

    trace = build_test_execution_trace_entity(
        status="failed",
        execution_context={"ruleVersionId": "rv-1", "artifactKey": "artifact-1"},
        correlation_id="corr-2",
        execution_id="exec-1",
        executed_at="2026-04-20T10:01:00Z",
    )
    assert trace.executionId == "exec-1"
    assert trace.ruleVersionId == "rv-1"
    assert trace.artifactKey == "artifact-1"

    merged = merge_test_run_execution_context(
        {"expression": "email like '%@%'", "executionContext": {"existing": True}},
        {"ruleVersionId": "rv-1", "compiledExpression": "compiled", "handoffReady": True},
        compiled_expression="compiled",
    )
    assert merged["existing"] is True
    assert merged["ruleVersionId"] == "rv-1"
    assert merged["executedExpression"] == "email like '%@%'"
    assert merged["executedExpressionSource"] == "compiled-artifact"

    generated_proof = build_generated_data_test_proof_payload(
        status="failed",
        execution_context={"ruleVersionId": "rv-1"},
        message="boom",
        requested_by_user_id="tester",
        correlation_id="corr-3",
        request_id="req-3",
        version_id="ver-1",
        sample_count=5,
    )
    assert generated_proof["proofData"]["executionContext"]["ruleVersionId"] == "rv-1"
    assert generated_proof["proofData"]["executionTrace"]["correlationId"] == "corr-3"

    manual_payload = build_manual_test_proof_storage_payload(
        {"proofData": {"existing": True}, "coverage": 1.0},
        execution_context={"ruleVersionId": "rv-9"},
        requested_by_user_id="tester",
        execution_trace={"executionId": "exec-9", "resultStatus": "passed"},
    )
    assert manual_payload["proofData"]["existing"] is True
    assert manual_payload["proofData"]["requested_by_user_id"] == "tester"
    assert manual_payload["executionContext"]["ruleVersionId"] == "rv-9"
    assert manual_payload["executionTrace"]["executionId"] == "exec-9"

    generated_update = build_generated_data_test_proof_update_payload(
        {"successRate": 0.75, "totalTests": 4, "failedCount": 1, "executionContext": {"ruleVersionId": "rv-1"}},
        final_status="failed",
        correlation_id="corr-4",
        request_id="req-4",
        version_id="ver-2",
        sample_count=4,
        semantic_matching={"enabled": True},
        requested_by_user_id="tester",
        data_object_id="do-1",
        data_object_name="Contact",
        version_name=3,
    )
    assert generated_update["coverage"] == 0.75
    assert generated_update["proofData"]["requestStatus"] == "failed"
    assert generated_update["proofData"]["dataObjectName"] == "Contact"
    assert generated_update["executionTrace"]["correlationId"] == "corr-4"


def test_testing_report_presenters() -> None:
    attrs = extract_test_selected_attributes(
        {
            "selectedAttributes": [
                {"name": "email"},
                {"id": "status"},
                "country",
            ]
        }
    )
    assert attrs == ["email", "status", "country"]

    reasons = build_test_failure_analysis(
        {
            "failureReasons": ["invalid email"],
            "diagnostics": [{"message": "invalid email"}, {"message": "status mismatch"}],
        },
        failures_found=2,
    )
    assert reasons == ["invalid email", "status mismatch"]

    latest = SimpleNamespace(
        id="proof-2",
        status="failed",
        testDate="2026-03-27T10:00:00Z",
        recordsTestedCount=10,
        failuresFound=2,
        coverage=0.8,
        proofData={
            "selectedAttributes": [{"name": "email"}],
            "passed_count": 8,
            "results": [{"passed": False, "data": {"email": None}}],
        },
        executionTrace=SimpleNamespace(
            ruleVersionNumber=2,
            ruleVersionId="rv-2",
            artifactKey="k2",
            compilerVersion="dq-7.3.0",
            model_dump=lambda: {
                "ruleVersionNumber": 2,
                "ruleVersionId": "rv-2",
                "artifactKey": "k2",
                "compilerVersion": "dq-7.3.0",
            },
        ),
    )
    previous = SimpleNamespace(
        id="proof-1",
        executionTrace=SimpleNamespace(
            ruleVersionNumber=1,
            model_dump=lambda: {"ruleVersionNumber": 1},
        ),
    )

    diff_text = render_test_proof_version_diff_section(
        {"changes": {"details": [{"field": "expression", "oldValue": "a", "newValue": "b"}]}},
        latest,
        previous,
    )
    assert "Version changed from V1 to V2" in diff_text

    report = build_test_markdown_report(
        rule_id="rule-1",
        proof=latest,
        rule_name="Email Rule",
        dimension="validity",
        compiled_expression="email contains '@'",
        version_diff_section=diff_text,
    )
    assert "# Rule Test Report" in report
    assert "Executed Rule Expression" in report
