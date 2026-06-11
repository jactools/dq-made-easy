import pytest

from app.application.services.registry_definition_resolver import RegistryDefinitionLookupError
from app.core.dependencies import get_registry_definition_resolver


class _Resolver:
    def __init__(self, payload=None, error: RegistryDefinitionLookupError | None = None) -> None:
        self._payload = payload
        self._error = error

    async def resolve_definition(self, definition_id: str) -> dict:
        if self._error is not None:
            raise self._error
        payload = dict(self._payload or {})
        payload.setdefault("definition_id", definition_id)
        return payload


@pytest.fixture(autouse=True)
def isolated_registry_definition_dependency(client):
    resolver = _Resolver(
        payload={
            "definition_id": "def.attribute.customer_id",
            "definition_type": "attribute",
            "definition_name": "customer_id",
            "business_definition": "Stable identifier assigned to a customer within the retail-banking product boundary.",
            "glossary_id": "glossary.retail",
            "glossary_name": "Retail Banking Glossary",
            "object_class": "customer",
            "property": "identifier",
            "representation_term": "identifier",
            "value_domain": {"type": "string", "format": "uuid"},
            "status": "approved",
            "owner": "data-governance",
            "synonyms": ["Customer Key"],
            "parent_definition_id": "def.attribute.customer",
            "parent_definition_name": "Customer",
            "child_definition_ids": ["def.attribute.customer_number"],
            "child_definition_names": ["Customer Number"],
            "child_definition_count": 1,
            "source_system": "openmetadata",
            "openmetadata_entity_id": "om-term-1",
            "openmetadata_entity_type": "glossary_term",
            "version": "1.0.0",
            "provenance": {"created_by": "platform", "approved_by": "data-governance"},
            "applies_to": ["data_object:customer"],
        }
    )
    client.app.dependency_overrides[get_registry_definition_resolver] = lambda: resolver
    yield resolver
    client.app.dependency_overrides.pop(get_registry_definition_resolver, None)


def test_get_registry_definition_returns_snake_case_payload(client, auth_headers, isolated_registry_definition_dependency) -> None:
    response = client.get(
        "/api/data-catalog/v1/registry/definitions/def.attribute.customer_id",
        headers=auth_headers("dq:rules:read"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["definition_id"] == "def.attribute.customer_id"
    assert payload["glossary_name"] == "Retail Banking Glossary"
    assert payload["definition_type"] == "attribute"
    assert payload["definition_name"] == "customer_id"
    assert payload["business_definition"].startswith("Stable identifier")
    assert payload["openmetadata_entity_type"] == "glossary_term"
    assert payload["value_domain"]["format"] == "uuid"
    assert payload["synonyms"] == ["Customer Key"]


def test_get_registry_definition_maps_not_found_error(client, auth_headers, isolated_registry_definition_dependency) -> None:
    isolated_registry_definition_dependency._error = RegistryDefinitionLookupError(
        "Registry definition 'def.attribute.customer_id' was not found in OpenMetadata",
        status_code=404,
    )

    response = client.get(
        "/api/data-catalog/v1/registry/definitions/def.attribute.customer_id",
        headers=auth_headers("dq:rules:read"),
    )

    assert response.status_code == 404
    payload = response.json()
    assert payload["detail"]["error"] == "registry_definition_not_found"
    assert payload["detail"]["definition_id"] == "def.attribute.customer_id"


def test_get_registry_definition_maps_ambiguous_error(client, auth_headers, isolated_registry_definition_dependency) -> None:
    isolated_registry_definition_dependency._error = RegistryDefinitionLookupError(
        "Registry definition 'def.attribute.customer_id' resolved to multiple OpenMetadata terms",
        status_code=409,
    )

    response = client.get(
        "/api/data-catalog/v1/registry/definitions/def.attribute.customer_id",
        headers=auth_headers("dq:rules:read"),
    )

    assert response.status_code == 409
    payload = response.json()
    assert payload["detail"]["error"] == "registry_definition_ambiguous"


def test_get_registry_definition_maps_unavailable_error(client, auth_headers, isolated_registry_definition_dependency) -> None:
    isolated_registry_definition_dependency._error = RegistryDefinitionLookupError(
        "OpenMetadata is unavailable while resolving registry definitions",
        status_code=503,
    )

    response = client.get(
        "/api/data-catalog/v1/registry/definitions/def.attribute.customer_id",
        headers=auth_headers("dq:rules:read"),
    )

    assert response.status_code == 503
    payload = response.json()
    assert payload["detail"]["error"] == "registry_definition_unavailable"


def test_list_registry_definitions_returns_snake_case_payload(client, auth_headers) -> None:
    class _ListResolver:
        async def list_definitions(self, *, query=None, definition_type=None, limit=50):
            return [
                {
                    "definition_id": "def.attribute.customer_id",
                    "definition_type": definition_type or "attribute",
                    "definition_name": query or "customer_id",
                    "business_definition": "Customer identifier.",
                    "source_system": "openmetadata",
                }
            ]

    client.app.dependency_overrides[get_registry_definition_resolver] = lambda: _ListResolver()
    try:
        response = client.get(
            "/api/data-catalog/v1/registry/definitions?query=customer_id&definition_type=attribute&limit=10",
            headers=auth_headers("dq:rules:read"),
        )
    finally:
        client.app.dependency_overrides.pop(get_registry_definition_resolver, None)

    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, list)
    assert payload[0]["definition_id"] == "def.attribute.customer_id"
    assert payload[0]["definition_type"] == "attribute"


def test_list_registry_definitions_maps_unavailable_error(client, auth_headers) -> None:
    class _ListResolver:
        async def list_definitions(self, *, query=None, definition_type=None, limit=50):
            del query, definition_type, limit
            raise RegistryDefinitionLookupError(
                "OpenMetadata is unavailable while resolving registry definitions",
                status_code=503,
            )

    client.app.dependency_overrides[get_registry_definition_resolver] = lambda: _ListResolver()
    try:
        response = client.get(
            "/api/data-catalog/v1/registry/definitions?query=customer_id",
            headers=auth_headers("dq:rules:read"),
        )
    finally:
        client.app.dependency_overrides.pop(get_registry_definition_resolver, None)

    assert response.status_code == 503
    assert response.json()["detail"]["error"] == "registry_definition_unavailable"


def test_list_registry_definitions_uses_fallback_definition_id_for_blank_query(client, auth_headers) -> None:
    class _ListResolver:
        async def list_definitions(self, *, query=None, definition_type=None, limit=50):
            del query, definition_type, limit
            raise RegistryDefinitionLookupError(
                "Registry definition search failed",
                status_code=500,
            )

    client.app.dependency_overrides[get_registry_definition_resolver] = lambda: _ListResolver()
    try:
        response = client.get(
            "/api/data-catalog/v1/registry/definitions",
            headers=auth_headers("dq:rules:read"),
        )
    finally:
        client.app.dependency_overrides.pop(get_registry_definition_resolver, None)

    assert response.status_code == 500
    assert response.json()["detail"]["definition_id"] == "registry-definition-search"


def test_list_reference_domains_returns_enumerated_value_domains(client, auth_headers) -> None:
    class _ReferenceDomainResolver:
        async def list_definitions(self, *, query=None, definition_type=None, limit=50):
            del query, definition_type, limit
            return [
                {
                    "definition_id": "def.attribute.customer_id",
                    "definition_type": "attribute",
                    "definition_name": "customer_id",
                    "business_definition": "Stable identifier assigned to a customer within the retail-banking product boundary.",
                    "value_domain": {"type": "string", "format": "uuid"},
                    "source_system": "openmetadata",
                },
                {
                    "definition_id": "def.attribute.customer_status",
                    "definition_type": "attribute",
                    "definition_name": "customer_status",
                    "business_definition": "Lifecycle state describing whether a retail banking customer is prospect, active, dormant, or closed.",
                    "value_domain": {
                        "type": "string",
                        "allowed_values": ["prospect", "active", "dormant", "closed"],
                        "constraints": {"nullable": False},
                    },
                    "source_system": "openmetadata",
                },
            ]

    client.app.dependency_overrides[get_registry_definition_resolver] = lambda: _ReferenceDomainResolver()
    try:
        response = client.get(
            "/api/data-catalog/v1/registry/reference-domains?limit=10",
            headers=auth_headers("dq:rules:read"),
        )
    finally:
        client.app.dependency_overrides.pop(get_registry_definition_resolver, None)

    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, list)
    assert len(payload) == 1
    assert payload[0]["definition_id"] == "def.attribute.customer_status"
    assert payload[0]["value_domain"]["allowed_values"] == ["prospect", "active", "dormant", "closed"]