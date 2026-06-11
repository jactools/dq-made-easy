import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import ConfigDict, Field
from dq_domain_validation import TestingOutputFormat

from app.api.v1 import testing_data_requests_api as _testing_data_requests_api
from app.api.v1 import testing_generated_data_api as _testing_generated_data_api
from app.api.v1 import testing_workflows_api as _testing_workflows_api
from app.schemas.pydantic_base import SnakeModel, to_snake_alias
from app.api.v1 import testing_api as _testing_api
from app.api.v1.schemas import (
    BatchTestRequestView,
    BatchTestRequestsPageView,
    BatchTestRunResultView,
    StoreTestProofResultView,
    TestDataPayloadView,
    TestProofView,
    TestRunResultView,
)
from app.api.v1.schemas.test_data_queue_view import CreateQueuedTestDataRequest
from app.api.v1.schemas.test_data_queue_view import QueuedTestDataRequestView
from app.api.v1.schemas.test_data_materialization_view import ReportTestDataMaterializationCompletionRequest
from app.api.v1.schemas.test_data_materialization_view import TestDataMaterializationCompletionView
from app.api.v1.schemas.test_data_materialization_view import TestDataMaterializationRequestView
from app.core.dependencies import get_data_catalog_repository
from app.core.dependencies import get_testing_repository
from app.core.dependencies import get_rules_repository
from app.core.log_event import log_event
from app.core.request_context import get_user_id
from app.core.telemetry import set_span_attributes, traced_span
from app.domain.interfaces import RulesRepository
from app.domain.interfaces.v1.data_catalog_repository import DataCatalogRepository
from app.domain.interfaces.v1.testing_repository import TestingRepository

router = APIRouter(tags=["testing"])
_log = logging.getLogger(__name__)


class CreateBatchTestRequest(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    ruleIds: list[str]
    testDataConfig: dict | None = None
    requestedBy: str | None = None
    workspace: str | None = None


class GenerateTestDataRequest(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    sampleCount: int = Field(default=10, ge=1, le=1000)


class TestRuleWithDataRequest(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    testData: list[dict]
    versionIdSource: str | None = None
    semanticMatching: "SemanticMatchingConfigRequest | None" = None


class LogTestActionRequest(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    coverage: float
    passed: bool
    recordsTestedCount: int
    failuresFound: int
    proofData: dict | None = None
    metrics: dict | None = None
    diagnostics: list[dict] | None = None


class TestRuleWithGeneratedDataRequest(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    versionId: str
    sampleCount: int = 10
    semanticMatching: "SemanticMatchingConfigRequest | None" = None
    proofId: str | None = None


class SemanticMatchingConfigRequest(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    enabled: bool = False
    fieldAliasMappings: dict[str, str] = Field(default_factory=dict)
    activeSynonyms: list[str] = Field(default_factory=lambda: ["active", "enabled", "true", "1", "yes", "on"])
    inactiveSynonyms: list[str] = Field(default_factory=lambda: ["inactive", "disabled", "false", "0", "no", "off"])

class CreateTestDataMaterializationRequest(SnakeModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid", alias_generator=to_snake_alias)

    data_object_version_id: str
    sample_count: int = Field(default=1000, ge=1, le=100000)
    output_format: TestingOutputFormat = Field(default="parquet")
    output_uri: str | None = None
    selected_attribute_names: list[str] = Field(default_factory=list)
    refresh: bool = Field(default=False)


@router.get("/batch-test-requests", response_model=BatchTestRequestsPageView)
async def get_batch_test_requests(
    workspace: str | None = Query(default=None),
    status: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    repository: TestingRepository = Depends(get_testing_repository),
) -> BatchTestRequestsPageView:
    log_event(_log, "testing.batch_requests.list.start", component="testing-api", workspace=workspace, status=status)
    result, row_count = _testing_workflows_api.list_batch_test_requests_page(workspace, status, page, limit, repository)
    log_event(_log, "testing.batch_requests.list.complete", component="testing-api", resultCount=row_count)
    return result


@router.post("/test-data/requests", response_model=QueuedTestDataRequestView)
async def create_test_data_request(
    request: Request,
    payload: CreateQueuedTestDataRequest,
    catalog_repository: DataCatalogRepository = Depends(get_data_catalog_repository),
) -> QueuedTestDataRequestView:
    return await _testing_data_requests_api.create_test_data_request(request, payload, catalog_repository)


@router.get("/test-data/requests/{request_id}", response_model=QueuedTestDataRequestView)
async def get_test_data_request(request_id: str) -> QueuedTestDataRequestView:
    return await _testing_data_requests_api.get_test_data_request_view(request_id)


@router.get("/test-data/requests/{request_id}/events", response_model=None)
async def stream_test_data_request_events(request_id: str, request: Request) -> Response:
    return await _testing_data_requests_api.stream_test_data_request_events(request_id, request)

@router.post(
    "/test-data/materializations",
    response_model=TestDataMaterializationRequestView,
    status_code=202,
)
async def create_test_data_materialization(
    request: Request,
    payload: CreateTestDataMaterializationRequest,
    catalog_repository: DataCatalogRepository = Depends(get_data_catalog_repository),
) -> TestDataMaterializationRequestView:
    return await _testing_data_requests_api.create_test_data_materialization(request, payload, catalog_repository)

@router.get(
    "/test-data/materializations/{request_id}",
    response_model=TestDataMaterializationRequestView,
)
async def get_test_data_materialization(request_id: str) -> TestDataMaterializationRequestView:
    return await _testing_data_requests_api.get_test_data_materialization_view(request_id)


@router.get(
    "/test-data/materializations/{request_id}/events",
    response_model=None,
)
async def stream_test_data_materialization_events(request_id: str, request: Request) -> Response:
    return await _testing_data_requests_api.stream_test_data_materialization_events(request_id, request)


@router.post(
    "/test-data/materializations/{request_id}/complete",
    response_model=TestDataMaterializationCompletionView,
)
async def report_test_data_materialization_completion(
    request_id: str,
    payload: ReportTestDataMaterializationCompletionRequest,
    catalog_repository: DataCatalogRepository = Depends(get_data_catalog_repository),
) -> TestDataMaterializationCompletionView:
    return await _testing_data_requests_api.report_test_data_materialization_completion(request_id, payload, catalog_repository)


@router.get("/batch-test-requests/{request_id}", response_model=BatchTestRequestView | None)
async def get_batch_test_request(
    request_id: str,
    repository: TestingRepository = Depends(get_testing_repository),
) -> BatchTestRequestView | None:
    result, event_name, level = _testing_api.get_batch_test_request_view(request_id, repository)
    log_event(_log, event_name, level=level, component="testing-api", runId=request_id)
    return result


@router.post("/batch-test-requests", response_model=list[BatchTestRequestView])
async def create_batch_test_request(
    payload: CreateBatchTestRequest,
    repository: TestingRepository = Depends(get_testing_repository),
) -> list[BatchTestRequestView]:
    log_event(_log, "testing.batch_requests.create.start", component="testing-api", requestedBy=payload.requestedBy)
    result, row_count = _testing_api.create_batch_test_request_views(payload, repository)
    log_event(_log, "testing.batch_requests.create.complete", component="testing-api", resultCount=row_count)
    return result


@router.post("/batch-test-requests/{request_id}/run", response_model=BatchTestRunResultView)
async def run_batch_test_request(
    request_id: str,
    repository: TestingRepository = Depends(get_testing_repository),
    rules_repository: RulesRepository = Depends(get_rules_repository),
) -> BatchTestRunResultView:
    with traced_span(
        "rules.execute.batch_request",
        endpoint_group="rules",
        operation="execute_rule_batch",
        batch_request_id=request_id,
    ) as span:
        log_event(_log, "testing.batch_request.run.start", component="testing-api", runId=request_id)
        result = await _testing_workflows_api.run_batch_test_request(request_id, repository, rules_repository)
        payload = result.response_payload
        set_span_attributes(span, **_testing_workflows_api.build_batch_test_request_span_attributes(result))
        log_event(_log, "testing.batch_request.run.complete", component="testing-api", runId=request_id)
        return BatchTestRunResultView.model_validate(payload)


@router.post("/data-object-versions/{version_id}/generate-test-data", response_model=TestDataPayloadView)
async def generate_test_data_for_version(
    request: Request,
    version_id: str,
    payload: GenerateTestDataRequest,
    catalog_repository: DataCatalogRepository = Depends(get_data_catalog_repository),
) -> TestDataPayloadView:
    log_event(_log, "testing.generate_data.start", component="testing-api", dataObjectVersionId=version_id)
    result = await _testing_generated_data_api.generate_test_data_payload(request, version_id, payload, catalog_repository)
    log_event(_log, "testing.generate_data.complete", component="testing-api", dataObjectVersionId=version_id)
    return result


@router.post("/rules/{rule_id}/test-with-data", response_model=TestRunResultView)
async def test_rule_with_data(
    rule_id: str,
    payload: TestRuleWithDataRequest,
    repository: TestingRepository = Depends(get_testing_repository),
    rules_repository: RulesRepository = Depends(get_rules_repository),
) -> TestRunResultView:
    with traced_span(
        "rules.execute.with_data",
        endpoint_group="rules",
        operation="execute_rule_with_data",
        rule_id=rule_id,
        test_record_count=len(payload.testData),
        version_id_source=payload.versionIdSource,
    ) as span:
        log_event(_log, "testing.rule_with_data.start", component="testing-api", ruleId=rule_id)
        result = await _testing_workflows_api.execute_rule_with_data(rule_id, payload, repository, rules_repository)
        response_payload = result.response_payload
        set_span_attributes(span, **_testing_workflows_api.build_rule_with_data_span_attributes(response_payload))
        log_event(_log, "testing.rule_with_data.complete", component="testing-api", ruleId=rule_id)
        return TestRunResultView.model_validate(response_payload)


@router.post("/rules/{rule_id}/test", response_model=StoreTestProofResultView)
async def log_test_action(
    rule_id: str,
    payload: LogTestActionRequest,
    repository: TestingRepository = Depends(get_testing_repository),
    rules_repository: RulesRepository = Depends(get_rules_repository),
) -> StoreTestProofResultView:
    log_event(_log, "testing.rule_test.store.start", component="testing-api", ruleId=rule_id)
    requester_id = get_user_id() or "system"
    stored = await _testing_workflows_api.store_manual_test_proof(rule_id, payload, repository, rules_repository, requester_id)
    log_event(_log, "testing.rule_test.store.complete", component="testing-api", ruleId=rule_id)
    return stored


@router.post("/rules/{rule_id}/test-runs/start", response_model=TestProofView)
async def start_rule_test_with_generated_data(
    request: Request,
    rule_id: str,
    payload: TestRuleWithGeneratedDataRequest,
    repository: TestingRepository = Depends(get_testing_repository),
    rules_repository: RulesRepository = Depends(get_rules_repository),
) -> TestProofView:
    log_event(_log, "testing.rule_run.start", component="testing-api", ruleId=rule_id)
    requester_id = get_user_id() or "system"
    pending_proof = await _testing_generated_data_api.start_generated_data_rule_test(
        request,
        rule_id,
        payload,
        repository,
        rules_repository,
        requester_id,
    )
    log_event(_log, "testing.rule_run.start.complete", component="testing-api", ruleId=rule_id, proofId=pending_proof.id)
    return pending_proof


@router.post("/rules/{rule_id}/test-with-generated-data", response_model=TestRunResultView)
async def test_rule_with_generated_data(
    request: Request,
    rule_id: str,
    payload: TestRuleWithGeneratedDataRequest,
    repository: TestingRepository = Depends(get_testing_repository),
    rules_repository: RulesRepository = Depends(get_rules_repository),
    catalog_repository: DataCatalogRepository = Depends(get_data_catalog_repository),
) -> TestRunResultView:
    with traced_span(
        "rules.execute.with_generated_data",
        endpoint_group="rules",
        operation="execute_rule_with_generated_data",
        rule_id=rule_id,
        version_id=payload.versionId,
        requested_sample_count=payload.sampleCount,
    ) as span:
        log_event(_log, "testing.rule_with_generated_data.start", component="testing-api", ruleId=rule_id)
        requester_id = get_user_id() or "system"
        try:
            result = await _testing_generated_data_api.execute_rule_with_generated_data(
                request,
                rule_id,
                payload,
                repository,
                rules_repository,
                catalog_repository,
                requester_id,
            )
        except HTTPException as exc:
            failure_context = _testing_generated_data_api.build_generated_data_failure_context(exc.detail)
            log_event(
                _log,
                "testing.rule_with_generated_data.failed",
                level="warning",
                component="testing-api",
                ruleId=rule_id,
                proofId=failure_context.get("proof_id"),
                error=failure_context.get("message"),
            )
            set_span_attributes(span, **dict(failure_context.get("span_attributes") or {}))
            raise

        response_payload = result.response_payload
        set_span_attributes(span, **_testing_generated_data_api.build_generated_data_success_span_attributes(response_payload))
        log_event(_log, "testing.rule_with_generated_data.complete", component="testing-api", ruleId=rule_id)
        return TestRunResultView.model_validate(response_payload)


@router.get("/test-proofs/{rule_id}", response_model=list[TestProofView])
async def get_test_proofs(
    rule_id: str,
    repository: TestingRepository = Depends(get_testing_repository),
) -> list[TestProofView]:
    proofs = _testing_workflows_api.list_test_proof_views(rule_id, repository)
    log_event(_log, "testing.proofs.list.complete", component="testing-api", ruleId=rule_id, resultCount=len(proofs))
    return proofs


@router.get("/test-proofs/{rule_id}/report")
async def export_test_proof_report(
    rule_id: str,
    format: str = Query(default="markdown", pattern="^(markdown|pdf)$"),
    proof_id: str | None = Query(default=None),
    repository: TestingRepository = Depends(get_testing_repository),
    rules_repository: RulesRepository = Depends(get_rules_repository),
) -> StreamingResponse:
    log_event(_log, "testing.proof_report.export.start", component="testing-api", ruleId=rule_id)
    try:
        response = await _testing_workflows_api.export_test_proof_report_response(
            rule_id,
            format,
            proof_id,
            repository,
            rules_repository,
        )
    except HTTPException:
        event_name = _testing_workflows_api.build_test_proof_report_failure_event_name(proof_id)
        log_event(_log, event_name, level="warning", component="testing-api", ruleId=rule_id)
        raise

    log_event(_log, "testing.proof_report.export.complete", component="testing-api", ruleId=rule_id, outputFormat=format)
    return response
