from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.api.v1.schemas import HealthScorecardPageView
from app.application.services.health_scorecards import HealthScorecardsQuery
from app.application.services.health_scorecards import get_health_scorecards
from app.core.dependencies import get_data_asset_repository
from app.core.dependencies import get_data_catalog_repository
from app.core.dependencies import get_exception_reason_analytics_projection_repository
from app.core.dependencies import get_gx_execution_run_repository
from app.core.dependencies import get_gx_run_plan_repository
from app.core.dependencies import get_gx_suite_repository
from app.core.dependencies import get_incident_repository
from app.core.dependencies import get_rules_repository
from app.domain.interfaces.v1.data_asset_repository import DataAssetRepository
from app.domain.interfaces.v1.data_catalog_repository import DataCatalogRepository
from app.domain.interfaces.v1.exception_reason_analytics_projection_repository import ExceptionReasonAnalyticsProjectionRepository
from app.domain.interfaces.v1.gx_execution_run_repository import GxExecutionRunRepository
from app.domain.interfaces.v1.gx_run_plan_repository import GxRunPlanRepository
from app.domain.interfaces.v1.gx_suite_repository import GxSuiteRepository
from app.domain.interfaces.v1.incident_repository import IncidentRepository
from app.domain.interfaces.v1.rules_repository import RulesRepository
from dq_domain_validation import LookbackUnit

router = APIRouter(tags=["observability"])


@router.get("/observability/health-scorecards", response_model=HealthScorecardPageView)
async def list_health_scorecards(
    request: Request,
    workspace_id: str | None = Query(default=None, alias="workspaceId"),
    data_asset_id: str | None = Query(default=None, alias="dataAssetId"),
    lookback_amount: int = Query(default=24, ge=1, le=720, alias="lookbackAmount"),
    lookback_unit: LookbackUnit = Query(default="hours", alias="lookbackUnit"),
    data_asset_repository: DataAssetRepository = Depends(get_data_asset_repository),
    run_repository: GxExecutionRunRepository = Depends(get_gx_execution_run_repository),
    run_plan_repository: GxRunPlanRepository = Depends(get_gx_run_plan_repository),
    rules_repository: RulesRepository = Depends(get_rules_repository),
    data_catalog_repository: DataCatalogRepository = Depends(get_data_catalog_repository),
    suite_repository: GxSuiteRepository = Depends(get_gx_suite_repository),
    projection_repository: ExceptionReasonAnalyticsProjectionRepository = Depends(get_exception_reason_analytics_projection_repository),
    incident_repository: IncidentRepository = Depends(get_incident_repository),
) -> HealthScorecardPageView:
    correlation_id = request.headers.get("X-Correlation-ID") or f"corr-{uuid4().hex[:12]}"

    try:
        payload = await get_health_scorecards(
            query=HealthScorecardsQuery(
                workspace_id=workspace_id,
                data_asset_id=data_asset_id,
                lookback_amount=lookback_amount,
                lookback_unit=lookback_unit,
            ),
            data_asset_repository=data_asset_repository,
            run_repository=run_repository,
            run_plan_repository=run_plan_repository,
            rules_repository=rules_repository,
            data_catalog_repository=data_catalog_repository,
            suite_repository=suite_repository,
            projection_repository=projection_repository,
            incident_repository=incident_repository,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "health_scorecards_unavailable",
                "message": "Health scorecards are unavailable",
                "correlation_id": correlation_id,
                "exception": exc.__class__.__name__,
            },
        ) from exc

    return HealthScorecardPageView.model_validate(payload)
