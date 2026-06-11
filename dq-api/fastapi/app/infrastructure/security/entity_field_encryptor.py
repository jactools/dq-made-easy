from __future__ import annotations

import json
import os
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from cryptography.fernet import Fernet
from cryptography.fernet import InvalidToken
from pydantic import BaseModel


_ENCRYPTION_PREFIX = "enc:v1:"


class EncryptionConfigurationError(RuntimeError):
    pass


class EncryptionPayloadError(RuntimeError):
    pass


def _to_mapping(payload: Mapping[str, Any] | BaseModel) -> dict[str, Any]:
    if isinstance(payload, BaseModel):
        return payload.model_dump()
    return dict(payload)


def _resolve_env_key(env_var_names: tuple[str, ...]) -> str:
    for env_var_name in env_var_names:
        raw_value = str(os.getenv(env_var_name) or "").strip()
        if raw_value:
            return raw_value
    joined_names = ", ".join(env_var_names)
    raise EncryptionConfigurationError(f"Missing encryption key. Set one of: {joined_names}")


@dataclass(frozen=True, slots=True)
class EntityFieldEncryptor:
    _fernet: Fernet
    _prefix: str = _ENCRYPTION_PREFIX

    @classmethod
    def from_env(cls, *env_var_names: str) -> "EntityFieldEncryptor":
        names = tuple(env_var_names) if env_var_names else ("APP_CONFIG_ENCRYPTION_KEY",)
        return cls.from_key(_resolve_env_key(names))

    @classmethod
    def from_key(cls, key: str) -> "EntityFieldEncryptor":
        raw_key = str(key or "").strip()
        if not raw_key:
            raise EncryptionConfigurationError("Encryption key cannot be empty")
        try:
            return cls(Fernet(raw_key.encode("utf-8")))
        except Exception as exc:
            raise EncryptionConfigurationError("Encryption key is invalid") from exc

    def encrypt_value(self, value: Any) -> str:
        plaintext = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        token = self._fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")
        return f"{self._prefix}{token}"

    def decrypt_value(self, value: Any) -> Any:
        if value is None:
            return None

        text_value = str(value)
        if not text_value:
            return ""
        if not text_value.startswith(self._prefix):
            raise EncryptionPayloadError("Encrypted value is missing the expected prefix")

        token = text_value[len(self._prefix) :]
        try:
            plaintext = self._fernet.decrypt(token.encode("utf-8")).decode("utf-8")
        except InvalidToken as exc:
            raise EncryptionPayloadError("Encrypted value could not be decrypted") from exc
        return json.loads(plaintext)

    def encrypt_attributes(
        self,
        payload: Mapping[str, Any] | BaseModel,
        attribute_names: Iterable[str] | None = None,
    ) -> dict[str, Any]:
        data = _to_mapping(payload)
        names = tuple(data.keys()) if attribute_names is None else tuple(attribute_names)
        transformed = dict(data)

        for attribute_name in names:
            if attribute_name in transformed:
                transformed[attribute_name] = self.encrypt_value(transformed[attribute_name])

        return transformed

    def decrypt_attributes(
        self,
        payload: Mapping[str, Any] | BaseModel,
        attribute_names: Iterable[str] | None = None,
    ) -> dict[str, Any]:
        data = _to_mapping(payload)
        names = tuple(data.keys()) if attribute_names is None else tuple(attribute_names)
        transformed = dict(data)

        for attribute_name in names:
            if attribute_name in transformed:
                transformed[attribute_name] = self.decrypt_value(transformed[attribute_name])

        return transformed

    def encrypt_entity(self, payload: Mapping[str, Any] | BaseModel) -> dict[str, Any]:
        return self.encrypt_attributes(payload)

    def decrypt_entity(self, payload: Mapping[str, Any] | BaseModel) -> dict[str, Any]:
        return self.decrypt_attributes(payload)