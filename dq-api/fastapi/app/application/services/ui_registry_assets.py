from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request as UrlRequest, urlopen
from uuid import uuid4
import mimetypes

from app.core.config import get_settings


@dataclass(frozen=True)
class ImportedUiRegistryAsset:
    kind: str
    source_url: str
    file_name: str
    content_type: str | None
    asset_path: str
    public_url: str
    byte_count: int


def _asset_kind_segment(kind: str) -> str:
    normalized = str(kind or "").strip().lower()
    if normalized in {"style", "styles", "stylesheet", "css"}:
        return "styles"
    if normalized in {"component", "components", "bundle", "bundles", "component_bundle"}:
        return "component-bundles"
    raise ValueError(f"Unsupported UI registry asset kind: {kind}")


def _sanitize_filename(source_url: str, filename: str | None = None) -> str:
    explicit_name = str(filename or "").strip()
    if explicit_name:
                candidate = Path(explicit_name).name
    else:
                parsed = urlparse(source_url)
                candidate = Path(parsed.path).name

    base_name = Path(candidate).name
    if not base_name or base_name in {".", ".."}:
        base_name = "asset"

    return f"{uuid4().hex}-{base_name}"


def _asset_root() -> Path:
    settings = get_settings()
    root = Path(settings.ui_registry_assets_dir).expanduser()
    if not root.is_absolute():
        root = Path.cwd() / root
    return root.resolve()


def _public_url(kind_segment: str, file_name: str) -> str:
    return f"/system/v1/ui-registry/assets/{kind_segment}/{file_name}"


def import_remote_ui_registry_asset(
    *,
    source_url: str,
    kind: str,
    filename: str | None = None,
) -> ImportedUiRegistryAsset:
    kind_segment = _asset_kind_segment(kind)
    target_file_name = _sanitize_filename(source_url, filename)
    request = UrlRequest(source_url, headers={"User-Agent": "DQ-UI-Registry-Importer/1.0"})

    with urlopen(request, timeout=30) as response:
        content = response.read()
        content_type = response.headers.get_content_type() if response.headers is not None else None

    asset_dir = _asset_root() / kind_segment
    asset_dir.mkdir(parents=True, exist_ok=True)
    asset_file = asset_dir / target_file_name
    asset_file.write_bytes(content)

    media_type = content_type or mimetypes.guess_type(asset_file.name)[0]
    return ImportedUiRegistryAsset(
        kind=kind_segment,
        source_url=source_url,
        file_name=target_file_name,
        content_type=media_type,
        asset_path=str(asset_file),
        public_url=_public_url(kind_segment, target_file_name),
        byte_count=len(content),
    )


def resolve_ui_registry_asset_path(kind: str, file_name: str) -> Path:
    kind_segment = _asset_kind_segment(kind)
    asset_root = _asset_root()
    candidate = (asset_root / kind_segment / file_name).resolve()
    if asset_root not in candidate.parents and candidate != asset_root:
        raise ValueError("Invalid UI registry asset path")
    return candidate