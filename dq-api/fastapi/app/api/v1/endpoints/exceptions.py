from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.api.v1 import execution_browse_api as _gx_browse_api
from app.api.v1.schemas import ExceptionAnalysisSessionView
from app.api.v1.schemas import ExceptionAnalysisSliceDetailView
from app.api.v1.schemas import ExceptionAnalysisSliceRequestView
from app.api.v1.schemas import ExceptionFactView
from app.api.v1.schemas import ExceptionFactsPageView
from app.api.v1.schemas import ExceptionReasonAnalyticsView
from app.api.v1.schemas.exception_fact_view import build_offset_pagination
from app.core.dependencies import get_data_catalog_repository
from app.core.dependencies import get_admin_repository
from app.core.dependencies import get_exception_analysis_session_repository
from app.core.dependencies import get_exception_fact_repository
from app.core.dependencies import get_exception_reason_analytics_projection_repository
from app.core.dependencies import get_gx_execution_run_repository
from app.core.dependencies import get_gx_suite_repository
from app.core.dependencies import get_validation_run_plan_repository
from app.core.dependencies import get_rules_repository
from app.core.auth import has_required_scope
from app.domain.interfaces import DataCatalogRepository
from app.domain.interfaces import AdminRepository
from app.domain.interfaces import ExceptionAnalysisSessionRepository
from app.domain.interfaces import ExceptionFactRepository
from app.domain.interfaces import ExceptionReasonAnalyticsProjectionRepository
from app.domain.interfaces import GxExecutionRunRepository
from app.domain.interfaces import GxSuiteRepository
from app.domain.interfaces import ValidationRunPlanRepository
from app.domain.interfaces import RulesRepository
from app.application.services.exception_analysis_session_service import ExceptionAnalysisSessionService
from app.application.services.exception_analysis_session_service import build_exception_analysis_slice_storage_backend
from app.application.services.exception_storage import ExceptionStorageError
from app.core.config import get_settings
from dq_domain_validation import GxExecutionStatus
from dq_domain_validation import LookbackUnit


router = APIRouter(prefix="/exceptions", tags=["exceptions"])

_ENGINE_METADATA_KEYS = frozenset({"checkpoint_name", "expectation_type"})
_ELEVATED_OPS_KEYS = frozenset(
    {
        "suite_id",
        "suite_version",
        "validation_artifact_id",
        "validation_artifact_version",
        "rule_version_id",
        "correlation_id",
        "engine_type",
        "execution_plan_id",
        "execution_plan_version_id",
        "delivery_id",
        "dataset_id",
        "data_product_id",
        "record_identifier_type",
        "record_identifier_value",
        "reason_code",
        "reason_text",
        "failure_class",
        "identifier_fields",
        "identifier_hash",
    }
)


def _normalize_query_text(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _normalize_query_enum(value: object) -> GxExecutionStatus | None:
    return value if isinstance(value, str) else None


def _require_text(value: Any, *, field_name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"Exception fact is missing {field_name}")
    return normalized


def _optional_text(value: Any) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def _require_positive_int(value: Any, *, field_name: str) -> int:
    if value in (None, ""):
        raise ValueError(f"Exception fact is missing {field_name}")
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Exception fact has invalid {field_name}") from exc
    if number < 1:
        raise ValueError(f"Exception fact has invalid {field_name}")
    return number


def _optional_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _row_value(row: Any, key: str) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    return getattr(row, key, None)


def _resolve_workspace_for_data_object_version(
    catalog_repository: DataCatalogRepository,
    data_object_version_id: str,
) -> str | None:
    version = catalog_repository.get_data_object_version(data_object_version_id)
    if version is None:
        return None

    catalog_rows = catalog_repository.list_data_objects_catalog()
    data_object_catalog = next((row for row in catalog_rows if str(getattr(row, "id", None) or "") == str(getattr(version, "data_object_id", None) or "")), None)
    if data_object_catalog is None:
        return None

    data_sets = catalog_repository.list_data_sets()
    data_set = next((row for row in data_sets if str(getattr(row, "id", None) or "") == str(getattr(data_object_catalog, "dataset_id", None) or "")), None)
    if data_set is None:
        return None

    return str(getattr(data_set, "workspace_id", None) or "").strip() or None


def _has_exception_fact_workspace_role(
    current_user: Any,
    workspace_id: str,
    allowed_roles: set[str],
) -> bool:
    if current_user is None or not workspace_id:
        return False
    for role in list(getattr(current_user, "workspace_roles", []) or []):
        role_workspace = str(getattr(role, "workspace_id", None) or "").strip()
        role_name = str(getattr(role, "role", None) or "").strip()
        if role_workspace == workspace_id and role_name in allowed_roles:
            return True
    return False


def _has_exception_fact_execution_ownership(current_user: Any, execution_run: Any) -> bool:
    if current_user is None or execution_run is None:
        return False

    current_user_id = str(getattr(current_user, "id", None) or "").strip()
    if not current_user_id:
        return False

    requested_by = str(getattr(execution_run, "requestedBy", None) or "").strip()
    return bool(requested_by) and requested_by == current_user_id


def _build_exception_fact_payload(row: Any) -> dict[str, Any]:
    ops_metadata = dict(_row_value(row, "opsMetadata") or {})
    engine_metadata = {
        key: value for key, value in ops_metadata.items() if key in _ENGINE_METADATA_KEYS and value not in (None, "")
    }
    remaining_ops_metadata = {
        key: value
        for key, value in ops_metadata.items()
        if key not in _ELEVATED_OPS_KEYS and key not in _ENGINE_METADATA_KEYS and value not in (None, "")
    }

    validation_artifact_id = _require_text(
        ops_metadata.get("validation_artifact_id"),
        field_name="validation_artifact_id",
    )
    validation_artifact_version = _require_positive_int(
        ops_metadata.get("validation_artifact_version"),
        field_name="validation_artifact_version",
    )

    return {
        "exceptionFactId": _require_text(_row_value(row, "id"), field_name="exception_fact_id"),
        "exceptionFactContractVersion": "v1",
        "engineType": _require_text(ops_metadata.get("engine_type"), field_name="engine_type"),
        "executionScope": {
            "deliveryId": _optional_text(ops_metadata.get("delivery_id")),
            "executionPlanId": _optional_text(ops_metadata.get("execution_plan_id")),
            "executionPlanVersionId": _optional_text(ops_metadata.get("execution_plan_version_id")),
            "executionRunId": _require_text(_row_value(row, "executionRunId"), field_name="execution_run_id"),
            "dataObjectVersionId": _require_text(
                _row_value(row, "dataObjectVersionId"),
                field_name="data_object_version_id",
            ),
            "datasetId": _optional_text(ops_metadata.get("dataset_id")),
            "dataProductId": _optional_text(ops_metadata.get("data_product_id")),
        },
        "artifactScope": {
            "validationArtifactId": validation_artifact_id,
            "validationArtifactVersion": validation_artifact_version,
            "nativeArtifactId": _optional_text(ops_metadata.get("suite_id")),
            "nativeArtifactVersion": _optional_text(ops_metadata.get("suite_version")),
        },
        "ruleScope": {
            "ruleId": _require_text(_row_value(row, "ruleId"), field_name="rule_id"),
            "ruleVersionId": _require_text(ops_metadata.get("rule_version_id"), field_name="rule_version_id"),
        },
        "recordReference": {
            "identifierType": _require_text(
                ops_metadata.get("record_identifier_type"),
                field_name="record_identifier_type",
            ),
            "identifierValue": _require_text(
                ops_metadata.get("record_identifier_value"),
                field_name="record_identifier_value",
            ),
            "identifierFields": _optional_string_list(ops_metadata.get("identifier_fields")),
            "identifierHash": _optional_text(ops_metadata.get("identifier_hash")),
        },
        "failure": {
            "reasonCode": _require_text(ops_metadata.get("reason_code"), field_name="reason_code"),
            "reasonText": _require_text(ops_metadata.get("reason_text"), field_name="reason_text"),
            "failureClass": _optional_text(ops_metadata.get("failure_class")),
            "detectedAt": _require_text(_row_value(row, "detectedAt"), field_name="detected_at"),
        },
        "correlationId": _optional_text(ops_metadata.get("correlation_id")),
        "engineMetadata": engine_metadata,
        "opsMetadata": remaining_ops_metadata,
    }


def _exception_fact_contract_error(*, correlation_id: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=500,
        detail={
            "error": "exception_fact_contract_unavailable",
            "message": message,
            "correlation_id": correlation_id,
        },
    )



def _project_exception_analysis_session_response(payload: dict[str, Any]) -> dict[str, Any]:
    current_slice = _project_exception_analysis_slice_response(payload.get("currentSlice") or {})
    slices = [
        _project_exception_analysis_slice_summary(row)
        for row in (payload.get("slices") or [])
        if isinstance(row, Mapping)
    ]
    return {
        "analysisSessionId": str(payload.get("analysisSessionId") or ""),
        "dataObjectVersionId": str(payload.get("dataObjectVersionId") or ""),
        "executionRunId": str(payload.get("executionRunId") or ""),
        "ruleId": str(payload.get("ruleId") or ""),
        "anchorTotalCount": int(payload.get("anchorTotalCount") or 0),
        "sliceCount": int(payload.get("sliceCount") or len(slices)),
        "createdAt": str(payload.get("createdAt") or ""),
        "updatedAt": str(payload.get("updatedAt") or ""),
        "analysisStatus": dict(payload.get("analysisStatus") or {}) if isinstance(payload.get("analysisStatus"), Mapping) else None,
        "currentSlice": current_slice,
        "slices": slices,
    }


def _project_exception_analysis_slice_summary(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "analysisSessionId": str(payload.get("analysisSessionId") or ""),
        "analysisSliceId": str(payload.get("analysisSliceId") or ""),
        "sliceIndex": int(payload.get("sliceIndex") or 0),
        "dataObjectVersionId": str(payload.get("dataObjectVersionId") or ""),
        "executionRunId": str(payload.get("executionRunId") or ""),
        "ruleId": str(payload.get("ruleId") or ""),
        "sliceLimit": int(payload.get("sliceLimit") or 0),
        "anchorTotalCount": int(payload.get("anchorTotalCount") or 0),
        "totalMatchingCount": int(payload.get("totalMatchingCount") or 0),
        "returnedCount": int(payload.get("returnedCount") or 0),
        "truncated": bool(payload.get("truncated") or False),
        "analysisPackUri": str(payload.get("analysisPackUri") or ""),
        "analysisPackSha256": str(payload.get("analysisPackSha256") or ""),
        "analysisManifestUri": str(payload.get("analysisManifestUri") or ""),
        "analysisManifestSha256": str(payload.get("analysisManifestSha256") or ""),
        "filters": dict(payload.get("filters") or {}),
        "nextSliceSuggestion": dict(payload.get("nextSliceSuggestion")) if isinstance(payload.get("nextSliceSuggestion"), dict) else None,
        "createdAt": str(payload.get("createdAt") or ""),
        "updatedAt": str(payload.get("updatedAt") or ""),
    }


def _project_exception_analysis_slice_response(payload: dict[str, Any]) -> dict[str, Any]:
    records = payload.get("records") if isinstance(payload.get("records"), list) else []
    return {
        **_project_exception_analysis_slice_summary(payload),
        "records": [ExceptionFactView.model_validate(_build_exception_fact_payload(row)).model_dump(mode="python", by_alias=False) for row in records if isinstance(row, Mapping)],
    }

def _build_exception_analysis_session_service(
    violation_repository: ExceptionFactRepository,
    analysis_session_repository: ExceptionAnalysisSessionRepository,
) -> ExceptionAnalysisSessionService:
    settings = get_settings()
    storage_backend = build_exception_analysis_slice_storage_backend(settings=settings)
    return ExceptionAnalysisSessionService(
        violation_repository=violation_repository,
        session_repository=analysis_session_repository,
        storage_backend=storage_backend,
    )


@router.get(
    "/facts",
    response_model=ExceptionFactsPageView,
    responses={
        200: {"description": "Canonical exception facts for a filtered execution scope."},
        500: {"description": "Stored exception facts cannot be projected to the canonical contract."},
    },
)
async def list_exception_facts(
    request: Request,
    data_object_version_id: str = Query(..., alias="dataObjectVersionId"),
    execution_run_id: str | None = Query(default=None, alias="executionRunId"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    admin_repository: AdminRepository = Depends(get_admin_repository),
    data_catalog_repository: DataCatalogRepository = Depends(get_data_catalog_repository),
    violation_repository: ExceptionFactRepository = Depends(get_exception_fact_repository),
) -> ExceptionFactsPageView:
    correlation_id = request.headers.get("X-Correlation-ID") or ""
    current_user = admin_repository.get_current_user(getattr(request.state, "user_id", None), getattr(request.state, "auth_claims", None))
    workspace_id = _resolve_workspace_for_data_object_version(data_catalog_repository, data_object_version_id)
    if workspace_id and not has_required_scope(list(getattr(current_user, "granted_scopes", []) or []), ["dq:rules:read"]) and not _has_exception_fact_workspace_role(
        current_user,
        workspace_id,
        {"exception-fact-reader", "exception_fact_reader", "admin"},
    ):
        raise HTTPException(status_code=403, detail={"error": "exception_fact_access_denied", "message": "Exception fact access is not allowed for this workspace", "workspace_id": workspace_id, "correlation_id": correlation_id})
    rows = await violation_repository.list_violations(
        data_object_version_id=data_object_version_id,
        execution_run_id=execution_run_id,
        limit=limit,
        offset=offset,
    )
    try:
        payload = {
            "data": [
                ExceptionFactView.model_validate(_build_exception_fact_payload(row))
                for row in rows.data
            ],
            "pagination": build_offset_pagination(total=rows.total, offset=offset, limit=limit),
        }
    except ValueError as exc:
        raise _exception_fact_contract_error(correlation_id=correlation_id, message=str(exc)) from exc
    return ExceptionFactsPageView.model_validate(payload)


@router.post(
    "/analysis-sessions",
    response_model=ExceptionAnalysisSessionView,
    status_code=201,
    responses={
        201: {"description": "Stored GX analysis slice session created."},
        403: {"description": "Access denied for the analysis scope."},
        503: {"description": "Analysis slice storage is unavailable."},
    },
)
async def create_exception_analysis_session(
    request: Request,
    request_body: ExceptionAnalysisSliceRequestView,
    admin_repository: AdminRepository = Depends(get_admin_repository),
    data_catalog_repository: DataCatalogRepository = Depends(get_data_catalog_repository),
    violation_repository: ExceptionFactRepository = Depends(get_exception_fact_repository),
    analysis_session_repository: ExceptionAnalysisSessionRepository = Depends(get_exception_analysis_session_repository),
) -> ExceptionAnalysisSessionView:
    correlation_id = request.headers.get("X-Correlation-ID") or ""
    current_user = admin_repository.get_current_user(getattr(request.state, "user_id", None), getattr(request.state, "auth_claims", None))
    workspace_id = _resolve_workspace_for_data_object_version(data_catalog_repository, request_body.dataObjectVersionId)
    if workspace_id and not has_required_scope(list(getattr(current_user, "granted_scopes", []) or []), ["dq:rules:read"]) and not _has_exception_fact_workspace_role(
        current_user,
        workspace_id,
        {"exception-fact-reader", "exception_fact_reader", "admin"},
    ):
        raise HTTPException(status_code=403, detail={"error": "exception_fact_access_denied", "message": "Exception analysis access is not allowed for this workspace", "workspace_id": workspace_id, "correlation_id": correlation_id})

    try:
        service = _build_exception_analysis_session_service(violation_repository, analysis_session_repository)
        payload = await service.create_session(request_body.model_dump(mode="python", by_alias=False))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": "exception_analysis_invalid_request", "message": str(exc), "correlation_id": correlation_id}) from exc
    except ExceptionStorageError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"error": "exception_analysis_storage_unavailable", "message": str(exc), "correlation_id": correlation_id}) from exc

    return ExceptionAnalysisSessionView.model_validate(_project_exception_analysis_session_response(payload))


@router.post(
    "/analysis-sessions/{analysis_session_id}/slices",
    response_model=ExceptionAnalysisSessionView,
    responses={
        200: {"description": "Stored GX analysis slice session updated with a new slice."},
        404: {"description": "Analysis session not found."},
        503: {"description": "Analysis slice storage is unavailable."},
    },
)
async def append_exception_analysis_slice(
    request: Request,
    analysis_session_id: str,
    request_body: ExceptionAnalysisSliceRequestView,
    admin_repository: AdminRepository = Depends(get_admin_repository),
    data_catalog_repository: DataCatalogRepository = Depends(get_data_catalog_repository),
    violation_repository: ExceptionFactRepository = Depends(get_exception_fact_repository),
    analysis_session_repository: ExceptionAnalysisSessionRepository = Depends(get_exception_analysis_session_repository),
) -> ExceptionAnalysisSessionView:
    correlation_id = request.headers.get("X-Correlation-ID") or ""
    existing_session = await analysis_session_repository.list_slices(analysis_session_id)
    if not existing_session:
        raise HTTPException(status_code=404, detail={"error": "exception_analysis_session_not_found", "message": f"Analysis session '{analysis_session_id}' not found", "analysis_session_id": analysis_session_id, "correlation_id": correlation_id})

    anchor_row = existing_session[0]
    if str(anchor_row.get("dataObjectVersionId") or "") != request_body.dataObjectVersionId or str(anchor_row.get("executionRunId") or "") != request_body.executionRunId or str(anchor_row.get("ruleId") or "") != request_body.ruleId:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "exception_analysis_anchor_mismatch",
                "message": "Analysis slice requests must keep the original data object version, execution run, and rule fixed",
                "analysis_session_id": analysis_session_id,
                "correlation_id": correlation_id,
            },
        )

    current_user = admin_repository.get_current_user(getattr(request.state, "user_id", None), getattr(request.state, "auth_claims", None))
    workspace_id = _resolve_workspace_for_data_object_version(data_catalog_repository, str(anchor_row.get("dataObjectVersionId") or ""))
    if workspace_id and not has_required_scope(list(getattr(current_user, "granted_scopes", []) or []), ["dq:rules:read"]) and not _has_exception_fact_workspace_role(
        current_user,
        workspace_id,
        {"exception-fact-reader", "exception_fact_reader", "admin"},
    ):
        raise HTTPException(status_code=403, detail={"error": "exception_fact_access_denied", "message": "Exception analysis access is not allowed for this workspace", "workspace_id": workspace_id, "correlation_id": correlation_id})

    try:
        service = _build_exception_analysis_session_service(violation_repository, analysis_session_repository)
        payload = await service.create_session(request_body.model_dump(mode="python", by_alias=False), analysis_session_id=analysis_session_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": "exception_analysis_invalid_request", "message": str(exc), "correlation_id": correlation_id}) from exc
    except ExceptionStorageError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"error": "exception_analysis_storage_unavailable", "message": str(exc), "correlation_id": correlation_id}) from exc

    return ExceptionAnalysisSessionView.model_validate(_project_exception_analysis_session_response(payload))


@router.get(
    "/analysis-sessions/{analysis_session_id}",
    response_model=ExceptionAnalysisSessionView,
    responses={
        200: {"description": "Stored GX analysis slice session."},
        404: {"description": "Analysis session not found."},
    },
)
async def get_exception_analysis_session(
    request: Request,
    analysis_session_id: str,
    summary_only: bool = Query(False, alias="summary_only"),
    admin_repository: AdminRepository = Depends(get_admin_repository),
    data_catalog_repository: DataCatalogRepository = Depends(get_data_catalog_repository),
    violation_repository: ExceptionFactRepository = Depends(get_exception_fact_repository),
    analysis_session_repository: ExceptionAnalysisSessionRepository = Depends(get_exception_analysis_session_repository),
) -> ExceptionAnalysisSessionView:
    correlation_id = request.headers.get("X-Correlation-ID") or ""
    existing_session = await analysis_session_repository.list_slices(analysis_session_id)
    if not existing_session:
        raise HTTPException(status_code=404, detail={"error": "exception_analysis_session_not_found", "message": f"Analysis session '{analysis_session_id}' not found", "analysis_session_id": analysis_session_id, "correlation_id": correlation_id})

    current_user = admin_repository.get_current_user(getattr(request.state, "user_id", None), getattr(request.state, "auth_claims", None))
    workspace_id = _resolve_workspace_for_data_object_version(data_catalog_repository, str(existing_session[0].get("dataObjectVersionId") or ""))
    if workspace_id and not has_required_scope(list(getattr(current_user, "granted_scopes", []) or []), ["dq:rules:read"]) and not _has_exception_fact_workspace_role(
        current_user,
        workspace_id,
        {"exception-fact-reader", "exception_fact_reader", "admin"},
    ):
        raise HTTPException(status_code=403, detail={"error": "exception_fact_access_denied", "message": "Exception analysis access is not allowed for this workspace", "workspace_id": workspace_id, "correlation_id": correlation_id})

    service = _build_exception_analysis_session_service(violation_repository, analysis_session_repository)
    payload = await service.get_session_summary(analysis_session_id) if summary_only else await service.get_session(analysis_session_id)
    if payload is None:
        raise HTTPException(status_code=404, detail={"error": "exception_analysis_session_not_found", "message": f"Analysis session '{analysis_session_id}' not found", "analysis_session_id": analysis_session_id, "correlation_id": correlation_id})
    return ExceptionAnalysisSessionView.model_validate(_project_exception_analysis_session_response(payload))


@router.get(
    "/analysis-sessions/{analysis_session_id}/slices/{analysis_slice_id}",
    response_model=ExceptionAnalysisSliceDetailView,
    responses={
        200: {"description": "Stored GX analysis slice detail."},
        404: {"description": "Analysis slice not found."},
    },
)
async def get_exception_analysis_slice(
    request: Request,
    analysis_session_id: str,
    analysis_slice_id: str,
    admin_repository: AdminRepository = Depends(get_admin_repository),
    data_catalog_repository: DataCatalogRepository = Depends(get_data_catalog_repository),
    violation_repository: ExceptionFactRepository = Depends(get_exception_fact_repository),
    analysis_session_repository: ExceptionAnalysisSessionRepository = Depends(get_exception_analysis_session_repository),
) -> ExceptionAnalysisSliceDetailView:
    correlation_id = request.headers.get("X-Correlation-ID") or ""
    slice_row = await analysis_session_repository.get_slice(analysis_session_id, analysis_slice_id)
    if slice_row is None:
        raise HTTPException(status_code=404, detail={"error": "exception_analysis_slice_not_found", "message": f"Analysis slice '{analysis_slice_id}' not found", "analysis_session_id": analysis_session_id, "analysis_slice_id": analysis_slice_id, "correlation_id": correlation_id})

    current_user = admin_repository.get_current_user(getattr(request.state, "user_id", None), getattr(request.state, "auth_claims", None))
    workspace_id = _resolve_workspace_for_data_object_version(data_catalog_repository, str(slice_row.get("dataObjectVersionId") or ""))
    if workspace_id and not has_required_scope(list(getattr(current_user, "granted_scopes", []) or []), ["dq:rules:read"]) and not _has_exception_fact_workspace_role(
        current_user,
        workspace_id,
        {"exception-fact-reader", "exception_fact_reader", "admin"},
    ):
        raise HTTPException(status_code=403, detail={"error": "exception_fact_access_denied", "message": "Exception analysis access is not allowed for this workspace", "workspace_id": workspace_id, "correlation_id": correlation_id})

    service = _build_exception_analysis_session_service(violation_repository, analysis_session_repository)
    payload = await service.get_slice(analysis_session_id, analysis_slice_id)
    if payload is None:
        raise HTTPException(status_code=404, detail={"error": "exception_analysis_slice_not_found", "message": f"Analysis slice '{analysis_slice_id}' not found", "analysis_session_id": analysis_session_id, "analysis_slice_id": analysis_slice_id, "correlation_id": correlation_id})
    return ExceptionAnalysisSliceDetailView.model_validate(_project_exception_analysis_slice_response(payload))


@router.get(
    "/facts/{exception_fact_id}",
    response_model=ExceptionFactView,
    responses={
        200: {"description": "One canonical exception fact."},
        404: {"description": "Exception fact not found."},
        500: {"description": "Stored exception fact cannot be projected to the canonical contract."},
    },
)
async def get_exception_fact(
    request: Request,
    exception_fact_id: str,
    data_object_version_id: str = Query(..., alias="dataObjectVersionId"),
    admin_repository: AdminRepository = Depends(get_admin_repository),
    data_catalog_repository: DataCatalogRepository = Depends(get_data_catalog_repository),
    execution_run_repository: GxExecutionRunRepository = Depends(get_gx_execution_run_repository),
    violation_repository: ExceptionFactRepository = Depends(get_exception_fact_repository),
) -> ExceptionFactView:
    correlation_id = request.headers.get("X-Correlation-ID") or ""
    current_user = admin_repository.get_current_user(getattr(request.state, "user_id", None), getattr(request.state, "auth_claims", None))
    workspace_id = _resolve_workspace_for_data_object_version(data_catalog_repository, data_object_version_id)
    if workspace_id and not has_required_scope(list(getattr(current_user, "granted_scopes", []) or []), ["dq:rules:read"]) and not _has_exception_fact_workspace_role(
        current_user,
        workspace_id,
        {"exception-fact-investigator", "exception_fact_investigator", "admin"},
    ):
        raise HTTPException(status_code=403, detail={"error": "exception_fact_access_denied", "message": "Exception fact detail access is not allowed for this workspace", "workspace_id": workspace_id, "correlation_id": correlation_id})
    row = await violation_repository.get_violation(data_object_version_id, exception_fact_id)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "exception_fact_not_found",
                "message": f"Exception fact '{exception_fact_id}' not found",
                "exception_fact_id": exception_fact_id,
                "data_object_version_id": data_object_version_id,
                "correlation_id": correlation_id,
            },
        )
    execution_run_id = str(getattr(row, "executionRunId", None) or "").strip()
    if not execution_run_id:
        raise _exception_fact_contract_error(correlation_id=correlation_id, message="Exception fact is missing execution_run_id")

    execution_run = await execution_run_repository.get_run(execution_run_id)
    if execution_run is None:
        raise _exception_fact_contract_error(
            correlation_id=correlation_id,
            message=f"Exception fact execution run '{execution_run_id}' is unavailable",
        )

    if workspace_id and not _has_exception_fact_execution_ownership(current_user, execution_run):
        raise HTTPException(
            status_code=403,
            detail={
                "error": "exception_fact_access_denied",
                "message": "Exception fact detail access is limited to the execution owner",
                "workspace_id": workspace_id,
                "execution_run_id": execution_run_id,
                "correlation_id": correlation_id,
            },
        )
    try:
        return ExceptionFactView.model_validate(_build_exception_fact_payload(row))
    except ValueError as exc:
        raise _exception_fact_contract_error(correlation_id=correlation_id, message=str(exc)) from exc


@router.get(
    "/reason-analytics",
    response_model=ExceptionReasonAnalyticsView,
    responses={
        200: {"description": "Exception reason analytics for the current monitoring window."},
        503: {"description": "Exception analytics are unavailable."},
    },
)
async def get_exception_reason_analytics(
    request: Request,
    lookback_amount: int = Query(default=24, ge=1, le=720, alias="lookbackAmount"),
    lookback_unit: LookbackUnit = Query(default="hours", alias="lookbackUnit"),
    status: GxExecutionStatus | None = Query(default=None),
    rule_name: str | None = Query(default=None, alias="ruleName"),
    data_object_name: str | None = Query(default=None, alias="dataObjectName"),
    search: str | None = Query(default=None),
    reason_code: str | None = Query(default=None, alias="reasonCode"),
    suite_id: str | None = Query(default=None, alias="suiteId"),
    data_object_version_id: str | None = Query(default=None, alias="dataObjectVersionId"),
    rule_version_id: str | None = Query(default=None, alias="ruleVersionId"),
    repository: GxExecutionRunRepository = Depends(get_gx_execution_run_repository),
    run_plan_repository: ValidationRunPlanRepository = Depends(get_validation_run_plan_repository),
    projection_repository: ExceptionReasonAnalyticsProjectionRepository = Depends(get_exception_reason_analytics_projection_repository),
    rules_repository: RulesRepository = Depends(get_rules_repository),
    data_catalog_repository: DataCatalogRepository = Depends(get_data_catalog_repository),
    suite_repository: GxSuiteRepository = Depends(get_gx_suite_repository),
) -> ExceptionReasonAnalyticsView:
    correlation_id = request.headers.get("X-Correlation-ID") or ""
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
        data_product_id=None,
        dataset_id=None,
        data_object_id=None,
        delivery_id=None,
        workspace_id=None,
        data_object_version_id=_normalize_query_text(data_object_version_id),
        rule_version_id=_normalize_query_text(rule_version_id),
        repository=repository,
        run_plan_repository=run_plan_repository,
        projection_repository=projection_repository,
        rules_repository=rules_repository,
        data_catalog_repository=data_catalog_repository,
        suite_repository=suite_repository,
    )
    return ExceptionReasonAnalyticsView.model_validate(analytics)