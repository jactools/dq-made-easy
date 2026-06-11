from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.api.v1.gx_assistance_api import send_itsm_request
from app.api.v1.schemas import SlaSloDefinitionReviewView
from app.api.v1.schemas import SlaSloEvaluationView
from app.api.v1.schemas import SlaSloDefinitionUpsertView
from app.api.v1.schemas import SlaSloDefinitionView
from app.api.v1.schemas import SlaSloSummaryView
from app.application.use_cases.sla_slo_management import SlaSloSummaryQuery
from app.application.use_cases.sla_slo_management import approve_sla_slo_definition as approve_sla_slo_definition_use_case
from app.application.use_cases.sla_slo_management import create_sla_slo_definition as create_sla_slo_definition_use_case
from app.application.use_cases.sla_slo_management import evaluate_sla_slo_breaches as evaluate_sla_slo_breaches_use_case
from app.application.use_cases.sla_slo_management import get_sla_slo_summary as get_sla_slo_summary_use_case
from app.application.use_cases.sla_slo_management import update_sla_slo_definition as update_sla_slo_definition_use_case
from app.core.dependencies import get_app_config_repository
from app.core.dependencies import get_dq_result_event_repository
from app.core.dependencies import get_sla_slo_repository
from app.core.request_context import get_user_id
from app.domain.interfaces import AppConfigRepository
from app.domain.interfaces import DqResultEventRepository
from app.domain.interfaces import SlaSloRepository

router = APIRouter(prefix="/service-levels", tags=["observability"])


@router.get("", response_model=SlaSloSummaryView)
async def list_service_levels(
    workspace_id: str | None = None,
    status: str | None = None,
    scope_kind: str | None = None,
    metric_kind: str | None = None,
    repository: SlaSloRepository = Depends(get_sla_slo_repository),
    dq_result_event_repository: DqResultEventRepository = Depends(get_dq_result_event_repository),
) -> SlaSloSummaryView:
    summary = await get_sla_slo_summary_use_case(
        query=SlaSloSummaryQuery(
            workspace_id=workspace_id,
            status=status,
            scope_kind=scope_kind,
            metric_kind=metric_kind,
        ),
        repository=repository,
        dq_result_event_repository=dq_result_event_repository,
    )
    return SlaSloSummaryView.model_validate(summary)


@router.post("", response_model=SlaSloDefinitionView, status_code=201)
async def create_service_level(
    request: Request,
    payload: SlaSloDefinitionUpsertView,
    repository: SlaSloRepository = Depends(get_sla_slo_repository),
) -> SlaSloDefinitionView:
    actor_id = str(getattr(request.state, "user_id", None) or get_user_id() or "").strip() or None
    created = await create_sla_slo_definition_use_case(
        payload=payload.model_dump(by_alias=True, exclude_none=True),
        repository=repository,
        actor_id=actor_id,
    )
    return SlaSloDefinitionView.model_validate(created)


@router.put("/{definition_id}", response_model=SlaSloDefinitionView)
async def update_service_level(
    request: Request,
    definition_id: str,
    payload: SlaSloDefinitionUpsertView,
    repository: SlaSloRepository = Depends(get_sla_slo_repository),
) -> SlaSloDefinitionView:
    actor_id = str(getattr(request.state, "user_id", None) or get_user_id() or "").strip() or None
    updated = await update_sla_slo_definition_use_case(
        definition_id=definition_id,
        payload=payload.model_dump(by_alias=True, exclude_none=True),
        repository=repository,
        actor_id=actor_id,
    )
    return SlaSloDefinitionView.model_validate(updated)


@router.post("/{definition_id}/approve", response_model=SlaSloDefinitionView)
async def approve_service_level(
    request: Request,
    definition_id: str,
    payload: SlaSloDefinitionReviewView,
    repository: SlaSloRepository = Depends(get_sla_slo_repository),
    app_config_repository: AppConfigRepository = Depends(get_app_config_repository),
) -> SlaSloDefinitionView:
    actor_id = str(getattr(request.state, "user_id", None) or get_user_id() or "").strip() or None
    correlation_id = str(request.headers.get("x-correlation-id") or "").strip() or f"corr-{uuid4().hex[:12]}"
    approved = await approve_sla_slo_definition_use_case(
        definition_id=definition_id,
        payload=payload.model_dump(by_alias=True, exclude_none=True),
        repository=repository,
        app_config_repository=app_config_repository,
        send_itsm_request=send_itsm_request,
        correlation_id=correlation_id,
        actor_id=actor_id,
    )
    return SlaSloDefinitionView.model_validate(approved)


@router.post("/evaluate", response_model=SlaSloEvaluationView)
async def evaluate_service_levels(
    workspace_id: str | None = Query(default=None, alias="workspace_id"),
    repository: SlaSloRepository = Depends(get_sla_slo_repository),
    dq_result_event_repository: DqResultEventRepository = Depends(get_dq_result_event_repository),
) -> SlaSloEvaluationView:
    if not workspace_id:
        raise HTTPException(status_code=400, detail={"error": "workspace_id_required", "message": "workspace_id is required"})

    payload = await evaluate_sla_slo_breaches_use_case(
        workspace_id=workspace_id,
        repository=repository,
        dq_result_event_repository=dq_result_event_repository,
    )
    return SlaSloEvaluationView.model_validate(payload)
