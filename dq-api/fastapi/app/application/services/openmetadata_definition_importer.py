from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request as UrlRequest, urlopen

from dq_utils.auth_utils import AuthConfigError
from dq_utils.auth_utils import OidcClientCredentialsTokenProvider
from dq_utils.auth_utils import OidcPasswordTokenProvider
from dq_utils.auth_utils import StaticTokenProvider
from dq_utils.auth_utils import TokenProvider
from dq_utils.auth_utils import resolve_oidc_token_url


class OpenMetadataDefinitionImportError(RuntimeError):
    def __init__(self, message: str, *, status_code: int = 503) -> None:
        super().__init__(message)
        self.status_code = status_code


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _has_named_property(payload: Any, name: str) -> bool:
    if isinstance(payload, dict):
        if _clean(payload.get("name")) == name and "propertyType" in payload:
            return True
        return any(_has_named_property(item, name) for item in payload.values())
    if isinstance(payload, list):
        return any(_has_named_property(item, name) for item in payload)
    return False


class OpenMetadataDefinitionImporter:
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
        self._provider = _clean(provider).lower()
        self._endpoint = _clean(endpoint).rstrip("/")
        self._api_key = _clean(api_key)
        self._oidc_issuer = _clean(oidc_issuer)
        self._oidc_token_url = _clean(oidc_token_url)
        self._oidc_client_id = _clean(oidc_client_id)
        self._oidc_client_secret = _clean(oidc_client_secret)
        self._oidc_scope = _clean(oidc_scope)
        self._oidc_username = _clean(oidc_username)
        self._oidc_password = _clean(oidc_password)
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

            token_url = resolve_oidc_token_url(issuer=self._oidc_issuer, token_url=self._oidc_token_url)
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

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self._token_provider_error:
            raise OpenMetadataDefinitionImportError(self._token_provider_error, status_code=503)
        if self._token_provider is not None:
            token = _clean(self._token_provider.get_token())
            if not token:
                raise OpenMetadataDefinitionImportError("OpenMetadata authentication returned an empty token", status_code=503)
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        body: Any | None = None,
        allow_not_found: bool = False,
    ) -> Any:
        if self._provider != "openmetadata":
            raise OpenMetadataDefinitionImportError(
                "OpenMetadata import requires CATALOG_PROVIDER=openmetadata",
                status_code=503,
            )
        if not self._endpoint:
            raise OpenMetadataDefinitionImportError(
                "OpenMetadata import requires CATALOG_ENDPOINT to be configured",
                status_code=503,
            )

        query = f"?{urlencode(params, doseq=True)}" if params else ""
        url = f"{self._endpoint}/api{path}{query}"
        headers = self._headers()
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode("utf-8")

        request = UrlRequest(url=url, data=data, headers=headers, method=method.upper())
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            if allow_not_found and exc.code == 404:
                return None
            raise OpenMetadataDefinitionImportError(
                f"OpenMetadata import request failed: {method.upper()} {path} -> HTTP {exc.code}: {raw[:400]}",
                status_code=exc.code,
            ) from exc
        except URLError as exc:
            raise OpenMetadataDefinitionImportError(f"Failed to reach OpenMetadata: {exc}", status_code=503) from exc

        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise OpenMetadataDefinitionImportError("OpenMetadata returned a non-JSON response", status_code=502) from exc

    def _ensure_glossary_term_property(self, name: str) -> bool:
        glossary_term_type = self._request_json("GET", "/v1/metadata/types/name/glossaryTerm")
        if _has_named_property(glossary_term_type, name):
            return False

        glossary_term_type_id = _clean((glossary_term_type or {}).get("id"))
        if not glossary_term_type_id:
            raise OpenMetadataDefinitionImportError(
                "OpenMetadata glossaryTerm metadata type response did not include an id",
                status_code=502,
            )

        string_type = self._request_json("GET", "/v1/metadata/types/name/string")
        string_type_id = _clean((string_type or {}).get("id"))
        if not string_type_id:
            raise OpenMetadataDefinitionImportError(
                "OpenMetadata string metadata type response did not include an id",
                status_code=502,
            )

        self._request_json(
            "PUT",
            f"/v1/metadata/types/{glossary_term_type_id}",
            body={
                "name": name,
                "description": f"Auto-provisioned glossaryTerm custom property '{name}' for data-definition imports.",
                "propertyType": {"id": string_type_id, "type": "type"},
            },
        )
        return True

    def import_contract(self, import_contract: dict[str, Any]) -> dict[str, Any]:
        glossary = import_contract.get("glossary") if isinstance(import_contract, dict) else None
        glossary_terms = import_contract.get("glossary_terms") if isinstance(import_contract, dict) else None
        if not isinstance(glossary, dict) or not isinstance(glossary_terms, list) or not glossary_terms:
            raise OpenMetadataDefinitionImportError(
                "OpenMetadata import contract must include glossary and glossary_terms",
                status_code=422,
            )

        glossary_entity = self._request_json(
            "PUT",
            "/v1/glossaries",
            body={
                "name": _clean(glossary.get("name")),
                "displayName": _clean(glossary.get("display_name")),
                "description": _clean(glossary.get("description")),
                "mutuallyExclusive": False,
            },
        )
        glossary_fqn = _clean(glossary_entity.get("fullyQualifiedName")) or _clean(glossary.get("name"))

        custom_properties_created: list[dict[str, Any]] = []
        seen_extension_keys: set[str] = set()
        for term in glossary_terms:
            if not isinstance(term, dict):
                continue
            extension = term.get("extension") if isinstance(term.get("extension"), dict) else {}
            for key in sorted(extension.keys()):
                if key in seen_extension_keys:
                    continue
                created = self._ensure_glossary_term_property(key)
                custom_properties_created.append({"name": key, "created": created})
                seen_extension_keys.add(key)

        imported_terms: list[dict[str, Any]] = []
        for term in glossary_terms:
            if not isinstance(term, dict):
                continue
            payload = dict(term)
            payload["glossary"] = glossary_fqn
            entity = self._request_json("PUT", "/v1/glossaryTerms", body=payload)
            imported_terms.append(
                {
                    "name": _clean(payload.get("name")),
                    "display_name": _clean(payload.get("displayName")),
                    "term_fqn": _clean(entity.get("fullyQualifiedName")),
                    "openmetadata_entity_id": _clean(entity.get("id")),
                }
            )

        return {
            "glossary": {
                "name": _clean(glossary.get("name")),
                "display_name": _clean(glossary.get("display_name")),
                "fully_qualified_name": glossary_fqn,
            },
            "custom_properties": custom_properties_created,
            "definition_count": len(imported_terms),
            "definitions": imported_terms,
        }