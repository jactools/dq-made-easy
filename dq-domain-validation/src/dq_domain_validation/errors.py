from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class DomainValidationError(ValueError):
    set_name: str
    value: Any
    allowed_values: tuple[str, ...]
    field_name: str | None = None

    def __str__(self) -> str:
        label = self.field_name or self.set_name
        return f"{label} must be one of: {', '.join(self.allowed_values)}"
