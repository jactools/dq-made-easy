from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request as UrlRequest, urlopen

from dq_utils.auth_utils import AuthConfigError
from dq_utils.auth_utils import OidcClientCredentialsTokenProvider
from dq_utils.auth_utils import OidcPasswordTokenProvider
from dq_utils.auth_utils import StaticTokenProvider
from dq_utils.auth_utils import TokenProvider
from dq_utils.auth_utils import resolve_oidc_token_url


logger = logging.getLogger(__name__)

_UUID_PATTERN = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$"
)
_FIELDS = "description,tags,owners,glossary,parent,children,synonyms,extension"


class RegistryDefinitionLookupError(RuntimeError):
    def __init__(self, message: str, *, status_code: int = 503) -> None:
        super().__init__(message)
        self.status_code = status_code


class RegistryDefinitionResolver(Protocol):
    async def resolve_definition(self, definition_id: str) -> dict[str, Any]:
        ...
    async def list_definitions(
        self,
        *,
        query: str | None = None,
        definition_type: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        ...


class OpenMetadataRegistryDefinitionResolver:
    def __init__(
        self,
        *,
        provider: str | None,
        endpoint: str | None,
        api_key: str | None,
        oidc_issuer: str | None = None,
        oidc_token_url: str | None = None,
        oidc_client_id: str | None = None,
        oidc_client_secret: str | None = None,
        oidc_scope: str | None = None,
        oidc_username: str | None = None,
        oidc_password: str | None = None,
        timeout_seconds: int = 30,
    ) -> None:
        self._provider = str(provider or "").strip().lower()
        self._endpoint = str(endpoint or "").rstrip("/")
        self._api_key = str(api_key or "").strip()
        self._oidc_issuer = str(oidc_issuer or "").strip()
        self._oidc_token_url = str(oidc_token_url or "").strip()
        self._oidc_client_id = str(oidc_client_id or "").strip()
        self._oidc_client_secret = str(oidc_client_secret or "").strip()
        self._oidc_scope = str(oidc_scope or "").strip()
        self._oidc_username = str(oidc_username or "").strip()
        self._oidc_password = str(oidc_password or "").strip()
        self._timeout_seconds = max(int(timeout_seconds), 1)
        self._token_provider, self._token_provider_error = self._initialize_token_provider()

    def _initialize_token_provider(self) -> tuple[TokenProvider | None, str | None]:
        try:
            if self._api_key:
                return StaticTokenProvider(self._api_key), None

            has_oidc_inputs = any(
                value
                for value in (
                    self._oidc_issuer,
                    self._oidc_token_url,
                    self._oidc_client_id,
                    self._oidc_client_secret,
                    self._oidc_scope,
                    self._oidc_username,
                    self._oidc_password,
                )
            )
            if not has_oidc_inputs:
                return None, None

            token_url = resolve_oidc_token_url(
                issuer=self._oidc_issuer,
                token_url=self._oidc_token_url,
            )
            if self._oidc_username or self._oidc_password:
                return (
                    OidcPasswordTokenProvider(
                        token_url=token_url or "",
                        client_id=self._oidc_client_id,
                        client_secret=self._oidc_client_secret or None,
                        username=self._oidc_username,
                        password=self._oidc_password,
                        scope=self._oidc_scope or None,
                        timeout_seconds=self._timeout_seconds,
                    ),
                    None,
                )

            return (
                OidcClientCredentialsTokenProvider(
                    token_url=token_url or "",
                    client_id=self._oidc_client_id,
                    client_secret=self._oidc_client_secret,
                    scope=self._oidc_scope or None,
                    timeout_seconds=self._timeout_seconds,
                ),
                None,
            )
        except AuthConfigError as exc:
            return None, str(exc)

    async def resolve_definition(self, definition_id: str) -> dict[str, Any]:
        return await asyncio.to_thread(self._resolve_definition_sync, definition_id)
    async def list_definitions(
        self,
        *,
        query: str | None = None,
        definition_type: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._list_definitions_sync, query, definition_type, limit)

    def _resolve_definition_sync(self, definition_id: str) -> dict[str, Any]:
        normalized_definition_id = str(definition_id or "").strip()
        if not normalized_definition_id:
            raise RegistryDefinitionLookupError("registry definition lookup requires 'definition_id'", status_code=400)
        if self._provider != "openmetadata":
            raise RegistryDefinitionLookupError(
                "Registry definition lookup requires CATALOG_PROVIDER=openmetadata",
                status_code=503,
            )
        if not self._endpoint:
            raise RegistryDefinitionLookupError(
                "Registry definition lookup requires CATALOG_ENDPOINT to be configured",
                status_code=503,
            )

        for path in self._build_definition_lookup_paths(normalized_definition_id):
            payload = self._request_json(path, allow_not_found=True)
            if self._is_definition_payload(payload):
                return self._normalize_definition(payload, normalized_definition_id)

        list_payload = self._request_json(
            f"/v1/glossaryTerms?{urlencode({'fields': _FIELDS, 'limit': 1000})}",
            allow_not_found=False,
        )
        matches = self._find_terms_in_list(list_payload, normalized_definition_id)
        if len(matches) == 1:
            return self._normalize_definition(matches[0], normalized_definition_id)
        if len(matches) > 1:
            raise RegistryDefinitionLookupError(
                f"Registry definition '{normalized_definition_id}' resolved to multiple OpenMetadata terms",
                status_code=409,
            )

        raise RegistryDefinitionLookupError(
            f"Registry definition '{normalized_definition_id}' was not found in OpenMetadata",
            status_code=404,
        )

    def _build_definition_lookup_paths(self, definition_id: str) -> list[str]:
        encoded_fields = quote(_FIELDS, safe=",")
        paths: list[str] = []
        if _UUID_PATTERN.fullmatch(definition_id):
            paths.append(f"/v1/glossaryTerms/{quote(definition_id, safe='')}?fields={encoded_fields}")
        paths.append(f"/v1/glossaryTerms/name/{quote(definition_id, safe='')}?fields={encoded_fields}")
        return paths
    def _list_definitions_sync(
        self,
        query: str | None,
        definition_type: str | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        if self._provider != "openmetadata":
            raise RegistryDefinitionLookupError(
                "Registry definition lookup requires CATALOG_PROVIDER=openmetadata",
                status_code=503,
            )
        if not self._endpoint:
            raise RegistryDefinitionLookupError(
                "Registry definition lookup requires CATALOG_ENDPOINT to be configured",
                status_code=503,
            )

        normalized_query = str(query or "").strip().lower()
        normalized_type = str(definition_type or "").strip().lower()
        safe_limit = max(1, min(int(limit), 200))
        list_payload = self._request_json(
            f"/v1/glossaryTerms?{urlencode({'fields': _FIELDS, 'limit': 1000})}",
            allow_not_found=False,
        )
        raw_items = list_payload.get("data") if isinstance(list_payload, dict) else []
        if not isinstance(raw_items, list):
            return []

        results: list[dict[str, Any]] = []
        for item in raw_items:
            if not isinstance(item, dict) or not self._is_definition_payload(item):
                continue
            try:
                normalized = self._normalize_definition(item, str(item.get("name") or item.get("id") or "definition"))
            except RegistryDefinitionLookupError:
                continue
            if normalized_type and str(normalized.get("definition_type") or "").strip().lower() != normalized_type:
                continue
            if normalized_query and not self._definition_matches_query(normalized, normalized_query):
                continue
            results.append(normalized)
            if len(results) >= safe_limit:
                break
        return results

    def _definition_matches_query(self, payload: dict[str, Any], query: str) -> bool:
        for value in (
            payload.get("definition_id"),
            payload.get("definition_name"),
            payload.get("business_definition"),
            payload.get("object_class"),
            payload.get("property"),
        ):
            if query in str(value or "").strip().lower():
                return True
        return False

    def _request_json(self, path: str, *, allow_not_found: bool) -> dict[str, Any] | None:
        url = f"{self._endpoint}{path}"
        correlation_id = str(uuid.uuid4())
        headers = {
            "Accept": "application/json",
            "X-Correlation-ID": correlation_id,
        }
        auth_header = self._resolve_authorization_header(correlation_id=correlation_id)
        if auth_header is not None:
            headers["Authorization"] = auth_header

        request = UrlRequest(url, headers=headers, method="GET")
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                payload = response.read().decode("utf-8")
        except HTTPError as exc:
            if exc.code == 404 and allow_not_found:
                return None
            detail = exc.read().decode("utf-8", errors="ignore") if hasattr(exc, "read") else ""
            logger.warning("OpenMetadata request failed for '%s' with HTTP %s: %s", url, exc.code, detail)
            raise RegistryDefinitionLookupError(
                f"OpenMetadata request failed with HTTP {exc.code} while resolving registry definitions",
                status_code=503,
            )
        except URLError as exc:
            logger.warning("OpenMetadata request failed for '%s': %s", url, exc)
            raise RegistryDefinitionLookupError(
                "OpenMetadata is unavailable while resolving registry definitions",
                status_code=503,
            )

        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError as exc:
            logger.warning("OpenMetadata response for '%s' was not valid JSON: %s", url, exc)
            raise RegistryDefinitionLookupError(
                "OpenMetadata returned an invalid registry-definition response",
                status_code=503,
            )
        return parsed if isinstance(parsed, dict) else None

    def _resolve_authorization_header(self, *, correlation_id: str) -> str | None:
        if self._token_provider_error:
            raise RegistryDefinitionLookupError(
                f"OpenMetadata auth is misconfigured: {self._token_provider_error}",
                status_code=503,
            )
        if self._token_provider is None:
            return None

        try:
            token = self._token_provider.get_token(correlation_id=correlation_id)
        except AuthConfigError as exc:
            logger.warning("OpenMetadata auth token acquisition failed: %s", exc)
            raise RegistryDefinitionLookupError(
                f"OpenMetadata auth token acquisition failed: {exc}",
                status_code=503,
            ) from exc

        normalized_token = str(token or "").strip()
        if not normalized_token:
            raise RegistryDefinitionLookupError(
                "OpenMetadata auth provider returned an empty access token",
                status_code=503,
            )
        if normalized_token.lower().startswith("bearer "):
            return normalized_token
        return f"Bearer {normalized_token}"

    def _find_terms_in_list(self, payload: dict[str, Any] | None, definition_id: str) -> list[dict[str, Any]]:
        if not isinstance(payload, dict):
            return []
        raw_items = payload.get("data") or payload.get("entities") or payload.get("items") or []
        if not isinstance(raw_items, list):
            return []
        return [item for item in raw_items if isinstance(item, dict) and self._matches_definition_identifier(item, definition_id)]

    def _matches_definition_identifier(self, payload: dict[str, Any], definition_id: str) -> bool:
        target = definition_id.strip()
        return any(candidate == target for candidate in self._identifier_candidates(payload))

    def _is_definition_payload(self, payload: dict[str, Any] | None) -> bool:
        if not isinstance(payload, dict) or not payload:
            return False
        if any(key in payload for key in ("data", "entities", "items")):
            return False
        return any(candidate for candidate in self._identifier_candidates(payload))

    def _identifier_candidates(self, payload: dict[str, Any]) -> list[str]:
        extension = self._extract_definition_metadata(payload.get("extension"))
        candidates = [
            payload.get("id"),
            payload.get("name"),
            payload.get("fullyQualifiedName"),
            payload.get("sourceUrl"),
            extension.get("definition_id"),
            extension.get("definitionId"),
            extension.get("registry_definition_id"),
            extension.get("registryDefinitionId"),
        ]
        return [str(candidate).strip() for candidate in candidates if str(candidate or "").strip()]

    def _normalize_definition(self, payload: dict[str, Any], definition_id: str) -> dict[str, Any]:
        extension = self._extract_definition_metadata(payload.get("extension"))
        glossary_payload = self._coerce_dict(
            self._first_non_empty(
                extension.get("glossary"),
                payload.get("glossary"),
            )
        )
        parent_reference = self._normalize_reference(
            self._first_non_empty(
                extension.get("parent"),
                payload.get("parent"),
            )
        )
        child_references = self._coerce_reference_list(
            self._first_non_empty(
                extension.get("children"),
                payload.get("children"),
            )
        )
        synonyms = self._coerce_list(
            self._first_non_empty(
                extension.get("synonyms"),
                payload.get("synonyms"),
            )
        )

        resolved_definition_id = self._first_non_empty(
            extension.get("definition_id"),
            extension.get("definitionId"),
            extension.get("registry_definition_id"),
            extension.get("registryDefinitionId"),
            payload.get("sourceUrl"),
            payload.get("fullyQualifiedName"),
            payload.get("name"),
            payload.get("id"),
        )
        if not resolved_definition_id:
            raise RegistryDefinitionLookupError(
                f"OpenMetadata definition '{definition_id}' is missing a stable definition identifier",
                status_code=503,
            )

        resolved_definition_type = self._first_non_empty(
            extension.get("definition_type"),
            extension.get("definitionType"),
            payload.get("definition_type"),
            payload.get("definitionType"),
        )
        if not resolved_definition_type:
            raise RegistryDefinitionLookupError(
                f"OpenMetadata definition '{definition_id}' is missing required definition_type",
                status_code=503,
            )

        business_definition = self._first_non_empty(
            extension.get("business_definition"),
            extension.get("businessDefinition"),
            payload.get("business_definition"),
            payload.get("businessDefinition"),
            payload.get("description"),
        )
        if not business_definition:
            raise RegistryDefinitionLookupError(
                f"OpenMetadata definition '{definition_id}' is missing required business_definition",
                status_code=503,
            )

        value_domain_payload = self._coerce_dict(
            self._first_non_empty(
                extension.get("value_domain"),
                extension.get("valueDomain"),
                payload.get("value_domain"),
                payload.get("valueDomain"),
            )
        )
        provenance_payload = self._coerce_dict(
            self._first_non_empty(
                extension.get("provenance"),
                payload.get("provenance"),
            )
        )
        applies_to_payload = self._coerce_list(
            self._first_non_empty(
                extension.get("applies_to"),
                extension.get("appliesTo"),
                payload.get("applies_to"),
                payload.get("appliesTo"),
            )
        )

        return {
            "definition_id": resolved_definition_id,
            "definition_type": resolved_definition_type,
            "definition_name": self._first_non_empty(
                extension.get("definition_name"),
                extension.get("definitionName"),
                payload.get("displayName"),
                payload.get("name"),
                resolved_definition_id,
            ),
            "business_definition": business_definition,
            "glossary_id": self._first_non_empty(
                glossary_payload.get("id"),
                glossary_payload.get("glossary_id"),
                glossary_payload.get("glossaryId"),
                default="",
            ),
            "glossary_name": self._first_non_empty(
                glossary_payload.get("display_name"),
                glossary_payload.get("displayName"),
                glossary_payload.get("name"),
                glossary_payload.get("glossary_name"),
                glossary_payload.get("glossaryName"),
                default="",
            ),
            "object_class": self._first_non_empty(
                extension.get("object_class"),
                extension.get("objectClass"),
                payload.get("object_class"),
                payload.get("objectClass"),
                default="",
            ),
            "property": self._first_non_empty(
                extension.get("property"),
                payload.get("property"),
                default="",
            ),
            "representation_term": self._first_non_empty(
                extension.get("representation_term"),
                extension.get("representationTerm"),
                payload.get("representation_term"),
                payload.get("representationTerm"),
                default="",
            ),
            "value_domain": {
                "type": self._first_non_empty(value_domain_payload.get("type"), default=None),
                "format": self._first_non_empty(value_domain_payload.get("format"), default=None),
                "unit": self._first_non_empty(value_domain_payload.get("unit"), default=None),
                "allowed_values": self._coerce_list(
                    self._first_non_empty(
                        value_domain_payload.get("allowed_values"),
                        value_domain_payload.get("allowedValues"),
                    )
                ),
                "constraints": self._coerce_dict(value_domain_payload.get("constraints")),
            },
            "status": self._first_non_empty(
                extension.get("status"),
                payload.get("status"),
                default="",
            ),
            "owner": self._normalize_owner(payload.get("owner") or payload.get("owners") or extension.get("owner")),
            "synonyms": synonyms,
            "parent_definition_id": self._first_non_empty(parent_reference.get("id"), default=""),
            "parent_definition_name": self._first_non_empty(parent_reference.get("name"), default=""),
            "child_definition_ids": [
                str(child.get("id") or "").strip()
                for child in child_references
                if str(child.get("id") or "").strip()
            ],
            "child_definition_names": [
                str(child.get("name") or "").strip()
                for child in child_references
                if str(child.get("name") or "").strip()
            ],
            "child_definition_count": len(child_references),
            "source_system": "openmetadata",
            "openmetadata_entity_id": self._first_non_empty(payload.get("id"), default=""),
            "openmetadata_entity_type": self._first_non_empty(payload.get("entityType"), default="glossary_term"),
            "version": self._first_non_empty(
                extension.get("version"),
                payload.get("version"),
                default="",
            ),
            "provenance": {
                "created_by": self._first_non_empty(provenance_payload.get("created_by"), provenance_payload.get("createdBy"), default=None),
                "approved_by": self._first_non_empty(provenance_payload.get("approved_by"), provenance_payload.get("approvedBy"), default=None),
                "created_at": self._first_non_empty(provenance_payload.get("created_at"), provenance_payload.get("createdAt"), default=None),
                "approved_at": self._first_non_empty(provenance_payload.get("approved_at"), provenance_payload.get("approvedAt"), default=None),
                "change_reason": self._first_non_empty(provenance_payload.get("change_reason"), provenance_payload.get("changeReason"), default=None),
            },
            "applies_to": applies_to_payload,
        }

    def _extract_definition_metadata(self, extension: Any) -> dict[str, Any]:
        if not isinstance(extension, dict):
            return {}
        for candidate in (
            self._read_nested_value(extension, "dq", "registry_definition"),
            self._read_nested_value(extension, "dq", "registryDefinition"),
            self._read_nested_value(extension, "iso11179", "definition"),
            extension.get("registry_definition"),
            extension.get("registryDefinition"),
        ):
            if isinstance(candidate, dict):
                return candidate
        return extension

    def _normalize_owner(self, owner: Any) -> str:
        if isinstance(owner, str):
            return owner.strip()
        if isinstance(owner, list):
            for item in owner:
                normalized = self._normalize_owner(item)
                if normalized:
                    return normalized
            return ""
        if isinstance(owner, dict):
            return self._first_non_empty(
                owner.get("displayName"),
                owner.get("name"),
                owner.get("id"),
                default="",
            )
        return ""

    def _read_nested_value(self, payload: Any, *path: str) -> Any:
        current = payload
        for key in path:
            if not isinstance(current, dict):
                return None
            current = current.get(key)
        return current

    def _coerce_dict(self, payload: Any) -> dict[str, Any]:
        if isinstance(payload, dict):
            return dict(payload)
        if isinstance(payload, str):
            try:
                parsed = json.loads(payload)
            except json.JSONDecodeError:
                return {}
            return dict(parsed) if isinstance(parsed, dict) else {}
        return {}

    def _normalize_reference(self, payload: Any) -> dict[str, Any]:
        if isinstance(payload, dict):
            return {
                "id": self._first_non_empty(
                    payload.get("id"),
                    payload.get("definition_id"),
                    payload.get("definitionId"),
                    payload.get("glossary_id"),
                    payload.get("glossaryId"),
                    default="",
                ),
                "name": self._first_non_empty(
                    payload.get("display_name"),
                    payload.get("displayName"),
                    payload.get("name"),
                    payload.get("definition_name"),
                    payload.get("definitionName"),
                    payload.get("glossary_name"),
                    payload.get("glossaryName"),
                    default="",
                ),
            }
        if isinstance(payload, str):
            normalized = payload.strip()
            if normalized:
                return {"id": normalized, "name": normalized}
        return {"id": "", "name": ""}

    def _coerce_reference_list(self, payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            references: list[dict[str, Any]] = []
            for item in payload:
                reference = self._normalize_reference(item)
                if reference.get("id") or reference.get("name"):
                    references.append(reference)
            return references
        reference = self._normalize_reference(payload)
        if reference.get("id") or reference.get("name"):
            return [reference]
        return []

    def _coerce_list(self, payload: Any) -> list[str]:
        if isinstance(payload, list):
            return [str(item).strip() for item in payload if str(item or "").strip()]
        if isinstance(payload, str) and payload.strip():
            stripped = payload.strip()
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item or "").strip()]
            return [stripped]
        return []

    def _first_non_empty(self, *values: Any, default: Any = None) -> Any:
        for value in values:
            if value is None:
                continue
            if isinstance(value, str):
                stripped = value.strip()
                if stripped:
                    return stripped
                continue
            return value
        return default