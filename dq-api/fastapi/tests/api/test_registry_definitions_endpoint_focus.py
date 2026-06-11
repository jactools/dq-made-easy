from __future__ import annotations

import pytest

from app.api.v1.endpoints.registry_definitions import get_registry_definition
from app.api.v1.endpoints.registry_definitions import list_registry_definitions
from app.application.services.registry_definition_resolver import RegistryDefinitionLookupError


_PAYLOAD = {
    "definition_id": "def.attribute.customer_id",
    "definition_type": "attribute",
    "definition_name": "customer_id",
    "business_definition": "Customer identifier.",
    "object_class": "customer",
    "property": "identifier",
    "representation_term": "identifier",
    "value_domain": {"type": "string", "format": "uuid"},
    "status": "approved",
    "owner": "data-governance",
    "source_system": "openmetadata",
    "openmetadata_entity_id": "om-term-1",
    "openmetadata_entity_type": "glossary_term",
    "version": "1.0.0",
    "provenance": {"created_by": "platform", "approved_by": "data-governance"},
    "applies_to": ["data_object:customer"],
}


class _GetResolver:
    def __init__(self, *, error: RegistryDefinitionLookupError | None = None) -> None:
        self.error = error
        self.last_definition_id: str | None = None

    async def resolve_definition(self, definition_id: str) -> dict:
        self.last_definition_id = definition_id
        if self.error is not None:
            raise self.error
        return dict(_PAYLOAD)


class _ListResolver:
    def __init__(self, *, error: RegistryDefinitionLookupError | None = None) -> None:
        self.error = error
        self.last_kwargs: dict | None = None

    async def list_definitions(self, *, query=None, definition_type=None, limit=50):
        self.last_kwargs = {"query": query, "definition_type": definition_type, "limit": limit}
        if self.error is not None:
            raise self.error
        return [dict(_PAYLOAD)]


@pytest.mark.anyio
async def test_get_registry_definition_returns_view() -> None:
    resolver = _GetResolver()

    result = await get_registry_definition("def.attribute.customer_id", resolver=resolver)

    assert resolver.last_definition_id == "def.attribute.customer_id"
    assert result.definition_id == "def.attribute.customer_id"
    assert result.definition_type == "attribute"
    assert result.value_domain.format == "uuid"


@pytest.mark.anyio
async def test_get_registry_definition_maps_lookup_errors() -> None:
    resolver = _GetResolver(
        error=RegistryDefinitionLookupError("OpenMetadata is unavailable while resolving registry definitions", status_code=503)
    )

    with pytest.raises(Exception) as exc_info:
        await get_registry_definition("def.attribute.customer_id", resolver=resolver)

    assert getattr(exc_info.value, "status_code", None) == 503
    assert exc_info.value.detail["error"] == "registry_definition_unavailable"
    assert exc_info.value.detail["definition_id"] == "def.attribute.customer_id"


@pytest.mark.anyio
async def test_list_registry_definitions_returns_views() -> None:
    resolver = _ListResolver()

    result = await list_registry_definitions(query="customer", definition_type="attribute", limit=10, resolver=resolver)

    assert resolver.last_kwargs == {"query": "customer", "definition_type": "attribute", "limit": 10}
    assert len(result) == 1
    assert result[0].definition_id == "def.attribute.customer_id"


@pytest.mark.anyio
async def test_list_registry_definitions_maps_lookup_errors() -> None:
    resolver = _ListResolver(
        error=RegistryDefinitionLookupError("Registry definition search failed", status_code=404)
    )

    with pytest.raises(Exception) as exc_info:
        await list_registry_definitions(query=None, definition_type=None, limit=50, resolver=resolver)

    assert getattr(exc_info.value, "status_code", None) == 404
    assert exc_info.value.detail["error"] == "registry_definition_not_found"
    assert exc_info.value.detail["definition_id"] == "registry-definition-search"