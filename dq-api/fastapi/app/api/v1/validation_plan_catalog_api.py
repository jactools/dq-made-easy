from __future__ import annotations

from app.api.presenters.validation_plan_catalog import build_validation_plan_catalog_view
from app.api.v1.schemas.validation_plan_catalog_view import ValidationPlanCatalogView
from app.domain.interfaces import ValidationRunPlanRepository


async def list_plan_catalog(
    *,
    workspace_id: str | None,
    business_key: str | None,
    suite_id: str | None,
    status: str | None,
    repository: ValidationRunPlanRepository,
) -> ValidationPlanCatalogView:
    rows = await repository.list_plans(
        workspace_id=workspace_id,
        business_key=business_key,
        status=status,
        artifact_id=suite_id,
    )
    return build_validation_plan_catalog_view(rows)
