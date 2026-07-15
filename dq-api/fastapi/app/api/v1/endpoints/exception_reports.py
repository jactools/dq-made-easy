from __future__ import annotations

import io
from collections.abc import Sequence
import textwrap
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.api.presenters.exception_reports import build_exception_summary_csv_export
from app.api.presenters.exception_reports import build_exception_summary_json_export
from app.api.presenters.exception_reports import build_exception_summary_markdown_report
from app.api.v1.endpoints.exceptions import _build_exception_fact_payload
from app.api.v1.endpoints.exceptions import _exception_fact_contract_error
from app.api.v1.schemas import DeliveryExceptionSummaryView
from app.api.v1.schemas import ExceptionFactView
from app.api.v1.schemas import ExceptionFactsPageView
from app.api.v1.schemas import ExceptionReasonAnalyticsView
from app.api.v1.schemas import ExecutionPlanExceptionSummaryView
from app.api.v1.schemas.exception_fact_view import build_offset_pagination
from app.application.use_cases.execution_queries import ScopedGxExecutionExceptionAnalyticsQuery
from app.application.use_cases.execution_queries import get_gx_execution_exception_analytics_for_scope
from app.core.auth import has_required_scope
from app.core.dependencies import get_data_catalog_repository
from app.core.dependencies import get_admin_repository
from app.core.dependencies import get_exception_fact_repository
from app.core.dependencies import get_exception_reason_analytics_projection_repository
from app.core.dependencies import get_gx_execution_run_repository
from app.core.dependencies import get_rules_repository
from app.core.dependencies import get_validation_run_plan_repository
from app.domain.interfaces import AdminRepository
from app.domain.interfaces import DataCatalogRepository
from app.domain.interfaces import ExceptionFactRepository
from app.domain.interfaces import ExceptionReasonAnalyticsProjectionRepository
from app.domain.interfaces import GxExecutionRunRepository
from app.domain.interfaces import RulesRepository
from app.domain.interfaces import ValidationRunPlanRepository
from dq_domain_validation import GxExecutionStatus
from dq_domain_validation import LookbackUnit


router = APIRouter(tags=["exceptions"])


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


def _build_export_response(
    *,
    format: str,
    filename_prefix: str,
    scope_kind: str,
    scope_id: str,
    serialized_summary: dict,
    object_storage_classification: str,
    evidence_classification: str,
) -> Response:
    if format == "csv":
        return Response(
            content=build_exception_summary_csv_export(
                scope_kind=scope_kind,
                scope_id=scope_id,
                serialized_summary=serialized_summary,
                object_storage_classification=object_storage_classification,
                evidence_classification=evidence_classification,
            ),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename_prefix}.csv"},
        )
    if format == "markdown":
        return Response(
            content=build_exception_summary_markdown_report(
                scope_kind=scope_kind,
                scope_id=scope_id,
                serialized_summary=serialized_summary,
                object_storage_classification=object_storage_classification,
                evidence_classification=evidence_classification,
            ),
            media_type="text/markdown",
            headers={"Content-Disposition": f"attachment; filename={filename_prefix}.md"},
        )
    if format == "pdf":
        markdown_report = build_exception_summary_markdown_report(
            scope_kind=scope_kind,
            scope_id=scope_id,
            serialized_summary=serialized_summary,
            object_storage_classification=object_storage_classification,
            evidence_classification=evidence_classification,
        )
        return Response(
            content=_markdown_to_pdf_bytes(markdown_report),
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={filename_prefix}.pdf"},
        )
    return Response(
        content=build_exception_summary_json_export(serialized_summary),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename={filename_prefix}.json"},
    )


def _exception_summary_unavailable(*, correlation_id: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={
            "error": "exception_summary_unavailable",
            "message": message,
            "correlation_id": correlation_id,
        },
    )


def _resolve_workspace_for_data_object_version(
    catalog_repository: DataCatalogRepository,
    data_object_version_id: str,
) -> str | None:
    version = catalog_repository.get_data_object_version(data_object_version_id)
    if version is None:
        return None

    data_object_catalog = next(
        (
            row
            for row in catalog_repository.list_data_objects_catalog()
            if str(getattr(row, "id", None) or "") == str(getattr(version, "data_object_id", None) or "")
        ),
        None,
    )
    if data_object_catalog is None:
        return None

    data_set = next(
        (
            row
            for row in catalog_repository.list_data_sets()
            if str(getattr(row, "id", None) or "") == str(getattr(data_object_catalog, "dataset_id", None) or "")
        ),
        None,
    )
    if data_set is None:
        return None

    return str(getattr(data_set, "workspace_id", None) or "").strip() or None


def _has_exception_fact_workspace_role(
    current_user: object | None,
    workspace_id: str,
    allowed_roles: set[str] | None = None,
) -> bool:
    if current_user is None or not workspace_id:
        return False
    allowed = allowed_roles or {"exception-fact-reader", "exception-fact-investigator", "admin"}
    for role in list(getattr(current_user, "workspace_roles", []) or []):
        if str(getattr(role, "workspace_id", None) or "").strip() != workspace_id:
            continue
        if str(getattr(role, "role", None) or "").strip() in allowed:
            return True
    return False


def _can_view_exception_fact_detail_identifiers(current_user: object | None, workspace_id: str) -> bool:
    granted_scopes = [str(scope).strip() for scope in getattr(current_user, "granted_scopes", []) or [] if str(scope).strip()]
    if has_required_scope(granted_scopes, ["dq:rules:read"]):
        return True
    return _has_exception_fact_workspace_role(
        current_user,
        workspace_id,
        {"exception-fact-investigator", "exception_fact_investigator", "admin"},
    )


async def _collect_semantic_exception_fact_rows(
    *,
    violation_repository: ExceptionFactRepository,
    data_object_version_ids: Sequence[str],
    execution_run_ids: Sequence[str],
) -> list[Any]:
    normalized_run_ids = {str(value).strip() for value in execution_run_ids if str(value).strip()}
    if not normalized_run_ids:
        return []

    seen_rows: set[tuple[str, str]] = set()
    collected_rows: list[Any] = []

    for data_object_version_id in [str(value).strip() for value in data_object_version_ids if str(value).strip()]:
        offset = 0
        while True:
            page = await violation_repository.list_violations(
                data_object_version_id,
                limit=500,
                offset=offset,
            )
            if not page.data:
                break

            for row in page.data:
                row_run_id = str(getattr(row, "executionRunId", None) or "").strip()
                if row_run_id not in normalized_run_ids:
                    continue

                row_scope_id = str(getattr(row, "dataObjectVersionId", None) or "").strip()
                row_id = str(getattr(row, "id", None) or "").strip()
                row_key = (row_scope_id, row_id)
                if row_key in seen_rows:
                    continue
                seen_rows.add(row_key)
                collected_rows.append(row)

            if len(page.data) < 500:
                break
            offset += 500

    collected_rows.sort(
        key=lambda row: (
            str(getattr(row, "detectedAt", None) or ""),
            str(getattr(row, "id", None) or ""),
        ),
        reverse=True,
    )
    return collected_rows


async def _load_semantic_exception_scope_rows(
    *,
    request: Request,
    scope_kind: str,
    scope_id: str,
    lookback_amount: int,
    lookback_unit: LookbackUnit,
    status: GxExecutionStatus | None,
    rule_name: str | None,
    data_object_name: str | None,
    search: str | None,
    reason_code: str | None,
    suite_id: str | None,
    data_object_version_id: str | None,
    rule_version_id: str | None,
    repository: GxExecutionRunRepository,
    projection_repository: ExceptionReasonAnalyticsProjectionRepository,
    rules_repository: RulesRepository,
    data_catalog_repository: DataCatalogRepository,
    validation_run_plan_repository: ValidationRunPlanRepository | None = None,
    admin_repository: AdminRepository,
    violation_repository: ExceptionFactRepository,
) -> tuple[Any, list[Any], str | None]:
    correlation_id = request.headers.get("X-Correlation-ID") or ""
    current_user = admin_repository.get_current_user(getattr(request.state, "user_id", None), getattr(request.state, "auth_claims", None))

    workspace_id: str | None = None
    if scope_kind == "delivery":
        delivery_note = data_catalog_repository.get_data_delivery_note(scope_id)
        if delivery_note is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "delivery_not_found",
                    "message": f"Data delivery '{scope_id}' not found",
                    "delivery_id": scope_id,
                    "correlation_id": correlation_id,
                },
            )
        workspace_id = _resolve_workspace_for_data_object_version(
            data_catalog_repository,
            str(getattr(delivery_note, "data_object_version_id", "") or "").strip(),
        )
    else:
        if validation_run_plan_repository is None:
            raise RuntimeError("validation_run_plan_repository is required for execution plan semantic exception routes")
        plan = await validation_run_plan_repository.get_plan(scope_id)
        if plan is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "execution_plan_not_found",
                    "message": f"Execution plan '{scope_id}' not found",
                    "execution_plan_id": scope_id,
                    "correlation_id": correlation_id,
                },
            )
        workspace_id = _resolve_workspace_for_data_object_version(
            data_catalog_repository,
            str(getattr(plan, "currentActiveVersionId", "") or "").strip(),
        )

    granted_scopes = [str(scope).strip() for scope in getattr(current_user, "granted_scopes", []) or [] if str(scope).strip()]
    if workspace_id and not has_required_scope(granted_scopes, ["dq:rules:read"]) and not _has_exception_fact_workspace_role(current_user, workspace_id):
        raise HTTPException(
            status_code=403,
            detail={
                "error": "exception_fact_access_denied",
                "message": "Exception summary access is not allowed for this workspace",
                "workspace_id": workspace_id,
                "correlation_id": correlation_id,
            },
        )

    result = await get_gx_execution_exception_analytics_for_scope(
        query=ScopedGxExecutionExceptionAnalyticsQuery(
            lookback_amount=lookback_amount,
            lookback_unit=str(lookback_unit),
            status=str(status) if status is not None else None,
            rule_name=rule_name,
            data_object_name=data_object_name,
            search=search,
            reason_code=reason_code,
            delivery_id=scope_id if scope_kind == "delivery" else None,
            execution_plan_id=scope_id if scope_kind == "execution_plan" else None,
            suite_id=suite_id,
            data_object_version_id=data_object_version_id,
            rule_version_id=rule_version_id,
        ),
        repository=repository,
        projection_repository=projection_repository,
        rules_repository=rules_repository,
        data_catalog_repository=data_catalog_repository,
    )

    rows = await _collect_semantic_exception_fact_rows(
        violation_repository=violation_repository,
        data_object_version_ids=result.data_object_version_ids,
        execution_run_ids=result.execution_run_ids,
    )
    return result, rows, workspace_id


def _build_semantic_exception_fact_views(rows: Sequence[Any], *, correlation_id: str) -> list[ExceptionFactView]:
    fact_views: list[ExceptionFactView] = []
    for row in rows:
        try:
            fact_views.append(ExceptionFactView.model_validate(_build_exception_fact_payload(row)))
        except ValueError as exc:
            raise _exception_fact_contract_error(correlation_id=correlation_id, message=str(exc)) from exc
    return fact_views


@router.get(
    "/deliveries/{delivery_id}/exception-summary",
    response_model=DeliveryExceptionSummaryView,
    responses={
        200: {"description": "Delivery-scoped exception summary with reason analytics."},
        404: {"description": "Data delivery not found."},
        503: {"description": "Exception summary is unavailable."},
    },
)
async def get_delivery_exception_summary(
    request: Request,
    delivery_id: str,
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
    projection_repository: ExceptionReasonAnalyticsProjectionRepository = Depends(get_exception_reason_analytics_projection_repository),
    rules_repository: RulesRepository = Depends(get_rules_repository),
    data_catalog_repository: DataCatalogRepository = Depends(get_data_catalog_repository),
    admin_repository: AdminRepository = Depends(get_admin_repository),
) -> DeliveryExceptionSummaryView:
    correlation_id = request.headers.get("X-Correlation-ID") or ""
    current_user = admin_repository.get_current_user(getattr(request.state, "user_id", None), getattr(request.state, "auth_claims", None))
    delivery_note = data_catalog_repository.get_data_delivery_note(delivery_id)
    if delivery_note is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "delivery_not_found",
                "message": f"Data delivery '{delivery_id}' not found",
                "delivery_id": delivery_id,
                "correlation_id": correlation_id,
            },
        )

    workspace_id = _resolve_workspace_for_data_object_version(
        data_catalog_repository,
        str(getattr(delivery_note, "data_object_version_id", None) or ""),
    )
    granted_scopes = [str(scope).strip() for scope in getattr(current_user, "granted_scopes", []) or [] if str(scope).strip()]
    if workspace_id and not has_required_scope(granted_scopes, ["dq:rules:read"]) and not _has_exception_fact_workspace_role(current_user, workspace_id):
        raise HTTPException(
            status_code=403,
            detail={
                "error": "exception_fact_access_denied",
                "message": "Exception summary access is not allowed for this workspace",
                "workspace_id": workspace_id,
                "correlation_id": correlation_id,
            },
        )

    try:
        result = await get_gx_execution_exception_analytics_for_scope(
            query=ScopedGxExecutionExceptionAnalyticsQuery(
                lookback_amount=lookback_amount,
                lookback_unit=str(lookback_unit),
                status=str(status) if status is not None else None,
                rule_name=rule_name,
                data_object_name=data_object_name,
                search=search,
                reason_code=reason_code,
                delivery_id=delivery_id,
                suite_id=suite_id,
                data_object_version_id=data_object_version_id,
                rule_version_id=rule_version_id,
            ),
            repository=repository,
            projection_repository=projection_repository,
            rules_repository=rules_repository,
            data_catalog_repository=data_catalog_repository,
        )
    except Exception as exc:
        raise _exception_summary_unavailable(correlation_id=correlation_id, message=str(exc)) from exc

    allow_detail_identifiers = _can_view_exception_fact_detail_identifiers(current_user, workspace_id or "")

    return DeliveryExceptionSummaryView.model_validate(
        {
            "deliveryId": delivery_id,
            "dataObjectVersionId": str(getattr(delivery_note, "data_object_version_id", "") or "").strip() or None,
            "deliveryLocation": str(getattr(delivery_note, "delivery_location", "") or "").strip() or None,
            "objectStorageClassification": str(getattr(delivery_note, "object_storage_classification", "") or "").strip(),
            "evidenceClassification": str(getattr(delivery_note, "evidence_classification", "") or "").strip(),
            "executionRunIds": result.execution_run_ids if allow_detail_identifiers else [],
            "dataObjectVersionIds": result.data_object_version_ids if allow_detail_identifiers else [],
            "analytics": ExceptionReasonAnalyticsView.model_validate(result.analytics),
        }
    )


@router.get(
    "/execution-plans/{execution_plan_id}/exception-summary",
    response_model=ExecutionPlanExceptionSummaryView,
    responses={
        200: {"description": "Execution-plan-scoped exception summary with reason analytics."},
        404: {"description": "Execution plan not found."},
        503: {"description": "Exception summary is unavailable."},
    },
)
async def get_execution_plan_exception_summary(
    request: Request,
    execution_plan_id: str,
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
    projection_repository: ExceptionReasonAnalyticsProjectionRepository = Depends(get_exception_reason_analytics_projection_repository),
    rules_repository: RulesRepository = Depends(get_rules_repository),
    data_catalog_repository: DataCatalogRepository = Depends(get_data_catalog_repository),
    validation_run_plan_repository: ValidationRunPlanRepository = Depends(get_validation_run_plan_repository),
    admin_repository: AdminRepository = Depends(get_admin_repository),
) -> ExecutionPlanExceptionSummaryView:
    correlation_id = request.headers.get("X-Correlation-ID") or ""
    current_user = admin_repository.get_current_user(getattr(request.state, "user_id", None), getattr(request.state, "auth_claims", None))
    plan = await validation_run_plan_repository.get_plan(execution_plan_id)
    if plan is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "execution_plan_not_found",
                "message": f"Execution plan '{execution_plan_id}' not found",
                "execution_plan_id": execution_plan_id,
                "correlation_id": correlation_id,
            },
        )

    workspace_id = _resolve_workspace_for_data_object_version(
        data_catalog_repository,
        str(getattr(plan, "currentActiveVersionId", None) or ""),
    )
    granted_scopes = [str(scope).strip() for scope in getattr(current_user, "granted_scopes", []) or [] if str(scope).strip()]
    if workspace_id and not has_required_scope(granted_scopes, ["dq:rules:read"]) and not _has_exception_fact_workspace_role(current_user, workspace_id):
        raise HTTPException(
            status_code=403,
            detail={
                "error": "exception_fact_access_denied",
                "message": "Exception summary access is not allowed for this workspace",
                "workspace_id": workspace_id,
                "correlation_id": correlation_id,
            },
        )

    try:
        result = await get_gx_execution_exception_analytics_for_scope(
            query=ScopedGxExecutionExceptionAnalyticsQuery(
                lookback_amount=lookback_amount,
                lookback_unit=str(lookback_unit),
                status=str(status) if status is not None else None,
                rule_name=rule_name,
                data_object_name=data_object_name,
                search=search,
                reason_code=reason_code,
                execution_plan_id=execution_plan_id,
                suite_id=suite_id,
                data_object_version_id=data_object_version_id,
                rule_version_id=rule_version_id,
            ),
            repository=repository,
            projection_repository=projection_repository,
            rules_repository=rules_repository,
            data_catalog_repository=data_catalog_repository,
        )
    except Exception as exc:
        raise _exception_summary_unavailable(correlation_id=correlation_id, message=str(exc)) from exc

    allow_detail_identifiers = _can_view_exception_fact_detail_identifiers(current_user, workspace_id or "")

    return ExecutionPlanExceptionSummaryView.model_validate(
        {
            "executionPlanId": execution_plan_id,
            "currentActiveVersionId": str(getattr(plan, "currentActiveVersionId", "") or "").strip() or None,
            "executionRunIds": result.execution_run_ids if allow_detail_identifiers else [],
            "dataObjectVersionIds": result.data_object_version_ids if allow_detail_identifiers else [],
            "analytics": ExceptionReasonAnalyticsView.model_validate(result.analytics),
        }
    )


@router.get(
    "/deliveries/{delivery_id}/exception-summary/export",
    responses={
        200: {"description": "Exported delivery exception summary."},
        404: {"description": "Data delivery not found."},
        503: {"description": "Exception summary export is unavailable."},
    },
)
async def export_delivery_exception_summary(
    request: Request,
    delivery_id: str,
    format: str = Query(default="json", pattern="^(json|csv|markdown|pdf)$"),
    lookback_amount: int = Query(default=24, ge=1, le=720, alias="lookbackAmount"),
    lookback_unit: LookbackUnit = Query(default="hours", alias="lookbackUnit"),
    status: GxExecutionStatus | None = Query(default=None),
    rule_name: str | None = Query(default=None, alias="ruleName"),
    data_object_name: str | None = Query(default=None, alias="dataObjectName"),
    search: str | None = Query(default=None),
    reason_code: str | None = Query(default=None, alias="reasonCode"),
    repository: GxExecutionRunRepository = Depends(get_gx_execution_run_repository),
    projection_repository: ExceptionReasonAnalyticsProjectionRepository = Depends(get_exception_reason_analytics_projection_repository),
    rules_repository: RulesRepository = Depends(get_rules_repository),
    data_catalog_repository: DataCatalogRepository = Depends(get_data_catalog_repository),
    admin_repository: AdminRepository = Depends(get_admin_repository),
) -> Response:
    summary = await get_delivery_exception_summary(
        request=request,
        delivery_id=delivery_id,
        lookback_amount=lookback_amount,
        lookback_unit=lookback_unit,
        status=status,
        rule_name=rule_name,
        data_object_name=data_object_name,
        search=search,
        reason_code=reason_code,
        suite_id=None,
        data_object_version_id=None,
        rule_version_id=None,
        repository=repository,
        projection_repository=projection_repository,
        rules_repository=rules_repository,
        data_catalog_repository=data_catalog_repository,
        admin_repository=admin_repository,
    )
    serialized_summary = summary.model_dump(by_alias=True, mode="json", exclude_none=True)
    return _build_export_response(
        format=format,
        filename_prefix=f"delivery-exception-summary-{delivery_id}",
        scope_kind="delivery",
        scope_id=delivery_id,
        serialized_summary=serialized_summary,
        object_storage_classification=str(summary.object_storage_classification or "").strip(),
        evidence_classification=str(summary.evidence_classification or "").strip(),
    )


@router.get(
    "/execution-plans/{execution_plan_id}/exception-summary/export",
    responses={
        200: {"description": "Exported execution plan exception summary."},
        404: {"description": "Execution plan not found."},
        503: {"description": "Exception summary export is unavailable."},
    },
)
async def export_execution_plan_exception_summary(
    request: Request,
    execution_plan_id: str,
    format: str = Query(default="json", pattern="^(json|csv|markdown|pdf)$"),
    lookback_amount: int = Query(default=24, ge=1, le=720, alias="lookbackAmount"),
    lookback_unit: LookbackUnit = Query(default="hours", alias="lookbackUnit"),
    status: GxExecutionStatus | None = Query(default=None),
    rule_name: str | None = Query(default=None, alias="ruleName"),
    data_object_name: str | None = Query(default=None, alias="dataObjectName"),
    search: str | None = Query(default=None),
    reason_code: str | None = Query(default=None, alias="reasonCode"),
    repository: GxExecutionRunRepository = Depends(get_gx_execution_run_repository),
    projection_repository: ExceptionReasonAnalyticsProjectionRepository = Depends(get_exception_reason_analytics_projection_repository),
    rules_repository: RulesRepository = Depends(get_rules_repository),
    data_catalog_repository: DataCatalogRepository = Depends(get_data_catalog_repository),
    validation_run_plan_repository: ValidationRunPlanRepository = Depends(get_validation_run_plan_repository),
    admin_repository: AdminRepository = Depends(get_admin_repository),
) -> Response:
    summary = await get_execution_plan_exception_summary(
        request=request,
        execution_plan_id=execution_plan_id,
        lookback_amount=lookback_amount,
        lookback_unit=lookback_unit,
        status=status,
        rule_name=rule_name,
        data_object_name=data_object_name,
        search=search,
        reason_code=reason_code,
        suite_id=None,
        data_object_version_id=None,
        rule_version_id=None,
        repository=repository,
        projection_repository=projection_repository,
        rules_repository=rules_repository,
        data_catalog_repository=data_catalog_repository,
        validation_run_plan_repository=validation_run_plan_repository,
        admin_repository=admin_repository,
    )
    serialized_summary = summary.model_dump(by_alias=True, mode="json", exclude_none=True)
    return _build_export_response(
        format=format,
        filename_prefix=f"execution-plan-exception-summary-{execution_plan_id}",
        scope_kind="execution_plan",
        scope_id=execution_plan_id,
        serialized_summary=serialized_summary,
        object_storage_classification="",
        evidence_classification="",
    )


@router.get(
    "/deliveries/{delivery_id}/exception-summary/records",
    response_model=ExceptionFactsPageView,
    responses={
        200: {"description": "Delivery-scoped semantic exception records."},
        404: {"description": "Data delivery not found."},
        503: {"description": "Semantic exception records are unavailable."},
    },
)
async def get_delivery_exception_summary_records(
    request: Request,
    delivery_id: str,
    limit: int = Query(default=25, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
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
    projection_repository: ExceptionReasonAnalyticsProjectionRepository = Depends(get_exception_reason_analytics_projection_repository),
    rules_repository: RulesRepository = Depends(get_rules_repository),
    data_catalog_repository: DataCatalogRepository = Depends(get_data_catalog_repository),
    admin_repository: AdminRepository = Depends(get_admin_repository),
    violation_repository: ExceptionFactRepository = Depends(get_exception_fact_repository),
) -> ExceptionFactsPageView:
    correlation_id = request.headers.get("X-Correlation-ID") or ""
    result, rows, _workspace_id = await _load_semantic_exception_scope_rows(
        request=request,
        scope_kind="delivery",
        scope_id=delivery_id,
        lookback_amount=lookback_amount,
        lookback_unit=lookback_unit,
        status=status,
        rule_name=rule_name,
        data_object_name=data_object_name,
        search=search,
        reason_code=reason_code,
        suite_id=suite_id,
        data_object_version_id=data_object_version_id,
        rule_version_id=rule_version_id,
        repository=repository,
        projection_repository=projection_repository,
        rules_repository=rules_repository,
        data_catalog_repository=data_catalog_repository,
        admin_repository=admin_repository,
        violation_repository=violation_repository,
    )
    fact_views = _build_semantic_exception_fact_views(rows, correlation_id=correlation_id)
    page_rows = fact_views[offset : offset + limit]
    return ExceptionFactsPageView.model_validate(
        {
            "data": page_rows,
            "pagination": build_offset_pagination(total=len(fact_views), offset=offset, limit=limit),
        }
    )


@router.get(
    "/deliveries/{delivery_id}/exception-summary/records/{exception_fact_id}",
    response_model=ExceptionFactView,
    responses={
        200: {"description": "One delivery-scoped semantic exception record."},
        404: {"description": "Exception record not found."},
        503: {"description": "Semantic exception record detail is unavailable."},
    },
)
async def get_delivery_exception_summary_record(
    request: Request,
    delivery_id: str,
    exception_fact_id: str,
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
    projection_repository: ExceptionReasonAnalyticsProjectionRepository = Depends(get_exception_reason_analytics_projection_repository),
    rules_repository: RulesRepository = Depends(get_rules_repository),
    data_catalog_repository: DataCatalogRepository = Depends(get_data_catalog_repository),
    admin_repository: AdminRepository = Depends(get_admin_repository),
    violation_repository: ExceptionFactRepository = Depends(get_exception_fact_repository),
) -> ExceptionFactView:
    correlation_id = request.headers.get("X-Correlation-ID") or ""
    result, rows, _workspace_id = await _load_semantic_exception_scope_rows(
        request=request,
        scope_kind="delivery",
        scope_id=delivery_id,
        lookback_amount=lookback_amount,
        lookback_unit=lookback_unit,
        status=status,
        rule_name=rule_name,
        data_object_name=data_object_name,
        search=search,
        reason_code=reason_code,
        suite_id=suite_id,
        data_object_version_id=data_object_version_id,
        rule_version_id=rule_version_id,
        repository=repository,
        projection_repository=projection_repository,
        rules_repository=rules_repository,
        data_catalog_repository=data_catalog_repository,
        admin_repository=admin_repository,
        violation_repository=violation_repository,
    )
    matching_row = next(
        (
            row
            for row in rows
            if str(getattr(row, "id", None) or "").strip() == exception_fact_id
        ),
        None,
    )
    if matching_row is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "exception_fact_not_found",
                "message": f"Exception record '{exception_fact_id}' not found",
                "exception_fact_id": exception_fact_id,
                "delivery_id": delivery_id,
                "correlation_id": correlation_id,
            },
        )
    try:
        return ExceptionFactView.model_validate(_build_exception_fact_payload(matching_row))
    except ValueError as exc:
        raise _exception_fact_contract_error(correlation_id=correlation_id, message=str(exc)) from exc


@router.get(
    "/execution-plans/{execution_plan_id}/exception-summary/records",
    response_model=ExceptionFactsPageView,
    responses={
        200: {"description": "Execution-plan-scoped semantic exception records."},
        404: {"description": "Execution plan not found."},
        503: {"description": "Semantic exception records are unavailable."},
    },
)
async def get_execution_plan_exception_summary_records(
    request: Request,
    execution_plan_id: str,
    limit: int = Query(default=25, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
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
    projection_repository: ExceptionReasonAnalyticsProjectionRepository = Depends(get_exception_reason_analytics_projection_repository),
    rules_repository: RulesRepository = Depends(get_rules_repository),
    data_catalog_repository: DataCatalogRepository = Depends(get_data_catalog_repository),
    validation_run_plan_repository: ValidationRunPlanRepository = Depends(get_validation_run_plan_repository),
    admin_repository: AdminRepository = Depends(get_admin_repository),
    violation_repository: ExceptionFactRepository = Depends(get_exception_fact_repository),
) -> ExceptionFactsPageView:
    correlation_id = request.headers.get("X-Correlation-ID") or ""
    _result, rows, _workspace_id = await _load_semantic_exception_scope_rows(
        request=request,
        scope_kind="execution_plan",
        scope_id=execution_plan_id,
        lookback_amount=lookback_amount,
        lookback_unit=lookback_unit,
        status=status,
        rule_name=rule_name,
        data_object_name=data_object_name,
        search=search,
        reason_code=reason_code,
        suite_id=suite_id,
        data_object_version_id=data_object_version_id,
        rule_version_id=rule_version_id,
        repository=repository,
        projection_repository=projection_repository,
        rules_repository=rules_repository,
        data_catalog_repository=data_catalog_repository,
        validation_run_plan_repository=validation_run_plan_repository,
        admin_repository=admin_repository,
        violation_repository=violation_repository,
    )
    fact_views = _build_semantic_exception_fact_views(rows, correlation_id=correlation_id)
    page_rows = fact_views[offset : offset + limit]
    return ExceptionFactsPageView.model_validate(
        {
            "data": page_rows,
            "pagination": build_offset_pagination(total=len(fact_views), offset=offset, limit=limit),
        }
    )


@router.get(
    "/execution-plans/{execution_plan_id}/exception-summary/records/{exception_fact_id}",
    response_model=ExceptionFactView,
    responses={
        200: {"description": "One execution-plan-scoped semantic exception record."},
        404: {"description": "Exception record not found."},
        503: {"description": "Semantic exception record detail is unavailable."},
    },
)
async def get_execution_plan_exception_summary_record(
    request: Request,
    execution_plan_id: str,
    exception_fact_id: str,
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
    projection_repository: ExceptionReasonAnalyticsProjectionRepository = Depends(get_exception_reason_analytics_projection_repository),
    rules_repository: RulesRepository = Depends(get_rules_repository),
    data_catalog_repository: DataCatalogRepository = Depends(get_data_catalog_repository),
    validation_run_plan_repository: ValidationRunPlanRepository = Depends(get_validation_run_plan_repository),
    admin_repository: AdminRepository = Depends(get_admin_repository),
    violation_repository: ExceptionFactRepository = Depends(get_exception_fact_repository),
) -> ExceptionFactView:
    correlation_id = request.headers.get("X-Correlation-ID") or ""
    _result, rows, _workspace_id = await _load_semantic_exception_scope_rows(
        request=request,
        scope_kind="execution_plan",
        scope_id=execution_plan_id,
        lookback_amount=lookback_amount,
        lookback_unit=lookback_unit,
        status=status,
        rule_name=rule_name,
        data_object_name=data_object_name,
        search=search,
        reason_code=reason_code,
        suite_id=suite_id,
        data_object_version_id=data_object_version_id,
        rule_version_id=rule_version_id,
        repository=repository,
        projection_repository=projection_repository,
        rules_repository=rules_repository,
        data_catalog_repository=data_catalog_repository,
        validation_run_plan_repository=validation_run_plan_repository,
        admin_repository=admin_repository,
        violation_repository=violation_repository,
    )
    matching_row = next(
        (
            row
            for row in rows
            if str(getattr(row, "id", None) or "").strip() == exception_fact_id
        ),
        None,
    )
    if matching_row is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "exception_fact_not_found",
                "message": f"Exception record '{exception_fact_id}' not found",
                "exception_fact_id": exception_fact_id,
                "execution_plan_id": execution_plan_id,
                "correlation_id": correlation_id,
            },
        )
    try:
        return ExceptionFactView.model_validate(_build_exception_fact_payload(matching_row))
    except ValueError as exc:
        raise _exception_fact_contract_error(correlation_id=correlation_id, message=str(exc)) from exc