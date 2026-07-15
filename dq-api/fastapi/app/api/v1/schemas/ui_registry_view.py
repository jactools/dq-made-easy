from __future__ import annotations

from typing import Any

from pydantic import Field
from pydantic import ConfigDict

from app.schemas.pydantic_base import SnakeModel, to_snake_alias


class UiRegistryStyleView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    id: str
    label: str
    description: str | None = None
    sourceRef: str | None = None
    cssUrl: str | None = None
    fallback: str = "ignore"
    priority: int = 0
    isActive: bool = True


class UiRegistryComponentBundleView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    id: str
    label: str
    description: str | None = None
    adapter: str | None = None
    fallback: str = "ignore"
    priority: int = 0
    isActive: bool = True


class UiRegistryView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    source: str
    version: str
    created: str | None = None
    updated: str | None = None
    cacheTtlSeconds: int = 300
    styles: list[UiRegistryStyleView] = Field(default_factory=list)
    componentBundles: list[UiRegistryComponentBundleView] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)