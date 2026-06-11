from __future__ import annotations

from fastapi import HTTPException

from app.application.services.registry_definition_resolver import RegistryDefinitionLookupError


def build_registry_definition_lookup_http_exception(
    exc: RegistryDefinitionLookupError,
    definition_id: str,
) -> HTTPException:
    error_code_by_status = {
        404: "registry_definition_not_found",
        409: "registry_definition_ambiguous",
        503: "registry_definition_unavailable",
    }
    return HTTPException(
        status_code=exc.status_code,
        detail={
            "error": error_code_by_status.get(exc.status_code, "registry_definition_lookup_failed"),
            "message": str(exc),
            "definition_id": definition_id,
        },
    )