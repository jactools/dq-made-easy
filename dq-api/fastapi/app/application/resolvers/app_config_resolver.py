from app.api.v1.schemas.app_config_view import AppConfigView
from app.domain.entities import AppConfigEntity
from app.infrastructure.repositories.app_config_defaults import APP_CONFIG_ENCRYPTED_KEYS


def resolve_app_config_view(entity: AppConfigEntity) -> AppConfigView:
    payload = entity.model_dump()
    for key in APP_CONFIG_ENCRYPTED_KEYS:
        if key in payload:
            payload[key] = ""
    return AppConfigView.model_validate(payload)
