from typing import Any

from pydantic import ConfigDict, Field

from app.api.v1.schemas.common_view import PaginationView
from app.schemas.pydantic_base import SnakeModel, to_snake_alias


class WorkspaceView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    id: str
    name: str
    description: str = ""
    alertRoutingPolicy: dict[str, Any] = Field(default_factory=dict)


class WorkspacesPageView(SnakeModel):
    data: list[WorkspaceView]
    pagination: PaginationView
