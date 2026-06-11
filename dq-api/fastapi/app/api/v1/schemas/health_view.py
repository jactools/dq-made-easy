from pydantic import ConfigDict

from app.schemas.pydantic_base import SnakeModel, to_snake_alias


class HealthView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    status: str
    timestamp: str


class ReadinessChecksView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    api: str


class ReadinessView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    status: str
    checks: ReadinessChecksView
    timestamp: str
