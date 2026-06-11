from typing import Any

from pydantic import ConfigDict, Field

from app.api.v1.schemas.common_view import PaginationView
from app.schemas.pydantic_base import SnakeModel, to_snake_alias


class AdminWorkspaceRoleView(SnakeModel):
    workspace_id: str
    role: str


class AdminUserView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    id: str
    first_name: str
    last_name: str
    email: str | None = None
    roles: list[str] = Field(default_factory=list)
    granted_scopes: list[str] = Field(default_factory=list)
    workspaces: list[str] = Field(default_factory=list)
    workspace_roles: list[AdminWorkspaceRoleView] = Field(default_factory=list)
    preferences: dict[str, Any] = Field(default_factory=dict)
    external_id: str | None = None


class AdminRoleView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    id: str
    name: str
    workspace: str = "default"
    permissions: list[str] = Field(default_factory=list)


class ExceptionFactAccessRequestView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    id: str
    requester_id: str
    workspace_id: str
    role_id: str
    status: str = "pending"
    requested_duration_minutes: int = 0
    comments: str | None = None
    requested_at: str = ""
    reviewed_by: str | None = None
    reviewed_at: str | None = None
    expires_at: str | None = None


class AdminUsersPageView(SnakeModel):
    data: list[AdminUserView]
    pagination: PaginationView
