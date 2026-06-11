from app.api.v1.schemas.health_view import HealthView, ReadinessView
from app.api.v1.schemas.system_view import SystemInfoView


def resolve_health_view(payload: dict) -> HealthView:
    return HealthView.model_validate(payload)


def resolve_readiness_view(payload: dict) -> ReadinessView:
    return ReadinessView.model_validate(payload)


def resolve_system_info_view(payload: dict) -> SystemInfoView:
    return SystemInfoView.model_validate(payload)
