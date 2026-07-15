from __future__ import annotations

from app.application.services.ui_registry import RegistryConfiguration
from app.application.services.ui_registry import RegistryManager
from app.application.services.ui_registry import RegistrySource
from app.application.services.ui_registry import RegistryManifest
from app.application.services.ui_registry import StyleEntry
from app.application.services.ui_registry import ComponentBundleEntry
from app.core.dependencies import get_ui_registry_manager


def test_internal_ui_registry_endpoint_returns_resolved_manifest(client, auth_headers) -> None:
    fallback_manifest = RegistryManifest(
        styles=[StyleEntry(id="theme-a", label="Theme A", css_url="/theme-a.css")],
        component_bundles=[ComponentBundleEntry(id="icons", label="Icons", adapter="app.adapters.icons")],
    )
    manager = RegistryManager.from_configuration(
        RegistryConfiguration(
            source=RegistrySource.DEFAULT,
            fallback_manifest=fallback_manifest,
            cache_ttl_seconds=120,
        )
    )

    from app.main import app

    app.dependency_overrides[get_ui_registry_manager] = lambda: manager

    response = client.get("/api/system/v1/ui-registry", headers=auth_headers("dq:admin:read"))

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "default"
    assert payload["version"] == "1.0.0"
    assert payload["cache_ttl_seconds"] == 120
    assert payload["styles"][0]["id"] == "theme-a"
    assert payload["component_bundles"][0]["adapter"] == "app.adapters.icons"


def test_public_ui_registry_endpoint_is_not_exposed(client, auth_headers) -> None:
    response = client.get("/system/v1/ui-registry", headers=auth_headers("dq:admin:read"))

    assert response.status_code == 404