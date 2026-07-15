from __future__ import annotations

from pydantic import Field, HttpUrl

from app.schemas.pydantic_base import SnakeModel, to_snake_alias
from pydantic import ConfigDict


class UiRegistryAssetImportRequestView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    sourceUrl: HttpUrl
    kind: str = Field(default="style")
    filename: str | None = None


class UiRegistryAssetImportResponseView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    kind: str
    sourceUrl: str
    fileName: str
    contentType: str | None = None
    assetPath: str
    publicUrl: str
    byteCount: int