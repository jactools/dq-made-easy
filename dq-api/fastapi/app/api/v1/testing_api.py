from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from fastapi import Request
from fastapi.responses import StreamingResponse

from app.api.presenters.testing import build_batch_test_execution_context_payload
from app.api.presenters.testing import build_manual_test_proof_storage_payload
from app.api.presenters.testing import build_test_execution_trace_entity
from app.api.presenters.testing import build_test_markdown_report
from app.api.presenters.testing import render_test_proof_version_diff_section
from app.api.presenters.testing import serialize_rule_execution_context_payload
from app.api.v1 import testing_data_requests_api as _testing_data_requests_api
from app.api.v1 import testing_generated_data_api as _testing_generated_data_api
from app.api.v1 import testing_workflows_api as _testing_workflows_api
from app.api.v1.schemas import StoreTestProofResultView
from app.api.v1.schemas.test_data_materialization_view import ReportTestDataMaterializationCompletionRequest
from app.api.v1.schemas.test_data_queue_view import CreateQueuedTestDataRequest
from app.application.resolvers import resolve_batch_test_request_list_view
from app.application.resolvers import resolve_batch_test_request_view
from app.application.resolvers import resolve_batch_test_requests_page_view
from app.application.resolvers import resolve_store_test_proof_result_view
from app.application.resolvers import resolve_test_proofs_view
from app.application.services import testing_generated_proof_service
from app.application.use_cases.testing_batch_requests import BatchTestRequestExecutionServices
from app.application.use_cases.testing_batch_requests import execute_batch_test_request as execute_batch_test_request_use_case
from app.application.use_cases.testing_batch_requests import RunBatchTestRequestCommand
from app.application.use_cases.testing_data_requests import create_queued_test_data_request as create_queued_test_data_request_use_case
from app.application.use_cases.testing_data_requests import CreateQueuedTestDataRequestCommand
from app.application.use_cases.testing_data_requests import create_test_data_materialization as create_test_data_materialization_use_case
from app.application.use_cases.testing_data_requests import CreateTestDataMaterializationCommand
from app.application.use_cases.testing_data_requests import get_queued_test_data_request as get_queued_test_data_request_use_case
from app.application.use_cases.testing_data_requests import GetQueuedTestDataRequestCommand
from app.application.use_cases.testing_data_requests import get_test_data_materialization as get_test_data_materialization_use_case
from app.application.use_cases.testing_data_requests import GetTestDataMaterializationCommand
from app.application.use_cases.testing_data_requests import report_test_data_materialization_completion as report_test_data_materialization_completion_use_case
from app.application.use_cases.testing_data_requests import ReportTestDataMaterializationCompletionCommand
from app.application.use_cases.testing_execution import store_manual_test_proof as store_manual_test_proof_use_case
from app.application.use_cases.testing_execution import execute_rule_with_data as execute_rule_with_data_use_case
from app.application.use_cases.testing_execution import ManualTestProofServices
from app.application.use_cases.testing_execution import RuleWithDataExecutionServices
from app.application.use_cases.testing_execution import RunRuleWithDataCommand
from app.application.use_cases.testing_execution import StoreManualTestProofCommand
from app.application.use_cases.testing_reports import export_test_proof_report as export_test_proof_report_use_case
from app.application.use_cases.testing_reports import ExportTestProofReportCommand
from app.application.use_cases.testing_reports import list_test_proofs as list_test_proofs_use_case
from app.application.use_cases.testing_reports import ListTestProofsCommand
from app.application.use_cases.testing_reports import TestProofReportServices
from app.api.presenters.testing import merge_test_run_execution_context
from app.domain.entities import rule_testing_context as _rule_testing_context
from app.domain.interfaces.v1.data_catalog_repository import DataCatalogRepository
from app.domain.interfaces.v1.testing_repository import TestingRepository


def build_create_test_data_request_command(
    payload: CreateQueuedTestDataRequest,
    catalog_repository: DataCatalogRepository,
) -> CreateQueuedTestDataRequestCommand:
    return _testing_data_requests_api.build_create_test_data_request_command(payload, catalog_repository)


def build_get_test_data_request_command(request_id: str) -> GetQueuedTestDataRequestCommand:
    return _testing_data_requests_api.build_get_test_data_request_command(request_id)


def build_create_test_data_materialization_command(payload: Any) -> CreateTestDataMaterializationCommand:
    return _testing_data_requests_api.build_create_test_data_materialization_command(payload)


def build_get_test_data_materialization_command(request_id: str) -> GetTestDataMaterializationCommand:
    return _testing_data_requests_api.build_get_test_data_materialization_command(request_id)


async def create_test_data_request(
    request: Request,
    payload: CreateQueuedTestDataRequest,
    catalog_repository: DataCatalogRepository,
) -> Any:
    return await _testing_data_requests_api.create_test_data_request(request, payload, catalog_repository)


async def get_test_data_request_view(request_id: str) -> Any:
    return await _testing_data_requests_api.get_test_data_request_view(request_id)


async def create_test_data_materialization(
    request: Request,
    payload: Any,
    catalog_repository: DataCatalogRepository,
) -> Any:
    return await _testing_data_requests_api.create_test_data_materialization(request, payload, catalog_repository)


async def get_test_data_materialization_view(request_id: str) -> Any:
    return await _testing_data_requests_api.get_test_data_materialization_view(request_id)


async def report_test_data_materialization_completion(
    request_id: str,
    payload: ReportTestDataMaterializationCompletionRequest,
    catalog_repository: DataCatalogRepository,
) -> Any:
    return await _testing_data_requests_api.report_test_data_materialization_completion(
        request_id,
        payload,
        catalog_repository,
    )


def list_batch_test_requests_page(
    workspace: str | None,
    status: str | None,
    page: int,
    limit: int,
    repository: TestingRepository,
) -> tuple[Any, int]:
    return _testing_workflows_api.list_batch_test_requests_page(workspace, status, page, limit, repository)


def get_batch_test_request_view(
    request_id: str,
    repository: TestingRepository,
) -> tuple[Any | None, str, str]:
    return _testing_workflows_api.get_batch_test_request_view(request_id, repository)


def create_batch_test_request_views(payload: Any, repository: TestingRepository) -> tuple[list[Any], int]:
    return _testing_workflows_api.create_batch_test_request_views(payload, repository)


def _mapping_payload(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump()
        if isinstance(dumped, Mapping):
            return dict(dumped)
    return {}


async def run_batch_test_request(
    request_id: str,
    repository: TestingRepository,
    rules_repository: Any,
) -> Any:
    return await _testing_workflows_api.run_batch_test_request(request_id, repository, rules_repository)


def build_batch_test_request_span_attributes(result: Any) -> dict[str, Any]:
    return _testing_workflows_api.build_batch_test_request_span_attributes(result)


def build_run_rule_with_data_command(rule_id: str, payload: Any) -> RunRuleWithDataCommand:
    return _testing_workflows_api.build_run_rule_with_data_command(rule_id, payload)


async def execute_rule_with_data(
    rule_id: str,
    payload: Any,
    repository: TestingRepository,
    rules_repository: Any,
) -> Any:
    return await _testing_workflows_api.execute_rule_with_data(rule_id, payload, repository, rules_repository)


def build_rule_with_data_span_attributes(response_payload: Mapping[str, Any] | dict[str, Any]) -> dict[str, Any]:
    return _testing_workflows_api.build_rule_with_data_span_attributes(response_payload)


async def start_generated_data_rule_test(
    request: Request,
    rule_id: str,
    payload: Any,
    repository: TestingRepository,
    rules_repository: Any,
    requester_id: str,
) -> Any:
    return await _testing_generated_data_api.start_generated_data_rule_test(
        request,
        rule_id,
        payload,
        repository,
        rules_repository,
        requester_id,
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
    return await _testing_generated_data_api.execute_rule_with_generated_data(
        request,
        rule_id,
        payload,
        repository,
        rules_repository,
        catalog_repository,
        requester_id,
    )


def build_generated_data_failure_context(detail: Any) -> dict[str, Any]:
    return _testing_generated_data_api.build_generated_data_failure_context(detail)


def build_generated_data_success_span_attributes(response_payload: Mapping[str, Any] | dict[str, Any]) -> dict[str, Any]:
    return _testing_generated_data_api.build_generated_data_success_span_attributes(response_payload)


async def generate_test_data_payload(
    request: Request,
    version_id: str,
    payload: Any,
    catalog_repository: DataCatalogRepository,
) -> Any:
    return await _testing_generated_data_api.generate_test_data_payload(
        request,
        version_id,
        payload,
        catalog_repository,
    )


async def store_manual_test_proof(
    rule_id: str,
    payload: Any,
    repository: TestingRepository,
    rules_repository: Any,
    requester_id: str,
) -> StoreTestProofResultView:
    return await _testing_workflows_api.store_manual_test_proof(rule_id, payload, repository, rules_repository, requester_id)


def list_test_proof_views(rule_id: str, repository: TestingRepository) -> list[Any]:
    return _testing_workflows_api.list_test_proof_views(rule_id, repository)


def build_test_proof_report_failure_event_name(proof_id: str | None) -> str:
    return _testing_workflows_api.build_test_proof_report_failure_event_name(proof_id)


async def export_test_proof_report_response(
    rule_id: str,
    output_format: str,
    proof_id: str | None,
    repository: TestingRepository,
    rules_repository: Any,
) -> StreamingResponse:
    return await _testing_workflows_api.export_test_proof_report_response(
        rule_id,
        output_format,
        proof_id,
        repository,
        rules_repository,
    )


def build_report_test_data_materialization_completion_command(
    request_id: str,
    payload: ReportTestDataMaterializationCompletionRequest,
) -> ReportTestDataMaterializationCompletionCommand:
    return _testing_data_requests_api.build_report_test_data_materialization_completion_command(request_id, payload)


def bind_queued_test_data_request_enqueuer(request: Request):
    return _testing_data_requests_api.bind_queued_test_data_request_enqueuer(request)


def bind_test_data_materialization_request_enqueuer(
    request: Request,
    catalog_repository: DataCatalogRepository,
):
    return _testing_data_requests_api.bind_test_data_materialization_request_enqueuer(request, catalog_repository)


def bind_materialized_delivery_completion_registrar(catalog_repository: DataCatalogRepository):
    return _testing_data_requests_api.bind_materialized_delivery_completion_registrar(catalog_repository)


def queued_test_data_request_view_payload(payload: Any) -> Any:
    return _testing_data_requests_api.queued_test_data_request_view_payload(payload)


def test_data_materialization_request_view_payload(payload: Any) -> Any:
    return _testing_data_requests_api.test_data_materialization_request_view_payload(payload)


def resolve_test_data_redis_url() -> str | None:
    return _testing_data_requests_api.resolve_test_data_redis_url()


async def read_test_data_request_record(redis_url: str, request_id: str) -> Any:
    return await _testing_data_requests_api.read_test_data_request_record(redis_url, request_id)


async def read_test_data_materialization_record(redis_url: str, request_id: str) -> Any:
    return await _testing_data_requests_api.read_test_data_materialization_record(redis_url, request_id)


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


def _persist_generated_data_test_proof(repository: TestingRepository, **kwargs: Any) -> Any:
    return _testing_generated_data_api._persist_generated_data_test_proof(repository, **kwargs)


def _bind_rule_versions_comparer(rules_repository: Any) -> Callable[[str, str, str], Any]:
    def _compare(rule_id: str, previous_version_id: str, latest_version_id: str) -> Any:
        return getattr(rules_repository, "compare_rule_versions")(rule_id, previous_version_id, latest_version_id)

    return _compare


def _bind_rule_getter(rules_repository: Any) -> Callable[[str], Any]:
    def _get(rule_id: str) -> Any:
        return getattr(rules_repository, "get_rule_by_id")(rule_id)

    return _get


def _bind_rule_version_getter(rules_repository: Any) -> Callable[[str, str], Any]:
    def _get(rule_id: str, version_id: str) -> Any:
        return getattr(rules_repository, "get_rule_version")(rule_id, version_id)

    return _get


def build_batch_test_request_execution_services(
    repository: TestingRepository,
    rules_repository: Any,
) -> BatchTestRequestExecutionServices:
    return BatchTestRequestExecutionServices(
        get_batch_test_request=repository.get_batch_test_request,
        build_execution_context=_bind_execution_context_builder(rules_repository),
        run_batch_test_request=repository.run_batch_test_request,
        build_batch_test_execution_context_payload=build_batch_test_execution_context_payload,
    )


def build_generated_test_data_services(
    request: Request,
    catalog_repository: DataCatalogRepository,
) -> Any:
    return _testing_generated_data_api.build_generated_test_data_services(request, catalog_repository)


def build_rule_with_data_execution_services(
    repository: TestingRepository,
    rules_repository: Any,
) -> RuleWithDataExecutionServices:
    return RuleWithDataExecutionServices(
        build_execution_context=_bind_execution_context_builder(rules_repository),
        serialize_execution_context=serialize_rule_execution_context_payload,
        run_rule_against_test_data=repository.run_rule_against_test_data,
        merge_execution_context=merge_test_run_execution_context,
    )


def build_manual_test_proof_services(
    repository: TestingRepository,
    rules_repository: Any,
) -> ManualTestProofServices:
    return ManualTestProofServices(
        resolve_current_rule_status=_bind_current_rule_status_resolver(rules_repository),
        build_execution_context=_bind_execution_context_builder(rules_repository),
        build_execution_trace=build_test_execution_trace_entity,
        build_manual_test_proof_storage_payload=build_manual_test_proof_storage_payload,
        store_test_proof=repository.store_test_proof,
        record_rule_tested_transition=_bind_rule_tested_transition_recorder(rules_repository),
    )


def build_start_generated_data_rule_test_services(
    repository: TestingRepository,
    rules_repository: Any,
) -> Any:
    return _testing_generated_data_api.build_start_generated_data_rule_test_services(repository, rules_repository)


def build_generated_data_rule_test_services(
    request: Request,
    repository: TestingRepository,
    rules_repository: Any,
    catalog_repository: DataCatalogRepository,
) -> Any:
    return _testing_generated_data_api.build_generated_data_rule_test_services(
        request,
        repository,
        rules_repository,
        catalog_repository,
    )


def build_test_proof_report_services(
    repository: TestingRepository,
    rules_repository: Any,
) -> TestProofReportServices:
    return TestProofReportServices(
        list_test_proofs=repository.list_test_proofs,
        resolve_test_proof_views=resolve_test_proofs_view,
        compare_rule_versions=_bind_rule_versions_comparer(rules_repository),
        get_rule_by_id=_bind_rule_getter(rules_repository),
        get_rule_version=_bind_rule_version_getter(rules_repository),
        render_version_diff_section=render_test_proof_version_diff_section,
        build_markdown_report=build_test_markdown_report,
        render_pdf=_testing_workflows_api._markdown_to_pdf_bytes,
    )