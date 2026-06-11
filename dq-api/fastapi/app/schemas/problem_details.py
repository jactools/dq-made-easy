from pydantic import ConfigDict

from app.schemas.pydantic_base import SnakeModel, to_snake_alias


class ProblemDetails(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    type: str
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None
    correlation_id: str | None = None
