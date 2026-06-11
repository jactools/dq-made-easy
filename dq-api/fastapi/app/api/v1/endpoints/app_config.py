from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.api.v1.schemas import AppConfigView
from app.application.resolvers import resolve_app_config_view
from app.application.services.status_governance_policy_loader import set_status_model_policy_from_source
from app.core.dependencies import get_app_config_repository
from app.domain.interfaces.v1.app_config_repository import AppConfigRepository

router = APIRouter(tags=["configuration"])


@router.get("/app-config", response_model=AppConfigView)
async def get_app_config(
    repository: AppConfigRepository = Depends(get_app_config_repository),
) -> AppConfigView:
    app_config = repository.get_app_config()
    set_status_model_policy_from_source(app_config)
    return resolve_app_config_view(app_config)


@router.put("/app-config", response_model=AppConfigView)
async def put_app_config(
    payload: dict[str, Any],
    repository: AppConfigRepository = Depends(get_app_config_repository),
) -> AppConfigView:
    try:
        set_status_model_policy_from_source(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    persisted_config = repository.set_app_config(payload)
    set_status_model_policy_from_source(persisted_config)
    return resolve_app_config_view(persisted_config)
