import pytest
from urllib.error import HTTPError
from urllib.error import URLError

import app.application.services.registry_definition_resolver as resolver_module
from app.application.services.registry_definition_resolver import OpenMetadataRegistryDefinitionResolver
from app.application.services.registry_definition_resolver import RegistryDefinitionLookupError


def _build_resolver() -> OpenMetadataRegistryDefinitionResolver:
    return OpenMetadataRegistryDefinitionResolver(
        provider="openmetadata",
        endpoint="https://openmetadata.example.com",
        api_key="token",
        timeout_seconds=30,
    )


@pytest.mark.anyio
async def test_resolve_definition_normalizes_openmetadata_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    resolver = _build_resolver()

    def fake_request_json(path: str, *, allow_not_found: bool):
        del path, allow_not_found
        return {
            "id": "om-term-1",
            "name": "customer_id",
            "displayName": "customer_id",
            "description": "Stable identifier assigned to a customer within the retail-banking product boundary.",
            "entityType": "glossary_term",
            "glossary": {
                "id": "glossary.retail",
                "displayName": "Retail Banking Glossary",
            },
            "parent": {
                "id": "def.attribute.customer",
                "displayName": "Customer",
            },
            "children": [
                {
                    "id": "def.attribute.customer_number",
                    "displayName": "Customer Number",
                },
            ],
            "synonyms": ["Customer Key", "Party Identifier"],
            "extension": {
                "registry_definition": {
                    "definition_id": "def.attribute.customer_id",
                    "definition_type": "attribute",
                    "object_class": "customer",
                    "property": "identifier",
                    "representation_term": "identifier",
                    "status": "approved",
                    "owner": "data-governance",
                    "version": "1.0.0",
                    "value_domain": {
                        "type": "string",
                        "format": "uuid",
                    },
                    "provenance": {
                        "created_by": "platform",
                        "approved_by": "data-governance",
                    },
                    "applies_to": ["data_object:customer"],
                }
            },
        }

    monkeypatch.setattr(resolver, "_request_json", fake_request_json)

    payload = await resolver.resolve_definition("def.attribute.customer_id")

    assert payload["definition_id"] == "def.attribute.customer_id"
    assert payload["definition_type"] == "attribute"
    assert payload["definition_name"] == "customer_id"
    assert payload["business_definition"].startswith("Stable identifier")
    assert payload["glossary_id"] == "glossary.retail"
    assert payload["glossary_name"] == "Retail Banking Glossary"
    assert payload["value_domain"]["format"] == "uuid"
    assert payload["owner"] == "data-governance"
    assert payload["synonyms"] == ["Customer Key", "Party Identifier"]
    assert payload["parent_definition_id"] == "def.attribute.customer"
    assert payload["parent_definition_name"] == "Customer"
    assert payload["child_definition_ids"] == ["def.attribute.customer_number"]
    assert payload["child_definition_names"] == ["Customer Number"]
    assert payload["child_definition_count"] == 1
    assert payload["openmetadata_entity_id"] == "om-term-1"


@pytest.mark.anyio
async def test_resolve_definition_rejects_missing_identifier(monkeypatch: pytest.MonkeyPatch) -> None:
    resolver = _build_resolver()
    call_counter = {"value": 0}

    def fake_request_json(path: str, *, allow_not_found: bool):
        del path, allow_not_found
        call_counter["value"] += 1
        if call_counter["value"] == 1:
            return None
        return {"data": []}

    monkeypatch.setattr(resolver, "_request_json", fake_request_json)

    with pytest.raises(RegistryDefinitionLookupError, match="was not found") as error:
        await resolver.resolve_definition("def.attribute.customer_id")

    assert error.value.status_code == 404


@pytest.mark.anyio
async def test_resolve_definition_rejects_ambiguous_matches(monkeypatch: pytest.MonkeyPatch) -> None:
    resolver = _build_resolver()
    call_counter = {"value": 0}

    def fake_request_json(path: str, *, allow_not_found: bool):
        del path, allow_not_found
        call_counter["value"] += 1
        if call_counter["value"] == 1:
            return None
        return {
            "data": [
                {"id": "1", "name": "def.attribute.customer_id"},
                {"id": "2", "sourceUrl": "def.attribute.customer_id"},
            ]
        }

    monkeypatch.setattr(resolver, "_request_json", fake_request_json)

    with pytest.raises(RegistryDefinitionLookupError, match="multiple OpenMetadata terms") as error:
        await resolver.resolve_definition("def.attribute.customer_id")

    assert error.value.status_code == 409


@pytest.mark.anyio
async def test_resolve_definition_rejects_incomplete_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    resolver = _build_resolver()

    def fake_request_json(path: str, *, allow_not_found: bool):
        del path, allow_not_found
        return {
            "id": "om-term-1",
            "name": "customer_id",
            "extension": {
                "registry_definition": {
                    "definition_id": "def.attribute.customer_id",
                }
            },
        }

    monkeypatch.setattr(resolver, "_request_json", fake_request_json)

    with pytest.raises(RegistryDefinitionLookupError, match="definition_type") as error:
        await resolver.resolve_definition("def.attribute.customer_id")

    assert error.value.status_code == 503


@pytest.mark.anyio
async def test_resolve_definition_parses_json_encoded_extension_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    resolver = _build_resolver()

    def fake_request_json(path: str, *, allow_not_found: bool):
        del path, allow_not_found
        return {
            "id": "om-term-1",
            "name": "customer_status",
            "displayName": "Customer Status",
            "description": "Lifecycle state describing whether a retail banking customer is prospect, active, dormant, or closed.",
            "entityType": "glossary_term",
            "extension": {
                "definition_id": "def.attribute.customer_status",
                "definition_type": "attribute",
                "definition_name": "customer_status",
                "object_class": "customer",
                "property": "status",
                "representation_term": "code",
                "status": "approved",
                "owner": "customer-domain-owner",
                "version": "1.0.0",
                "value_domain": '{"allowed_values":["prospect","active"],"constraints":{"nullable":false},"type":"string"}',
                "provenance": '{"approved_by":"customer-domain-owner","created_by":"platform"}',
                "applies_to": '["data_object:customer"]',
            },
        }

    monkeypatch.setattr(resolver, "_request_json", fake_request_json)

    payload = await resolver.resolve_definition("def.attribute.customer_status")

    assert payload["definition_id"] == "def.attribute.customer_status"
    assert payload["value_domain"]["type"] == "string"
    assert payload["value_domain"]["allowed_values"] == ["prospect", "active"]
    assert payload["provenance"]["approved_by"] == "customer-domain-owner"
    assert payload["applies_to"] == ["data_object:customer"]


@pytest.mark.anyio
async def test_resolve_definition_normalizes_owner_from_owners_list(monkeypatch: pytest.MonkeyPatch) -> None:
    resolver = _build_resolver()

    def fake_request_json(path: str, *, allow_not_found: bool):
        del path, allow_not_found
        return {
            "id": "om-term-2",
            "name": "customer_segment",
            "displayName": "customer_segment",
            "description": "Business grouping assigned to a customer for servicing and marketing.",
            "entityType": "glossary_term",
            "owners": [
                {
                    "displayName": "customer-domain-owner",
                    "name": "customer-domain-owner",
                }
            ],
            "extension": {
                "registry_definition": {
                    "definition_id": "def.attribute.customer_segment",
                    "definition_type": "attribute",
                    "definition_name": "customer_segment",
                }
            },
        }

    monkeypatch.setattr(resolver, "_request_json", fake_request_json)

    payload = await resolver.resolve_definition("def.attribute.customer_segment")

    assert payload["owner"] == "customer-domain-owner"


def test_initialize_token_provider_supports_static_password_and_client_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class _StaticProvider:
        def __init__(self, token: str) -> None:
            captured["static_token"] = token

    class _PasswordProvider:
        def __init__(self, **kwargs) -> None:
            captured["password"] = kwargs

    class _ClientProvider:
        def __init__(self, **kwargs) -> None:
            captured["client"] = kwargs

    monkeypatch.setattr(resolver_module, "StaticTokenProvider", _StaticProvider)
    monkeypatch.setattr(resolver_module, "OidcPasswordTokenProvider", _PasswordProvider)
    monkeypatch.setattr(resolver_module, "OidcClientCredentialsTokenProvider", _ClientProvider)
    monkeypatch.setattr(resolver_module, "resolve_oidc_token_url", lambda issuer, token_url: token_url or f"{issuer}/token")

    static_resolver = OpenMetadataRegistryDefinitionResolver(
        provider="openmetadata",
        endpoint="https://openmetadata.example.com",
        api_key="static-token",
    )
    assert static_resolver._token_provider is not None
    assert captured["static_token"] == "static-token"

    password_resolver = OpenMetadataRegistryDefinitionResolver(
        provider="openmetadata",
        endpoint="https://openmetadata.example.com",
        api_key="",
        oidc_issuer="https://issuer.example.com",
        oidc_client_id="client-id",
        oidc_client_secret="client-secret",
        oidc_scope="openid",
        oidc_username="alice",
        oidc_password="secret",
        timeout_seconds=7,
    )
    assert password_resolver._token_provider is not None
    assert captured["password"] == {
        "token_url": "https://issuer.example.com/token",
        "client_id": "client-id",
        "client_secret": "client-secret",
        "username": "alice",
        "password": "secret",
        "scope": "openid",
        "timeout_seconds": 7,
    }

    client_resolver = OpenMetadataRegistryDefinitionResolver(
        provider="openmetadata",
        endpoint="https://openmetadata.example.com",
        api_key="",
        oidc_issuer="https://issuer.example.com",
        oidc_client_id="client-id",
        oidc_client_secret="client-secret",
        oidc_scope="openid",
    )
    assert client_resolver._token_provider is not None
    assert captured["client"] == {
        "token_url": "https://issuer.example.com/token",
        "client_id": "client-id",
        "client_secret": "client-secret",
        "scope": "openid",
        "timeout_seconds": 30,
    }


def test_initialize_token_provider_returns_none_without_oidc_and_captures_auth_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    resolver = OpenMetadataRegistryDefinitionResolver(
        provider="openmetadata",
        endpoint="https://openmetadata.example.com",
        api_key="",
    )
    assert resolver._token_provider is None
    assert resolver._token_provider_error is None

    monkeypatch.setattr(
        resolver_module,
        "resolve_oidc_token_url",
        lambda issuer, token_url: (_ for _ in ()).throw(resolver_module.AuthConfigError("bad auth")),
    )
    failing = OpenMetadataRegistryDefinitionResolver(
        provider="openmetadata",
        endpoint="https://openmetadata.example.com",
        api_key="",
        oidc_issuer="https://issuer.example.com",
    )
    assert failing._token_provider is None
    assert failing._token_provider_error == "bad auth"


def test_resolve_definition_sync_validates_inputs_and_lookup_paths() -> None:
    resolver = _build_resolver()

    with pytest.raises(RegistryDefinitionLookupError, match="definition_id") as empty_error:
        resolver._resolve_definition_sync("   ")
    assert empty_error.value.status_code == 400

    wrong_provider = OpenMetadataRegistryDefinitionResolver(provider="other", endpoint="https://openmetadata.example.com", api_key="token")
    with pytest.raises(RegistryDefinitionLookupError, match="CATALOG_PROVIDER"):
        wrong_provider._resolve_definition_sync("def.id")

    missing_endpoint = OpenMetadataRegistryDefinitionResolver(provider="openmetadata", endpoint="", api_key="token")
    with pytest.raises(RegistryDefinitionLookupError, match="CATALOG_ENDPOINT"):
        missing_endpoint._resolve_definition_sync("def.id")

    uuid_value = "123e4567-e89b-42d3-a456-426614174000"
    paths = resolver._build_definition_lookup_paths(uuid_value)
    assert paths[0].startswith(f"/v1/glossaryTerms/{uuid_value}")
    assert paths[1].startswith(f"/v1/glossaryTerms/name/{uuid_value}")
    assert resolver._build_definition_lookup_paths("definition/name")[0].startswith("/v1/glossaryTerms/name/definition%2Fname")


def test_list_definitions_sync_filters_limits_and_skips_invalid_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    resolver = _build_resolver()
    items = [
        {"id": "1", "name": "keep-1"},
        {"id": "2", "name": "skip-normalize"},
        {"id": "3", "name": "keep-2"},
        "bad-item",
    ]

    monkeypatch.setattr(resolver, "_request_json", lambda path, *, allow_not_found: {"data": items})
    monkeypatch.setattr(resolver, "_is_definition_payload", lambda item: isinstance(item, dict))

    def fake_normalize(item: dict[str, object], definition_id: str) -> dict[str, object]:
        del definition_id
        if item["name"] == "skip-normalize":
            raise RegistryDefinitionLookupError("bad row", status_code=503)
        return {
            "definition_id": item["id"],
            "definition_name": item["name"],
            "business_definition": "Customer status definition",
            "object_class": "customer",
            "property": "status",
            "definition_type": "attribute" if item["name"] == "keep-1" else "metric",
        }

    monkeypatch.setattr(resolver, "_normalize_definition", fake_normalize)

    results = resolver._list_definitions_sync(query="customer", definition_type="attribute", limit=0)
    assert results == [
        {
            "definition_id": "1",
            "definition_name": "keep-1",
            "business_definition": "Customer status definition",
            "object_class": "customer",
            "property": "status",
            "definition_type": "attribute",
        }
    ]

    assert resolver._list_definitions_sync(query=None, definition_type=None, limit=500) == [
        {
            "definition_id": "1",
            "definition_name": "keep-1",
            "business_definition": "Customer status definition",
            "object_class": "customer",
            "property": "status",
            "definition_type": "attribute",
        },
        {
            "definition_id": "3",
            "definition_name": "keep-2",
            "business_definition": "Customer status definition",
            "object_class": "customer",
            "property": "status",
            "definition_type": "metric",
        },
    ]

    monkeypatch.setattr(resolver, "_request_json", lambda path, *, allow_not_found: None)
    assert resolver._list_definitions_sync(query=None, definition_type=None, limit=10) == []
    monkeypatch.setattr(resolver, "_request_json", lambda path, *, allow_not_found: {"data": {"bad": "shape"}})
    assert resolver._list_definitions_sync(query=None, definition_type=None, limit=10) == []


def test_list_definitions_sync_validates_provider_and_endpoint() -> None:
    wrong_provider = OpenMetadataRegistryDefinitionResolver(provider="other", endpoint="https://openmetadata.example.com", api_key="token")
    with pytest.raises(RegistryDefinitionLookupError, match="CATALOG_PROVIDER"):
        wrong_provider._list_definitions_sync(None, None, 10)

    missing_endpoint = OpenMetadataRegistryDefinitionResolver(provider="openmetadata", endpoint="", api_key="token")
    with pytest.raises(RegistryDefinitionLookupError, match="CATALOG_ENDPOINT"):
        missing_endpoint._list_definitions_sync(None, None, 10)


def test_definition_query_match_and_term_list_helpers_cover_false_paths() -> None:
    resolver = _build_resolver()
    payload = {
        "definition_id": "def.customer.status",
        "definition_name": "Customer Status",
        "business_definition": "Lifecycle state",
        "object_class": "customer",
        "property": "status",
    }
    assert resolver._definition_matches_query(payload, "lifecycle") is True
    assert resolver._definition_matches_query(payload, "missing") is False

    assert resolver._find_terms_in_list(None, "def.customer.status") == []
    assert resolver._find_terms_in_list({"data": {"bad": "shape"}}, "def.customer.status") == []
    assert resolver._find_terms_in_list({"items": [{"name": "other"}, {"name": "def.customer.status"}]}, "def.customer.status") == [
        {"name": "def.customer.status"}
    ]

    assert resolver._matches_definition_identifier({"name": "def.customer.status"}, "def.customer.status") is True
    assert resolver._matches_definition_identifier({"name": "other"}, "def.customer.status") is False
    assert resolver._is_definition_payload({"name": "term"}) is True
    assert resolver._is_definition_payload({"data": []}) is False
    assert resolver._identifier_candidates({"extension": {"dq": {"registryDefinition": {"definitionId": "def.customer.status"}}}}) == ["def.customer.status"]


def test_request_json_and_authorization_header_handle_success_and_fail_fast_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    resolver = _build_resolver()

    class _FakeResponse:
        def __init__(self, payload: bytes) -> None:
            self._payload = payload

        def read(self) -> bytes:
            return self._payload

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            del exc_type, exc, tb
            return False

    seen_headers: dict[str, str] = {}

    def fake_urlopen(request, timeout: int):
        del timeout
        seen_headers.update(dict(request.headers.items()))
        return _FakeResponse(b'{"name":"definition"}')

    monkeypatch.setattr(resolver_module, "urlopen", fake_urlopen)
    monkeypatch.setattr(resolver, "_resolve_authorization_header", lambda *, correlation_id: f"Bearer {correlation_id}")
    assert resolver._request_json("/v1/glossaryTerms/name/example", allow_not_found=False) == {"name": "definition"}
    assert seen_headers["Accept"] == "application/json"
    assert seen_headers["Authorization"].startswith("Bearer ")
    assert any(key.lower() == "x-correlation-id" for key in seen_headers)

    monkeypatch.setattr(resolver_module, "urlopen", lambda request, timeout: _FakeResponse(b'[1,2,3]'))
    assert resolver._request_json("/v1/glossaryTerms/name/example", allow_not_found=False) is None

    error_404 = HTTPError("https://example.com", 404, "not found", hdrs=None, fp=None)
    monkeypatch.setattr(resolver_module, "urlopen", lambda request, timeout: (_ for _ in ()).throw(error_404))
    assert resolver._request_json("/v1/glossaryTerms/name/example", allow_not_found=True) is None

    class _ErrorBody:
        def read(self) -> bytes:
            return b'boom'

        def close(self) -> None:
            return None

    error_500 = HTTPError("https://example.com", 500, "boom", hdrs=None, fp=_ErrorBody())
    monkeypatch.setattr(resolver_module, "urlopen", lambda request, timeout: (_ for _ in ()).throw(error_500))
    with pytest.raises(RegistryDefinitionLookupError, match="HTTP 500"):
        resolver._request_json("/v1/glossaryTerms/name/example", allow_not_found=False)

    monkeypatch.setattr(resolver_module, "urlopen", lambda request, timeout: (_ for _ in ()).throw(URLError("down")))
    with pytest.raises(RegistryDefinitionLookupError, match="unavailable"):
        resolver._request_json("/v1/glossaryTerms/name/example", allow_not_found=False)

    monkeypatch.setattr(resolver_module, "urlopen", lambda request, timeout: _FakeResponse(b'{not-json'))
    with pytest.raises(RegistryDefinitionLookupError, match="invalid registry-definition response"):
        resolver._request_json("/v1/glossaryTerms/name/example", allow_not_found=False)

    monkeypatch.setattr(
        resolver,
        "_resolve_authorization_header",
        OpenMetadataRegistryDefinitionResolver._resolve_authorization_header.__get__(
            resolver,
            OpenMetadataRegistryDefinitionResolver,
        ),
    )
    resolver._token_provider_error = "bad auth"
    with pytest.raises(RegistryDefinitionLookupError, match="misconfigured"):
        resolver._resolve_authorization_header(correlation_id="cid-1")
    resolver._token_provider_error = None
    resolver._token_provider = None
    assert resolver._resolve_authorization_header(correlation_id="cid-1") is None

    class _RaisingProvider:
        def get_token(self, *, correlation_id: str) -> str:
            del correlation_id
            raise resolver_module.AuthConfigError("token error")

    resolver._token_provider = _RaisingProvider()
    with pytest.raises(RegistryDefinitionLookupError, match="token acquisition failed"):
        resolver._resolve_authorization_header(correlation_id="cid-2")

    class _EmptyProvider:
        def get_token(self, *, correlation_id: str) -> str:
            del correlation_id
            return "   "

    resolver._token_provider = _EmptyProvider()
    with pytest.raises(RegistryDefinitionLookupError, match="empty access token"):
        resolver._resolve_authorization_header(correlation_id="cid-3")

    class _TokenProvider:
        def __init__(self, token: str) -> None:
            self._token = token

        def get_token(self, *, correlation_id: str) -> str:
            del correlation_id
            return self._token

    resolver._token_provider = _TokenProvider("Bearer existing")
    assert resolver._resolve_authorization_header(correlation_id="cid-4") == "Bearer existing"
    resolver._token_provider = _TokenProvider("plain-token")
    assert resolver._resolve_authorization_header(correlation_id="cid-5") == "Bearer plain-token"


def test_normalization_helpers_cover_error_and_fallback_paths() -> None:
    resolver = _build_resolver()

    with pytest.raises(RegistryDefinitionLookupError, match="stable definition identifier"):
        resolver._normalize_definition({"extension": {"registry_definition": {"definition_type": "attribute", "business_definition": "desc"}}}, "def.id")
    with pytest.raises(RegistryDefinitionLookupError, match="definition_type"):
        resolver._normalize_definition({"name": "def.id", "extension": {"registry_definition": {"business_definition": "desc"}}}, "def.id")
    with pytest.raises(RegistryDefinitionLookupError, match="business_definition"):
        resolver._normalize_definition({"name": "def.id", "extension": {"registry_definition": {"definition_type": "attribute"}}}, "def.id")

    nested_extension = {
        "dq": {"registryDefinition": {"definitionId": "def.id", "definitionType": "attribute", "businessDefinition": "desc"}}
    }
    normalized = resolver._normalize_definition({"id": "om-1", "displayName": "Name", "extension": nested_extension}, "def.id")
    assert normalized["definition_id"] == "def.id"
    assert normalized["definition_type"] == "attribute"
    assert normalized["business_definition"] == "desc"
    assert normalized["definition_name"] == "Name"

    assert resolver._extract_definition_metadata({"dq": {"registry_definition": {"definition_id": "x"}}}) == {"definition_id": "x"}
    assert resolver._extract_definition_metadata("bad") == {}
    assert resolver._normalize_owner([{}, {"id": "owner-id"}]) == "owner-id"
    assert resolver._normalize_owner(123) == ""
    assert resolver._read_nested_value({"a": {"b": {"c": 1}}}, "a", "b", "c") == 1
    assert resolver._read_nested_value({"a": 1}, "a", "b") is None
    assert resolver._coerce_dict({"a": 1}) == {"a": 1}
    assert resolver._coerce_dict('{"a":1}') == {"a": 1}
    assert resolver._coerce_dict('[1,2]') == {}
    assert resolver._coerce_dict('{bad') == {}
    assert resolver._coerce_list([" a ", "", None, 3]) == ["a", "3"]
    assert resolver._coerce_list('["a","b"]') == ["a", "b"]
    assert resolver._coerce_list('{bad') == ["{bad"]
    assert resolver._coerce_list("   ") == []
    assert resolver._first_non_empty(None, "   ", "value") == "value"
    assert resolver._first_non_empty(None, 3, default="x") == 3
    assert resolver._first_non_empty(None, "   ", default="x") == "x"