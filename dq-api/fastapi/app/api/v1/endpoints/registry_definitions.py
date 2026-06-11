from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.presenters.registry_definitions import build_registry_definition_lookup_http_exception
from app.api.v1.schemas import RegistryDefinitionView
from app.application.services.registry_definition_resolver import RegistryDefinitionLookupError
from app.application.services.registry_definition_resolver import RegistryDefinitionResolver
from app.core.dependencies import get_registry_definition_resolver


router = APIRouter(tags=["registry-definitions"])


def _as_lookup_http_exception(exc: RegistryDefinitionLookupError, definition_id: str) -> HTTPException:
    return build_registry_definition_lookup_http_exception(exc, definition_id)


@router.get(
    "/registry/reference-domains",
    response_model=list[RegistryDefinitionView],
    responses={
        200: {"description": "List governed reference domains and code lists."},
        503: {"description": "OpenMetadata is unavailable or misconfigured."},
    },
)
async def list_reference_domains(
    query: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    resolver: Any = Depends(get_registry_definition_resolver),
) -> list[RegistryDefinitionView]:
    try:
        payload = await resolver.list_definitions(
            query=query,
            definition_type="attribute",
            limit=200,
        )
    except RegistryDefinitionLookupError as exc:
        raise _as_lookup_http_exception(exc, query or "reference-domain-search") from exc

    reference_domains = [
        item
        for item in payload
        if isinstance(item, dict)
        and isinstance(item.get("value_domain"), dict)
        and bool(item["value_domain"].get("allowed_values"))
    ]
    return [RegistryDefinitionView.model_validate(item) for item in reference_domains[:limit]]


@router.get(
    "/registry/definitions/{definition_id}",
    response_model=RegistryDefinitionView,
    responses={
        200: {"description": "Resolved governed registry definition."},
        404: {"description": "Registry definition not found."},
        409: {"description": "Registry definition identifier is ambiguous."},
        503: {"description": "OpenMetadata is unavailable or misconfigured."},
    },
)
async def get_registry_definition(
    definition_id: str,
    resolver: Any = Depends(get_registry_definition_resolver),
) -> RegistryDefinitionView:
    try:
        payload = await resolver.resolve_definition(definition_id)
    except RegistryDefinitionLookupError as exc:
        raise _as_lookup_http_exception(exc, definition_id) from exc
    return RegistryDefinitionView.model_validate(payload)

@router.get(
    "/registry/definitions",
    response_model=list[RegistryDefinitionView],
    responses={
        200: {"description": "List or search governed registry definitions."},
        503: {"description": "OpenMetadata is unavailable or misconfigured."},
    },
)
async def list_registry_definitions(
    query: str | None = Query(default=None),
    definition_type: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    resolver: Any = Depends(get_registry_definition_resolver),
) -> list[RegistryDefinitionView]:
    try:
        payload = await resolver.list_definitions(
            query=query,
            definition_type=definition_type,
            limit=limit,
        )
    except RegistryDefinitionLookupError as exc:
        raise _as_lookup_http_exception(exc, query or "registry-definition-search") from exc
    return [RegistryDefinitionView.model_validate(item) for item in payload]