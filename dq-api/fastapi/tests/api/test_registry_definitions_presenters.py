from __future__ import annotations

from app.api.presenters.registry_definitions import build_registry_definition_lookup_http_exception
from app.application.services.registry_definition_resolver import RegistryDefinitionLookupError


def test_build_registry_definition_lookup_http_exception() -> None:
    not_found = build_registry_definition_lookup_http_exception(
        RegistryDefinitionLookupError("missing", status_code=404),
        "def.attribute.customer_id",
    )
    assert not_found.status_code == 404
    assert not_found.detail == {
        "error": "registry_definition_not_found",
        "message": "missing",
        "definition_id": "def.attribute.customer_id",
    }

    fallback = build_registry_definition_lookup_http_exception(
        RegistryDefinitionLookupError("boom", status_code=500),
        "query-term",
    )
    assert fallback.status_code == 500
    assert fallback.detail == {
        "error": "registry_definition_lookup_failed",
        "message": "boom",
        "definition_id": "query-term",
    }
