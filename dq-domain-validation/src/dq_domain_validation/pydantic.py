from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Annotated

from pydantic_core import PydanticCustomError, core_schema

from .errors import DomainValidationError
from .registry import allowed_values
from .registry import validate_allowed_value


@dataclass(frozen=True, slots=True)
class AllowedValue:
    set_name: str
    field_name: str | None = None

    def _validate(self, value: Any) -> str:
        try:
            return validate_allowed_value(self.set_name, value, field_name=self.field_name)
        except DomainValidationError as exc:
            raise PydanticCustomError(
                "domain_allowed_value",
                str(exc),
                {
                    "set_name": exc.set_name,
                    "allowed_values": list(exc.allowed_values),
                    "field_name": exc.field_name,
                },
            ) from exc

    def __get_pydantic_core_schema__(self, source_type: Any, handler: Any) -> core_schema.CoreSchema:
        return core_schema.no_info_after_validator_function(self._validate, handler(str))

    def __get_pydantic_json_schema__(self, core_schema_value: core_schema.CoreSchema, handler: Any) -> dict[str, Any]:
        schema = handler(core_schema_value)
        schema.update(
            {
                "type": "string",
                "enum": list(allowed_values(self.set_name)),
                "x-dq-domain-allowed-values-set": self.set_name,
            }
        )
        return schema


def allowed_value_type(set_name: str, *, field_name: str | None = None) -> Any:
    return Annotated[str, AllowedValue(set_name=set_name, field_name=field_name)]
