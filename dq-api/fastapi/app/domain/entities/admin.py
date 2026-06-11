from __future__ import annotations

from typing import Any

from pydantic import Field

from app.domain.entities.base import EntityModel
from app.domain.user_names import compose_user_display_name


class AdminRoleEntity(EntityModel):
    id: str
    name: str
    workspace: str = "default"
    permissions: list[str] = Field(default_factory=list)


class ExceptionFactAccessRequestEntity(EntityModel):
    id: str
    requesterId: str
    workspaceId: str
    roleId: str
    status: str = "pending"
    requestedDurationMinutes: int = 0
    comments: str | None = None
    requestedAt: str = ""
    reviewedBy: str | None = None
    reviewedAt: str | None = None
    expiresAt: str | None = None

class UserWorkspaceRoleEntity(EntityModel):
    workspace_id: str
    role: str


class AdminUserEntity(EntityModel):
    id: str
    first_name: str
    last_name: str
    email: str | None = None
    roles: list[str] = Field(default_factory=list)
    granted_scopes: list[str] = Field(default_factory=list)
    workspaces: list[str] = Field(default_factory=list)
    workspace_roles: list[UserWorkspaceRoleEntity] = Field(default_factory=list)
    preferences: dict[str, Any] = Field(default_factory=dict)
    external_id: str | None = None

    @property
    def display_name(self) -> str:
        return compose_user_display_name(self.first_name, self.last_name, fallback=self.email or self.id)
