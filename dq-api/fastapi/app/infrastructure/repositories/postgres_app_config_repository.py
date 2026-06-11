from typing import Any
import ast
import json
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.domain.entities.app_config import AppConfigEntity
from app.domain.interfaces.v1.app_config_repository import AppConfigRepository
from app.infrastructure.orm.models import AppConfigRow
from app.infrastructure.orm.session import session_scope
from app.infrastructure.repositories.app_config_defaults import APP_CONFIG_DEFAULTS
from app.infrastructure.repositories.app_config_defaults import APP_CONFIG_KEY_MAP
from app.infrastructure.repositories.app_config_defaults import APP_CONFIG_REVERSE_KEY_MAP
from app.infrastructure.repositories.app_config_defaults import APP_CONFIG_ENCRYPTED_KEYS
from app.infrastructure.repositories.app_config_defaults import apply_env_sso_overrides
from app.infrastructure.repositories.app_config_defaults import infer_app_config_value_type
from app.infrastructure.repositories.app_config_defaults import normalize_app_config_payload
from app.infrastructure.repositories.app_config_defaults import serialize_app_config_value
from app.infrastructure.security import EntityFieldEncryptor


class PostgresAppConfigRepository(AppConfigRepository):
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        self._field_encryptor = EntityFieldEncryptor.from_env()

    def get_app_config(self) -> AppConfigEntity:
        config: dict[str, Any] = dict(APP_CONFIG_DEFAULTS)

        rows = self._fetch_all()
        for row in rows:
            key = str(row.get("config_key") or row.get("configKey") or "").lower()
            target_key = APP_CONFIG_KEY_MAP.get(key)
            if not target_key:
                continue
            raw_value = row.get("config_value")
            if raw_value is None:
                raw_value = row.get("configValue")
            if raw_value is None:
                raw_value = row.get("value")
            expected_type = infer_app_config_value_type(target_key)
            parsed = self._coerce_value(raw_value, expected_type)
            if parsed is not None:
                if target_key in APP_CONFIG_ENCRYPTED_KEYS:
                    parsed = self._field_encryptor.decrypt_value(parsed)
                config[target_key] = parsed

        return AppConfigEntity(**apply_env_sso_overrides(config))

    def set_app_config(self, payload: dict[str, Any]) -> AppConfigEntity:
        normalized = normalize_app_config_payload(payload)
        encrypted_payload = self._field_encryptor.encrypt_attributes(normalized, APP_CONFIG_ENCRYPTED_KEYS)

        for target_key, value in encrypted_payload.items():
            config_key = APP_CONFIG_REVERSE_KEY_MAP[target_key]
            value_type = infer_app_config_value_type(target_key)
            self._upsert(
                config_key,
                serialize_app_config_value(value, value_type),
                value_type,
            )

        return self.get_app_config()

    def _coerce_value(self, value: Any, value_type: str) -> Any:
        if value is None:
            return None

        normalized_type = value_type.lower()
        if normalized_type == "number":
            try:
                parsed = float(value)
            except (TypeError, ValueError):
                return None
            return int(parsed) if parsed.is_integer() else parsed

        if normalized_type == "boolean":
            if isinstance(value, bool):
                return value
            return str(value).strip().lower() in {"true", "1", "t", "yes"}

        if normalized_type == "json":
            try:
                return json.loads(value) if isinstance(value, str) else value
            except Exception:
                if not isinstance(value, str):
                    return None
                try:
                    return ast.literal_eval(value)
                except (ValueError, SyntaxError):
                    return None

        return str(value)

    def _infer_type(self, key: str) -> str:
        return infer_app_config_value_type(key)

    def _fetch_all(self) -> list[dict[str, Any]]:
        with session_scope(self.database_url) as session:
            rows = session.execute(select(AppConfigRow)).scalars().all()
            return [
                {
                    "config_key": row.config_key,
                    "config_value": row.config_value,
                    "value_type": row.value_type,
                }
                for row in rows
            ]

    def _upsert(self, config_key: str, config_value: str, value_type: str) -> None:
        with session_scope(self.database_url) as session:
            stmt = insert(AppConfigRow).values(
                config_key=config_key,
                config_value=config_value,
                value_type=value_type,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=[AppConfigRow.config_key],
                set_={
                    "config_value": stmt.excluded.config_value,
                    "value_type": stmt.excluded.value_type,
                },
            )
            session.execute(stmt)
            session.commit()


