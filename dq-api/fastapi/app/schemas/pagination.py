from pydantic import ConfigDict, Field

from app.schemas.pydantic_base import SnakeModel, to_snake_alias


class PaginationMeta(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    page: int = Field(default=1, ge=1)
    size: int = Field(default=50, ge=1, le=500)
    total: int = Field(default=0, ge=0)


class PaginationParams(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    page: int = Field(default=1, ge=1)
    size: int = Field(default=50, ge=1, le=500)


class PaginatedResponse(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    data: list[dict]
    pagination: PaginationMeta
