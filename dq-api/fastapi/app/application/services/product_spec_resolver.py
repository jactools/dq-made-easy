from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from dq_utils.auth_utils import AuthConfigError
from dq_utils.auth_utils import OidcClientCredentialsTokenProvider
from dq_utils.auth_utils import OidcPasswordTokenProvider
from dq_utils.auth_utils import StaticTokenProvider
from dq_utils.auth_utils import TokenProvider
from dq_utils.auth_utils import resolve_oidc_token_url


logger = logging.getLogger(__name__)

_FIELDS = "description,extension"
_TERM_CUSTOM_PROPERTY_DESCRIPTIONS = {
    "product_spec_id": "Stable dq-made-easy product-spec identifier.",
    "product_name": "Canonical product-spec display name.",
    "product_version": "Governed product-spec semantic version.",
    "product_lifecycle_state": "Lifecycle state for the product specification.",
    "product_owner": "Owning team or role for the product specification.",
    "product_objective": "Business objective for the governed product specification.",
    "product_scope": "JSON-encoded scope metadata for the product specification.",
    "business_definition": "Canonical governed business definition.",
    "registry_definition_ids": "JSON-encoded registry-definition identifiers linked to the product spec.",
    "odcs_contract_refs": "JSON-encoded linked ODCS contract references.",
    "provenance": "JSON-encoded provenance metadata.",
    "migration": "JSON-encoded migration metadata for legacy product-spec onboarding.",
}


class ProductSpecLookupError(RuntimeError):
    def __init__(self, message: str, *, status_code: int = 503) -> None:
        super().__init__(message)
        self.status_code = status_code


class ProductSpecResolver(Protocol):
    async def resolve_product_spec(self, product_spec_id: str) -> dict[str, Any]:
        ...

    async def list_product_specs(
        self,
        *,
        owner: str | None = None,
        lifecycle_state: str | None = None,
        registry_definition_id: str | None = None,
        linked_contract_id: str | None = None,
        search: str | None = None,
    ) -> list[dict[str, Any]]:
        ...

    async def create_product_spec(self, payload: dict[str, Any]) -> dict[str, Any]:
        ...

    async def update_product_spec(self, product_spec_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        ...

    async def import_product_specs(self, payload: dict[str, Any], *, dry_run: bool = False) -> dict[str, Any]:
        ...

    async def apply_stewardship_action(
        self,
        product_spec_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        ...

    async def summarize_product_specs(self) -> dict[str, Any]:
        ...


class OpenMetadataProductSpecResolver:
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
        timeout_seconds: int,
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

    async def resolve_product_spec(self, product_spec_id: str) -> dict[str, Any]:
        return await asyncio.to_thread(self._resolve_product_spec_sync, product_spec_id)

    async def list_product_specs(
        self,
        *,
        owner: str | None = None,
        lifecycle_state: str | None = None,
        registry_definition_id: str | None = None,
        linked_contract_id: str | None = None,
        search: str | None = None,
    ) -> list[dict[str, Any]]:
        return await asyncio.to_thread(
            self._list_product_specs_sync,
            owner,
            lifecycle_state,
            registry_definition_id,
            linked_contract_id,
            search,
        )

    async def create_product_spec(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await asyncio.to_thread(self._create_product_spec_sync, payload)

    async def update_product_spec(self, product_spec_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return await asyncio.to_thread(self._update_product_spec_sync, product_spec_id, payload)

    async def import_product_specs(self, payload: dict[str, Any], *, dry_run: bool = False) -> dict[str, Any]:
        return await asyncio.to_thread(self._import_product_specs_sync, payload, dry_run)

    async def apply_stewardship_action(self, product_spec_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return await asyncio.to_thread(self._apply_stewardship_action_sync, product_spec_id, payload)

    async def summarize_product_specs(self) -> dict[str, Any]:
        return await asyncio.to_thread(self._summarize_product_specs_sync)

    def _resolve_product_spec_sync(self, product_spec_id: str) -> dict[str, Any]:
        normalized_product_spec_id = str(product_spec_id or "").strip()
        if not normalized_product_spec_id:
            raise ProductSpecLookupError("product spec lookup requires 'product_spec_id'", status_code=400)
        self._require_catalog_configuration()

        for path in self._build_product_spec_lookup_paths(normalized_product_spec_id):
            payload = self._request_json(path, allow_not_found=True, allow_bad_request=True)
            if self._is_product_spec_payload(payload):
                return self._normalize_product_spec(payload, normalized_product_spec_id)

        list_payload = self._fetch_product_spec_list_payload()
        matches = self._find_product_specs_in_list(list_payload, normalized_product_spec_id)
        if len(matches) == 1:
            return self._normalize_product_spec(matches[0], normalized_product_spec_id)
        if len(matches) > 1:
            raise ProductSpecLookupError(
                f"Product spec '{normalized_product_spec_id}' resolved to multiple OpenMetadata terms",
                status_code=409,
            )

        raise ProductSpecLookupError(
            f"Product spec '{normalized_product_spec_id}' was not found in OpenMetadata",
            status_code=404,
        )

    def _list_product_specs_sync(
        self,
        owner: str | None,
        lifecycle_state: str | None,
        registry_definition_id: str | None,
        linked_contract_id: str | None,
        search: str | None,
    ) -> list[dict[str, Any]]:
        self._require_catalog_configuration()

        results: list[dict[str, Any]] = []
        seen_product_spec_ids: set[str] = set()
        for item in self._iter_list_items(self._fetch_product_spec_list_payload()):
            if not self._looks_like_product_spec_candidate(item):
                continue

            candidate_product_spec_id = self._first_non_empty(
                self._extract_product_spec_metadata(item.get("extension")).get("product_spec_id"),
                self._extract_product_spec_metadata(item.get("extension")).get("productSpecId"),
                self._extract_product_spec_metadata(item.get("extension")).get("odps_product_spec_id"),
                self._extract_product_spec_metadata(item.get("extension")).get("odpsProductSpecId"),
                item.get("name"),
                item.get("id"),
                default="product_spec",
            )
            normalized = self._normalize_product_spec(item, candidate_product_spec_id)
            normalized_product_spec_id = str(normalized.get("product_spec_id") or "").strip()
            if normalized_product_spec_id in seen_product_spec_ids:
                raise ProductSpecLookupError(
                    f"Product-spec inventory contains duplicate stable identifier '{normalized_product_spec_id}'",
                    status_code=409,
                )
            if not self._matches_product_spec_filters(
                normalized,
                owner=owner,
                lifecycle_state=lifecycle_state,
                registry_definition_id=registry_definition_id,
                linked_contract_id=linked_contract_id,
                search=search,
            ):
                continue
            seen_product_spec_ids.add(normalized_product_spec_id)
            results.append(normalized)

        return sorted(results, key=lambda item: (str(item.get("product_spec_id") or ""), str(item.get("product_name") or "")))

    def _create_product_spec_sync(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._require_catalog_configuration()
        normalized_payload = self._normalize_product_spec_upsert_payload(payload)
        try:
            self._resolve_product_spec_sync(normalized_payload["product_spec_id"])
        except ProductSpecLookupError as exc:
            if exc.status_code != 404:
                raise
        else:
            raise ProductSpecLookupError(
                f"Product spec '{normalized_payload['product_spec_id']}' already exists in OpenMetadata",
                status_code=409,
            )
        return self._sync_product_spec(normalized_payload)

    def _update_product_spec_sync(self, product_spec_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self._require_catalog_configuration()
        normalized_product_spec_id = str(product_spec_id or "").strip()
        if not normalized_product_spec_id:
            raise ProductSpecLookupError("product spec update requires 'product_spec_id'", status_code=422)

        normalized_payload = self._normalize_product_spec_upsert_payload(payload)
        if normalized_payload["product_spec_id"] != normalized_product_spec_id:
            raise ProductSpecLookupError(
                "Product spec update path and payload must use the same stable product_spec_id",
                status_code=409,
            )

        existing = self._resolve_product_spec_sync(normalized_product_spec_id)
        request_openmetadata_entity_id = str(payload.get("openmetadata_entity_id") or "").strip()
        existing_openmetadata_entity_id = str(existing.get("openmetadata_entity_id") or "").strip()
        if request_openmetadata_entity_id and existing_openmetadata_entity_id and request_openmetadata_entity_id != existing_openmetadata_entity_id:
            raise ProductSpecLookupError(
                f"Product spec '{normalized_product_spec_id}' payload references a different OpenMetadata entity id",
                status_code=409,
            )
        return self._sync_product_spec(normalized_payload)

    def _import_product_specs_sync(self, payload: dict[str, Any], dry_run: bool) -> dict[str, Any]:
        self._require_catalog_configuration()
        normalized_import = self._normalize_product_spec_import_payload(payload)

        items: list[dict[str, Any]] = []
        created = 0
        updated = 0
        validated = 0

        for product_spec_payload in normalized_import["product_specs"]:
            product_spec_id = product_spec_payload["product_spec_id"]

            existing_product_spec: dict[str, Any] | None = None
            try:
                existing_product_spec = self._resolve_product_spec_sync(product_spec_id)
            except ProductSpecLookupError as exc:
                if exc.status_code != 404:
                    raise

            if dry_run:
                validated += 1
                items.append(
                    {
                        "product_spec_id": product_spec_id,
                        "outcome": "would_update" if existing_product_spec is not None else "would_create",
                    }
                )
                continue

            synced = self._sync_product_spec(product_spec_payload)
            if existing_product_spec is None:
                created += 1
                outcome = "created"
            else:
                updated += 1
                outcome = "updated"
            items.append(
                {
                    "product_spec_id": product_spec_id,
                    "outcome": outcome,
                    "product_spec": synced,
                }
            )

        return {
            "dry_run": dry_run,
            "total": len(normalized_import["product_specs"]),
            "created": created,
            "updated": updated,
            "validated": validated,
            "items": items,
        }

    def _apply_stewardship_action_sync(self, product_spec_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        normalized_product_spec_id = str(product_spec_id or "").strip()
        if not normalized_product_spec_id:
            raise ProductSpecLookupError("product spec stewardship action requires 'product_spec_id'", status_code=422)

        action = str(payload.get("action") or "").strip().lower()
        actor = str(payload.get("actor") or "").strip()
        change_reason = str(payload.get("change_reason") or payload.get("changeReason") or "").strip()
        glossary = payload.get("glossary")
        if not action or action not in {
            "submit_for_approval",
            "approve",
            "request_changes",
            "deprecate",
            "retire",
        }:
            raise ProductSpecLookupError(
                "product spec stewardship action requires a supported action",
                status_code=422,
            )
        if not actor:
            raise ProductSpecLookupError("product spec stewardship action requires 'actor'", status_code=422)
        if not change_reason:
            raise ProductSpecLookupError("product spec stewardship action requires 'change_reason'", status_code=422)
        if not isinstance(glossary, dict):
            raise ProductSpecLookupError("product spec stewardship action requires glossary metadata", status_code=422)

        existing = self._resolve_product_spec_sync(normalized_product_spec_id)
        existing_product_name = str(existing.get("product_name") or "").strip()
        if not existing_product_name:
            raise ProductSpecLookupError(
                "product spec stewardship action requires existing product_name",
                status_code=422,
            )
        existing_product_version = str(existing.get("product_version") or "").strip()
        if not existing_product_version:
            raise ProductSpecLookupError(
                "product spec stewardship action requires existing product_version",
                status_code=422,
            )
        existing_product_owner = str(existing.get("product_owner") or "").strip()
        if not existing_product_owner:
            raise ProductSpecLookupError(
                "product spec stewardship action requires existing product_owner",
                status_code=422,
            )
        existing_product_objective = str(existing.get("product_objective") or "").strip()
        if not existing_product_objective:
            raise ProductSpecLookupError(
                "product spec stewardship action requires existing product_objective",
                status_code=422,
            )
        existing_business_definition = str(existing.get("business_definition") or "").strip()
        if not existing_business_definition:
            raise ProductSpecLookupError(
                "product spec stewardship action requires existing business_definition",
                status_code=422,
            )
        existing_product_scope = existing.get("product_scope")
        if not isinstance(existing_product_scope, dict) or not existing_product_scope:
            raise ProductSpecLookupError(
                "product spec stewardship action requires existing product_scope",
                status_code=422,
            )
        existing_registry_definition_ids = existing.get("registry_definition_ids")
        if not isinstance(existing_registry_definition_ids, list) or not existing_registry_definition_ids:
            raise ProductSpecLookupError(
                "product spec stewardship action requires existing registry_definition_ids",
                status_code=422,
            )
        existing_odcs_contract_refs = existing.get("odcs_contract_refs")
        if not isinstance(existing_odcs_contract_refs, list) or not existing_odcs_contract_refs:
            raise ProductSpecLookupError(
                "product spec stewardship action requires existing odcs_contract_refs",
                status_code=422,
            )

        mapped_lifecycle_state = {
            "submit_for_approval": "in_review",
            "approve": "active",
            "request_changes": "draft",
            "deprecate": "deprecated",
            "retire": "retired",
        }[action]

        normalized_payload = self._normalize_product_spec_upsert_payload(
            {
                "glossary": glossary,
                "product_spec_id": normalized_product_spec_id,
                "product_name": existing_product_name,
                "product_version": existing_product_version,
                "product_lifecycle_state": mapped_lifecycle_state,
                "product_owner": existing_product_owner,
                "product_objective": existing_product_objective,
                "product_scope": existing_product_scope,
                "business_definition": existing_business_definition,
                "registry_definition_ids": existing_registry_definition_ids,
                "odcs_contract_refs": existing_odcs_contract_refs,
                "provenance": {
                    **(existing.get("provenance") or {}),
                    "approved_by": actor if action in {"approve", "retire"} else (existing.get("provenance") or {}).get("approved_by"),
                    "change_reason": change_reason,
                },
                "migration": existing.get("migration") or {},
            }
        )
        return self._sync_product_spec(normalized_payload)

    def _summarize_product_specs_sync(self) -> dict[str, Any]:
        inventory = self._list_product_specs_sync(
            owner=None,
            lifecycle_state=None,
            registry_definition_id=None,
            linked_contract_id=None,
            search=None,
        )
        by_lifecycle_state: dict[str, int] = {}
        by_owner: dict[str, int] = {}
        for item in inventory:
            lifecycle_state = str(item.get("product_lifecycle_state") or "unspecified").strip() or "unspecified"
            owner = str(item.get("product_owner") or "unassigned").strip() or "unassigned"
            by_lifecycle_state[lifecycle_state] = by_lifecycle_state.get(lifecycle_state, 0) + 1
            by_owner[owner] = by_owner.get(owner, 0) + 1
        return {
            "total": len(inventory),
            "by_lifecycle_state": dict(sorted(by_lifecycle_state.items())),
            "by_owner": dict(sorted(by_owner.items())),
        }

    def _require_catalog_configuration(self) -> None:
        if self._provider != "openmetadata":
            raise ProductSpecLookupError(
                "Product spec lookup requires CATALOG_PROVIDER=openmetadata",
                status_code=503,
            )
        if not self._endpoint:
            raise ProductSpecLookupError(
                "Product spec lookup requires CATALOG_ENDPOINT to be configured",
                status_code=503,
            )

    def _fetch_product_spec_list_payload(self) -> dict[str, Any] | None:
        return self._request_json(
            f"/v1/glossaryTerms?{urlencode({'fields': _FIELDS, 'limit': 1000})}",
            allow_not_found=False,
        )

    def _sync_product_spec(self, payload: dict[str, Any]) -> dict[str, Any]:
        glossary = payload["glossary"]
        glossary_entity = self._request_json(
            "/v1/glossaries",
            allow_not_found=False,
            method="PUT",
            body={
                "name": glossary["name"],
                "displayName": glossary["display_name"],
                "description": glossary["description"],
                "mutuallyExclusive": False,
            },
            error_context="syncing product specs",
        )
        glossary_fqn = self._first_non_empty(
            (glossary_entity or {}).get("fullyQualifiedName") if isinstance(glossary_entity, dict) else None,
            glossary["name"],
            default=glossary["name"],
        )

        for property_name, description in _TERM_CUSTOM_PROPERTY_DESCRIPTIONS.items():
            self._ensure_glossary_term_property(property_name, description)

        data_contracts = self._list_data_contracts()
        resolved_contract_refs = [self._resolve_linked_contract_reference(data_contracts, reference) for reference in payload["odcs_contract_refs"]]
        term_payload = self._build_product_spec_term_payload(payload, glossary_fqn, resolved_contract_refs)
        entity = self._request_json(
            "/v1/glossaryTerms",
            allow_not_found=False,
            method="PUT",
            body=term_payload,
            error_context="syncing product specs",
        )
        merged_payload = dict(entity) if isinstance(entity, dict) else {}
        if not isinstance(merged_payload.get("extension"), dict):
            merged_payload["extension"] = dict(term_payload["extension"])
        merged_payload.setdefault("name", term_payload["name"])
        merged_payload.setdefault("displayName", term_payload["displayName"])
        merged_payload.setdefault("description", term_payload["description"])
        merged_payload.setdefault("entityType", "glossary_term")
        normalized = self._normalize_product_spec(merged_payload, payload["product_spec_id"])
        normalized["openmetadata_entity_id"] = self._first_non_empty(merged_payload.get("id"), normalized.get("openmetadata_entity_id"), default="")
        normalized["openmetadata_entity_type"] = self._first_non_empty(
            merged_payload.get("entityType"),
            merged_payload.get("type"),
            default="glossary_term",
        )
        return normalized

    def _build_product_spec_lookup_paths(self, product_spec_id: str) -> list[str]:
        encoded_fields = quote(_FIELDS, safe=",")
        paths: list[str] = []
        if self._looks_like_uuid(product_spec_id):
            paths.append(f"/v1/glossaryTerms/{quote(product_spec_id, safe='')}?fields={encoded_fields}")
        paths.append(f"/v1/glossaryTerms/name/{quote(product_spec_id, safe='')}?fields={encoded_fields}")
        return paths

    def _request_json(
        self,
        path: str,
        *,
        allow_not_found: bool,
        allow_bad_request: bool = False,
        method: str = "GET",
        body: Any | None = None,
        error_context: str = "resolving product specs",
    ) -> dict[str, Any] | None:
        url = f"{self._endpoint}{path}"
        correlation_id = str(uuid.uuid4())
        headers = {
            "Accept": "application/json",
            "X-Correlation-ID": correlation_id,
        }
        auth_header = self._resolve_authorization_header(correlation_id=correlation_id)
        if auth_header is not None:
            headers["Authorization"] = auth_header

        request_body = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            request_body = json.dumps(body).encode("utf-8")

        request = Request(url, data=request_body, headers=headers, method=method.upper())
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                payload = response.read().decode("utf-8")
        except HTTPError as exc:
            if exc.code == 404 and allow_not_found:
                return None
            if exc.code == 400 and allow_bad_request:
                logger.info("OpenMetadata direct product-spec probe returned HTTP 400 for '%s'; falling back to list scan", url)
                return None
            detail = exc.read().decode("utf-8", errors="ignore") if hasattr(exc, "read") else ""
            logger.warning("OpenMetadata request failed for '%s' with HTTP %s: %s", url, exc.code, detail)
            raise ProductSpecLookupError(
                f"OpenMetadata request failed with HTTP {exc.code} while {error_context}",
                status_code=503,
            )
        except URLError as exc:
            logger.warning("OpenMetadata request failed for '%s': %s", url, exc)
            raise ProductSpecLookupError(
                f"OpenMetadata is unavailable while {error_context}",
                status_code=503,
            )

        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError as exc:
            logger.warning("OpenMetadata response for '%s' was not valid JSON: %s", url, exc)
            raise ProductSpecLookupError(
                "OpenMetadata returned an invalid product-spec response",
                status_code=503,
            )
        return parsed if isinstance(parsed, dict) else None

    def _normalize_product_spec_upsert_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        glossary = payload.get("glossary") if isinstance(payload.get("glossary"), dict) else None
        if glossary is None:
            raise ProductSpecLookupError("product spec create/update requires a glossary object", status_code=422)

        glossary_name = str(glossary.get("name") or "").strip()
        glossary_display_name = str(glossary.get("display_name") or glossary.get("displayName") or "").strip()
        glossary_description = str(glossary.get("description") or "").strip()
        if not glossary_name or not glossary_display_name or not glossary_description:
            raise ProductSpecLookupError(
                "product spec create/update requires glossary.name, glossary.display_name, and glossary.description",
                status_code=422,
            )

        product_spec_id = str(payload.get("product_spec_id") or payload.get("productSpecId") or "").strip()
        if not product_spec_id:
            raise ProductSpecLookupError("product spec create/update requires 'product_spec_id'", status_code=422)

        required_text_fields = {
            "product_name": payload.get("product_name") or payload.get("productName"),
            "product_version": payload.get("product_version") or payload.get("productVersion"),
            "product_lifecycle_state": payload.get("product_lifecycle_state") or payload.get("productLifecycleState"),
            "product_owner": payload.get("product_owner") or payload.get("productOwner"),
            "product_objective": payload.get("product_objective") or payload.get("productObjective"),
            "business_definition": payload.get("business_definition") or payload.get("businessDefinition"),
        }
        normalized_text_fields: dict[str, str] = {}
        for field_name, value in required_text_fields.items():
            normalized = str(value or "").strip()
            if not normalized:
                raise ProductSpecLookupError(f"product spec create/update requires '{field_name}'", status_code=422)
            normalized_text_fields[field_name] = normalized

        product_scope = payload.get("product_scope") or payload.get("productScope")
        if not isinstance(product_scope, dict) or not product_scope:
            raise ProductSpecLookupError("product spec create/update requires a non-empty product_scope object", status_code=422)

        registry_definition_ids = self._normalize_string_list(payload.get("registry_definition_ids") or payload.get("registryDefinitionIds"))
        if not registry_definition_ids:
            raise ProductSpecLookupError("product spec create/update requires at least one registry_definition_id", status_code=422)

        odcs_contract_refs_payload = payload.get("odcs_contract_refs") or payload.get("odcsContractRefs") or []
        if not isinstance(odcs_contract_refs_payload, list) or not odcs_contract_refs_payload:
            raise ProductSpecLookupError("product spec create/update requires at least one odcs_contract_ref", status_code=422)
        odcs_contract_refs = [self._normalize_requested_contract_reference(item) for item in odcs_contract_refs_payload]

        provenance = payload.get("provenance")
        if provenance is None:
            provenance = {}
        if not isinstance(provenance, dict):
            raise ProductSpecLookupError("product spec create/update requires provenance to be an object", status_code=422)

        migration_payload = payload.get("migration")
        if migration_payload is None:
            migration_payload = {}
        migration = self._coerce_dict(migration_payload)

        return {
            "glossary": {
                "name": glossary_name,
                "display_name": glossary_display_name,
                "description": glossary_description,
            },
            "product_spec_id": product_spec_id,
            **normalized_text_fields,
            "product_scope": dict(product_scope),
            "registry_definition_ids": registry_definition_ids,
            "odcs_contract_refs": odcs_contract_refs,
            "provenance": dict(provenance),
            "migration": migration,
        }

    def _normalize_product_spec_import_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ProductSpecLookupError("product spec import requires a JSON object payload", status_code=422)

        glossary = payload.get("glossary")
        product_specs_payload = payload.get("product_specs") or payload.get("productSpecs")
        if not isinstance(product_specs_payload, list) or not product_specs_payload:
            raise ProductSpecLookupError("product spec import requires at least one product_spec entry", status_code=422)

        normalized_product_specs: list[dict[str, Any]] = []
        seen_product_spec_ids: set[str] = set()
        for item in product_specs_payload:
            if not isinstance(item, dict):
                raise ProductSpecLookupError("each imported product_spec entry must be an object", status_code=422)

            upsert_payload = dict(item)
            upsert_payload["glossary"] = glossary
            normalized = self._normalize_product_spec_upsert_payload(upsert_payload)

            product_spec_id = normalized["product_spec_id"]
            if product_spec_id in seen_product_spec_ids:
                raise ProductSpecLookupError(
                    f"product spec import payload contains duplicate stable identifier '{product_spec_id}'",
                    status_code=409,
                )
            seen_product_spec_ids.add(product_spec_id)
            normalized_product_specs.append(normalized)

        return {
            "glossary": self._coerce_dict(glossary),
            "product_specs": normalized_product_specs,
        }

    def _normalize_requested_contract_reference(self, payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ProductSpecLookupError("each odcs_contract_ref must be an object", status_code=422)
        normalized = self._normalize_contract_reference(payload)
        if not normalized.get("odcs_contract_id") or not normalized.get("odcs_contract_name") or not normalized.get("odcs_contract_version"):
            raise ProductSpecLookupError(
                "each odcs_contract_ref must include odcs_contract_id, odcs_contract_name, and odcs_contract_version",
                status_code=422,
            )
        return normalized

    def _normalize_string_list(self, payload: Any) -> list[str]:
        values = self._coerce_list(payload)
        seen: set[str] = set()
        normalized: list[str] = []
        for value in values:
            text = str(value or "").strip()
            if text and text not in seen:
                seen.add(text)
                normalized.append(text)
        return normalized

    def _build_product_spec_term_payload(
        self,
        payload: dict[str, Any],
        glossary_fqn: str,
        contract_refs: list[dict[str, Any]],
    ) -> dict[str, Any]:
        extension = {
            "product_spec_id": payload["product_spec_id"],
            "product_name": payload["product_name"],
            "product_version": payload["product_version"],
            "product_lifecycle_state": payload["product_lifecycle_state"],
            "product_owner": payload["product_owner"],
            "product_objective": payload["product_objective"],
            "product_scope": json.dumps(payload["product_scope"], separators=(",", ":"), sort_keys=True),
            "business_definition": payload["business_definition"],
            "registry_definition_ids": json.dumps(payload["registry_definition_ids"], separators=(",", ":"), sort_keys=True),
            "odcs_contract_refs": json.dumps(contract_refs, separators=(",", ":"), sort_keys=True),
            "provenance": json.dumps(payload["provenance"], separators=(",", ":"), sort_keys=True),
            "migration": json.dumps(payload.get("migration") or {}, separators=(",", ":"), sort_keys=True),
        }
        return {
            "name": payload["product_spec_id"],
            "displayName": payload["product_name"],
            "description": payload["business_definition"],
            "glossary": glossary_fqn,
            "mutuallyExclusive": False,
            "extension": extension,
        }

    def _ensure_glossary_term_property(self, name: str, description: str) -> bool:
        glossary_term_type = self._request_json(
            "/v1/metadata/types/name/glossaryTerm",
            allow_not_found=False,
            error_context="syncing product specs",
        )
        if self._has_named_property(glossary_term_type, name):
            return False
        glossary_term_type_id = self._first_non_empty((glossary_term_type or {}).get("id") if isinstance(glossary_term_type, dict) else None, default="")
        if not glossary_term_type_id:
            raise ProductSpecLookupError("OpenMetadata glossaryTerm metadata type response did not include an id", status_code=503)

        string_type = self._request_json(
            "/v1/metadata/types/name/string",
            allow_not_found=False,
            error_context="syncing product specs",
        )
        string_type_id = self._first_non_empty((string_type or {}).get("id") if isinstance(string_type, dict) else None, default="")
        if not string_type_id:
            raise ProductSpecLookupError("OpenMetadata string metadata type response did not include an id", status_code=503)

        self._request_json(
            f"/v1/metadata/types/{glossary_term_type_id}",
            allow_not_found=False,
            method="PUT",
            body={
                "name": name,
                "description": description,
                "propertyType": {
                    "id": string_type_id,
                    "type": "type",
                },
            },
            error_context="syncing product specs",
        )
        return True

    def _list_data_contracts(self) -> list[dict[str, Any]]:
        payload = self._request_json(
            f"/v1/dataContracts?{urlencode({'limit': 1000})}",
            allow_not_found=False,
            error_context="syncing product specs",
        )
        if not isinstance(payload, dict):
            return []
        raw_items = payload.get("data") or payload.get("entities") or payload.get("items") or []
        if not isinstance(raw_items, list):
            return []
        return [item for item in raw_items if isinstance(item, dict)]

    def _resolve_linked_contract_reference(self, data_contracts: list[dict[str, Any]], reference: dict[str, Any]) -> dict[str, Any]:
        matches: list[dict[str, Any]] = []
        for contract in data_contracts:
            candidates = {
                str(contract.get("id") or "").strip(),
                str(contract.get("sourceUrl") or "").strip(),
                str(contract.get("name") or "").strip(),
                str(contract.get("fullyQualifiedName") or "").strip(),
            }
            if reference["odcs_contract_id"] in candidates or reference["odcs_contract_name"] in candidates:
                matches.append(contract)

        if not matches:
            raise ProductSpecLookupError(
                f"Linked ODCS contract '{reference['odcs_contract_id']}' was not found in OpenMetadata",
                status_code=422,
            )
        if len(matches) > 1:
            raise ProductSpecLookupError(
                f"Linked ODCS contract '{reference['odcs_contract_id']}' resolved to multiple OpenMetadata data contracts",
                status_code=409,
            )

        contract = matches[0]
        return {
            "odcs_contract_id": reference["odcs_contract_id"],
            "odcs_contract_name": reference["odcs_contract_name"],
            "odcs_contract_version": reference["odcs_contract_version"],
            "openmetadata_entity_id": self._first_non_empty(contract.get("id"), default=""),
            "openmetadata_entity_type": reference.get("openmetadata_entity_type") or "data_contract",
            "source_system": reference.get("source_system") or "openmetadata",
        }

    def _has_named_property(self, payload: Any, name: str) -> bool:
        if isinstance(payload, dict):
            if str(payload.get("name") or "").strip() == name and "propertyType" in payload:
                return True
            return any(self._has_named_property(value, name) for value in payload.values())
        if isinstance(payload, list):
            return any(self._has_named_property(item, name) for item in payload)
        return False

    def _resolve_authorization_header(self, *, correlation_id: str) -> str | None:
        if self._token_provider_error:
            raise ProductSpecLookupError(
                f"OpenMetadata auth is misconfigured: {self._token_provider_error}",
                status_code=503,
            )
        if self._token_provider is None:
            return None

        try:
            token = self._token_provider.get_token(correlation_id=correlation_id)
        except AuthConfigError as exc:
            logger.warning("OpenMetadata auth token acquisition failed: %s", exc)
            raise ProductSpecLookupError(
                f"OpenMetadata auth token acquisition failed: {exc}",
                status_code=503,
            ) from exc

        normalized_token = str(token or "").strip()
        if not normalized_token:
            raise ProductSpecLookupError(
                "OpenMetadata auth provider returned an empty access token",
                status_code=503,
            )
        if normalized_token.lower().startswith("bearer "):
            return normalized_token
        return f"Bearer {normalized_token}"

    def _is_product_spec_payload(self, payload: dict[str, Any] | None) -> bool:
        if not isinstance(payload, dict) or not payload:
            return False
        if any(key in payload for key in ("data", "entities", "items")):
            return False
        return any(candidate for candidate in self._identifier_candidates(payload))

    def _find_product_specs_in_list(self, payload: dict[str, Any] | None, product_spec_id: str) -> list[dict[str, Any]]:
        return [item for item in self._iter_list_items(payload) if self._matches_product_spec_identifier(item, product_spec_id)]

    def _iter_list_items(self, payload: dict[str, Any] | None) -> list[dict[str, Any]]:
        if not isinstance(payload, dict):
            return []
        raw_items = payload.get("data") or payload.get("entities") or payload.get("items") or []
        if not isinstance(raw_items, list):
            return []
        return [item for item in raw_items if isinstance(item, dict)]

    def _looks_like_product_spec_candidate(self, payload: dict[str, Any]) -> bool:
        extension = self._extract_product_spec_metadata(payload.get("extension"))
        product_spec_id = self._first_non_empty(
            extension.get("product_spec_id"),
            extension.get("productSpecId"),
            extension.get("odps_product_spec_id"),
            extension.get("odpsProductSpecId"),
            payload.get("name"),
            default="",
        )
        if str(product_spec_id or "").strip().startswith("ps."):
            return True
        marker_payloads = (
            extension.get("odcs_contract_refs"),
            extension.get("odcsContractRefs"),
            extension.get("registry_definition_ids"),
            extension.get("registryDefinitionIds"),
            extension.get("product_objective"),
            extension.get("productObjective"),
            extension.get("product_scope"),
            extension.get("productScope"),
        )
        return any(value not in (None, "", [], {}) for value in marker_payloads)

    def _matches_product_spec_filters(
        self,
        payload: dict[str, Any],
        *,
        owner: str | None,
        lifecycle_state: str | None,
        registry_definition_id: str | None,
        linked_contract_id: str | None,
        search: str | None,
    ) -> bool:
        normalized_owner = str(owner or "").strip().lower()
        if normalized_owner and str(payload.get("product_owner") or "").strip().lower() != normalized_owner:
            return False

        normalized_lifecycle_state = str(lifecycle_state or "").strip().lower()
        if normalized_lifecycle_state and str(payload.get("product_lifecycle_state") or "").strip().lower() != normalized_lifecycle_state:
            return False

        normalized_registry_definition_id = str(registry_definition_id or "").strip()
        if normalized_registry_definition_id and normalized_registry_definition_id not in list(payload.get("registry_definition_ids") or []):
            return False

        normalized_linked_contract_id = str(linked_contract_id or "").strip()
        if normalized_linked_contract_id and normalized_linked_contract_id not in {
            str(reference.get("odcs_contract_id") or "").strip()
            for reference in list(payload.get("odcs_contract_refs") or [])
            if isinstance(reference, dict)
        }:
            return False

        normalized_search = str(search or "").strip().lower()
        if not normalized_search:
            return True

        haystacks = [
            str(payload.get("product_spec_id") or ""),
            str(payload.get("product_name") or ""),
            str(payload.get("product_owner") or ""),
            str(payload.get("product_objective") or ""),
            str(payload.get("business_definition") or ""),
            *[str(value or "") for value in list(payload.get("registry_definition_ids") or [])],
            *[
                str(reference.get("odcs_contract_id") or "")
                for reference in list(payload.get("odcs_contract_refs") or [])
                if isinstance(reference, dict)
            ],
        ]
        return any(normalized_search in haystack.lower() for haystack in haystacks if haystack)

    def _matches_product_spec_identifier(self, payload: dict[str, Any], product_spec_id: str) -> bool:
        target = product_spec_id.strip()
        return any(candidate == target for candidate in self._identifier_candidates(payload))

    def _identifier_candidates(self, payload: dict[str, Any]) -> list[str]:
        extension = self._extract_product_spec_metadata(payload.get("extension"))
        candidates = [
            payload.get("id"),
            payload.get("name"),
            payload.get("fullyQualifiedName"),
            payload.get("sourceUrl"),
            extension.get("product_spec_id"),
            extension.get("productSpecId"),
            extension.get("odps_product_spec_id"),
            extension.get("odpsProductSpecId"),
            extension.get("data_product_id"),
            extension.get("dataProductId"),
        ]
        return [str(candidate).strip() for candidate in candidates if str(candidate or "").strip()]

    def _normalize_product_spec(self, payload: dict[str, Any], product_spec_id: str) -> dict[str, Any]:
        extension = self._extract_product_spec_metadata(payload.get("extension"))
        registry_definition_ids = self._coerce_list(
            self._first_non_empty(
                extension.get("registry_definition_ids"),
                extension.get("registryDefinitionIds"),
                extension.get("registry_definitions"),
                extension.get("registryDefinitions"),
            )
        )
        odcs_contract_refs = self._coerce_contract_reference_list(
            self._first_non_empty(
                extension.get("odcs_contract_refs"),
                extension.get("odcsContractRefs"),
                extension.get("odcs_contracts"),
                extension.get("odcsContracts"),
            )
        )

        resolved_product_spec_id = self._first_non_empty(
            extension.get("product_spec_id"),
            extension.get("productSpecId"),
            extension.get("odps_product_spec_id"),
            extension.get("odpsProductSpecId"),
            payload.get("sourceUrl"),
            payload.get("fullyQualifiedName"),
            payload.get("name"),
            payload.get("id"),
        )
        if not resolved_product_spec_id:
            raise ProductSpecLookupError(
                f"OpenMetadata product spec '{product_spec_id}' is missing a stable product_spec_id",
                status_code=503,
            )

        product_name = self._first_non_empty(
            extension.get("product_name"),
            extension.get("productName"),
            payload.get("displayName"),
            payload.get("name"),
            resolved_product_spec_id,
        )
        business_definition = self._first_non_empty(
            extension.get("business_definition"),
            extension.get("businessDefinition"),
            payload.get("description"),
        )
        if not business_definition:
            raise ProductSpecLookupError(
                f"OpenMetadata product spec '{product_spec_id}' is missing required business_definition",
                status_code=503,
            )

        product_owner = self._normalize_owner(
            self._first_non_empty(
                extension.get("product_owner"),
                extension.get("productOwner"),
                payload.get("owner"),
                payload.get("owners"),
            )
        )
        product_scope = self._coerce_dict(
            self._first_non_empty(
                extension.get("product_scope"),
                extension.get("productScope"),
                extension.get("scope"),
                payload.get("scope"),
            )
        )
        provenance_payload = self._coerce_dict(
            self._first_non_empty(
                extension.get("provenance"),
                payload.get("provenance"),
            )
        )
        migration_payload = self._coerce_dict(
            self._first_non_empty(
                extension.get("migration"),
                payload.get("migration"),
            )
        )

        if not odcs_contract_refs:
            raise ProductSpecLookupError(
                f"OpenMetadata product spec '{product_spec_id}' is missing linked ODCS contract references",
                status_code=503,
            )

        return {
            "product_spec_id": resolved_product_spec_id,
            "product_name": product_name,
            "product_version": self._first_non_empty(
                extension.get("product_version"),
                extension.get("productVersion"),
                payload.get("version"),
                default="",
            ),
            "product_lifecycle_state": self._first_non_empty(
                extension.get("product_lifecycle_state"),
                extension.get("productLifecycleState"),
                payload.get("status"),
                payload.get("lifecycleState"),
                default="",
            ),
            "product_owner": product_owner,
            "product_objective": self._first_non_empty(
                extension.get("product_objective"),
                extension.get("productObjective"),
                payload.get("objective"),
                payload.get("description"),
                default="",
            ),
            "product_scope": product_scope,
            "business_definition": business_definition,
            "registry_definition_ids": registry_definition_ids,
            "odcs_contract_refs": odcs_contract_refs,
            "openmetadata_entity_id": self._first_non_empty(payload.get("id"), default=""),
            "openmetadata_entity_type": self._first_non_empty(payload.get("entityType"), default="glossary_term"),
            "source_system": "openmetadata",
            "provenance": {
                "created_by": self._first_non_empty(provenance_payload.get("created_by"), provenance_payload.get("createdBy"), default=None),
                "approved_by": self._first_non_empty(provenance_payload.get("approved_by"), provenance_payload.get("approvedBy"), default=None),
                "created_at": self._first_non_empty(provenance_payload.get("created_at"), provenance_payload.get("createdAt"), default=None),
                "approved_at": self._first_non_empty(provenance_payload.get("approved_at"), provenance_payload.get("approvedAt"), default=None),
                "change_reason": self._first_non_empty(provenance_payload.get("change_reason"), provenance_payload.get("changeReason"), default=None),
            },
            "migration": migration_payload,
        }

    def _extract_product_spec_metadata(self, extension: Any) -> dict[str, Any]:
        if not isinstance(extension, dict):
            return {}
        for candidate in (
            self._read_nested_value(extension, "dq", "product_spec"),
            self._read_nested_value(extension, "dq", "productSpec"),
            self._read_nested_value(extension, "odps", "product_spec"),
            self._read_nested_value(extension, "odps", "productSpec"),
            extension.get("product_spec"),
            extension.get("productSpec"),
        ):
            if isinstance(candidate, dict):
                return candidate
        return extension

    def _coerce_contract_reference_list(self, payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            references: list[dict[str, Any]] = []
            for item in payload:
                reference = self._normalize_contract_reference(item)
                if reference.get("odcs_contract_id"):
                    references.append(reference)
            return references
        if isinstance(payload, str):
            text = payload.strip()
            if text:
                try:
                    parsed = json.loads(text)
                except json.JSONDecodeError:
                    parsed = None
                if isinstance(parsed, list):
                    return self._coerce_contract_reference_list(parsed)
                if isinstance(parsed, dict):
                    return self._coerce_contract_reference_list([parsed])
        reference = self._normalize_contract_reference(payload)
        if reference.get("odcs_contract_id"):
            return [reference]
        return []

    def _normalize_contract_reference(self, payload: Any) -> dict[str, Any]:
        if isinstance(payload, dict):
            return {
                "odcs_contract_id": self._first_non_empty(
                    payload.get("odcs_contract_id"),
                    payload.get("odcsContractId"),
                    payload.get("contract_id"),
                    payload.get("contractId"),
                    payload.get("id"),
                    default="",
                ),
                "odcs_contract_name": self._first_non_empty(
                    payload.get("odcs_contract_name"),
                    payload.get("odcsContractName"),
                    payload.get("contract_name"),
                    payload.get("contractName"),
                    payload.get("name"),
                    default="",
                ),
                "odcs_contract_version": self._first_non_empty(
                    payload.get("odcs_contract_version"),
                    payload.get("odcsContractVersion"),
                    payload.get("contract_version"),
                    payload.get("contractVersion"),
                    payload.get("version"),
                    default="",
                ),
                "openmetadata_entity_id": self._first_non_empty(
                    payload.get("openmetadata_entity_id"),
                    payload.get("openmetadataEntityId"),
                    default="",
                ),
                "openmetadata_entity_type": self._first_non_empty(
                    payload.get("openmetadata_entity_type"),
                    payload.get("openmetadataEntityType"),
                    default="data_contract",
                ),
                "source_system": self._first_non_empty(payload.get("source_system"), payload.get("sourceSystem"), default="openmetadata"),
            }
        if isinstance(payload, str):
            normalized = payload.strip()
            if normalized:
                return {
                    "odcs_contract_id": normalized,
                    "odcs_contract_name": normalized,
                    "odcs_contract_version": "",
                    "openmetadata_entity_id": "",
                    "openmetadata_entity_type": "data_contract",
                    "source_system": "openmetadata",
                }
        return {
            "odcs_contract_id": "",
            "odcs_contract_name": "",
            "odcs_contract_version": "",
            "openmetadata_entity_id": "",
            "openmetadata_entity_type": "data_contract",
            "source_system": "openmetadata",
        }

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

    def _coerce_list(self, payload: Any) -> list[str]:
        if isinstance(payload, list):
            result: list[str] = []
            for item in payload:
                normalized = self._first_non_empty(item)
                if normalized:
                    result.append(normalized)
            return result
        if isinstance(payload, str):
            text = payload.strip()
            if not text:
                return []
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                return [text]
            if isinstance(parsed, list):
                return [self._first_non_empty(item) for item in parsed if self._first_non_empty(item)]
            if isinstance(parsed, dict):
                return [self._first_non_empty(value) for value in parsed.values() if self._first_non_empty(value)]
            parsed_text = self._first_non_empty(parsed)
            return [parsed_text] if parsed_text else []
        normalized = self._first_non_empty(payload)
        return [normalized] if normalized else []

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

    def _first_non_empty(self, *values: Any, default: Any = "") -> Any:
        for value in values:
            if value is None:
                continue
            if isinstance(value, str):
                text = value.strip()
                if text:
                    return text
                continue
            if isinstance(value, (list, tuple, set)):
                if value:
                    return value
                continue
            if isinstance(value, dict):
                if value:
                    return value
                continue
            return value
        return default

    @staticmethod
    def _looks_like_uuid(value: str) -> bool:
        text = str(value or "").strip()
        if len(text) != 36:
            return False
        parts = text.split("-")
        return len(parts) == 5 and all(parts)