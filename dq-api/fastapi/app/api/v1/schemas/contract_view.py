from __future__ import annotations

from pydantic import ConfigDict

from app.schemas.pydantic_base import SnakeModel, to_snake_alias


class ContractImportRequestView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    contractText: str
    contractFormat: str | None = None
