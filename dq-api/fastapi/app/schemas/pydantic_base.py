from __future__ import annotations

import re
from pydantic import BaseModel, ConfigDict


def _to_snake(s: str) -> str:
    """Convert CamelCase/camelCase to snake_case for use as Pydantic alias generator."""
    s = s.replace("PagerDuty", "Pagerduty")
    s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", s)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1).lower()


class SnakeModel(BaseModel):
    """BaseModel that emits snake_case aliases for JSON output.

    Use this as the base for response schemas to ensure canonical
    snake_case API payloads without runtime conversion middleware.
    """

    model_config = ConfigDict(
        alias_generator=_to_snake,
        populate_by_name=True,
        from_attributes=True,
    )


# Export a convenient name for use in other modules when they need the
# alias generator in local `ConfigDict` merges.
to_snake_alias = _to_snake
