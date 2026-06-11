from __future__ import annotations

from typing import Any

from pydantic import ConfigDict, Field

from app.schemas.pydantic_base import SnakeModel, to_snake_alias


class RegistryDefinitionValueDomainView(SnakeModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=to_snake_alias)

    type: str | None = None
    format: str | None = None
    unit: str | None = None
    allowed_values: list[str] = Field(default_factory=list)
    constraints: dict[str, Any] = Field(default_factory=dict)


class RegistryDefinitionProvenanceView(SnakeModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=to_snake_alias)

    created_by: str | None = None
    approved_by: str | None = None
    created_at: str | None = None
    approved_at: str | None = None
    change_reason: str | None = None


class RegistryDefinitionView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=to_snake_alias)

    definition_id: str
    definition_type: str
    definition_name: str
    business_definition: str
    glossary_id: str = ""
    glossary_name: str = ""
    object_class: str = ""
    property: str = ""
    representation_term: str = ""
    value_domain: RegistryDefinitionValueDomainView = Field(default_factory=RegistryDefinitionValueDomainView)
    status: str = ""
    owner: str = ""
    synonyms: list[str] = Field(default_factory=list)
    parent_definition_id: str = ""
    parent_definition_name: str = ""
    child_definition_ids: list[str] = Field(default_factory=list)
    child_definition_names: list[str] = Field(default_factory=list)
    child_definition_count: int = 0
    source_system: str = "openmetadata"
    openmetadata_entity_id: str = ""
    openmetadata_entity_type: str = "glossary_term"
    version: str = ""
    provenance: RegistryDefinitionProvenanceView = Field(default_factory=RegistryDefinitionProvenanceView)
    applies_to: list[str] = Field(default_factory=list)