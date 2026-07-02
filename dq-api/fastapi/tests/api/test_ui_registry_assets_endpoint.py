from __future__ import annotations

from io import BytesIO
from __future__ import annotations

import tarfile
import zipfile
from pathlib import Path
from types import SimpleNamespace

from app.application.services import ui_registry_assets as asset_service
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

        get_response = client.get(f"/api{payload['public_url']}", headers=auth_headers("dq:admin:read"))

        assert get_response.status_code == 200
        assert get_response.text == "body { color: #123456; }"
    finally:
        get_settings.cache_clear()


def test_ui_registry_asset_upload_extracts_style_bundle(client, auth_headers, monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DQ_UI_REGISTRY_ASSETS_DIR", str(tmp_path / "ui-registry-assets"))
    get_settings.cache_clear()

    archive_bytes = BytesIO()
    with zipfile.ZipFile(archive_bytes, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("theme.css", b"body { color: #123456; }")

    response = client.post(
        "/api/system/v1/ui-registry/assets/upload",
        headers=auth_headers("dq:config:manage"),
        data={"kind": "style"},
        files={"file": ("theme.zip", archive_bytes.getvalue(), "application/zip")},
    )

    try:
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["kind"] == "styles"
        assert payload["source_url"] == "upload://theme.zip"
        assert payload["public_url"].startswith("/system/v1/ui-registry/assets/styles/")

        asset_path = Path(payload["asset_path"])
        assert asset_path.exists()
        assert asset_path.read_text(encoding="utf-8") == "body { color: #123456; }"
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