from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, status

from app.api.presenters.data_catalog import build_data_catalog_page_payload
from app.api.presenters.product_specs import build_product_spec_inventory_http_exception
from app.api.presenters.product_specs import build_product_spec_lookup_http_exception
from app.api.presenters.product_specs import build_product_spec_mutation_http_exception
from app.api.v1.schemas.product_spec_view import ProductSpecsPageView
from app.api.v1.schemas.product_spec_view import ProductSpecImportReportView
from app.api.v1.schemas.product_spec_view import ProductSpecImportRequestView
from app.api.v1.schemas.product_spec_view import ProductSpecSummaryView
from app.api.v1.schemas.product_spec_view import ProductSpecStewardshipActionRequestView
from app.api.v1.schemas.product_spec_view import ProductSpecUpsertRequestView
from app.api.v1.schemas.product_spec_view import ProductSpecView
from app.application.services.product_spec_resolver import ProductSpecLookupError
from app.core.dependencies import get_product_spec_resolver


router = APIRouter(tags=["product-specs"])


@router.get(
    "/product-specs",
    response_model=ProductSpecsPageView,
    responses={
        200: {"description": "Product specification registry inventory."},
        409: {"description": "Product specification inventory contains conflicting stable identifiers."},
        503: {"description": "OpenMetadata is unavailable or misconfigured."},
    },
)
async def list_product_specs(
    owner: str | None = Query(default=None),
    lifecycle_state: str | None = Query(default=None),
    registry_definition_id: str | None = Query(default=None),
    linked_contract_id: str | None = Query(default=None),
    search: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    resolver: Any = Depends(get_product_spec_resolver),
) -> ProductSpecsPageView:
    try:
        payload = await resolver.list_product_specs(
            owner=owner,
            lifecycle_state=lifecycle_state,
            registry_definition_id=registry_definition_id,
            linked_contract_id=linked_contract_id,
            search=search,
        )
    except ProductSpecLookupError as exc:
        raise build_product_spec_inventory_http_exception(exc) from exc
    return ProductSpecsPageView.model_validate(build_data_catalog_page_payload(payload, page, limit))


@router.get(
    "/product-specs/summary",
    response_model=ProductSpecSummaryView,
    responses={
        200: {"description": "Product-spec registry summary grouped by lifecycle state and owner."},
        503: {"description": "OpenMetadata is unavailable or misconfigured."},
    },
)
async def summarize_product_specs(
    resolver: Any = Depends(get_product_spec_resolver),
) -> ProductSpecSummaryView:
    try:
        payload = await resolver.summarize_product_specs()
    except ProductSpecLookupError as exc:
        raise build_product_spec_inventory_http_exception(exc) from exc
    return ProductSpecSummaryView.model_validate(payload)


@router.post(
    "/product-specs",
    response_model=ProductSpecView,
    status_code=status.HTTP_201_CREATED,
    responses={
        201: {"description": "Created and synchronized product specification."},
        409: {"description": "Product specification already exists or conflicts with registry state."},
        422: {"description": "The product-spec request payload is invalid."},
        503: {"description": "OpenMetadata is unavailable or misconfigured."},
    },
)
async def create_product_spec(
    body: ProductSpecUpsertRequestView,
    resolver: Any = Depends(get_product_spec_resolver),
) -> ProductSpecView:
    try:
        payload = await resolver.create_product_spec(body.model_dump(exclude_none=True))
    except ProductSpecLookupError as exc:
        raise build_product_spec_mutation_http_exception(exc, body.product_spec_id) from exc
    return ProductSpecView.model_validate(payload)


@router.post(
    "/product-specs/import",
    response_model=ProductSpecImportReportView,
    responses={
        200: {"description": "Imported product-spec manifest and synchronized all entries."},
        409: {"description": "Product-spec import payload conflicts with registry state."},
        422: {"description": "The product-spec import payload is invalid."},
        503: {"description": "OpenMetadata is unavailable or misconfigured."},
    },
)
async def import_product_specs(
    body: ProductSpecImportRequestView,
    dry_run: bool = Query(default=False),
    resolver: Any = Depends(get_product_spec_resolver),
) -> ProductSpecImportReportView:
    try:
        payload = await resolver.import_product_specs(body.model_dump(exclude_none=True), dry_run=dry_run)
    except ProductSpecLookupError as exc:
        raise build_product_spec_mutation_http_exception(exc) from exc
    return ProductSpecImportReportView.model_validate(payload)


@router.post(
    "/product-specs/{product_spec_id}/stewardship-actions",
    response_model=ProductSpecView,
    responses={
        200: {"description": "Applied stewardship action and synchronized lifecycle state."},
        404: {"description": "Product specification not found."},
        409: {"description": "Product specification conflicts with registry state."},
        422: {"description": "The product-spec stewardship request payload is invalid."},
        503: {"description": "OpenMetadata is unavailable or misconfigured."},
    },
)
async def apply_product_spec_stewardship_action(
    product_spec_id: str,
    body: ProductSpecStewardshipActionRequestView,
    resolver: Any = Depends(get_product_spec_resolver),
) -> ProductSpecView:
    try:
        payload = await resolver.apply_stewardship_action(
            product_spec_id,
            body.model_dump(exclude_none=True),
        )
    except ProductSpecLookupError as exc:
        raise build_product_spec_mutation_http_exception(exc, product_spec_id) from exc
    return ProductSpecView.model_validate(payload)


@router.put(
    "/product-specs/{product_spec_id}",
    response_model=ProductSpecView,
    responses={
        200: {"description": "Updated and synchronized product specification."},
        404: {"description": "Product specification not found."},
        409: {"description": "Product specification conflicts with registry state."},
        422: {"description": "The product-spec request payload is invalid."},
        503: {"description": "OpenMetadata is unavailable or misconfigured."},
    },
)
async def update_product_spec(
    product_spec_id: str,
    body: ProductSpecUpsertRequestView,
    resolver: Any = Depends(get_product_spec_resolver),
) -> ProductSpecView:
    try:
        payload = await resolver.update_product_spec(product_spec_id, body.model_dump(exclude_none=True))
    except ProductSpecLookupError as exc:
        raise build_product_spec_mutation_http_exception(exc, product_spec_id) from exc
    return ProductSpecView.model_validate(payload)


@router.get(
    "/product-specs/{product_spec_id}",
    response_model=ProductSpecView,
    responses={
        200: {"description": "Resolved product specification."},
        404: {"description": "Product specification not found."},
        409: {"description": "Product specification identifier is ambiguous."},
        503: {"description": "OpenMetadata is unavailable or misconfigured."},
    },
)
async def get_product_spec(
    product_spec_id: str,
    resolver: Any = Depends(get_product_spec_resolver),
) -> ProductSpecView:
    try:
        payload = await resolver.resolve_product_spec(product_spec_id)
    except ProductSpecLookupError as exc:
        raise build_product_spec_lookup_http_exception(exc, product_spec_id) from exc
    return ProductSpecView.model_validate(payload)