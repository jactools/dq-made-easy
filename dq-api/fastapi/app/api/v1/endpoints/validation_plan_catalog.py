from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.v1 import validation_plan_catalog_api as _validation_plan_catalog_api
from app.api.v1.schemas.validation_plan_catalog_view import ValidationPlanCatalogView
from app.core.dependencies import get_validation_run_plan_repository
from app.domain.interfaces import ValidationRunPlanRepository

router = APIRouter(prefix="/validation-plan-catalog", tags=["validation-plans"])


@router.get("", response_model=ValidationPlanCatalogView, responses={200: {"description": "Validation plan and suite catalog."}})
async def list_validation_plan_catalog(
    workspace_id: str | None = Query(default=None, alias="workspaceId"),
    business_key: str | None = Query(default=None, alias="businessKey"),
    suite_id: str | None = Query(default=None, alias="suiteId"),
    status: str | None = Query(default=None),
    repository: ValidationRunPlanRepository = Depends(get_validation_run_plan_repository),
) -> ValidationPlanCatalogView:
    return await _validation_plan_catalog_api.list_plan_catalog(
        workspace_id=workspace_id,
        business_key=business_key,
        suite_id=suite_id,
        status=status,
        repository=repository,
    )
