from pydantic import ConfigDict

from app.schemas.pydantic_base import SnakeModel, to_snake_alias


class PaginationView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    total: int
    page: int
    limit: int
    total_pages: int
    has_next: bool
    has_previous: bool


class OkResponseView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    ok: bool


class IdResponseView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    id: str
