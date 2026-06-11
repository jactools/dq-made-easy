from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException


@dataclass(slots=True)
class RunRuleWithDataCommand:
    rule_id: str
    test_data: list[dict[str, Any]]
    version_id_source: str | None = None
    semantic_matching: dict[str, Any] | None = None


@dataclass(slots=True)
class ExecuteRuleWithDataResult:
    response_payload: dict[str, Any]


@dataclass(slots=True)
class StoreManualTestProofCommand:
    rule_id: str
    payload: dict[str, Any]
    passed: bool
    requested_by_user_id: str | None = None


@dataclass(slots=True)
class RuleWithDataExecutionServices:
    build_execution_context: BuildExecutionContext
    serialize_execution_context: SerializeExecutionContext
    run_rule_against_test_data: RunRuleAgainstTestData
    merge_execution_context: MergeExecutionContext


@dataclass(slots=True)
class ManualTestProofServices:
    resolve_current_rule_status: ResolveCurrentRuleStatus
    build_execution_context: BuildExecutionContext
    build_execution_trace: BuildExecutionTrace
    build_manual_test_proof_storage_payload: BuildManualTestProofStoragePayload
    store_test_proof: StoreTestProof
    record_rule_tested_transition: RecordRuleTestedTransition


BuildExecutionContext = Callable[[str], Awaitable[Any]]
SerializeExecutionContext = Callable[[Any], dict[str, Any]]
RunRuleAgainstTestData = Callable[..., Any]
MergeExecutionContext = Callable[[dict[str, Any], Any, str], dict[str, Any]]
ResolveCurrentRuleStatus = Callable[[str], Awaitable[str | None]]
BuildExecutionTrace = Callable[..., Any]
BuildManualTestProofStoragePayload = Callable[..., dict[str, Any]]
StoreTestProof = Callable[[str, dict[str, Any]], Any]
RecordRuleTestedTransition = Callable[[str, str, str | None], Awaitable[None]]


def _resolve_failure_is_missing_compiler_artifact(exc: HTTPException) -> bool:
    detail = getattr(exc, "detail", None)
    return (
        exc.status_code == 409
        and isinstance(detail, Mapping)
        and detail.get("error") == "active_compiler_artifact_required"
    )


async def execute_rule_with_data(
    command: RunRuleWithDataCommand,
    services: RuleWithDataExecutionServices,
) -> ExecuteRuleWithDataResult:
    execution_context = await services.build_execution_context(command.rule_id)
    context_payload = services.serialize_execution_context(execution_context)
    compiled_expression = str(context_payload.get("compiledExpression") or "").strip()

    run_result = services.run_rule_against_test_data(
        command.rule_id,
        command.test_data,
        command.version_id_source,
        compiled_expression=compiled_expression or None,
        semantic_config=command.semantic_matching,
    )
    response_payload = run_result.model_dump()
    response_payload["executionContext"] = services.merge_execution_context(
        response_payload,
        execution_context,
        compiled_expression=compiled_expression,
    )
    return ExecuteRuleWithDataResult(response_payload=response_payload)


async def store_manual_test_proof(
    command: StoreManualTestProofCommand,
    services: ManualTestProofServices,
) -> Any:
    current_status = await services.resolve_current_rule_status(command.rule_id)
    try:
        execution_context = await services.build_execution_context(command.rule_id)
    except HTTPException as exc:
        if _resolve_failure_is_missing_compiler_artifact(exc):
            execution_context = None
        else:
            raise

    execution_trace = services.build_execution_trace(
        status="passed" if command.passed else "failed",
        execution_context=execution_context,
        executed_at=None,
    )
    payload_dict = services.build_manual_test_proof_storage_payload(
        command.payload,
        execution_context=execution_context,
        requested_by_user_id=command.requested_by_user_id,
        execution_trace=execution_trace,
    )
    stored = services.store_test_proof(command.rule_id, payload_dict)

    if command.passed and current_status is not None:
        try:
            await services.record_rule_tested_transition(command.rule_id, current_status, command.requested_by_user_id)
        except ValueError:
            pass
    return stored