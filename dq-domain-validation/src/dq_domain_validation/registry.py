from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from typing import Any
import tomllib

from .errors import DomainValidationError


@dataclass(frozen=True, slots=True)
class AllowedValueSet:
    name: str
    values: tuple[str, ...]
    description: str | None = None


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


@lru_cache(maxsize=1)
def _load_manifest() -> dict[str, AllowedValueSet]:
    manifest_path = resources.files("dq_domain_validation.data").joinpath("allowed_values.toml")
    payload = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
    raw_sets = payload.get("allowed_values")
    if not isinstance(raw_sets, dict):
        raise ValueError("allowed_values.toml must define an [allowed_values] table")

    sets: dict[str, AllowedValueSet] = {}
    for set_name, raw_entry in raw_sets.items():
        if not isinstance(raw_entry, dict):
            raise ValueError(f"allowed value set '{set_name}' must be a table")
        raw_values = raw_entry.get("values")
        if not isinstance(raw_values, list):
            raise ValueError(f"allowed value set '{set_name}' must define a values array")
        values = tuple(value for value in (_normalize_text(item) for item in raw_values) if value)
        if not values:
            raise ValueError(f"allowed value set '{set_name}' must define at least one value")
        description = _normalize_text(raw_entry.get("description")) or None
        sets[str(set_name)] = AllowedValueSet(name=str(set_name), values=values, description=description)
    return sets


def available_allowed_value_sets() -> tuple[str, ...]:
    return tuple(sorted(_load_manifest()))


def allowed_values(set_name: str) -> tuple[str, ...]:
    normalized_set_name = _normalize_text(set_name)
    try:
        return _load_manifest()[normalized_set_name].values
    except KeyError as exc:
        raise KeyError(f"Unknown allowed value set '{normalized_set_name}'") from exc


def validate_allowed_value(set_name: str, value: Any, *, field_name: str | None = None) -> str:
    normalized_set_name = _normalize_text(set_name)
    normalized_value = _normalize_text(value)
    allowed = allowed_values(normalized_set_name)
    if normalized_value not in allowed:
        raise DomainValidationError(
            set_name=normalized_set_name,
            value=value,
            allowed_values=allowed,
            field_name=field_name,
        )
    return normalized_value
