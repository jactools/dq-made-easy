from __future__ import annotations

from typing import Any

from pydantic import Field

from app.domain.entities.base import EntityModel


class WorkspaceEntity(EntityModel):
    id: str
    name: str
    description: str = ""
    alertRoutingPolicy: dict[str, Any] = Field(default_factory=dict)
