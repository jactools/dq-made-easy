from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from app.application.services.ui_registry import ComponentBundleEntry
from app.application.services.ui_registry import EnvironmentLoader
from app.application.services.ui_registry import FileLoader
from app.application.services.ui_registry import RegistryConfiguration
from app.application.services.ui_registry import RegistryLoadError
from app.application.services.ui_registry import RegistryManifest
from app.application.services.ui_registry import RegistryManager
from app.application.services.ui_registry import RegistrySource
from app.application.services.ui_registry import RegistryValidationError
from app.application.services.ui_registry import StyleEntry
from app.infrastructure.repositories.in_memory_ui_registry_repository import InMemoryUiRegistryRepository


def test_registry_manifest_round_trip() -> None:
    manifest = RegistryManifest(
        version="2.0.0",
        styles=[StyleEntry(id="theme-a", label="Theme A", css_url="/theme-a.css")],
        component_bundles=[ComponentBundleEntry(id="icons", label="Icons", adapter="app.adapters.icons")],
    )

    restored = RegistryManifest.from_dict(manifest.to_dict())

    assert restored.version == "2.0.0"
    assert restored.styles[0].id == "theme-a"
    assert restored.component_bundles[0].adapter == "app.adapters.icons"


def test_registry_manifest_enforces_version_contract() -> None:
    manifest = RegistryManifest(version="2.0.0")

    with pytest.raises(RegistryValidationError, match="does not match expected"):
        manifest.validate_contract("1.0.0")


def test_registry_configuration_resolves_source_precedence() -> None:
    configuration = RegistryConfiguration(
        source=RegistrySource.DEFAULT,
        json_payload="{}",
        file_path="/tmp/registry.json",
        url="https://registry.example.com",
    )

    assert configuration.resolve_source() == RegistrySource.ENVIRONMENT


def test_file_loader_reads_json_manifest(tmp_path) -> None:
    manifest_path = tmp_path / "registry.json"
    manifest_path.write_text(
        json.dumps(
            {
                "version": "1.0.0",
                "styles": [{"id": "theme-a", "label": "Theme A", "css_url": "/theme-a.css"}],
                "component_bundles": [],
            }
        ),
        encoding="utf-8",
    )

    manifest = FileLoader(manifest_path).load()

    assert manifest.styles[0].label == "Theme A"


def test_environment_loader_reads_json(monkeypatch: pytest.MonkeyPatch) -> None:
    loader = EnvironmentLoader(
        json.dumps(
            {
                "styles": [{"id": "theme-b", "label": "Theme B", "css_url": "/theme-b.css"}],
                "component_bundles": [],
            }
        )
    )

    manifest = loader.load()

    assert manifest.styles[0].id == "theme-b"


def test_registry_manager_uses_default_manifest() -> None:
    default_manifest = RegistryManifest(
        styles=[StyleEntry(id="default-theme", label="Default Theme", css_url="/default.css")],
        component_bundles=[],
    )

    manifest = RegistryManager(source=RegistrySource.DEFAULT, default_manifest=default_manifest).load()

    assert manifest is default_manifest


def test_registry_manager_falls_back_on_missing_file() -> None:
    fallback_manifest = RegistryManifest(
        styles=[StyleEntry(id="fallback-theme", label="Fallback Theme", css_url="/fallback.css")],
        component_bundles=[],
    )
    configuration = RegistryConfiguration(
        source=RegistrySource.FILE,
        file_path="/definitely/not/present/ui-registry.json",
        fallback_manifest=fallback_manifest,
    )

    manifest = RegistryManager.from_configuration(configuration).load()

    assert manifest.styles[0].id == "fallback-theme"


def test_registry_manager_refreshes_when_cache_expires(tmp_path) -> None:
    manifest_path = tmp_path / "registry.json"
    manifest_path.write_text(
        json.dumps(
            {
                "version": "1.0.0",
                "styles": [{"id": "theme-a", "label": "Theme A", "css_url": "/theme-a.css"}],
                "component_bundles": [],
            }
        ),
        encoding="utf-8",
    )

    current_time = datetime(2026, 7, 1, tzinfo=timezone.utc)

    def clock() -> datetime:
        return current_time

    manager = RegistryManager(
        source=RegistrySource.FILE,
        configuration=RegistryConfiguration(
            source=RegistrySource.FILE,
            file_path=manifest_path,
            cache_ttl_seconds=30,
        ),
        clock=clock,
    )

    first_manifest = manager.load()

    manifest_path.write_text(
        json.dumps(
            {
                "version": "1.0.0",
                "styles": [{"id": "theme-b", "label": "Theme B", "css_url": "/theme-b.css"}],
                "component_bundles": [],
            }
        ),
        encoding="utf-8",
    )

    current_time += timedelta(seconds=10)
    second_manifest = manager.load()

    current_time += timedelta(seconds=30)
    third_manifest = manager.load()

    assert first_manifest.styles[0].id == "theme-a"
    assert second_manifest.styles[0].id == "theme-a"
    assert third_manifest.styles[0].id == "theme-b"


def test_registry_manager_raises_for_unsupported_source() -> None:
    class _Settings:
        ui_registry_source = "bogus"
        ui_registry_json = None
        ui_registry_file = None
        ui_registry_url = None
        ui_registry_manifest_version = "1.0.0"
        ui_registry_cache_ttl_seconds = 300

    with pytest.raises(RegistryLoadError, match="Unsupported UI registry source"):
        RegistryConfiguration.from_settings(_Settings())


def test_registry_manager_persists_loaded_manifest_snapshot() -> None:
    repository = InMemoryUiRegistryRepository()
    manager = RegistryManager(
        source=RegistrySource.DEFAULT,
        default_manifest=RegistryManifest(
            styles=[StyleEntry(id="default-theme", label="Default Theme", css_url="/default.css")],
            component_bundles=[],
        ),
        repository=repository,
    )

    manifest = manager.load()

    assert repository.manifest is not None
    assert repository.manifest.metadata["source_type"] == "default"
    assert manifest.metadata["stored_in_database"] is True
    assert manifest.metadata["storage_table"] == "ui_registry_manifest"


def test_registry_manager_prefers_persisted_snapshot_for_default_source() -> None:
    repository = InMemoryUiRegistryRepository(
        RegistryManifest(
            styles=[StyleEntry(id="db-theme", label="DB Theme", css_url="/db.css")],
            component_bundles=[],
        )
    )

    manifest = RegistryManager(source=RegistrySource.DEFAULT, repository=repository).load()

    assert manifest.styles[0].id == "db-theme"