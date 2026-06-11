from typing import Any

from pydantic import ConfigDict, Field

from app.api.v1.schemas.common_view import OkResponseView
from app.schemas.pydantic_base import SnakeModel, to_snake_alias


class LoginWorkspaceRoleView(SnakeModel):
    workspace_id: str
    role: str


class LoginResponseView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    id: str
    first_name: str
    last_name: str
    email: str | None = None
    roles: list[str] = Field(default_factory=list)
    granted_scopes: list[str] = Field(default_factory=list)
    workspaces: str | list[str] = Field(default_factory=list)
    workspace_roles: list[LoginWorkspaceRoleView] = Field(default_factory=list)
    workspace: str | None = None
    preferences: dict[str, Any] = Field(default_factory=dict)
    external_id: str | None = None
    token: str


class LogoutResponseView(OkResponseView):
    pass
