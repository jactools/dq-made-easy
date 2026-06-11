from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException

from app.application.services import testing_generated_proof_service


def _snake_to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part[:1].upper() + part[1:] for part in tail)


def _payload_value(payload: Any, name: str) -> Any:
    if isinstance(payload, Mapping):
        if name in payload:
            return payload[name]
        camel_name = _snake_to_camel(name)
        if camel_name in payload:
            return payload[camel_name]
        return None
    if hasattr(payload, name):
        return getattr(payload, name)
    camel_name = _snake_to_camel(name)
    if hasattr(payload, camel_name):
        return getattr(payload, camel_name)
    return None


def _normalize_optional_str(value: Any) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


@dataclass(slots=True)
class GenerateTestDataForVersionCommand:
    version_id: str
    sample_count: int


@dataclass(slots=True)
class GenerateTestDataForDataAssetCommand:
    asset_id: str
    sample_count: int


@dataclass(slots=True)
class StartGeneratedDataRuleTestCommand:
    rule_id: str
    version_id: str
    sample_count: int
    correlation_id: str
    requested_by_user_id: str | None = None
    semantic_matching: dict[str, Any] | None = None


@dataclass(slots=True)
class GeneratedDataRuleTestCommand:
    rule_id: str
    version_id: str
    sample_count: int
    requested_by_user_id: str | None = None
    proof_id: str | None = None
    semantic_matching: dict[str, Any] | None = None


@dataclass(slots=True)
class GeneratedDataRuleTestResult:
    response_payload: dict[str, Any]


@dataclass(slots=True)
class GeneratedTestDataServices:
    resolve_version_generation_payload: ResolveVersionGenerationPayload
    enqueue_queued_test_data_request: EnqueueQueuedTestDataRequest
    wait_for_test_data_request_result: WaitForQueuedTestDataRequestResult


@dataclass(slots=True)
class GeneratedDataAssetServices:
    resolve_data_asset_generation_payload: ResolveDataAssetGenerationPayload
    enqueue_queued_test_data_request: EnqueueQueuedTestDataRequest
    wait_for_test_data_request_result: WaitForQueuedTestDataRequestResult


@dataclass(slots=True)
class StartGeneratedDataRuleTestServices:
    build_execution_context: BuildExecutionContext
    persist_generated_data_proof: PersistGeneratedDataProof


@dataclass(slots=True)
class GeneratedDataRuleTestServices:
    build_execution_context: BuildExecutionContext
    serialize_execution_context: SerializeExecutionContext
    resolve_version_generation_payload: ResolveVersionGenerationPayload
    enqueue_queued_test_data_request: EnqueueQueuedTestDataRequest
    wait_for_test_data_request_result: WaitForQueuedTestDataRequestResult
    persist_generated_data_proof: PersistGeneratedDataProof
    update_generated_data_proof: UpdateGeneratedDataProof
    run_rule_against_test_data: RunRuleAgainstTestData
    merge_execution_context: MergeExecutionContext
    serialize_proof: SerializeProof
    resolve_current_rule_status: ResolveCurrentRuleStatus
    record_rule_tested_transition: RecordRuleTestedTransition


ResolveVersionGenerationPayload = Callable[[str, int], dict[str, Any]]
ResolveDataAssetGenerationPayload = Callable[[str, int], dict[str, Any]]
EnqueueQueuedTestDataRequest = Callable[[dict[str, Any]], Awaitable[Any]]
WaitForQueuedTestDataRequestResult = Callable[[str], Awaitable[Any]]
BuildExecutionContext = Callable[[str], Awaitable[Any]]
SerializeExecutionContext = Callable[[Any], dict[str, Any]]
PersistGeneratedDataProof = Callable[..., Any]
UpdateGeneratedDataProof = Callable[..., Any]
RunRuleAgainstTestData = Callable[..., Any]
MergeExecutionContext = Callable[[dict[str, Any], Any, str], dict[str, Any]]
SerializeProof = Callable[[Any], dict[str, Any]]
ResolveCurrentRuleStatus = Callable[[str], Awaitable[str | None]]
RecordRuleTestedTransition = Callable[[str, str, str | None], Awaitable[None]]


def _request_metadata(request_payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "data_object_id": request_payload.get("data_object_id"),
        "data_object_name": request_payload.get("data_object_name"),
        "version_name": request_payload.get("version_name"),
    }


def _persist_proof(
    persist_generated_data_proof: PersistGeneratedDataProof,
    *,
    command: StartGeneratedDataRuleTestCommand | GeneratedDataRuleTestCommand,
    execution_context: Any,
    request_payload: dict[str, Any],
    status: str,
    message: str,
    proof_id: str | None = None,
    correlation_id: str | None = None,
    request_id: str | None = None,
) -> Any:
    return persist_generated_data_proof(
        rule_id=command.rule_id,
        proof_id=proof_id,
        status=status,
        execution_context=execution_context,
        message=message,
        requested_by_user_id=command.requested_by_user_id,
        correlation_id=correlation_id,
        request_id=request_id,
        version_id=command.version_id,
        sample_count=command.sample_count,
        semantic_matching=command.semantic_matching,
        **_request_metadata(request_payload),
    )


async def generate_test_data_for_version(
    command: GenerateTestDataForVersionCommand,
    services: GeneratedTestDataServices,
) -> Any:
    request_payload = services.resolve_version_generation_payload(command.version_id, command.sample_count)
    queued_request = await services.enqueue_queued_test_data_request(request_payload=request_payload)
    request_id = _normalize_optional_str(_payload_value(queued_request, "request_id"))
    completed_request = await services.wait_for_test_data_request_result(request_id or "")
    return _payload_value(completed_request, "result")


async def generate_test_data_for_data_asset(
    command: GenerateTestDataForDataAssetCommand,
    services: GeneratedDataAssetServices,
) -> Any:
    request_payload = services.resolve_data_asset_generation_payload(command.asset_id, command.sample_count)
    queued_request = await services.enqueue_queued_test_data_request(request_payload=request_payload)
    request_id = _normalize_optional_str(_payload_value(queued_request, "request_id"))
    completed_request = await services.wait_for_test_data_request_result(request_id or "")
    return _payload_value(completed_request, "result")


async def start_generated_data_rule_test(
    command: StartGeneratedDataRuleTestCommand,
    services: StartGeneratedDataRuleTestServices,
) -> Any:
    execution_context = await services.build_execution_context(command.rule_id)
    return services.persist_generated_data_proof(
        rule_id=command.rule_id,
        proof_id=None,
        status="pending",
        execution_context=execution_context,
        message="Rule test accepted and queued.",
        correlation_id=command.correlation_id,
        requested_by_user_id=command.requested_by_user_id,
        version_id=command.version_id,
        sample_count=command.sample_count,
        semantic_matching=command.semantic_matching,
    )


async def execute_rule_with_generated_data(
    command: GeneratedDataRuleTestCommand,
    services: GeneratedDataRuleTestServices,
) -> GeneratedDataRuleTestResult:
    execution_context = await services.build_execution_context(command.rule_id)
    context_payload = services.serialize_execution_context(execution_context)
    compiled_expression = str(context_payload.get("compiledExpression") or "").strip()
    request_payload = services.resolve_version_generation_payload(command.version_id, command.sample_count)

    try:
        queued_request = await services.enqueue_queued_test_data_request(request_payload=request_payload)
    except HTTPException as exc:
        failure_message = testing_generated_proof_service.resolve_failure_message(exc.detail)
        stored_failure = _persist_proof(
            services.persist_generated_data_proof,
            command=command,
            execution_context=execution_context,
            request_payload=request_payload,
            proof_id=command.proof_id,
            status="failed",
            message=failure_message,
        )
        raise HTTPException(
            status_code=exc.status_code,
            detail={
                "error": "queued_test_data_generation_failed",
                "message": failure_message,
                "proof_id": _payload_value(stored_failure, "id"),
                "stored_proof": services.serialize_proof(stored_failure),
            },
        ) from exc

    queued_request_id = _normalize_optional_str(_payload_value(queued_request, "request_id"))
    queued_correlation_id = _normalize_optional_str(_payload_value(queued_request, "correlation_id"))

    stored_running = _persist_proof(
        services.persist_generated_data_proof,
        command=command,
        execution_context=execution_context,
        request_payload=request_payload,
        proof_id=command.proof_id,
        status="running",
        message="Generating test data and executing rule...",
        correlation_id=queued_correlation_id,
        request_id=queued_request_id,
    )
    proof_id = _normalize_optional_str(_payload_value(stored_running, "id"))

    try:
        completed_request = await services.wait_for_test_data_request_result(queued_request_id or "")
    except HTTPException as exc:
        failure_message = testing_generated_proof_service.resolve_failure_message(exc.detail)
        stored_failure = _persist_proof(
            services.persist_generated_data_proof,
            command=command,
            execution_context=execution_context,
            request_payload=request_payload,
            proof_id=proof_id,
            status="failed",
            message=failure_message,
            correlation_id=queued_correlation_id,
            request_id=queued_request_id,
        )
        raise HTTPException(
            status_code=exc.status_code,
            detail={
                "error": "queued_test_data_generation_failed",
                "message": failure_message,
                "proof_id": _payload_value(stored_failure, "id"),
                "stored_proof": services.serialize_proof(stored_failure),
                "correlation_id": queued_correlation_id,
            },
        ) from exc

    generated_result = _payload_value(completed_request, "result")
    generated_samples = list(_payload_value(generated_result, "samples") or [])

    run_result = services.run_rule_against_test_data(
        command.rule_id,
        generated_samples,
        command.version_id,
        compiled_expression=compiled_expression or None,
        semantic_config=command.semantic_matching,
    )
    if int(getattr(run_result, "totalTests", 0) or 0) <= 0:
        stored_failure = _persist_proof(
            services.persist_generated_data_proof,
            command=command,
            execution_context=execution_context,
            request_payload=request_payload,
            proof_id=proof_id,
            status="failed",
            message="No test records were executed for the provided versionId.",
            correlation_id=queued_correlation_id,
            request_id=queued_request_id,
        )
        raise HTTPException(
            status_code=400,
            detail={
                "error": "queued_test_data_generation_failed",
                "message": (
                    "No test records were executed for the provided versionId. "
                    "Ensure versionId points to a valid data-object version with testable attributes."
                ),
                "proof_id": _payload_value(stored_failure, "id"),
                "stored_proof": services.serialize_proof(stored_failure),
                "correlation_id": queued_correlation_id,
            },
        )

    response_payload = run_result.model_dump()
    merged_execution_context = services.merge_execution_context(
        response_payload,
        execution_context,
        compiled_expression=compiled_expression,
    )
    response_payload["executionContext"] = merged_execution_context
    final_status = "passed" if bool(response_payload.get("rulePassed")) else "failed"
    stored_result = services.update_generated_data_proof(
        proof_id=proof_id,
        response_payload=response_payload,
        final_status=final_status,
        correlation_id=queued_correlation_id,
        request_id=queued_request_id,
        version_id=command.version_id,
        sample_count=command.sample_count,
        semantic_matching=command.semantic_matching,
        requested_by_user_id=command.requested_by_user_id,
        **_request_metadata(request_payload),
    )

    if final_status == "passed":
        current_status = await services.resolve_current_rule_status(command.rule_id)
        if current_status is not None:
            try:
                await services.record_rule_tested_transition(command.rule_id, current_status, command.requested_by_user_id)
            except ValueError:
                pass

    response_payload["storedProof"] = services.serialize_proof(stored_result)
    return GeneratedDataRuleTestResult(response_payload=response_payload)