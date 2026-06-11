from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from typing import Any
from uuid import uuid4

from fastapi import Request

from app.api.presenters.testing import build_generated_data_test_proof_payload as build_generated_data_test_proof_payload_presenter
from app.api.presenters.testing import build_generated_data_test_proof_update_payload
from app.api.presenters.testing import merge_test_run_execution_context
from app.api.presenters.testing import serialize_rule_execution_context_payload
from app.api.v1 import test_data_queue_support as _test_data_queue_support
from app.api.v1 import testing_data_requests_api as _testing_data_requests_api
from app.api.v1.schemas import TestDataPayloadView
from app.api.v1.schemas import TestProofView
from app.application.resolvers import resolve_test_proofs_view
from app.application.services import testing_generated_proof_service
from app.application.use_cases.testing_generated_data import generate_test_data_for_version as generate_test_data_for_version_use_case
from app.application.use_cases.testing_generated_data import GenerateTestDataForVersionCommand
from app.application.use_cases.testing_generated_data import GeneratedDataRuleTestCommand
from app.application.use_cases.testing_generated_data import GeneratedDataRuleTestServices
from app.application.use_cases.testing_generated_data import GeneratedTestDataServices
from app.application.use_cases.testing_generated_data import execute_rule_with_generated_data as execute_rule_with_generated_data_use_case
from app.application.use_cases.testing_generated_data import start_generated_data_rule_test as start_generated_data_rule_test_use_case
from app.application.use_cases.testing_generated_data import StartGeneratedDataRuleTestCommand
from app.application.use_cases.testing_generated_data import StartGeneratedDataRuleTestServices
from app.domain.entities import rule_testing_context as _rule_testing_context
from app.domain.interfaces.v1.data_catalog_repository import DataCatalogRepository
from app.domain.interfaces.v1.testing_repository import TestingRepository


def _mapping_payload(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump()
        if isinstance(dumped, Mapping):
            return dict(dumped)
    return {}


def _bind_execution_context_builder(rules_repository: Any) -> Callable[[str], Awaitable[Any]]:
    async def _build(rule_id: str) -> Any:
        return await _rule_testing_context.build_execution_context(rules_repository, rule_id)

    return _build


def _bind_current_rule_status_resolver(rules_repository: Any) -> Callable[[str], Awaitable[str | None]]:
    async def _resolve(rule_id: str) -> str | None:
        return await _rule_testing_context.resolve_current_rule_status(rules_repository, rule_id)

    return _resolve


def _bind_rule_tested_transition_recorder(
    rules_repository: Any,
) -> Callable[[str, str, str | None], Awaitable[None]]:
    async def _record(rule_id: str, current_status: str, actor_id: str | None) -> None:
        await rules_repository.record_rule_status_transition(
            rule_id,
            current_status,
            "tested",
            actor_id,
            reason="Rule test passed",
        )

    return _record


def _bind_version_generation_payload_resolver(
    catalog_repository: DataCatalogRepository,
) -> Callable[[str, int], dict[str, Any]]:
    def _resolve(version_id: str, sample_count: int) -> dict[str, Any]:
        return _test_data_queue_support.resolve_version_generation_payload(version_id, sample_count, catalog_repository)

    return _resolve


def _serialize_test_proof(proof: Any) -> dict[str, Any]:
    return testing_generated_proof_service.serialize_test_proof(proof, resolve_test_proofs_view)


def _build_generated_data_test_proof_payload(**kwargs: Any) -> dict[str, Any]:
    return build_generated_data_test_proof_payload_presenter(**kwargs)


def _persist_generated_data_test_proof(repository: TestingRepository, **kwargs: Any) -> TestProofView:
    stored = testing_generated_proof_service.persist_generated_data_test_proof(
        repository,
        build_proof_payload=_build_generated_data_test_proof_payload,
        **kwargs,
    )
    return TestProofView.model_validate(stored)


def _bind_generated_data_proof_persister(repository: TestingRepository) -> Callable[..., TestProofView]:
    def _persist(**kwargs: Any) -> TestProofView:
        return _persist_generated_data_test_proof(repository, **kwargs)

    return _persist


def _bind_generated_data_proof_updater(repository: TestingRepository) -> Callable[..., Any]:
    def _update(**kwargs: Any) -> Any:
        return repository.update_test_proof(
            kwargs["proof_id"],
            build_generated_data_test_proof_update_payload(
                kwargs["response_payload"],
                final_status=kwargs["final_status"],
                correlation_id=kwargs.get("correlation_id"),
                request_id=kwargs.get("request_id"),
                version_id=kwargs.get("version_id"),
                sample_count=kwargs.get("sample_count"),
                semantic_matching=kwargs.get("semantic_matching"),
                requested_by_user_id=kwargs.get("requested_by_user_id"),
                data_object_id=kwargs.get("data_object_id"),
                data_object_name=kwargs.get("data_object_name"),
                version_name=kwargs.get("version_name"),
            ),
            status=kwargs["final_status"],
        )

    return _update


def build_start_generated_data_rule_test_command(
    request: Request,
    rule_id: str,
    payload: Any,
    requester_id: str,
) -> StartGeneratedDataRuleTestCommand:
    return StartGeneratedDataRuleTestCommand(
        rule_id=rule_id,
        version_id=payload.versionId,
        sample_count=payload.sampleCount,
        correlation_id=request.headers.get("X-Correlation-ID") or f"corr-{uuid4().hex[:12]}",
        requested_by_user_id=requester_id,
        semantic_matching=payload.semanticMatching.model_dump() if payload.semanticMatching else None,
    )


async def start_generated_data_rule_test(
    request: Request,
    rule_id: str,
    payload: Any,
    repository: TestingRepository,
    rules_repository: Any,
    requester_id: str,
) -> Any:
    return await start_generated_data_rule_test_use_case(
        command=build_start_generated_data_rule_test_command(request, rule_id, payload, requester_id),
        services=build_start_generated_data_rule_test_services(repository, rules_repository),
    )


def _resolve_generated_data_requested_by_user_id(request: Request, requester_id: str | None) -> str:
    request_state = getattr(request, "state", None)
    request_state_user_id = getattr(request_state, "user_id", None)
    return str(requester_id or request_state_user_id or "system")


def build_generated_data_rule_test_command(
    request: Request,
    rule_id: str,
    payload: Any,
    requester_id: str | None,
) -> GeneratedDataRuleTestCommand:
    return GeneratedDataRuleTestCommand(
        rule_id=rule_id,
        version_id=payload.versionId,
        sample_count=payload.sampleCount,
        requested_by_user_id=_resolve_generated_data_requested_by_user_id(request, requester_id),
        proof_id=str(payload.proofId or "").strip() or None,
        semantic_matching=payload.semanticMatching.model_dump() if payload.semanticMatching else None,
    )


async def execute_rule_with_generated_data(
    request: Request,
    rule_id: str,
    payload: Any,
    repository: TestingRepository,
    rules_repository: Any,
    catalog_repository: DataCatalogRepository,
    requester_id: str | None,
) -> Any:
    return await execute_rule_with_generated_data_use_case(
        command=build_generated_data_rule_test_command(request, rule_id, payload, requester_id),
        services=build_generated_data_rule_test_services(
            request,
            repository,
            rules_repository,
            catalog_repository,
        ),
    )


def build_generated_data_failure_context(detail: Any) -> dict[str, Any]:
    detail_payload = _mapping_payload(detail)
    failure_message = testing_generated_proof_service.resolve_failure_message(detail)
    return {
        "message": failure_message,
        "proof_id": detail_payload.get("proof_id"),
        "span_attributes": {
            "execution_status": "failed",
            "failure_proof_id": detail_payload.get("proof_id"),
            "failure_reason": failure_message,
        },
    }


def build_generated_data_success_span_attributes(response_payload: Mapping[str, Any] | dict[str, Any]) -> dict[str, Any]:
    normalized_payload = _mapping_payload(response_payload)
    execution_context = _mapping_payload(normalized_payload.get("executionContext"))
    return {
        "execution_status": "completed",
        "executed_expression_source": execution_context.get("executedExpressionSource"),
        "total_tests": normalized_payload.get("totalTests"),
        "passed_count": normalized_payload.get("passedCount"),
        "failed_count": normalized_payload.get("failedCount"),
    }


async def generate_test_data_payload(
    request: Request,
    version_id: str,
    payload: Any,
    catalog_repository: DataCatalogRepository,
) -> TestDataPayloadView:
    result_payload = await generate_test_data_for_version_use_case(
        command=GenerateTestDataForVersionCommand(version_id=version_id, sample_count=payload.sampleCount),
        services=build_generated_test_data_services(request, catalog_repository),
    )
    return TestDataPayloadView.model_validate(
        _test_data_queue_support.queued_test_data_result_entity(result_payload).model_dump(mode="python")
    )


def build_generated_test_data_services(
    request: Request,
    catalog_repository: DataCatalogRepository,
) -> GeneratedTestDataServices:
    return GeneratedTestDataServices(
        resolve_version_generation_payload=_bind_version_generation_payload_resolver(catalog_repository),
        enqueue_queued_test_data_request=_testing_data_requests_api.bind_queued_test_data_request_enqueuer(request),
        wait_for_test_data_request_result=_testing_data_requests_api.wait_for_test_data_request_result,
    )


def build_start_generated_data_rule_test_services(
    repository: TestingRepository,
    rules_repository: Any,
) -> StartGeneratedDataRuleTestServices:
    return StartGeneratedDataRuleTestServices(
        build_execution_context=_bind_execution_context_builder(rules_repository),
        persist_generated_data_proof=_bind_generated_data_proof_persister(repository),
    )


def build_generated_data_rule_test_services(
    request: Request,
    repository: TestingRepository,
    rules_repository: Any,
    catalog_repository: DataCatalogRepository,
) -> GeneratedDataRuleTestServices:
    return GeneratedDataRuleTestServices(
        build_execution_context=_bind_execution_context_builder(rules_repository),
        serialize_execution_context=serialize_rule_execution_context_payload,
        resolve_version_generation_payload=_bind_version_generation_payload_resolver(catalog_repository),
        enqueue_queued_test_data_request=_testing_data_requests_api.bind_queued_test_data_request_enqueuer(request),
        wait_for_test_data_request_result=_testing_data_requests_api.wait_for_test_data_request_result,
        persist_generated_data_proof=_bind_generated_data_proof_persister(repository),
        update_generated_data_proof=_bind_generated_data_proof_updater(repository),
        run_rule_against_test_data=repository.run_rule_against_test_data,
        merge_execution_context=merge_test_run_execution_context,
        serialize_proof=_serialize_test_proof,
        resolve_current_rule_status=_bind_current_rule_status_resolver(rules_repository),
        record_rule_tested_transition=_bind_rule_tested_transition_recorder(rules_repository),
    )