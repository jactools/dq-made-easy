from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
import io
import textwrap
from typing import Any

from fastapi.responses import StreamingResponse
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.api.presenters.data_catalog import build_data_catalog_page_payload
from app.api.presenters.testing import build_batch_test_execution_context_payload
from app.api.presenters.testing import build_manual_test_proof_storage_payload
from app.api.presenters.testing import build_test_execution_trace_entity
from app.api.presenters.testing import build_test_markdown_report
from app.api.presenters.testing import merge_test_run_execution_context
from app.api.presenters.testing import render_test_proof_version_diff_section
from app.api.presenters.testing import serialize_rule_execution_context_payload
from app.application.resolvers import resolve_batch_test_request_list_view
from app.application.resolvers import resolve_batch_test_request_view
from app.application.resolvers import resolve_batch_test_requests_page_view
from app.application.resolvers import resolve_store_test_proof_result_view
from app.application.resolvers import resolve_test_proofs_view
from app.application.use_cases.testing_batch_requests import BatchTestRequestExecutionServices
from app.application.use_cases.testing_batch_requests import execute_batch_test_request as execute_batch_test_request_use_case
from app.application.use_cases.testing_batch_requests import RunBatchTestRequestCommand
from app.application.use_cases.testing_execution import execute_rule_with_data as execute_rule_with_data_use_case
from app.application.use_cases.testing_execution import ManualTestProofServices
from app.application.use_cases.testing_execution import RuleWithDataExecutionServices
from app.application.use_cases.testing_execution import RunRuleWithDataCommand
from app.application.use_cases.testing_execution import StoreManualTestProofCommand
from app.application.use_cases.testing_execution import store_manual_test_proof as store_manual_test_proof_use_case
from app.application.use_cases.testing_reports import export_test_proof_report as export_test_proof_report_use_case
from app.application.use_cases.testing_reports import ExportTestProofReportCommand
from app.application.use_cases.testing_reports import list_test_proofs as list_test_proofs_use_case
from app.application.use_cases.testing_reports import ListTestProofsCommand
from app.application.use_cases.testing_reports import TestProofReportServices
from app.domain.entities import rule_testing_context as _rule_testing_context
from app.domain.interfaces.v1.testing_repository import TestingRepository


def _markdown_to_pdf_bytes(markdown_text: str) -> bytes:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    margin_x = 40
    margin_y = 40
    line_height = 14
    y = height - margin_y

    pdf.setFont("Helvetica", 10)

    for raw_line in markdown_text.splitlines():
        line = raw_line.rstrip()
        wrapped = textwrap.wrap(line, width=105) if line else [""]
        for part in wrapped:
            if y <= margin_y:
                pdf.showPage()
                pdf.setFont("Helvetica", 10)
                y = height - margin_y
            pdf.drawString(margin_x, y, part)
            y -= line_height

    pdf.save()
    buffer.seek(0)
    return buffer.getvalue()


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


def list_batch_test_requests_page(
    workspace: str | None,
    status: str | None,
    page: int,
    limit: int,
    repository: TestingRepository,
) -> tuple[Any, int]:
    rows = repository.list_batch_test_requests(workspace, status)
    page_payload = build_data_catalog_page_payload([row.model_dump() for row in rows], page, limit)
    return resolve_batch_test_requests_page_view(page_payload), len(rows)


def get_batch_test_request_view(
    request_id: str,
    repository: TestingRepository,
) -> tuple[Any | None, str, str]:
    result = repository.get_batch_test_request(request_id)
    if result is None:
        return None, "testing.batch_request.get.not_found", "warning"
    return resolve_batch_test_request_view(result), "testing.batch_request.get.complete", "info"


def create_batch_test_request_views(payload: Any, repository: TestingRepository) -> tuple[list[Any], int]:
    rows = repository.create_batch_test_requests(
        payload.ruleIds,
        payload.testDataConfig,
        payload.requestedBy,
        payload.workspace,
    )
    return resolve_batch_test_request_list_view(rows), len(rows)


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


async def run_batch_test_request(
    request_id: str,
    repository: TestingRepository,
    rules_repository: Any,
) -> Any:
    return await execute_batch_test_request_use_case(
        command=RunBatchTestRequestCommand(request_id=request_id),
        services=build_batch_test_request_execution_services(repository, rules_repository),
    )


def build_batch_test_request_span_attributes(result: Any) -> dict[str, Any]:
    payload = _mapping_payload(getattr(result, "response_payload", None))
    attributes: dict[str, Any] = {
        "execution_status": str(payload.get("status") or "unknown"),
    }
    rule_id = str(getattr(result, "rule_id", "") or "").strip()
    if not rule_id:
        return attributes

    execution_context = _mapping_payload(payload.get("executionContext"))
    scheduler_handoff = _mapping_payload(execution_context.get("schedulerHandoff"))
    attributes.update(
        {
            "rule_id": rule_id,
            "executor_target": scheduler_handoff.get("executorTarget"),
            "handoff_status": scheduler_handoff.get("handoffStatus"),
            "handoff_ready": bool(scheduler_handoff.get("handoffReady")) if scheduler_handoff else None,
        }
    )
    return attributes


def build_run_rule_with_data_command(rule_id: str, payload: Any) -> RunRuleWithDataCommand:
    return RunRuleWithDataCommand(
        rule_id=rule_id,
        test_data=list(payload.testData),
        version_id_source=payload.versionIdSource,
        semantic_matching=payload.semanticMatching.model_dump() if payload.semanticMatching else None,
    )


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


async def execute_rule_with_data(
    rule_id: str,
    payload: Any,
    repository: TestingRepository,
    rules_repository: Any,
) -> Any:
    return await execute_rule_with_data_use_case(
        command=build_run_rule_with_data_command(rule_id, payload),
        services=build_rule_with_data_execution_services(repository, rules_repository),
    )


def build_rule_with_data_span_attributes(response_payload: Mapping[str, Any] | dict[str, Any]) -> dict[str, Any]:
    normalized_payload = _mapping_payload(response_payload)
    execution_context = _mapping_payload(normalized_payload.get("executionContext"))
    return {
        "executed_expression_source": execution_context.get("executedExpressionSource"),
        "total_tests": normalized_payload.get("totalTests"),
        "passed_count": normalized_payload.get("passedCount"),
        "failed_count": normalized_payload.get("failedCount"),
    }


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


async def store_manual_test_proof(
    rule_id: str,
    payload: Any,
    repository: TestingRepository,
    rules_repository: Any,
    requester_id: str,
) -> Any:
    stored = await store_manual_test_proof_use_case(
        command=StoreManualTestProofCommand(
            rule_id=rule_id,
            payload=payload.model_dump(),
            passed=bool(payload.passed),
            requested_by_user_id=requester_id,
        ),
        services=build_manual_test_proof_services(repository, rules_repository),
    )
    return resolve_store_test_proof_result_view(stored)


def list_test_proof_views(rule_id: str, repository: TestingRepository) -> list[Any]:
    return list_test_proofs_use_case(
        command=ListTestProofsCommand(rule_id=rule_id),
        list_test_proofs=repository.list_test_proofs,
        resolve_test_proof_views=resolve_test_proofs_view,
    )


def build_test_proof_report_failure_event_name(proof_id: str | None) -> str:
    return "testing.proof_report.export.proof_not_found" if proof_id else "testing.proof_report.export.not_found"


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
        render_pdf=_markdown_to_pdf_bytes,
    )


async def export_test_proof_report_response(
    rule_id: str,
    output_format: str,
    proof_id: str | None,
    repository: TestingRepository,
    rules_repository: Any,
) -> StreamingResponse:
    result = await export_test_proof_report_use_case(
        command=ExportTestProofReportCommand(rule_id=rule_id, output_format=output_format, proof_id=proof_id),
        services=build_test_proof_report_services(repository, rules_repository),
    )
    body = (
        result.body
        if isinstance(result.body, bytes)
        else str(result.body).encode("utf-8")
        if result.media_type != "text/markdown"
        else result.body
    )
    return StreamingResponse(
        iter([body]),
        media_type=result.media_type,
        headers={"Content-Disposition": f"attachment; filename={result.filename}"},
    )