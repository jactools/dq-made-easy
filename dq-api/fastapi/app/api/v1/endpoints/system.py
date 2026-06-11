import os

from fastapi import APIRouter, Depends, Query, Request

from app.api.presenters.system import build_suggestions_metrics_payload
from app.api.presenters.system import build_system_build_date
from app.api.presenters.system import build_system_info_payload
from app.api.presenters.system import serialize_system_entity
from app.api.v1.schemas import SystemInfoView, VersionCatalogView
from app.application.resolvers import resolve_system_info_view
from app.application.services import build_version_catalog
from app.core.auth_login_metrics import auth_login_metrics_store
from app.core.api_metrics import api_metrics_store
from app.core.dependencies import get_app_config_repository
from app.core.dependencies import get_system_repository
from app.domain.interfaces import AppConfigRepository
from app.domain.interfaces import SystemRepository

router = APIRouter(tags=["system"])


def _serialize_entity(entity) -> dict:
    return serialize_system_entity(entity)


def _build_date() -> str:
    return build_system_build_date(os.getenv("BUILD_DATE"))


@router.get("/system-info", response_model=SystemInfoView)
async def get_system_info(
    request: Request,
    repository: SystemRepository = Depends(get_system_repository),
    app_config_repository: AppConfigRepository = Depends(get_app_config_repository),
) -> SystemInfoView:
    db_info = repository.get_system_info()
    app_config = app_config_repository.get_app_config()
    version_catalog = build_version_catalog(request, app_config_repository)
    return resolve_system_info_view(
        build_system_info_payload(
            db_info=db_info,
            app_config=app_config,
            version_catalog=version_catalog,
            build_date=_build_date(),
        )
    )


@router.get("/version-catalog", response_model=VersionCatalogView)
async def get_version_catalog(
    request: Request,
    app_config_repository: AppConfigRepository = Depends(get_app_config_repository),
) -> VersionCatalogView:
    return VersionCatalogView.model_validate(build_version_catalog(request, app_config_repository))


@router.get("/suggestions/metrics")
async def get_suggestions_metrics(
    repository: SystemRepository = Depends(get_system_repository),
) -> dict:
    return build_suggestions_metrics_payload(repository.get_suggestions_metrics_summary())


@router.get("/auth-login-metrics")
async def get_auth_login_metrics(
    app_config_repository: AppConfigRepository = Depends(get_app_config_repository),
) -> dict:
    config = app_config_repository.get_app_config()
    retention_days: int = getattr(config, "auditLogRetentionDays", 90) or 90
    return {
        "success": True,
        **auth_login_metrics_store.get_summary(retention_days=retention_days),
    }


@router.get("/api-metrics")
async def get_api_metrics(
    app_config_repository: AppConfigRepository = Depends(get_app_config_repository),
    api_endpoint_filter: str | None = Query(default=None, alias="apiEndpointFilter"),
    api_method_filter: str = Query(default="all", alias="apiMethodFilter"),
    api_min_requests: int = Query(default=0, ge=0, alias="apiMinRequests"),
    recent_error_status_filter: str = Query(default="all", alias="recentErrorStatusFilter"),
    recent_error_path_filter: str | None = Query(default=None, alias="recentErrorPathFilter"),
    exclude_health_endpoints: bool = Query(default=False, alias="excludeHealthEndpoints"),
) -> dict:
    """Return API request metrics aggregated from the in-process store.

    Filtering is applied based on the Application Settings:
    - ``logLevel``              — controls which error statuses appear in
                                  *recentErrors* (error→5xx, warn/info→4xx+5xx,
                                  debug→all)
    - ``auditLogRetentionDays`` — only include requests recorded within this
                                  many days
    """
    config = app_config_repository.get_app_config()
    retention_days: int = getattr(config, "auditLogRetentionDays", 90) or 90
    log_level: str = getattr(config, "logLevel", "info") or "info"
    return {
        "success": True,
        **api_metrics_store.get_summary(
            retention_days=retention_days,
            log_level=log_level,
            endpoint_filter=api_endpoint_filter,
            method_filter=api_method_filter,
            min_requests=api_min_requests,
            recent_error_status_filter=recent_error_status_filter,
            recent_error_path_filter=recent_error_path_filter,
            exclude_health_endpoints=exclude_health_endpoints,
        ),
    }


@router.post("/api-metrics/ping")
async def ping_api_metrics() -> dict:
    """Seed a tracked API metric event so trend charts can initialize quickly."""
    api_metrics_store.record(
        method="POST",
        path="/system/v1/api-metrics/ping",
        status_code=200,
        duration_ms=1.0,
        error_detail=None,
    )
    return {"success": True}