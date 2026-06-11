import logging
import re
from datetime import UTC, datetime, timedelta
from typing import Any
from time import perf_counter
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
import httpx
from pydantic import ConfigDict, ValidationError, Field

from app.application.services.grouped_execution_planner import GroupedExecutionPlanner
from app.application.services import gx_queue_service
from app.application.services.exception_storage import build_exception_storage_service
from app.api.presenters.gx import build_gx_suite_entity
from app.api.presenters.gx import build_gx_suite_expectation_entity
from app.api.presenters.gx import to_gx_run_plan_activation_view
from app.api.presenters.gx import to_gx_run_plan_validation_view
from app.api.presenters.gx import to_gx_run_plan_view
from app.api.presenters.gx import to_gx_suite_run_dispatch_handoff_view
from app.api.v1 import gx_assistance_api as _gx_assistance_api
from app.api.v1 import execution_browse_api as _gx_browse_api
from app.api.v1 import gx_dispatch_api as _gx_dispatch_api
from app.api.v1 import gx_execution_api as _gx_execution_api
from app.api.v1 import gx_report_api as _gx_report_api
from app.api.v1 import gx_runtime_api as _gx_runtime_api
from app.api.v1 import gx_run_plan_api as _gx_run_plan_api
from app.api.v1 import gx_start_api as _gx_start_api
from app.api.v1 import gx_suite_api as _gx_suite_api
from app.api.v1.schemas import ExceptionAnalyticsView
from app.api.v1.schemas import GxArtifactEnvelopeView
from app.api.v1.schemas import GxAssistanceRequestResponseView
from app.api.v1.schemas import GxAssistanceRequestView
from app.api.v1.schemas import GxExecutionRunStatusHistoryView
from app.api.v1.schemas import GxExecutionRunSummaryView
from app.api.v1.schemas import GxExecutionRunStatisticsView
from app.api.v1.schemas import GxExecutionRunView
from app.api.v1.schemas import GxExecutionQueueStatusView
from app.api.v1.schemas import DqResultDriftSummaryView
from app.api.v1.schemas import GxRunPlanActivationView
from app.api.v1.schemas import GxRunPlanCreateRequestView
from app.api.v1.schemas import GxRunPlanGovernanceTransitionRequestView
from app.api.v1.schemas import GxRunPlanValidationView
from app.api.v1.schemas import GxRunPlanVersionCreateRequestView
from app.api.v1.schemas import GxRunPlanView
from app.api.v1.schemas import GxSuiteRunDispatchHandoffView
from app.api.v1.schemas import GxSuiteRunHandoffView
from app.api.v1.schemas import GxSuiteRunScheduleRequestView
from app.api.v1.schemas import GxSuiteStatusHistoryView
from app.core.config import Settings
from app.core.config import get_settings
from app.core.dependencies import get_app_config_repository
from app.core.dependencies import get_exception_fact_repository
from app.core.dependencies import get_exception_reason_analytics_projection_repository
from app.core.dependencies import get_gx_execution_run_repository
from app.core.dependencies import get_approvals_repository
from app.core.dependencies import get_grouped_execution_planner
from app.core.dependencies import get_gx_suite_repository
from app.core.dependencies import get_dq_result_event_repository
from app.core.dependencies import get_data_catalog_repository
from app.core.dependencies import get_rules_repository
from app.core.dependencies import get_validation_artifact_repository
from app.core.dependencies import get_validation_run_plan_repository
from app.core.request_context import get_user_id
from app.core.log_event import log_event
from app.core.otel_metrics import increment_gx_failure
from app.core.otel_metrics import record_gx_operation_metric
from app.core.telemetry import set_span_attributes, traced_span
from app.domain.entities import GxExecutionRunEntity, GxRunPlanEntity, GxRunPlanVersionEntity
from app.domain.entities.gx_execution_run import build_gx_execution_diagnostic_entities
from app.domain.entities.gx_execution_run import build_gx_dispatch_payload_entity
from app.domain.entities.gx_execution_run import build_gx_execution_run_create_entity
from app.domain.entities.gx_execution_run import build_gx_grouped_execution_plan_entity
from app.domain.entities.gx_execution_run import build_gx_execution_result_item_entities
from app.domain.entities.gx_execution_run import build_gx_execution_result_summary_entity
from app.domain.entities.gx_execution_run import build_gx_structured_error_detail_entity
from app.domain.entities.gx_execution_run import GxDispatchPayloadEntity
from app.domain.entities.gx_run_plan import build_gx_run_plan_grouped_suite_snapshot_entity
from app.domain.interfaces import AppConfigRepository
from app.domain.interfaces import DataCatalogRepository
from app.domain.interfaces import ApprovalsRepository
from app.domain.interfaces import ExceptionFactRepository
from app.domain.interfaces import ExceptionReasonAnalyticsProjectionRepository
from app.domain.interfaces import GxExecutionRunRepository
from app.domain.interfaces import DqResultEventRepository
from app.domain.interfaces import GxSuiteRepository
from app.domain.interfaces import RulesRepository
from app.domain.interfaces import ValidationArtifactRepository
from app.domain.interfaces import ValidationRunPlanRepository
from dq_domain_validation import GxArtifactStatus
from dq_domain_validation import GxExecutionStatus
from dq_domain_validation import LookbackUnit
from dq_domain_validation import SourceOverrideFormat
from app.schemas.pydantic_base import SnakeModel, to_snake_alias

_log = logging.getLogger(__name__)
aioredis = gx_queue_service.aioredis
redis_sync = gx_queue_service.redis_sync

router = APIRouter(prefix="/gx", tags=["gx"])


class GxReconciliationRunCreateRequestView(SnakeModel):
    model_config = ConfigDict(alias_generator=to_snake_alias, populate_by_name=True, extra="forbid")

    workspaceId: str
    leftDatasourceId: str
    rightDatasourceId: str
    leftDatasourceName: str | None = None
    rightDatasourceName: str | None = None
    leftDatasourceType: str | None = None
    rightDatasourceType: str | None = None
    reconciliationParams: dict[str, Any] = Field(default_factory=dict)
    previewLeftRows: list[dict[str, Any]] = Field(default_factory=list)
    previewRightRows: list[dict[str, Any]] = Field(default_factory=list)
    scheduledAt: str | None = None
    requestedBy: str | None = None


_ACTIVE_RECONCILIATION_STATUSES = {"pending", "running"}


def _is_reconciliation_run(run: GxExecutionRunEntity, workspace_id: str | None = None) -> bool:
    contract = run.executionContract.model_dump(mode="python", by_alias=True, exclude_none=True) if run.executionContract else {}
    if str(contract.get("workflow_type") or "") != "reconciliation":
        return False
    if workspace_id is not None and str(contract.get("workspace_id") or "") != workspace_id:
        return False
    return True


def _reconciliation_datasource_ids(run: GxExecutionRunEntity) -> set[str]:
    contract = run.executionContract.model_dump(mode="python", by_alias=True, exclude_none=True) if run.executionContract else {}
    datasource_ids: set[str] = set()
    for key in ("left_datasource_id", "right_datasource_id", "leftDatasourceId", "rightDatasourceId"):
        value = str(contract.get(key) or "").strip()
        if value:
            datasource_ids.add(value)
    return datasource_ids


def _find_active_reconciliation_conflict(
    runs: list[GxExecutionRunEntity],
    *,
    workspace_id: str,
    left_datasource_id: str,
    right_datasource_id: str,
) -> GxExecutionRunEntity | None:
    requested_datasource_ids = {str(left_datasource_id or "").strip(), str(right_datasource_id or "").strip()}
    requested_datasource_ids.discard("")
    if not requested_datasource_ids:
        return None

    for run in runs:
        if not _is_reconciliation_run(run, workspace_id=workspace_id):
            continue
        if str(run.status or "") not in _ACTIVE_RECONCILIATION_STATUSES:
            continue
        if requested_datasource_ids.intersection(_reconciliation_datasource_ids(run)):
            return run
    return None


def _build_reconciliation_run_payload(
    body: GxReconciliationRunCreateRequestView,
    *,
    run_id: str,
    correlation_id: str,
    requested_by: str | None,
    submitted_at: str,
) -> dict[str, Any]:
    execution_contract = {
        "engine_type": "gx",
        "engine_target": "pyspark",
        "execution_shape": "join_pair",
        "workflow_type": "reconciliation",
        **body.model_dump(mode="python", by_alias=True, exclude_none=True),
    }
    return {
        "run_id": run_id,
        "suite_id": None,
        "suite_version": None,
        "rule_id": None,
        "rule_version_id": None,
        "correlation_id": correlation_id,
        "requested_by": requested_by,
        "engine_type": "gx",
        "engine_target": "pyspark",
        "execution_shape": "join_pair",
        "status": "pending",
        "submitted_at": submitted_at,
        "execution_contract": execution_contract,
        "execution_progress": {
            "percent": 0,
            "label": "Queued for reconciliation",
            "source": "reconciliation-workbench",
        },
        "status_reason": "reconciliation_run_created",
        "status_details": {
            "workflow_type": "reconciliation",
            "workspace_id": body.workspaceId,
        },
    }


_LIST_SUITE_EXAMPLE = {
    "suiteId": "gx_suite_8f40b9ea",
    "suiteVersion": 3,
    "artifactVersion": "v1",
    "assignmentScope": {
        "dataObjectId": "do_123",
        "datasetId": "ds_456",
        "dataProductId": "odcs.dp.sales-001",
    },
    "resolvedExecutionScope": {
        "dataObjectVersionIds": ["dov_123", "dov_124"],
    },
    "gxSuite": {
        "expectation_suite_name": "dq_sales_orders_v3",
        "expectations": [],
        "meta": {},
    },
    "compiledFrom": {
        "ruleIds": ["rule_1", "rule_2"],
        "compilerVersion": "dq-compiler-7.3",
        "generatedAt": "2026-03-22T10:30:00Z",
    },
    "executionHints": {
        "recommendedEngine": "pyspark",
        "primaryKeyFields": ["order_id"],
    },
}


class GxExecutionRunReportRequestView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    newStatus: GxExecutionStatus
    changedBy: str | None = None
    reason: str | None = None
    details: dict[str, Any] | None = None
    executionProgress: dict[str, Any] | None = None
    startedAt: str | None = None
    completedAt: str | None = None
    resultSummary: dict[str, Any] | None = None
    performanceSummary: dict[str, Any] | None = None
    diagnostics: list[dict[str, Any]] | None = None
    failureCode: str | None = None
    failureMessage: str | None = None


class GxAdhocSuiteRunsRequestView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    dataObjectVersionId: str | None = None
    ruleId: str | None = None
    ruleIds: list[str] = Field(default_factory=list)
    tagIds: list[str] = Field(default_factory=list)

    targetDataObjectVersionIds: list[str] = Field(default_factory=list)

    sourceOverrideUri: str | None = None
    sourceOverrideFormat: SourceOverrideFormat | None = None
    sourceOverrideOptions: dict[str, Any] | None = None

    status: GxArtifactStatus = "active"
    latestOnly: bool = True


@router.get(
    "/suites/by-rule/{rule_id}",
    response_model=list[GxArtifactEnvelopeView],
    responses={
        200: {"description": "GX suite envelopes attached to a rule."},
    },
)
async def list_gx_suites_for_rule(
    rule_id: str,
    status: GxArtifactStatus = Query(default="active"),
    latest_only: bool = Query(default=True, alias="latestOnly"),
    repository: ValidationArtifactRepository = Depends(get_validation_artifact_repository),
) -> list[GxArtifactEnvelopeView]:
    started_at = perf_counter()
    rows = await _gx_suite_api.list_suites_for_rule(
        rule_id=rule_id,
        status=status,
        latest_only=latest_only,
        repository=repository,
    )
    _record_gx_operation(
        surface="gx_api",
        operation="list_suites_for_rule",
        result="succeeded",
        started_at=started_at,
        status_code=200,
    )
    return rows


@router.post(
    "/runs/adhoc",
    response_model=list[GxSuiteRunDispatchHandoffView],
    status_code=202,
    responses={
        202: {"description": "GX suite runs accepted and enqueued for dispatch."},
        400: {"description": "Invalid request payload."},
        404: {"description": "No matching suites found."},
        422: {"description": "Request is missing required selectors."},
        503: {"description": "Dispatch queue is unavailable."},
    },
)
async def create_adhoc_gx_suite_runs(
    request: Request,
    request_body: GxAdhocSuiteRunsRequestView,
    repository: GxSuiteRepository = Depends(get_gx_suite_repository),
    rules_repository: RulesRepository = Depends(get_rules_repository),
    execution_run_repository: GxExecutionRunRepository = Depends(get_gx_execution_run_repository),
) -> list[GxSuiteRunDispatchHandoffView]:
    started_at = perf_counter()
    enqueue_suite_run = _gx_runtime_api.bind_scheduled_suite_run_enqueue(
        data_catalog_repository=get_data_catalog_repository(),
        settings_provider=get_settings,
        async_redis_module=aioredis,
        sync_redis_module=redis_sync,
        logger=_log,
    )
    accepted_views = await _gx_dispatch_api.create_adhoc_suite_runs(
        request=request,
        request_body=request_body,
        repository=repository,
        rules_repository=rules_repository,
        execution_run_repository=execution_run_repository,
        requested_by=get_user_id() or "system",
        enqueue_suite_run=enqueue_suite_run,
    )

    _record_gx_operation(
        surface="gx_api",
        operation="adhoc_runs",
        result="accepted",
        started_at=started_at,
        status_code=202,
    )

    return accepted_views


def _record_gx_operation(
    *,
    surface: str,
    operation: str,
    result: str,
    started_at: float,
    status_code: int,
    engine_target: str | None = None,
    execution_shape: str | None = None,
) -> None:
    record_gx_operation_metric(
        surface=surface,
        operation=operation,
        result=result,
        status_code=status_code,
        duration_ms=(perf_counter() - started_at) * 1000.0,
        engine_target=engine_target,
        execution_shape=execution_shape,
    )


def _normalize_gx_failure_reason(detail: Any, default: str) -> str:
    typed_detail = build_gx_structured_error_detail_entity(detail)
    if typed_detail is not None:
        candidate = str(typed_detail.reason or typed_detail.error or "").strip().lower()
        normalized = re.sub(r"[^a-z0-9]+", "_", candidate).strip("_")
        return normalized or default

    text = str(detail or "").strip().lower()
    if not text:
        return default
    if "run plan version" in text and "not found" in text:
        return "run_plan_version_not_found"
    if "run plan" in text and "not found" in text:
        return "run_plan_not_found"
    if "suite" in text and "not found" in text:
        return "suite_not_found"
    if "invalid_run_plan_transition" in text or ("transition" in text and "cannot" in text):
        return "invalid_run_plan_transition"
    if "pending" in text and "already exists" in text:
        return "approval_request_exists"
    return default


def _normalize_query_text(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _normalize_query_enum(value: object) -> GxExecutionStatus | None:
    return value if isinstance(value, str) else None


def _record_gx_failure_operation(
    *,
    operation: str,
    started_at: float,
    status_code: int,
    reason: str,
) -> None:
    increment_gx_failure(surface="gx_api", operation=operation, reason=reason)
    _record_gx_operation(
        surface="gx_api",
        operation=operation,
        result="failed",
        started_at=started_at,
        status_code=status_code,
    )


@router.post(
    "/suites",
    response_model=GxArtifactEnvelopeView,
    status_code=201,
    responses={
        201: {
            "description": "Persisted GX suite envelope.",
            "content": {
                "application/json": {
                    "example": _LIST_SUITE_EXAMPLE,
                }
            },
        },
        400: {
            "description": "Envelope validation failed.",
        },
        409: {
            "description": "Existing suite version hash mismatch; overwrite rejected.",
        },
    },
)
async def save_gx_suite(
    body: GxArtifactEnvelopeView,
    status: GxArtifactStatus = Query(default="active"),
    expected_existing_hash: str | None = Query(default=None, alias="expectedExistingHash"),
    source_pipeline: str | None = Query(default=None, alias="sourcePipeline"),
    response: Response = None,
    repository: ValidationArtifactRepository = Depends(get_validation_artifact_repository),
) -> GxArtifactEnvelopeView:
    suite_id = body.suiteId
    started_at = perf_counter()
    with traced_span(
        "gx.suite.save",
        endpoint_group="gx",
        operation="save_suite",
        suite_id=suite_id,
        suite_version=body.suiteVersion,
        suite_status=status,
        source_pipeline=source_pipeline or "manual",
    ) as span:
        log_event(
            _log, "gx.suite.save.start",
            component="gx-api",
            suiteId=suite_id,
            suiteVersion=body.suiteVersion,
            status=status,
            sourcePipeline=source_pipeline,
        )
        try:
            save_result = await _gx_suite_api.save_suite(
                body=body,
                status=status,
                expected_existing_hash=expected_existing_hash,
                source_pipeline=source_pipeline,
                repository=repository,
            )
        except HTTPException as exc:
            if exc.status_code == 400:
                set_span_attributes(span, gx_save_result="validation_error")
                increment_gx_failure(surface="gx_api", operation="save_suite", reason="validation_error")
                _record_gx_operation(
                    surface="gx_api",
                    operation="save_suite",
                    result="failed",
                    started_at=started_at,
                    status_code=400,
                )
                log_event(
                    _log, "gx.suite.save.validation_error", level="warning",
                    component="gx-api", suiteId=suite_id,
                )
            elif exc.status_code == 409:
                set_span_attributes(span, gx_save_result="hash_conflict")
                increment_gx_failure(surface="gx_api", operation="save_suite", reason="hash_conflict")
                _record_gx_operation(
                    surface="gx_api",
                    operation="save_suite",
                    result="failed",
                    started_at=started_at,
                    status_code=409,
                )
                log_event(
                    _log, "gx.suite.save.hash_conflict", level="warning",
                    component="gx-api", suiteId=suite_id, suiteVersion=body.suiteVersion,
                )
            raise

        if save_result.artifact_hash and response is not None:
            response.headers["X-Artifact-Hash"] = save_result.artifact_hash

        set_span_attributes(span, gx_save_result="saved", artifact_hash_present=bool(save_result.artifact_hash))
        log_event(
            _log, "gx.suite.save.complete",
            component="gx-api",
            suiteId=suite_id,
            suiteVersion=body.suiteVersion,
            status=status,
            artifactHash=save_result.artifact_hash,
        )
        _record_gx_operation(
            surface="gx_api",
            operation="save_suite",
            result="succeeded",
            started_at=started_at,
            status_code=201,
        )
        return save_result.saved_view


@router.patch(
    "/suites/{suite_id}/status",
    response_model=GxArtifactEnvelopeView,
    responses={
        200: {
            "description": "Status updated. Returns updated envelope.",
            "content": {
                "application/json": {
                    "example": {**_LIST_SUITE_EXAMPLE, "status": "deprecated"},
                }
            },
        },
        404: {
            "description": "Suite not found.",
        },
    },
)
async def patch_gx_suite_status(
    suite_id: str,
    status: GxArtifactStatus = Query(...),
    suite_version: int | None = Query(default=None, alias="suiteVersion", ge=1),
    reason: str | None = Query(default=None),
    repository: ValidationArtifactRepository = Depends(get_validation_artifact_repository),
) -> GxArtifactEnvelopeView:
    started_at = perf_counter()
    log_event(
        _log, "gx.suite.status.update.start",
        component="gx-api",
        suiteId=suite_id,
        suiteVersion=suite_version,
        newStatus=status,
        reason=reason,
    )
    try:
        updated = await _gx_suite_api.patch_suite_status(
            suite_id=suite_id,
            status=status,
            suite_version=suite_version,
            reason=reason,
            repository=repository,
        )
    except HTTPException as exc:
        if exc.status_code == 404:
            log_event(
                _log, "gx.suite.status.update.not_found", level="warning",
                component="gx-api", suiteId=suite_id, suiteVersion=suite_version,
            )
            increment_gx_failure(surface="gx_api", operation="update_suite_status", reason="suite_not_found")
            _record_gx_operation(
                surface="gx_api",
                operation="update_suite_status",
                result="failed",
                started_at=started_at,
                status_code=404,
            )
        raise

    log_event(
        _log, "gx.suite.status.update.complete",
        component="gx-api",
        suiteId=suite_id,
        suiteVersion=suite_version,
        newStatus=status,
    )
    _record_gx_operation(
        surface="gx_api",
        operation="update_suite_status",
        result="succeeded",
        started_at=started_at,
        status_code=200,
    )
    return updated


@router.get(
    "/suites",
    response_model=list[GxArtifactEnvelopeView],
    responses={
        200: {
            "description": "GX suite envelopes retrieved by the requested scope.",
            "content": {
                "application/json": {
                    "examples": {
                        "byDataObject": {
                            "summary": "Retrieval by dataObjectId",
                            "value": [_LIST_SUITE_EXAMPLE],
                        },
                        "byDataObjectVersion": {
                            "summary": "Retrieval by dataObjectVersionId",
                            "value": [
                                {
                                    **_LIST_SUITE_EXAMPLE,
                                    "resolvedExecutionScope": {"dataObjectVersionIds": ["dov_999"]},
                                }
                            ],
                        },
                        "byDataset": {
                            "summary": "Retrieval by datasetId",
                            "value": [
                                {
                                    **_LIST_SUITE_EXAMPLE,
                                    "assignmentScope": {
                                        "dataObjectId": None,
                                        "datasetId": "ds_456",
                                        "dataProductId": "odcs.dp.sales-001",
                                    },
                                }
                            ],
                        },
                        "byDataProduct": {
                            "summary": "Retrieval by ODCS dataProductId",
                            "value": [
                                {
                                    **_LIST_SUITE_EXAMPLE,
                                    "assignmentScope": {
                                        "dataObjectId": None,
                                        "datasetId": None,
                                        "dataProductId": "odcs.dp.sales-001",
                                    },
                                }
                            ],
                        },
                    }
                }
            },
        },
        400: {
            "description": "None or multiple primary scopes were provided, or values are malformed.",
        },
    },
)
async def list_gx_suites(
    data_object_id: str | None = Query(default=None, alias="dataObjectId"),
    data_object_version_id: str | None = Query(default=None, alias="dataObjectVersionId"),
    dataset_id: str | None = Query(default=None, alias="datasetId"),
    data_product_id: str | None = Query(default=None, alias="dataProductId"),
    status: GxArtifactStatus = Query(default="active"),
    latest_only: bool = Query(default=True, alias="latestOnly"),
    repository: ValidationArtifactRepository = Depends(get_validation_artifact_repository),
) -> list[GxArtifactEnvelopeView]:
    started_at = perf_counter()
    try:
        list_result = await _gx_suite_api.list_suites(
            data_object_id=data_object_id,
            data_object_version_id=data_object_version_id,
            dataset_id=dataset_id,
            data_product_id=data_product_id,
            status=status,
            latest_only=latest_only,
            repository=repository,
        )
    except HTTPException as exc:
        increment_gx_failure(surface="gx_api", operation="list_suites", reason="invalid_query")
        _record_gx_operation(
            surface="gx_api",
            operation="list_suites",
            result="failed",
            started_at=started_at,
            status_code=400,
        )
        raise exc

    log_event(
        _log, "gx.suite.list.start",
        component="gx-api",
        dataObjectId=list_result.query.dataObjectId,
        dataObjectVersionId=list_result.query.dataObjectVersionId,
        datasetId=list_result.query.datasetId,
        dataProductId=list_result.query.dataProductId,
        status=list_result.query.status,
        latestOnly=list_result.query.latestOnly,
    )
    log_event(
        _log, "gx.suite.list.complete",
        component="gx-api",
        resultCount=len(list_result.suites),
        status=list_result.query.status,
    )
    _record_gx_operation(
        surface="gx_api",
        operation="list_suites",
        result="succeeded",
        started_at=started_at,
        status_code=200,
    )
    return list_result.suites


@router.get(
    "/suites/{suite_id}",
    response_model=GxArtifactEnvelopeView,
    responses={
        200: {
            "description": "Direct suite fetch by suiteId and optional suiteVersion.",
            "content": {
                "application/json": {
                    "example": _LIST_SUITE_EXAMPLE,
                }
            },
        },
        404: {
            "description": "Requested suite ID or version was not found.",
        },
    },
)
async def get_gx_suite(
    suite_id: str,
    suite_version: int | None = Query(default=None, alias="suiteVersion", ge=1),
    status: GxArtifactStatus = Query(default="active"),
    repository: ValidationArtifactRepository = Depends(get_validation_artifact_repository),
) -> GxArtifactEnvelopeView:
    started_at = perf_counter()
    try:
        get_result = await _gx_suite_api.get_suite(
            suite_id=suite_id,
            suite_version=suite_version,
            status=status,
            repository=repository,
        )
    except HTTPException as exc:
        if exc.status_code == 404:
            log_event(
                _log, "gx.suite.fetch.not_found", level="warning",
                component="gx-api", suiteId=suite_id, suiteVersion=suite_version,
            )
            increment_gx_failure(surface="gx_api", operation="fetch_suite", reason="suite_not_found")
            _record_gx_operation(
                surface="gx_api",
                operation="fetch_suite",
                result="failed",
                started_at=started_at,
                status_code=404,
            )
        elif exc.status_code == 400:
            increment_gx_failure(surface="gx_api", operation="fetch_suite", reason="invalid_query")
            _record_gx_operation(
                surface="gx_api",
                operation="fetch_suite",
                result="failed",
                started_at=started_at,
                status_code=400,
            )
        raise exc

    log_event(
        _log, "gx.suite.fetch.start",
        component="gx-api",
        suiteId=suite_id,
        suiteVersion=get_result.query.suiteVersion,
        status=status,
    )
    log_event(
        _log, "gx.suite.fetch.complete",
        component="gx-api",
        suiteId=suite_id,
        suiteVersion=get_result.query.suiteVersion,
    )
    _record_gx_operation(
        surface="gx_api",
        operation="fetch_suite",
        result="succeeded",
        started_at=started_at,
        status_code=200,
    )
    return get_result.suite


@router.post(
    "/suites/{suite_id}/runs/start",
    response_model=GxSuiteRunHandoffView,
    status_code=202,
    responses={
        202: {
            "description": "GX suite run accepted and handed off for execution.",
        },
        422: {
            "description": "Suite payload is not runnable.",
        },
        404: {
            "description": "Suite not found.",
        },
    },
)
async def start_gx_suite_run(
    request: Request,
    suite_id: str,
    suite_version: int | None = Query(default=None, alias="suiteVersion", ge=1),
    status: GxArtifactStatus = Query(default="active"),
    repository: GxSuiteRepository = Depends(get_gx_suite_repository),
    execution_run_repository: GxExecutionRunRepository = Depends(get_gx_execution_run_repository),
) -> GxSuiteRunHandoffView:
    started_at = perf_counter()
    with traced_span(
        "gx.suite.run.start",
        endpoint_group="gx",
        operation="start_suite_run",
        suite_id=suite_id,
        suite_version=suite_version,
        status=status,
    ) as span:
        log_event(
            _log,
            "gx.suite.run.start",
            component="gx-api",
            suiteId=suite_id,
            suiteVersion=suite_version,
            status=status,
        )
        requested_by = get_user_id() or "system"

        try:
            start_result = await _gx_start_api.start_suite_run(
                request=request,
                suite_id=suite_id,
                suite_version=suite_version,
                status=status,
                repository=repository,
                execution_run_repository=execution_run_repository,
                data_catalog_repository=get_data_catalog_repository(),
                requested_by=requested_by,
            )
        except HTTPException as exc:
            detail_payload = exc.detail if isinstance(exc.detail, dict) else None
            if exc.status_code == 404:
                log_event(
                    _log,
                    "gx.suite.run.not_found",
                    level="warning",
                    component="gx-api",
                    suiteId=suite_id,
                    suiteVersion=suite_version,
                )
                increment_gx_failure(surface="gx_api", operation="start_suite_run", reason="suite_not_found")
                _record_gx_operation(
                    surface="gx_api",
                    operation="start_suite_run",
                    result="failed",
                    started_at=started_at,
                    status_code=404,
                    execution_shape="unknown",
                )
            elif exc.status_code == 503 and (detail_payload or {}).get("error") == "execution_run_persistence_failed":
                log_event(
                    _log,
                    "gx.suite.run.persistence_failed",
                    level="error",
                    component="gx-api",
                    suiteId=suite_id,
                    suiteVersion=suite_version,
                    correlationId=(detail_payload or {}).get("correlation_id"),
                    runId=(detail_payload or {}).get("run_id"),
                    exceptionType=(detail_payload or {}).get("exception"),
                )
                increment_gx_failure(surface="gx_api", operation="start_suite_run", reason="execution_run_persistence_failed")
                _record_gx_operation(
                    surface="gx_api",
                    operation="start_suite_run",
                    result="failed",
                    started_at=started_at,
                    status_code=503,
                    engine_target=getattr(exc, "engine_target", None),
                    execution_shape=getattr(exc, "execution_shape", None),
                )
            raise

        set_span_attributes(
            span,
            gx_run_result="accepted",
            suite_run_id=start_result.run_id,
            correlation_id=start_result.correlation_id,
            execution_shape=start_result.execution_shape,
            run_persisted=True,
        )
        log_event(
            _log,
            "gx.suite.run.start.complete",
            component="gx-api",
            suiteId=suite_id,
            suiteVersion=suite_version,
            runId=start_result.run_id,
            correlationId=start_result.correlation_id,
        )
        _record_gx_operation(
            surface="gx_api",
            operation="start_suite_run",
            result="accepted",
            started_at=started_at,
            status_code=202,
            engine_target=start_result.engine_target,
            execution_shape=start_result.execution_shape,
        )
        return start_result.handoff_view


@router.post(
    "/suites/{suite_id}/runs/schedule",
    response_model=GxSuiteRunDispatchHandoffView,
    status_code=202,
    responses={
        202: {
            "description": "GX suite run accepted and enqueued for scheduled dispatch.",
        },
        422: {
            "description": "Suite payload is not runnable.",
        },
        404: {
            "description": "Suite not found.",
        },
        503: {
            "description": "Dispatch queue is unavailable.",
        },
    },
)
async def schedule_gx_suite_run(
    request: Request,
    suite_id: str,
    request_body: GxSuiteRunScheduleRequestView,
    suite_version: int | None = Query(default=None, alias="suiteVersion", ge=1),
    status: GxArtifactStatus = Query(default="active"),
    repository: GxSuiteRepository = Depends(get_gx_suite_repository),
    execution_run_repository: GxExecutionRunRepository = Depends(get_gx_execution_run_repository),
) -> GxSuiteRunDispatchHandoffView:
    started_at = perf_counter()
    enqueue_suite_run = _gx_runtime_api.bind_scheduled_suite_run_enqueue(
        data_catalog_repository=get_data_catalog_repository(),
        settings_provider=get_settings,
        async_redis_module=aioredis,
        sync_redis_module=redis_sync,
        logger=_log,
    )
    with traced_span(
        "gx.suite.run.schedule",
        endpoint_group="gx",
        operation="schedule_suite_run",
        suite_id=suite_id,
        suite_version=suite_version,
        status=status,
        scheduled_at=request_body.scheduledAt.isoformat(),
    ) as span:
        log_event(
            _log,
            "gx.suite.run.schedule.start",
            component="gx-api",
            suiteId=suite_id,
            suiteVersion=suite_version,
            status=status,
            scheduledAt=request_body.scheduledAt.isoformat(),
        )
        try:
            schedule_result = await _gx_dispatch_api.schedule_suite_run(
                request=request,
                suite_id=suite_id,
                suite_version=suite_version,
                status=status,
                request_body=request_body,
                repository=repository,
                execution_run_repository=execution_run_repository,
                requested_by=get_user_id() or "system",
                enqueue_suite_run=enqueue_suite_run,
            )
        except HTTPException as exc:
            suite = getattr(exc, "suite", None)
            if exc.status_code == 404:
                log_event(
                    _log,
                    "gx.suite.run.not_found",
                    level="warning",
                    component="gx-api",
                    suiteId=suite_id,
                    suiteVersion=suite_version,
                )

            detail = build_gx_structured_error_detail_entity(exc.detail)
            error_code = detail.error if detail is not None else "schedule_suite_run_failed"
            correlation_id = detail.correlationId if detail is not None else None
            queue_message_id = detail.queueMessageId if detail is not None else None
            log_event(
                _log,
                "gx.suite.run.schedule.failed",
                level="error",
                component="gx-api",
                suiteId=suite_id,
                suiteVersion=suite_version,
                correlationId=correlation_id,
                queueMessageId=queue_message_id,
                error=error_code,
            )
            increment_gx_failure(surface="gx_api", operation="schedule_suite_run", reason=str(error_code))
            _record_gx_operation(
                surface="gx_api",
                operation="schedule_suite_run",
                result="failed",
                started_at=started_at,
                status_code=exc.status_code,
                engine_target=suite.executionContract.engineTarget if suite is not None and suite.executionContract is not None else None,
                execution_shape=suite.executionContract.executionShape if suite is not None and suite.executionContract is not None else None,
            )
            raise

        dispatch_view = schedule_result.dispatch_view
        correlation_id = str(dispatch_view.correlationId or "")

        set_span_attributes(
            span,
            gx_run_result="scheduled",
            suite_run_id=dispatch_view.queueMessageId,
            correlation_id=correlation_id,
            execution_shape=dispatch_view.executionShape,
            dispatch_mode=dispatch_view.dispatchMode,
            queue_key=dispatch_view.queueKey,
            queue_message_id=dispatch_view.queueMessageId,
        )
        log_event(
            _log,
            "gx.suite.run.schedule.complete",
            component="gx-api",
            suiteId=suite_id,
            suiteVersion=suite_version,
            queueMessageId=dispatch_view.queueMessageId,
            queueKey=dispatch_view.queueKey,
            correlationId=correlation_id,
        )
        _record_gx_operation(
            surface="gx_api",
            operation="schedule_suite_run",
            result="accepted",
            started_at=started_at,
            status_code=202,
            engine_target=dispatch_view.engineTarget,
            execution_shape=dispatch_view.executionShape,
        )
        return dispatch_view


@router.post(
    "/run-plans/initiate",
    response_model=GxRunPlanView,
    status_code=201,
    responses={
        201: {"description": "Draft DQ run plan initiated."},
        404: {"description": "Suite not found."},
        422: {"description": "Suite is not runnable."},
    },
)
async def initiate_gx_run_plan(
    request_body: GxRunPlanCreateRequestView,
    request: Request = None,
    artifact_repository: ValidationArtifactRepository = Depends(get_validation_artifact_repository),
    run_plan_repository: ValidationRunPlanRepository = Depends(get_validation_run_plan_repository),
    grouped_execution_planner: GroupedExecutionPlanner = Depends(get_grouped_execution_planner),
) -> GxRunPlanView:
    started_at = perf_counter()
    try:
        row = await _gx_run_plan_api.create_run_plan(
            request_body=request_body,
            request=request,
            created_by=get_user_id() or "system",
            artifact_repository=artifact_repository,
            run_plan_repository=run_plan_repository,
            grouped_execution_planner=grouped_execution_planner,
        )
    except HTTPException as exc:
        _record_gx_failure_operation(
            operation="initiate_run_plan",
            started_at=started_at,
            status_code=exc.status_code,
            reason=_normalize_gx_failure_reason(exc.detail, "initiate_run_plan_failed"),
        )
        raise

    _record_gx_operation(
        surface="gx_api",
        operation="initiate_run_plan",
        result="succeeded",
        started_at=started_at,
        status_code=201,
    )
    return to_gx_run_plan_view(row)


@router.post(
    "/run-plans",
    response_model=GxRunPlanView,
    status_code=201,
    responses={
        201: {"description": "Draft GX run plan created."},
        404: {"description": "Suite not found."},
        422: {"description": "Suite is not runnable."},
    },
)
async def create_gx_run_plan(
    request_body: GxRunPlanCreateRequestView,
    request: Request = None,
    artifact_repository: ValidationArtifactRepository = Depends(get_validation_artifact_repository),
    rules_repository: RulesRepository = Depends(get_rules_repository),
    run_plan_repository: ValidationRunPlanRepository = Depends(get_validation_run_plan_repository),
    grouped_execution_planner: GroupedExecutionPlanner = Depends(get_grouped_execution_planner),
) -> GxRunPlanView:
    started_at = perf_counter()
    try:
        row = await _gx_run_plan_api.create_run_plan(
            request_body=request_body,
            request=request,
            created_by=get_user_id() or "system",
            artifact_repository=artifact_repository,
            rules_repository=rules_repository,
            run_plan_repository=run_plan_repository,
            grouped_execution_planner=grouped_execution_planner,
        )
    except HTTPException as exc:
        _record_gx_failure_operation(
            operation="create_run_plan",
            started_at=started_at,
            status_code=exc.status_code,
            reason=_normalize_gx_failure_reason(exc.detail, "create_run_plan_failed"),
        )
        raise

    _record_gx_operation(
        surface="gx_api",
        operation="create_run_plan",
        result="succeeded",
        started_at=started_at,
        status_code=201,
    )
    return to_gx_run_plan_view(row)


@router.get(
    "/run-plans/{run_plan_id}",
    response_model=GxRunPlanView,
    responses={200: {"description": "GX run plan detail."}, 404: {"description": "Run plan not found."}},
)
async def get_gx_run_plan(
    run_plan_id: str,
    repository: ValidationRunPlanRepository = Depends(get_validation_run_plan_repository),
) -> GxRunPlanView:
    started_at = perf_counter()
    try:
        run_plan_view = await _gx_run_plan_api.get_run_plan(run_plan_id=run_plan_id, repository=repository)
    except HTTPException as exc:
        _record_gx_failure_operation(
            operation="get_run_plan",
            started_at=started_at,
            status_code=exc.status_code,
            reason=_normalize_gx_failure_reason(exc.detail, "run_plan_not_found"),
        )
        raise
    _record_gx_operation(
        surface="gx_api",
        operation="get_run_plan",
        result="succeeded",
        started_at=started_at,
        status_code=200,
    )
    return run_plan_view


@router.post(
    "/run-plans/{run_plan_id}/versions",
    response_model=GxRunPlanView,
    status_code=201,
    responses={
        201: {"description": "Draft run plan version created."},
        404: {"description": "Run plan or suite not found."},
        409: {"description": "Run plan is not editable."},
        422: {"description": "Suite is not runnable."},
    },
)
async def create_gx_run_plan_version(
    run_plan_id: str,
    request_body: GxRunPlanVersionCreateRequestView,
    request: Request = None,
    artifact_repository: ValidationArtifactRepository = Depends(get_validation_artifact_repository),
    rules_repository: RulesRepository = Depends(get_rules_repository),
    run_plan_repository: ValidationRunPlanRepository = Depends(get_validation_run_plan_repository),
    grouped_execution_planner: GroupedExecutionPlanner = Depends(get_grouped_execution_planner),
) -> GxRunPlanView:
    started_at = perf_counter()
    try:
        row = await _gx_run_plan_api.create_run_plan_version(
            run_plan_id=run_plan_id,
            request_body=request_body,
            request=request,
            created_by=get_user_id() or "system",
            artifact_repository=artifact_repository,
            rules_repository=rules_repository,
            run_plan_repository=run_plan_repository,
            grouped_execution_planner=grouped_execution_planner,
        )
    except HTTPException as exc:
        _record_gx_failure_operation(
            operation="create_run_plan_version",
            started_at=started_at,
            status_code=exc.status_code,
            reason=_normalize_gx_failure_reason(exc.detail, "create_run_plan_version_failed"),
        )
        raise

    _record_gx_operation(
        surface="gx_api",
        operation="create_run_plan_version",
        result="succeeded",
        started_at=started_at,
        status_code=201,
    )
    return to_gx_run_plan_view(row)


@router.post(
    "/run-plans/{run_plan_id}/versions/{run_plan_version_id}/governance-state",
    response_model=GxRunPlanView,
    responses={
        200: {"description": "Run plan governance state updated."},
        404: {"description": "Run plan or version not found."},
        409: {"description": "Requested transition is invalid."},
    },
)
async def transition_gx_run_plan_version_governance_state(
    run_plan_id: str,
    run_plan_version_id: str,
    request_body: GxRunPlanGovernanceTransitionRequestView,
    request: Request = None,
    approvals_repository: ApprovalsRepository = Depends(get_approvals_repository),
    run_plan_repository: ValidationRunPlanRepository = Depends(get_validation_run_plan_repository),
) -> GxRunPlanView:
    started_at = perf_counter()
    try:
        row = await _gx_run_plan_api.transition_run_plan_version(
            run_plan_id=run_plan_id,
            run_plan_version_id=run_plan_version_id,
            request_body=request_body,
            request=request,
            updated_by=get_user_id() or "system",
            approvals_repository=approvals_repository,
            run_plan_repository=run_plan_repository,
        )
    except HTTPException as exc:
        _record_gx_failure_operation(
            operation="transition_run_plan_version",
            started_at=started_at,
            status_code=exc.status_code,
            reason=_normalize_gx_failure_reason(exc.detail, "transition_run_plan_version_failed"),
        )
        raise

    _record_gx_operation(
        surface="gx_api",
        operation="transition_run_plan_version",
        result="succeeded",
        started_at=started_at,
        status_code=200,
    )
    return to_gx_run_plan_view(row)

@router.post(
    "/run-plans/{run_plan_id}/versions/{run_plan_version_id}/validate",
    response_model=GxRunPlanValidationView,
    responses={
        200: {"description": "Run plan version validated and status updated."},
        404: {"description": "Run plan or version not found."},
        409: {"description": "Run plan version cannot be validated from the current state."},
    },
)
async def validate_gx_run_plan_version(
    request: Request,
    run_plan_id: str,
    run_plan_version_id: str,
    run_plan_repository: ValidationRunPlanRepository = Depends(get_validation_run_plan_repository),
) -> GxRunPlanValidationView:
    started_at = perf_counter()
    try:
        result = await _gx_run_plan_api.validate_run_plan_version(
            request=request,
            run_plan_id=run_plan_id,
            run_plan_version_id=run_plan_version_id,
            updated_by=get_user_id() or "system",
            run_plan_repository=run_plan_repository,
        )
    except HTTPException as exc:
        _record_gx_failure_operation(
            operation="validate_run_plan_version",
            started_at=started_at,
            status_code=exc.status_code,
            reason=_normalize_gx_failure_reason(exc.detail, "validate_run_plan_version_failed"),
        )
        raise

    _record_gx_operation(
        surface="gx_api",
        operation="validate_run_plan_version",
        result="succeeded",
        started_at=started_at,
        status_code=200,
    )
    return to_gx_run_plan_validation_view(result)


@router.post(
    "/assistance-requests",
    response_model=GxAssistanceRequestResponseView,
    responses={
        200: {"description": "Assistance request routed successfully."},
        400: {"description": "Assistance routing is misconfigured."},
        502: {"description": "Configured ITSM endpoint rejected the request."},
        503: {"description": "Configured ITSM endpoint is unavailable."},
    },
)
async def create_gx_assistance_request(
    request_view: GxAssistanceRequestView,
    request: Request,
    app_config_repository: AppConfigRepository = Depends(get_app_config_repository),
) -> GxAssistanceRequestResponseView:
    started_at = perf_counter()
    try:
        response_view = await _gx_assistance_api.create_assistance_request(
            request_view=request_view,
            request=request,
            app_config_repository=app_config_repository,
        )
    except HTTPException as exc:
        increment_gx_failure(
            surface="gx_api",
            operation="request_assistance",
            reason=_normalize_gx_failure_reason(exc.detail, "request_assistance_failed"),
        )
        _record_gx_operation(
            surface="gx_api",
            operation="request_assistance",
            result="failed",
            started_at=started_at,
            status_code=exc.status_code,
        )
        raise

    _record_gx_operation(
        surface="gx_api",
        operation="request_assistance",
        result="succeeded",
        started_at=started_at,
        status_code=200,
    )
    return response_view


@router.get(
    "/run-plans",
    response_model=list[GxRunPlanView],
    responses={200: {"description": "GX run plans."}},
)
async def list_gx_run_plans(
    workspace_id: str | None = Query(default=None, alias="workspaceId"),
    business_key: str | None = Query(default=None, alias="businessKey"),
    suite_id: str | None = Query(default=None, alias="suiteId"),
    status: str | None = Query(default=None),
    repository: ValidationRunPlanRepository = Depends(get_validation_run_plan_repository),
) -> list[GxRunPlanView]:
    started_at = perf_counter()
    run_plan_views = await _gx_run_plan_api.list_run_plans(
        workspace_id=workspace_id,
        business_key=business_key,
        suite_id=suite_id,
        status=status,
        repository=repository,
    )
    _record_gx_operation(
        surface="gx_api",
        operation="list_run_plans",
        result="succeeded",
        started_at=started_at,
        status_code=200,
    )
    return run_plan_views


@router.post(
    "/run-plans/{run_plan_id}/versions/{run_plan_version_id}/activate",
    response_model=GxRunPlanActivationView,
    status_code=202,
    responses={
        202: {"description": "Run plan activated and scheduled dispatch accepted."},
        404: {"description": "Run plan or version not found."},
        409: {"description": "Run plan is not in draft state."},
        503: {"description": "Scheduler/worker dependencies are unavailable."},
    },
)
async def activate_gx_run_plan_version(
    request: Request,
    run_plan_id: str,
    run_plan_version_id: str,
    run_plan_repository: ValidationRunPlanRepository = Depends(get_validation_run_plan_repository),
    execution_run_repository: GxExecutionRunRepository = Depends(get_gx_execution_run_repository),
) -> GxRunPlanActivationView:
    started_at = perf_counter()
    enqueue_grouped_scope_run = _gx_runtime_api.bind_grouped_scope_run_enqueue(
        settings_provider=get_settings,
        async_redis_module=aioredis,
        sync_redis_module=redis_sync,
        logger=_log,
    )
    enqueue_scheduled_suite_run = _gx_runtime_api.bind_scheduled_suite_run_enqueue(
        data_catalog_repository=get_data_catalog_repository(),
        settings_provider=get_settings,
        async_redis_module=aioredis,
        sync_redis_module=redis_sync,
        logger=_log,
    )
    try:
        result = await _gx_run_plan_api.activate_run_plan_version(
            request=request,
            run_plan_id=run_plan_id,
            run_plan_version_id=run_plan_version_id,
            activated_by=get_user_id() or "system",
            run_plan_repository=run_plan_repository,
            execution_run_repository=execution_run_repository,
            enqueue_grouped_scope_run=enqueue_grouped_scope_run,
            enqueue_scheduled_suite_run=enqueue_scheduled_suite_run,
        )
    except HTTPException as exc:
        _record_gx_failure_operation(
            operation="activate_run_plan",
            started_at=started_at,
            status_code=exc.status_code,
            reason=_normalize_gx_failure_reason(exc.detail, "activate_run_plan_failed"),
        )
        raise

    _record_gx_operation(
        surface="gx_api",
        operation="activate_run_plan",
        result="accepted",
        started_at=started_at,
        status_code=202,
    )
    return to_gx_run_plan_activation_view(result)


@router.get(
    "/runs",
    response_model=list[GxExecutionRunSummaryView],
    responses={
        200: {
            "description": "Recent GX execution runs with browse-friendly summary fields.",
        },
    },
)
async def list_gx_execution_runs(
    lookback_amount: int = Query(default=24, ge=1, le=720, alias="lookbackAmount"),
    lookback_unit: LookbackUnit = Query(default="hours", alias="lookbackUnit"),
    status: GxExecutionStatus | None = Query(default=None),
    rule_name: str | None = Query(default=None, alias="ruleName"),
    owner: str | None = Query(default=None),
    domain: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    data_object_name: str | None = Query(default=None, alias="dataObjectName"),
    search: str | None = Query(default=None),
    limit: int = Query(default=25, ge=1, le=100),
    data_product_id: str | None = Query(default=None, alias="dataProductId"),
    dataset_id: str | None = Query(default=None, alias="datasetId"),
    data_object_id: str | None = Query(default=None, alias="dataObjectId"),
    data_object_version_id: str | None = Query(default=None, alias="dataObjectVersionId"),
    delivery_id: str | None = Query(default=None, alias="deliveryId"),
    workspace_id: str | None = Query(default=None, alias="workspaceId"),
    run_plan_id: str | None = Query(default=None, alias="runPlanId"),
    repository: GxExecutionRunRepository = Depends(get_gx_execution_run_repository),
    run_plan_repository: ValidationRunPlanRepository = Depends(get_validation_run_plan_repository),
    rules_repository: RulesRepository = Depends(get_rules_repository),
    data_catalog_repository: DataCatalogRepository = Depends(get_data_catalog_repository),
    suite_repository: GxSuiteRepository = Depends(get_gx_suite_repository),
) -> list[GxExecutionRunSummaryView]:
    started_at = perf_counter()
    summaries = await _gx_browse_api.list_execution_runs(
        lookback_amount=lookback_amount,
        lookback_unit=lookback_unit,
        status=_normalize_query_enum(status),
        rule_name=_normalize_query_text(rule_name),
        owner=_normalize_query_text(owner),
        domain=_normalize_query_text(domain),
        severity=_normalize_query_text(severity),
        data_object_name=_normalize_query_text(data_object_name),
        search=_normalize_query_text(search),
        limit=limit,
        data_product_id=_normalize_query_text(data_product_id),
        dataset_id=_normalize_query_text(dataset_id),
        data_object_id=_normalize_query_text(data_object_id),
        data_object_version_id=_normalize_query_text(data_object_version_id),
        delivery_id=_normalize_query_text(delivery_id),
        workspace_id=_normalize_query_text(workspace_id),
        run_plan_id=_normalize_query_text(run_plan_id),
        repository=repository,
        run_plan_repository=run_plan_repository,
        rules_repository=rules_repository,
        data_catalog_repository=data_catalog_repository,
        suite_repository=suite_repository,
    )

    _record_gx_operation(
        surface="gx_api",
        operation="list_runs",
        result="succeeded",
        started_at=started_at,
        status_code=200,
    )
    return summaries


@router.get(
    "/runs/stats",
    response_model=GxExecutionRunStatisticsView,
    responses={
        200: {
            "description": "Execution run statistics for Grafana dashboards.",
        },
        503: {
            "description": "Execution run statistics are unavailable.",
        },
    },
)
async def get_gx_execution_run_statistics(
    request: Request,
    lookback_amount: int = Query(default=24, ge=1, le=720, alias="lookbackAmount"),
    lookback_unit: LookbackUnit = Query(default="hours", alias="lookbackUnit"),
    recent_limit: int = Query(default=10, ge=1, le=50, alias="recentLimit"),
    status: GxExecutionStatus | None = Query(default=None),
    rule_name: str | None = Query(default=None, alias="ruleName"),
    owner: str | None = Query(default=None),
    domain: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    data_object_name: str | None = Query(default=None, alias="dataObjectName"),
    search: str | None = Query(default=None),
    data_product_id: str | None = Query(default=None, alias="dataProductId"),
    dataset_id: str | None = Query(default=None, alias="datasetId"),
    data_object_id: str | None = Query(default=None, alias="dataObjectId"),
    data_object_version_id: str | None = Query(default=None, alias="dataObjectVersionId"),
    delivery_id: str | None = Query(default=None, alias="deliveryId"),
    workspace_id: str | None = Query(default=None, alias="workspaceId"),
    run_plan_id: str | None = Query(default=None, alias="runPlanId"),
    repository: GxExecutionRunRepository = Depends(get_gx_execution_run_repository),
    run_plan_repository: ValidationRunPlanRepository = Depends(get_validation_run_plan_repository),
    rules_repository: RulesRepository = Depends(get_rules_repository),
    data_catalog_repository: DataCatalogRepository = Depends(get_data_catalog_repository),
    suite_repository: GxSuiteRepository = Depends(get_gx_suite_repository),
) -> GxExecutionRunStatisticsView:
    correlation_id = request.headers.get("X-Correlation-ID") or f"corr-{uuid4().hex[:12]}"
    return await _gx_browse_api.list_execution_run_statistics(
        correlation_id=correlation_id,
        lookback_amount=lookback_amount,
        lookback_unit=lookback_unit,
        recent_limit=recent_limit,
        status=_normalize_query_enum(status),
        rule_name=_normalize_query_text(rule_name),
        owner=_normalize_query_text(owner),
        domain=_normalize_query_text(domain),
        severity=_normalize_query_text(severity),
        data_object_name=_normalize_query_text(data_object_name),
        search=_normalize_query_text(search),
        data_product_id=_normalize_query_text(data_product_id),
        dataset_id=_normalize_query_text(dataset_id),
        data_object_id=_normalize_query_text(data_object_id),
        data_object_version_id=_normalize_query_text(data_object_version_id),
        delivery_id=_normalize_query_text(delivery_id),
        workspace_id=_normalize_query_text(workspace_id),
        run_plan_id=_normalize_query_text(run_plan_id),
        repository=repository,
        run_plan_repository=run_plan_repository,
        rules_repository=rules_repository,
        data_catalog_repository=data_catalog_repository,
        suite_repository=suite_repository,
    )


@router.get(
    "/exception-analytics",
    response_model=ExceptionAnalyticsView,
    responses={
        200: {
            "description": "Exception-store-backed GX failure analytics for the current monitoring window.",
        },
        503: {
            "description": "Exception analytics are unavailable.",
        },
    },
)
async def get_gx_execution_exception_analytics(
    request: Request,
    lookback_amount: int = Query(default=24, ge=1, le=720, alias="lookbackAmount"),
    lookback_unit: LookbackUnit = Query(default="hours", alias="lookbackUnit"),
    status: GxExecutionStatus | None = Query(default=None),
    rule_name: str | None = Query(default=None, alias="ruleName"),
    data_object_name: str | None = Query(default=None, alias="dataObjectName"),
    search: str | None = Query(default=None),
    reason_code: str | None = Query(default=None, alias="reasonCode"),
    suite_id: str | None = Query(default=None, alias="suiteId"),
    data_product_id: str | None = Query(default=None, alias="dataProductId"),
    dataset_id: str | None = Query(default=None, alias="datasetId"),
    data_object_id: str | None = Query(default=None, alias="dataObjectId"),
    data_object_version_id: str | None = Query(default=None, alias="dataObjectVersionId"),
    delivery_id: str | None = Query(default=None, alias="deliveryId"),
    rule_version_id: str | None = Query(default=None, alias="ruleVersionId"),
    workspace_id: str | None = Query(default=None, alias="workspaceId"),
    repository: GxExecutionRunRepository = Depends(get_gx_execution_run_repository),
    run_plan_repository: ValidationRunPlanRepository = Depends(get_validation_run_plan_repository),
    projection_repository: ExceptionReasonAnalyticsProjectionRepository = Depends(get_exception_reason_analytics_projection_repository),
    rules_repository: RulesRepository = Depends(get_rules_repository),
    data_catalog_repository: DataCatalogRepository = Depends(get_data_catalog_repository),
    suite_repository: GxSuiteRepository = Depends(get_gx_suite_repository),
) -> ExceptionAnalyticsView:
    started_at = perf_counter()
    correlation_id = request.headers.get("X-Correlation-ID") or f"corr-{uuid4().hex[:12]}"

    try:
        analytics = await _gx_browse_api.get_exception_analytics(
            correlation_id=correlation_id,
            lookback_amount=lookback_amount,
            lookback_unit=lookback_unit,
            status=_normalize_query_enum(status),
            rule_name=_normalize_query_text(rule_name),
            data_object_name=_normalize_query_text(data_object_name),
            search=_normalize_query_text(search),
            reason_code=_normalize_query_text(reason_code),
            suite_id=_normalize_query_text(suite_id),
            data_product_id=_normalize_query_text(data_product_id),
            dataset_id=_normalize_query_text(dataset_id),
            data_object_id=_normalize_query_text(data_object_id),
            data_object_version_id=_normalize_query_text(data_object_version_id),
            delivery_id=_normalize_query_text(delivery_id),
            rule_version_id=_normalize_query_text(rule_version_id),
            workspace_id=_normalize_query_text(workspace_id),
            repository=repository,
            run_plan_repository=run_plan_repository,
            projection_repository=projection_repository,
            rules_repository=rules_repository,
            data_catalog_repository=data_catalog_repository,
            suite_repository=suite_repository,
        )
    except HTTPException as exc:
        _record_gx_failure_operation(
            operation="fetch_exception_analytics",
            started_at=started_at,
            status_code=exc.status_code,
            reason=_normalize_gx_failure_reason(exc.detail, "exception_analytics_unavailable"),
        )
        raise

    _record_gx_operation(
        surface="gx_api",
        operation="fetch_exception_analytics",
        result="succeeded",
        started_at=started_at,
        status_code=200,
    )
    return analytics


@router.get(
    "/result-history/drift",
    response_model=DqResultDriftSummaryView,
    responses={
        200: {"description": "DQ result drift detections for the selected result-history scope."},
        503: {"description": "DQ result drift detection is unavailable."},
    },
)
async def get_gx_result_history_drift_summary(
    request: Request,
    lookback_amount: int = Query(default=24, ge=1, le=720, alias="lookbackAmount"),
    lookback_unit: LookbackUnit = Query(default="hours", alias="lookbackUnit"),
    status: GxExecutionStatus | None = Query(default=None),
    rule_id: str | None = Query(default=None, alias="ruleId"),
    dataset_id: str | None = Query(default=None, alias="datasetId"),
    domain_id: str | None = Query(default=None, alias="domainId"),
    data_product_id: str | None = Query(default=None, alias="dataProductId"),
    repository: DqResultEventRepository = Depends(get_dq_result_event_repository),
) -> DqResultDriftSummaryView:
    started_at = perf_counter()
    correlation_id = request.headers.get("X-Correlation-ID") or f"corr-{uuid4().hex[:12]}"

    try:
        result = await _gx_browse_api.get_result_history_drift_summary(
            correlation_id=correlation_id,
            lookback_amount=lookback_amount,
            lookback_unit=str(lookback_unit),
            status=_normalize_query_enum(status),
            rule_id=_normalize_query_text(rule_id),
            dataset_id=_normalize_query_text(dataset_id),
            domain_id=_normalize_query_text(domain_id),
            data_product_id=_normalize_query_text(data_product_id),
            repository=repository,
        )
    except HTTPException as exc:
        _record_gx_failure_operation(
            operation="fetch_result_history_drift_summary",
            started_at=started_at,
            status_code=exc.status_code,
            reason=_normalize_gx_failure_reason(exc.detail, "dq_result_drift_unavailable"),
        )
        raise

    _record_gx_operation(
        surface="gx_api",
        operation="fetch_result_history_drift_summary",
        result="succeeded",
        started_at=started_at,
        status_code=200,
    )
    return result


@router.post(
    "/runs/reconciliation",
    response_model=GxExecutionRunView,
    responses={
        200: {"description": "Reconciliation run persisted."},
        409: {"description": "One or more selected datasources are already involved in an active reconciliation run."},
    },
)
async def create_gx_reconciliation_run(
    request: Request,
    body: GxReconciliationRunCreateRequestView,
    repository: GxExecutionRunRepository = Depends(get_gx_execution_run_repository),
) -> GxExecutionRunView:
    started_at = perf_counter()
    correlation_id = request.headers.get("X-Correlation-ID") or f"corr-{uuid4().hex[:12]}"
    requested_by = body.requestedBy or get_user_id()

    active_conflict = _find_active_reconciliation_conflict(
        await repository.list_runs({}),
        workspace_id=body.workspaceId,
        left_datasource_id=body.leftDatasourceId,
        right_datasource_id=body.rightDatasourceId,
    )
    if active_conflict is not None:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "reconciliation_datasource_busy",
                "message": "One or more selected datasources are already involved in an active reconciliation run.",
                "workspace_id": body.workspaceId,
                "left_datasource_id": body.leftDatasourceId,
                "right_datasource_id": body.rightDatasourceId,
                "active_run_id": active_conflict.id,
                "active_run_status": active_conflict.status,
            },
        )

    run_id = f"recon-{uuid4().hex}"
    submitted_at = datetime.now(UTC).isoformat()

    created = await repository.create_run(
        build_gx_execution_run_create_entity(
            _build_reconciliation_run_payload(
                body,
                run_id=run_id,
                correlation_id=correlation_id,
                requested_by=requested_by,
                submitted_at=submitted_at,
            )
        )
    )

    _record_gx_operation(
        surface="gx_api",
        operation="create_reconciliation_run",
        result="succeeded",
        started_at=started_at,
        status_code=200,
    )
    return GxExecutionRunView.model_validate(created.model_dump(mode="python", by_alias=False, exclude_none=True))


@router.get(
    "/runs/reconciliation",
    response_model=list[GxExecutionRunView],
    responses={
        200: {"description": "Persisted reconciliation runs."},
    },
)
async def list_gx_reconciliation_runs(
    workspace_id: str | None = Query(default=None, alias="workspaceId"),
    status: GxExecutionStatus | None = Query(default=None),
    limit: int = Query(default=10, ge=1, le=100),
    repository: GxExecutionRunRepository = Depends(get_gx_execution_run_repository),
) -> list[GxExecutionRunView]:
    started_at = perf_counter()
    runs = await repository.list_runs({})
    filtered_runs = [
        run
        for run in runs
        if _is_reconciliation_run(run, workspace_id=workspace_id)
        and (status is None or str(run.status or "") == str(status))
    ]

    _record_gx_operation(
        surface="gx_api",
        operation="list_reconciliation_runs",
        result="succeeded",
        started_at=started_at,
        status_code=200,
    )
    return [
        GxExecutionRunView.model_validate(run.model_dump(mode="python", by_alias=False, exclude_none=True))
        for run in filtered_runs[:limit]
    ]


@router.get(
    "/runs/{run_id}",
    response_model=GxExecutionRunView,
    responses={
        200: {
            "description": "Persisted GX execution run metadata and lifecycle state.",
        },
        404: {
            "description": "Execution run not found.",
        },
    },
)
async def get_gx_execution_run(
    run_id: str,
    repository: GxExecutionRunRepository = Depends(get_gx_execution_run_repository),
) -> GxExecutionRunView:
    started_at = perf_counter()
    log_event(_log, "gx.run.fetch.start", component="gx-api", runId=run_id)
    try:
        run_view = await _gx_execution_api.fetch_execution_run_view(run_id=run_id, repository=repository)
    except HTTPException as exc:
        if exc.status_code == 404:
            log_event(_log, "gx.run.fetch.not_found", level="warning", component="gx-api", runId=run_id)
            increment_gx_failure(surface="gx_api", operation="fetch_run", reason="run_not_found")
            _record_gx_operation(
                surface="gx_api",
                operation="fetch_run",
                result="failed",
                started_at=started_at,
                status_code=404,
            )
        raise

    log_event(_log, "gx.run.fetch.complete", component="gx-api", runId=run_id, status=run_view.status)
    _record_gx_operation(
        surface="gx_api",
        operation="fetch_run",
        result="succeeded",
        started_at=started_at,
        status_code=200,
    )
    return run_view


@router.get(
    "/runs/{run_id}/status-history",
    response_model=list[GxExecutionRunStatusHistoryView],
    responses={
        200: {
            "description": "Chronological status transition trail for the given GX execution run.",
        },
        404: {
            "description": "Execution run not found.",
        },
    },
)
async def get_gx_execution_run_status_history(
    run_id: str,
    repository: GxExecutionRunRepository = Depends(get_gx_execution_run_repository),
) -> list[GxExecutionRunStatusHistoryView]:
    started_at = perf_counter()
    try:
        history = await _gx_execution_api.fetch_execution_run_status_history(run_id=run_id, repository=repository)
    except HTTPException as exc:
        if exc.status_code == 404:
            log_event(_log, "gx.run.history.not_found", level="warning", component="gx-api", runId=run_id)
            increment_gx_failure(surface="gx_api", operation="fetch_run_history", reason="run_not_found")
            _record_gx_operation(
                surface="gx_api",
                operation="fetch_run_history",
                result="failed",
                started_at=started_at,
                status_code=404,
            )
        raise

    log_event(_log, "gx.run.history.fetched", component="gx-api", runId=run_id, resultCount=len(history))
    _record_gx_operation(
        surface="gx_api",
        operation="fetch_run_history",
        result="succeeded",
        started_at=started_at,
        status_code=200,
    )
    return history


@router.post(
    "/runs/{run_id}/report",
    response_model=GxExecutionRunView,
    responses={
        200: {"description": "Execution run state updated."},
        404: {"description": "Execution run not found."},
    },
)
async def report_gx_execution_run(
    run_id: str,
    body: GxExecutionRunReportRequestView,
    repository: GxExecutionRunRepository = Depends(get_gx_execution_run_repository),
    suite_repository: GxSuiteRepository = Depends(get_gx_suite_repository),
    rules_repository: RulesRepository = Depends(get_rules_repository),
    dq_result_event_repository: DqResultEventRepository = Depends(get_dq_result_event_repository),
    violation_repository: ExceptionFactRepository = Depends(get_exception_fact_repository),
    projection_repository: ExceptionReasonAnalyticsProjectionRepository = Depends(get_exception_reason_analytics_projection_repository),
) -> GxExecutionRunView:
    started_at = perf_counter()
    try:
        updated = await _gx_report_api.report_execution_run_view(
            run_id=run_id,
            body=body,
            repository=repository,
            suite_repository=suite_repository,
            rules_repository=rules_repository,
            dq_result_event_repository=dq_result_event_repository,
            violation_repository=violation_repository,
            projection_repository=projection_repository,
            settings_provider=get_settings,
            exception_storage_builder=build_exception_storage_service,
        )
    except HTTPException as exc:
        if exc.status_code == 404:
            increment_gx_failure(surface="gx_api", operation="report_run", reason="run_not_found")
            _record_gx_operation(
                surface="gx_api",
                operation="report_run",
                result="failed",
                started_at=started_at,
                status_code=404,
            )
        elif exc.status_code == 503:
            reason = "report_persistence_failed"
            if isinstance(exc.detail, dict):
                reason = str(exc.detail.get("error") or reason)
            increment_gx_failure(surface="gx_api", operation="report_run", reason=reason)
            _record_gx_operation(
                surface="gx_api",
                operation="report_run",
                result="failed",
                started_at=started_at,
                status_code=503,
            )
        raise

    _record_gx_operation(
        surface="gx_api",
        operation="report_run",
        result="succeeded",
        started_at=started_at,
        status_code=200,
    )
    return updated


@router.get(
    "/runs/{run_id}/queue-status",
    response_model=GxExecutionQueueStatusView,
    responses={
        200: {"description": "GX dispatch queue length and run position."},
        404: {"description": "Execution run not found."},
        409: {"description": "Run is missing queue handoff metadata."},
        503: {"description": "Dispatch queue is unavailable."},
    },
)
async def get_gx_execution_run_queue_status(
    run_id: str,
    scan_limit: int = Query(default=500, ge=1, le=5000, alias="scanLimit"),
    repository: GxExecutionRunRepository = Depends(get_gx_execution_run_repository),
    settings: Settings = Depends(get_settings),
) -> GxExecutionQueueStatusView:
    started_at = perf_counter()
    try:
        result = await _gx_execution_api.get_execution_run_queue_status(
            run_id=run_id,
            scan_limit=scan_limit,
            repository=repository,
            settings=settings,
            async_redis_module=aioredis,
            sync_redis_module=redis_sync,
            logger=_log,
        )
    except HTTPException as exc:
        _record_gx_failure_operation(
            operation="fetch_queue_status",
            started_at=started_at,
            status_code=exc.status_code,
            reason=_normalize_gx_failure_reason(exc.detail, "fetch_queue_status_failed"),
        )
        raise

    _record_gx_operation(
        surface="gx_api",
        operation="fetch_queue_status",
        result="succeeded",
        started_at=started_at,
        status_code=200,
    )
    return result


@router.get(
    "/suites/{suite_id}/status-history",
    response_model=list[GxSuiteStatusHistoryView],
    responses={
        200: {
            "description": "Chronological status transition trail for the given suite.",
        },
        404: {
            "description": "Suite not found.",
        },
    },
)
async def get_gx_suite_status_history(
    suite_id: str,
    suite_version: int | None = Query(default=None, alias="suiteVersion", ge=1),
    repository: ValidationArtifactRepository = Depends(get_validation_artifact_repository),
) -> list[GxSuiteStatusHistoryView]:
    started_at = perf_counter()
    log_event(
        _log, "gx.suite.history.fetched",
        component="gx-api",
        suiteId=suite_id,
        suiteVersion=suite_version,
    )
    history = await _gx_suite_api.list_suite_status_history(
        suite_id=suite_id,
        suite_version=suite_version,
        repository=repository,
    )
    _record_gx_operation(
        surface="gx_api",
        operation="fetch_suite_history",
        result="succeeded",
        started_at=started_at,
        status_code=200,
    )
    return history
