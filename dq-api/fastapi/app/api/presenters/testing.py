from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import ConfigDict

from app.domain.entities.base import EntityModel
from app.domain.entities.rule import RuleExecutionContextEntity
from app.domain.entities.testing import ExecutionTraceEntity


class TestingSchedulerHandoffEntity(EntityModel):
    model_config = ConfigDict(populate_by_name=True)

    handoffId: str
    correlationId: str
    batchRequestId: str
    submittedAt: str
    executorTarget: str = "dq-engine"
    handoffStatus: str = "accepted"
    handoffReady: bool = False


def _model_dump_payload(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump()
        if isinstance(dumped, Mapping):
            return dict(dumped)
    return {}


def _field(payload: Any, *names: str) -> Any:
    if isinstance(payload, Mapping):
        for name in names:
            if payload.get(name) is not None:
                return payload.get(name)
        return None
    for name in names:
        value = getattr(payload, name, None)
        if value is not None:
            return value
    return None


def serialize_rule_execution_context_payload(
    execution_context: RuleExecutionContextEntity | Mapping[str, Any] | None,
) -> dict[str, Any]:
    if isinstance(execution_context, RuleExecutionContextEntity):
        return execution_context.model_dump(by_alias=True, exclude_none=True)
    return _model_dump_payload(execution_context)


def serialize_test_execution_trace_payload(
    execution_trace: ExecutionTraceEntity | Mapping[str, Any] | None,
) -> dict[str, Any]:
    if isinstance(execution_trace, ExecutionTraceEntity):
        return execution_trace.model_dump(mode="python")
    return _model_dump_payload(execution_trace)


def extract_test_selected_attributes(proof_data: Mapping[str, Any] | None) -> list[str]:
    if not isinstance(proof_data, Mapping):
        return []
    selected = proof_data.get("selectedAttributes")
    if not isinstance(selected, list):
        return []
    out: list[str] = []
    for attribute in selected:
        if isinstance(attribute, Mapping):
            value = str(attribute.get("name") or attribute.get("id") or "").strip()
        else:
            value = str(attribute or "").strip()
        if value:
            out.append(value)
    return out


def build_test_failure_analysis(proof_data: Mapping[str, Any] | None, failures_found: int) -> list[str]:
    if failures_found <= 0 or not isinstance(proof_data, Mapping):
        return []

    explicit_reasons = [
        str(reason or "").strip()
        for reason in (proof_data.get("failureReasons") or [])
        if str(reason or "").strip()
    ]
    diagnostic_reasons = [
        str(item.get("message") or "").strip()
        for item in (proof_data.get("diagnostics") or [])
        if isinstance(item, Mapping) and str(item.get("message") or "").strip()
    ]

    reasons: list[str] = []
    for reason in [*explicit_reasons, *diagnostic_reasons]:
        if reason not in reasons:
            reasons.append(reason)
        if len(reasons) >= 3:
            return reasons

    failed_rows = [
        row for row in (proof_data.get("results") or [])
        if isinstance(row, Mapping) and row.get("passed") is False
    ]
    if failed_rows:
        null_or_empty_by_field: dict[str, int] = {}
        for row in failed_rows:
            payload = row.get("data") if isinstance(row.get("data"), Mapping) else {}
            for key, value in payload.items():
                if value is None or (isinstance(value, str) and not value.strip()):
                    normalized_key = str(key)
                    null_or_empty_by_field[normalized_key] = null_or_empty_by_field.get(normalized_key, 0) + 1

        hotspot_fields = sorted(null_or_empty_by_field.items(), key=lambda entry: entry[1], reverse=True)[:2]
        if hotspot_fields:
            quoted = ", ".join([f'"{field}"' for field, _ in hotspot_fields])
            reasons.append(
                f"Likely cause: these field(s) were blank or missing in many failing rows: {quoted}."
            )

        sample_payload = failed_rows[0].get("data") if isinstance(failed_rows[0].get("data"), Mapping) else {}
        sample_pairs = [f'"{key}": {value}' for key, value in list(sample_payload.items())[:2]]
        if sample_pairs:
            reasons.append(f"Example failing row fields: {', '.join(sample_pairs)}.")

    if not reasons:
        reasons.append("Some records failed, but no specific reason was captured in diagnostics.")
    return reasons


def render_test_proof_version_diff_section(
    diff_payload: Mapping[str, Any] | None,
    latest_proof: Any,
    previous_proof: Any | None,
) -> str:
    latest_trace = serialize_test_execution_trace_payload(_field(latest_proof, "executionTrace", "execution_trace"))
    previous_trace = (
        serialize_test_execution_trace_payload(_field(previous_proof, "executionTrace", "execution_trace"))
        if previous_proof is not None
        else {}
    )

    latest_v = latest_trace.get("ruleVersionNumber")
    previous_v = previous_trace.get("ruleVersionNumber")

    if previous_proof is None:
        return "Only one proof is available, so no version comparison can be computed yet."

    if latest_v == previous_v:
        return f"No rule version change detected between the latest two proofs (both are V{latest_v})."

    if not diff_payload:
        return (
            f"Version changed from V{previous_v or 'N/A'} to V{latest_v or 'N/A'}, "
            "but detailed field-level comparison is not available."
        )

    changes = diff_payload.get("changes") if isinstance(diff_payload, Mapping) else None
    details = changes.get("details") if isinstance(changes, Mapping) else None
    if not isinstance(details, list) or not details:
        return (
            f"Version changed from V{previous_v or 'N/A'} to V{latest_v or 'N/A'}, "
            "with no detected field-level differences."
        )

    lines = [
        f"Version changed from V{previous_v or 'N/A'} to V{latest_v or 'N/A'}.",
        "Detected differences:",
    ]
    for item in details:
        if not isinstance(item, Mapping):
            continue
        field_name = str(item.get("field") or "unknown")
        old_value = item.get("oldValue")
        new_value = item.get("newValue")
        lines.append(f"- {field_name}: `{old_value}` -> `{new_value}`")
    return "\n".join(lines)


def build_test_markdown_report(
    *,
    rule_id: str,
    proof: Any,
    rule_name: str,
    dimension: str,
    compiled_expression: str,
    version_diff_section: str,
) -> str:
    proof_data = _model_dump_payload(_field(proof, "proofData", "proof_data"))
    execution_trace = serialize_test_execution_trace_payload(_field(proof, "executionTrace", "execution_trace"))
    execution_context = proof_data.get("executionContext") if isinstance(proof_data.get("executionContext"), Mapping) else {}

    records_tested = int(_field(proof, "recordsTestedCount", "records_tested_count") or 0)
    failures_found = int(_field(proof, "failuresFound", "failures_found") or 0)
    passed_count = int(proof_data.get("passedCount") or proof_data.get("passed_count") or max(0, records_tested - failures_found))
    success_rate = (passed_count / records_tested * 100) if records_tested > 0 else 0
    coverage_raw = float(_field(proof, "coverage") or 0)
    coverage_pct = coverage_raw * 100 if 0 <= coverage_raw <= 1 else coverage_raw
    selected_attributes = extract_test_selected_attributes(proof_data)
    failure_analysis = build_test_failure_analysis(proof_data, failures_found)

    version_number = execution_trace.get("ruleVersionNumber") or execution_context.get("ruleVersionNumber")
    artifact_key = str(execution_trace.get("artifactKey") or execution_context.get("artifactKey") or "").strip()
    compiler_version = str(execution_trace.get("compilerVersion") or execution_context.get("compilerVersion") or "").strip()
    tested_at = str(_field(proof, "testDate", "test_date") or "")
    proof_id = str(_field(proof, "id") or "")
    proof_status = str(_field(proof, "status") or "")

    went_good = [
        f"{passed_count:,} record(s) passed out of {records_tested:,}.",
        f"Success rate: {success_rate:.2f}%.",
        f"Coverage: {coverage_pct:.2f}%.",
    ]
    if selected_attributes:
        went_good.append(f"Test scope included attribute(s): {', '.join(selected_attributes)}.")
    if version_number:
        went_good.append(f"Executed against rule version V{version_number}.")

    went_wrong: list[str] = []
    if failures_found > 0:
        went_wrong.append(f"{failures_found:,} record(s) failed the rule check.")
        went_wrong.extend(failure_analysis)
    else:
        went_wrong.append("No failing records were found in this test run.")

    lines = [
        f"# Rule Test Report — {rule_name or rule_id}",
        "",
        "## Business Summary",
        f"- Rule ID: `{rule_id}`",
        f"- Rule name: {rule_name or 'N/A'}",
        f"- Quality dimension: {dimension or 'N/A'}",
        f"- Business evidence ID: `{proof_id}`",
        f"- Tested at: {tested_at or 'N/A'}",
        f"- Rule version: {('V' + str(version_number)) if version_number else 'N/A'}",
        f"- Artifact key: {artifact_key or 'N/A'}",
        f"- Compiler version: {compiler_version or 'N/A'}",
        "",
        "## What Went Good",
    ]
    lines.extend([f"- {line}" for line in went_good])
    lines.append("")
    lines.append("## What Went Wrong")
    lines.extend([f"- {line}" for line in went_wrong])
    lines.append("")

    if selected_attributes:
        lines.append("## Tested Attributes")
        lines.extend([f"- {name}" for name in selected_attributes])
        lines.append("")

    lines.append("## Version Differences")
    lines.append(version_diff_section)
    lines.append("")

    if compiled_expression:
        lines.append("## Executed Rule Expression")
        lines.append("```text")
        lines.append(compiled_expression)
        lines.append("```")
        lines.append("")

    lines.append("## Business Evidence Snapshot")
    lines.append(f"- Evidence ID: `{proof_id}`")
    lines.append(f"- Result: {'Passed' if proof_status.lower() == 'passed' else 'Failed'}")
    lines.append(f"- Records tested: {records_tested:,}")
    lines.append(f"- Records failed: {failures_found:,}")
    lines.append(f"- Coverage: {coverage_pct:.2f}%")
    lines.append(f"- Success rate: {success_rate:.2f}%")
    lines.append("")
    return "\n".join(lines)


def build_testing_scheduler_handoff_entity(
    request_id: str,
    execution_context: RuleExecutionContextEntity | Mapping[str, Any] | None,
    correlation_id: str,
    *,
    handoff_id: str | None = None,
    submitted_at: str | None = None,
) -> TestingSchedulerHandoffEntity:
    context_payload = serialize_rule_execution_context_payload(execution_context)
    target = None
    execution_contract = context_payload.get("executionContract")
    if isinstance(execution_contract, Mapping):
        target = str(execution_contract.get("engineTarget") or "").strip() or None

    return TestingSchedulerHandoffEntity(
        handoffId=handoff_id or f"handoff-{uuid4().hex[:12]}",
        correlationId=correlation_id,
        batchRequestId=request_id,
        submittedAt=submitted_at or datetime.now(UTC).isoformat(),
        executorTarget=target or "dq-engine",
        handoffStatus="accepted",
        handoffReady=bool(context_payload.get("handoffReady")),
    )


def build_batch_test_execution_context_payload(
    request_id: str,
    execution_context: RuleExecutionContextEntity | Mapping[str, Any] | None,
    correlation_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    context_payload = serialize_rule_execution_context_payload(execution_context)
    scheduler_handoff = build_testing_scheduler_handoff_entity(
        request_id,
        execution_context,
        correlation_id,
    )
    context_payload["correlationId"] = correlation_id
    context_payload["schedulerHandoff"] = scheduler_handoff.model_dump(mode="python")
    return context_payload, scheduler_handoff.model_dump(mode="python")


def build_test_execution_trace_entity(
    *,
    status: str,
    execution_context: RuleExecutionContextEntity | Mapping[str, Any] | None,
    correlation_id: str | None = None,
    execution_id: str | None = None,
    executed_at: str | None = None,
) -> ExecutionTraceEntity:
    context_payload = serialize_rule_execution_context_payload(execution_context)
    return ExecutionTraceEntity(
        executionId=execution_id or f"exec-{uuid4().hex[:12]}",
        correlationId=correlation_id or f"corr-{uuid4().hex[:12]}",
        executedAt=executed_at if executed_at is not None else (
            datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
            if status in {"passed", "failed"}
            else None
        ),
        resultStatus=status,
        artifactKey=context_payload.get("artifactKey"),
        ruleVersionId=context_payload.get("ruleVersionId"),
        ruleVersionNumber=context_payload.get("ruleVersionNumber"),
        compilerVersion=context_payload.get("compilerVersion"),
        compilerRevision=context_payload.get("compilerRevision"),
        schemaVersion=context_payload.get("schemaVersion"),
    )


def merge_test_run_execution_context(
    run_result_payload: Mapping[str, Any] | None,
    execution_context: RuleExecutionContextEntity | Mapping[str, Any] | None,
    *,
    compiled_expression: str | None = None,
) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    if isinstance(run_result_payload, Mapping):
        raw_context = run_result_payload.get("executionContext")
        if isinstance(raw_context, Mapping):
            merged.update(dict(raw_context))

    merged.update(serialize_rule_execution_context_payload(execution_context))
    merged["executedExpressionSource"] = (
        "compiled-artifact" if str(compiled_expression or "").strip() else "rule-expression"
    )
    merged["executedExpression"] = (
        run_result_payload.get("expression") if isinstance(run_result_payload, Mapping) else None
    )
    return merged


def build_generated_data_test_proof_payload(
    *,
    status: str,
    execution_context: RuleExecutionContextEntity | Mapping[str, Any] | None,
    message: str,
    requested_by_user_id: str | None = None,
    correlation_id: str | None = None,
    request_id: str | None = None,
    version_id: str | None = None,
    sample_count: int | None = None,
    semantic_matching: dict[str, Any] | None = None,
    data_object_id: str | None = None,
    data_object_name: str | None = None,
    version_name: int | str | None = None,
) -> dict[str, Any]:
    execution_trace = build_test_execution_trace_entity(
        status=status,
        execution_context=execution_context,
        correlation_id=correlation_id,
    )
    context_payload = serialize_rule_execution_context_payload(execution_context)
    proof_data = {
        "requestStatus": status,
        "requestMessage": message,
        "testDataRequestId": request_id,
        "requested_by_user_id": requested_by_user_id,
        "versionId": version_id,
        "sampleCount": sample_count,
        "dataObjectId": data_object_id,
        "dataObjectName": data_object_name,
        "versionName": version_name,
        "semanticMatching": semantic_matching or None,
        "executionContext": context_payload,
        "executionTrace": execution_trace.model_dump(mode="python"),
    }
    if status == "failed":
        proof_data["error"] = message
        proof_data["errorType"] = "queued_test_data_generation_failed"

    return {
        "coverage": 0.0,
        "passed": status == "passed",
        "recordsTestedCount": 0,
        "failuresFound": 0,
        "proofData": proof_data,
        "executionTrace": execution_trace.model_dump(mode="python"),
        "status": status,
    }


def build_manual_test_proof_storage_payload(
    payload: Mapping[str, Any],
    *,
    execution_context: RuleExecutionContextEntity | Mapping[str, Any] | None,
    requested_by_user_id: str,
    execution_trace: ExecutionTraceEntity | Mapping[str, Any] | None,
) -> dict[str, Any]:
    payload_dict = dict(payload)
    context_payload = serialize_rule_execution_context_payload(execution_context)
    existing_proof_data = payload.get("proofData")
    payload_dict["proofData"] = {
        **(dict(existing_proof_data) if isinstance(existing_proof_data, Mapping) else {}),
        "requested_by_user_id": requested_by_user_id,
        "executionContext": context_payload,
    }
    payload_dict["executionContext"] = context_payload or None
    payload_dict["executionTrace"] = serialize_test_execution_trace_payload(execution_trace)
    return payload_dict


def build_generated_data_test_proof_update_payload(
    response_payload: Mapping[str, Any],
    *,
    final_status: str,
    correlation_id: str | None = None,
    request_id: str | None = None,
    version_id: str | None = None,
    sample_count: int | None = None,
    semantic_matching: dict[str, Any] | None = None,
    requested_by_user_id: str | None = None,
    data_object_id: str | None = None,
    data_object_name: str | None = None,
    version_name: int | str | None = None,
) -> dict[str, Any]:
    payload = dict(response_payload)
    execution_context = payload.get("executionContext") if isinstance(payload.get("executionContext"), Mapping) else None
    return {
        "coverage": payload.get("successRate") or 0,
        "passed": final_status == "passed",
        "recordsTestedCount": payload.get("totalTests") or 0,
        "failuresFound": payload.get("failedCount") or 0,
        "proofData": {
            **payload,
            "requestStatus": final_status,
            "requestMessage": "Rule test completed.",
            "testDataRequestId": request_id,
            "versionId": version_id,
            "dataObjectId": data_object_id,
            "dataObjectName": data_object_name,
            "versionName": version_name,
            "sampleCount": sample_count,
            "semanticMatching": semantic_matching,
            "requested_by_user_id": requested_by_user_id,
        },
        "executionTrace": build_test_execution_trace_entity(
            status=final_status,
            execution_context=execution_context,
            correlation_id=correlation_id,
        ).model_dump(mode="python"),
    }