from __future__ import annotations

import json
from io import BytesIO

import tarfile
import zipfile
from pathlib import Path
from types import SimpleNamespace

from app.application.services import ui_registry_assets as asset_service
from app.application.services.ui_registry import RegistryConfiguration
from app.application.services.ui_registry import RegistryManifest
from app.application.services.ui_registry import RegistryManager
from app.application.services.ui_registry import RegistrySource
from app.core.dependencies import get_ui_registry_manager
from app.infrastructure.repositories.in_memory_ui_registry_repository import InMemoryUiRegistryRepository
from app.main import app
from app.core.config import get_settings


class _FakeResponse:
    def __init__(self, content: bytes, content_type: str = "text/css") -> None:
        self._content = content
        self.headers = SimpleNamespace(get_content_type=lambda: content_type)

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def read(self) -> bytes:
        return self._content


def test_ui_registry_asset_import_downloads_to_local_directory(client, auth_headers, monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DQ_UI_REGISTRY_ASSETS_DIR", str(tmp_path / "ui-registry-assets"))
    get_settings.cache_clear()

    monkeypatch.setattr(
        asset_service,
        "urlopen",
        lambda request, timeout=30: _FakeResponse(b"body { color: #123456; }", "text/css"),
    )

    try:
        response = client.post(
            "/api/system/v1/ui-registry/assets/import",
            headers=auth_headers("dq:config:manage"),
            json={
                "source_url": "https://example.com/theme.css",
                "kind": "style",
            },
        )

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["kind"] == "styles"
        assert payload["source_url"] == "https://example.com/theme.css"
        assert payload["public_url"].startswith("/system/v1/ui-registry/assets/styles/")

        asset_path = Path(payload["asset_path"])
        assert asset_path.exists()
        assert asset_path.read_text(encoding="utf-8") == "body { color: #123456; }"

        get_response = client.get(f"/api{payload['public_url']}")

        assert get_response.status_code == 200
        assert get_response.text == "body { color: #123456; }"
    finally:
        get_settings.cache_clear()


def test_ui_registry_asset_upload_extracts_style_bundle(client, auth_headers, monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DQ_UI_REGISTRY_ASSETS_DIR", str(tmp_path / "ui-registry-assets"))
    get_settings.cache_clear()

    repository = InMemoryUiRegistryRepository()
    manager = RegistryManager.from_configuration(
        RegistryConfiguration(
            source=RegistrySource.DEFAULT,
            fallback_manifest=RegistryManifest(),
        ),
        repository=repository,
    )
    app.dependency_overrides[get_ui_registry_manager] = lambda: manager

    archive_bytes = BytesIO()
    with tarfile.open(fileobj=archive_bytes, mode="w:gz") as archive:
        package_json = json.dumps(
            {
                "name": "@rabobank/rds-style",
                "version": "8.0.2",
                "files": ["css", "favicons", "fonts"],
            }
        ).encode("utf-8")
        package_info = tarfile.TarInfo(name="package/package.json")
        package_info.size = len(package_json)
        archive.addfile(package_info, BytesIO(package_json))

        css_content = b'@font-face { src: url("../fonts/myriad/files/demo.woff2"); }\nbody { color: #123456; }\n'
        css_info = tarfile.TarInfo(name="package/css/rds-style.css")
        css_info.size = len(css_content)
        archive.addfile(css_info, BytesIO(css_content))

        font_content = b"fake-font-bytes"
        font_info = tarfile.TarInfo(name="package/fonts/myriad/files/demo.woff2")
        font_info.size = len(font_content)
        archive.addfile(font_info, BytesIO(font_content))

    response = client.post(
        "/api/system/v1/ui-registry/assets/upload",
        headers=auth_headers("dq:config:manage"),
        data={"kind": "style", "label": "Custom Style"},
        files={"file": ("rds-style-8.0.2.tgz", archive_bytes.getvalue(), "application/gzip")},
    )

    try:
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["kind"] == "styles"
        assert payload["source_url"] == "upload://rds-style-8.0.2.tgz"
        assert payload["public_url"].startswith("/system/v1/ui-registry/assets/styles/")
        assert payload["public_url"].endswith("/css/rds-style.css")

        asset_path = Path(payload["asset_path"])
        assert asset_path.exists()

        get_response = client.get(f"/api{payload['public_url']}")

        assert get_response.status_code == 200
        assert get_response.text == '@font-face { src: url("../fonts/myriad/files/demo.woff2"); }\nbody { color: #123456; }\n'

        registry_response = client.get("/api/system/v1/ui-registry", headers=auth_headers("dq:admin:read"))
        assert registry_response.status_code == 200
        registry_payload = registry_response.json()
        assert registry_payload["styles"], registry_payload
        assert registry_payload["styles"][0]["css_url"] == payload["public_url"]
        assert registry_payload["styles"][0]["label"] == "Custom Style"

        font_public_url = payload["public_url"].replace("css/rds-style.css", "fonts/myriad/files/demo.woff2")
        font_response = client.get(f"/api{font_public_url}")

        assert font_response.status_code == 200
        assert font_response.content == b"fake-font-bytes"
    finally:
        app.dependency_overrides.pop(get_ui_registry_manager, None)
        get_settings.cache_clear()


def test_ui_registry_asset_upload_rejects_invalid_zip_archives(client, auth_headers, monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DQ_UI_REGISTRY_ASSETS_DIR", str(tmp_path / "ui-registry-assets"))
    get_settings.cache_clear()

    response = client.post(
        "/api/system/v1/ui-registry/assets/upload",
        headers=auth_headers("dq:config:manage"),
        data={"kind": "style"},
        files={"file": ("theme.zip", b"not-a-valid-zip", "application/zip")},
    )

    try:
        assert response.status_code == 400, response.text
        assert "valid .zip file" in response.json()["detail"]
    finally:
        get_settings.cache_clear()


def test_ui_registry_asset_upload_extracts_component_bundle(client, auth_headers, monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DQ_UI_REGISTRY_ASSETS_DIR", str(tmp_path / "ui-registry-assets"))
    get_settings.cache_clear()

    archive_bytes = BytesIO()
    with tarfile.open(fileobj=archive_bytes, mode="w:gz") as archive:
        content = b"export const icons = [];\n"
        info = tarfile.TarInfo(name="icons.mjs")
        info.size = len(content)
        archive.addfile(info, BytesIO(content))

    response = client.post(
        "/api/system/v1/ui-registry/assets/upload",
        headers=auth_headers("dq:config:manage"),
        data={"kind": "component"},
        files={"file": ("icons.tgz", archive_bytes.getvalue(), "application/gzip")},
    )

    try:
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["kind"] == "component-bundles"
        assert payload["source_url"] == "upload://icons.tgz"
        assert payload["public_url"].startswith("/system/v1/ui-registry/assets/component-bundles/")

        asset_path = Path(payload["asset_path"])
        assert asset_path.exists()
        assert asset_path.read_text(encoding="utf-8") == "export const icons = [];\n"
    finally:
        get_settings.cache_clear()