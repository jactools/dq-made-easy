from typing import Any, Protocol

from app.domain.entities.app_config import AppConfigEntity


class AppConfigRepository(Protocol):
    def get_app_config(self) -> AppConfigEntity: ...

    def set_app_config(self, payload: dict[str, Any]) -> AppConfigEntity: ...
