from typing import Any

from app.domain.entities.app_config import AppConfigEntity
from app.domain.interfaces.v1.app_config_repository import AppConfigRepository
from app.infrastructure.repositories.app_config_defaults import APP_CONFIG_DEFAULTS
from app.infrastructure.repositories.app_config_defaults import apply_env_sso_overrides
from app.infrastructure.repositories.app_config_defaults import normalize_app_config_payload


class InMemoryAppConfigRepository(AppConfigRepository):
    def __init__(self) -> None:
        self._config = dict(APP_CONFIG_DEFAULTS)

    def get_app_config(self) -> AppConfigEntity:
        return AppConfigEntity(**apply_env_sso_overrides(dict(self._config)))

    def set_app_config(self, payload: dict[str, Any]) -> AppConfigEntity:
        self._config = normalize_app_config_payload(payload)
        return self.get_app_config()
