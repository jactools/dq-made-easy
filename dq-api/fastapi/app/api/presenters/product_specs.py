from __future__ import annotations

from fastapi import HTTPException

from app.application.services.product_spec_resolver import ProductSpecLookupError


def build_product_spec_lookup_http_exception(
    exc: ProductSpecLookupError,
    product_spec_id: str,
) -> HTTPException:
    error_code_by_status = {
        404: "product_spec_not_found",
        409: "product_spec_ambiguous",
        503: "product_spec_unavailable",
    }
    return HTTPException(
        status_code=exc.status_code,
        detail={
            "error": error_code_by_status.get(exc.status_code, "product_spec_lookup_failed"),
            "message": str(exc),
            "product_spec_id": product_spec_id,
        },
    )


def build_product_spec_inventory_http_exception(exc: ProductSpecLookupError) -> HTTPException:
    error_code_by_status = {
        409: "product_spec_inventory_conflict",
        503: "product_spec_inventory_unavailable",
    }
    return HTTPException(
        status_code=exc.status_code,
        detail={
            "error": error_code_by_status.get(exc.status_code, "product_spec_inventory_failed"),
            "message": str(exc),
        },
    )


def build_product_spec_mutation_http_exception(
    exc: ProductSpecLookupError,
    product_spec_id: str | None = None,
) -> HTTPException:
    error_code_by_status = {
        404: "product_spec_not_found",
        409: "product_spec_conflict",
        422: "invalid_product_spec_request",
        503: "product_spec_unavailable",
    }
    detail = {
        "error": error_code_by_status.get(exc.status_code, "product_spec_mutation_failed"),
        "message": str(exc),
    }
    normalized_product_spec_id = str(product_spec_id or "").strip()
    if normalized_product_spec_id:
        detail["product_spec_id"] = normalized_product_spec_id
    return HTTPException(status_code=exc.status_code, detail=detail)