from __future__ import annotations

import pytest

from app.application.services.registry_definition_resolver import RegistryDefinitionLookupError
from app.core.dependencies import get_data_catalog_repository
from app.core.dependencies import get_registry_definition_resolver
from app.infrastructure.repositories.in_memory_data_catalog_repository import InMemoryDataCatalogRepository
from app.main import app


class _StubRegistryDefinitionResolver:
    def __init__(self) -> None:
        self._definitions = {
            "def.attribute.customer_active_flag": {
                "definition_id": "def.attribute.customer_active_flag",
                "definition_type": "attribute",
                "definition_name": "Customer active flag",
                "business_definition": "Indicates whether the customer is currently active.",
                "object_class": "Customer",
                "property": "active flag",
                "representation_term": "flag",
                "value_domain": {"type": "boolean"},
                "status": "approved",
                "owner": "Data Governance",
                "source_system": "openmetadata",
                "openmetadata_entity_id": "om-term-active-flag",
                "openmetadata_entity_type": "glossary_term",
                "version": "1.0.0",
                "provenance": {},
                "applies_to": ["customer.is_active"],
            },
            "def.attribute.customer_status": {
                "definition_id": "def.attribute.customer_status",
                "definition_type": "attribute",
                "definition_name": "Customer status",
                "business_definition": "The current lifecycle status for the customer record.",
                "object_class": "Customer",
                "property": "status",
                "representation_term": "code",
                "value_domain": {"type": "string"},
                "status": "approved",
                "owner": "Data Governance",
                "source_system": "openmetadata",
                "openmetadata_entity_id": "om-term-customer-status",
                "openmetadata_entity_type": "glossary_term",
                "version": "1.0.0",
                "provenance": {},
                "applies_to": ["customer.status_reason"],
            },
        }

    async def resolve_definition(self, definition_id: str) -> dict[str, object]:
        payload = self._definitions.get(definition_id)
        if payload is None:
            raise RegistryDefinitionLookupError(
                f"Registry definition '{definition_id}' was not found in OpenMetadata",
                status_code=404,
            )
        return payload

    async def list_definitions(
        self,
        *,
        query: str | None = None,
        definition_type: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, object]]:
        normalized_query = str(query or "").strip().lower()
        normalized_type = str(definition_type or "").strip().lower()
        results: list[dict[str, object]] = []
        for payload in self._definitions.values():
            if normalized_type and str(payload.get("definition_type") or "").lower() != normalized_type:
                continue
            haystack = " ".join(
                [
                    str(payload.get("definition_id") or ""),
                    str(payload.get("definition_name") or ""),
                    str(payload.get("business_definition") or ""),
                ]
            ).lower()
            if normalized_query and normalized_query not in haystack:
                continue
            results.append(payload)
        return results[:limit]


@pytest.fixture(autouse=True)
def isolated_mapping_dependencies() -> None:
    repository = InMemoryDataCatalogRepository()
    resolver = _StubRegistryDefinitionResolver()
    app.dependency_overrides[get_data_catalog_repository] = lambda: repository
    app.dependency_overrides[get_registry_definition_resolver] = lambda: resolver
    yield
    app.dependency_overrides.pop(get_data_catalog_repository, None)
    app.dependency_overrides.pop(get_registry_definition_resolver, None)


def test_attributes_catalog_exposes_inherited_definition_mapping(client, auth_headers) -> None:
    response = client.get(
        "/api/data-catalog/v1/attributes-catalog?versionId=dov-3",
        headers=auth_headers("dq:rules:read"),
    )

    assert response.status_code == 200
    payload = response.json()
    attr_10 = next(row for row in payload["data"] if row["id"] == "attr-10")
    assert attr_10["definition_id"] == "def.attribute.customer_active_flag"
    assert attr_10["definition_mapping_status"] == "inherited"
    assert attr_10["definition_mapping_attribute_id"] == "attr-2v2"
    assert attr_10["definition_mapping_version_id"] == "dov-2"


def test_post_attribute_definition_mapping_overrides_inherited_mapping(client, auth_headers) -> None:
    response = client.post(
        "/api/data-catalog/v1/attribute-definition-mappings",
        headers=auth_headers("dq:rules:write"),
        json={
            "attribute_id": "attr-10",
            "definition_id": "def.attribute.customer_status",
            "mapping_state": "mapped",
            "mapped_by": "steward@example.com",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["attribute_id"] == "attr-10"
    assert payload["definition_id"] == "def.attribute.customer_status"
    assert payload["definition_mapping_status"] == "explicit"

    attributes_response = client.get(
        "/api/data-catalog/v1/attributes-catalog?versionId=dov-3",
        headers=auth_headers("dq:rules:read"),
    )
    assert attributes_response.status_code == 200
    attr_10 = next(row for row in attributes_response.json()["data"] if row["id"] == "attr-10")
    assert attr_10["definition_id"] == "def.attribute.customer_status"
    assert attr_10["definition_mapping_status"] == "explicit"


def test_post_attribute_definition_mapping_fails_fast_for_unknown_definition(client, auth_headers) -> None:
    response = client.post(
        "/api/data-catalog/v1/attribute-definition-mappings",
        headers=auth_headers("dq:rules:write"),
        json={
            "attribute_id": "attr-11",
            "definition_id": "missing.definition",
            "mapping_state": "mapped",
        },
    )

    assert response.status_code == 404
    payload = response.json()
    assert payload["detail"]["error"] == "registry_definition_lookup_failed"
    assert payload["detail"]["definition_id"] == "missing.definition"


def test_list_registry_definitions_supports_query_filter(client, auth_headers) -> None:
    response = client.get(
        "/api/data-catalog/v1/registry/definitions?query=active&definitionType=attribute",
        headers=auth_headers("dq:rules:read"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["definition_id"] == "def.attribute.customer_active_flag"