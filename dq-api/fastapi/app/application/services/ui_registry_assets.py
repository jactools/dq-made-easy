from __future__ import annotations

from io import BytesIO
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request as UrlRequest, urlopen
from uuid import uuid4
import mimetypes
import tarfile
import zipfile

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


@dataclass(frozen=True)
class _ExtractedArchiveAsset:
    file_name: str
    content: bytes


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


def _store_ui_registry_asset(
    *,
    kind_segment: str,
    source_url: str,
    target_file_name: str,
    content: bytes,
    content_type: str | None,
) -> ImportedUiRegistryAsset:
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


def _extract_uploaded_archive(upload_filename: str, content: bytes) -> _ExtractedArchiveAsset:
    archive_name = Path(upload_filename or "").name.lower()

    if archive_name.endswith(".zip"):
        with zipfile.ZipFile(BytesIO(content)) as archive:
            members = [member for member in archive.infolist() if not member.is_dir()]
            if len(members) != 1:
                raise ValueError("Uploaded archive must contain exactly one file")

            member = members[0]
            extracted_name = Path(member.filename).name
            if not extracted_name or extracted_name in {".", ".."}:
                raise ValueError("Uploaded archive contains an invalid file name")

            return _ExtractedArchiveAsset(file_name=extracted_name, content=archive.read(member))

    if archive_name.endswith(".tgz") or archive_name.endswith(".tar.gz"):
        with tarfile.open(fileobj=BytesIO(content), mode="r:*") as archive:
            members = [member for member in archive.getmembers() if member.isfile()]
            if len(members) != 1:
                raise ValueError("Uploaded archive must contain exactly one file")

            member = members[0]
            extracted_name = Path(member.name).name
            if not extracted_name or extracted_name in {".", ".."}:
                raise ValueError("Uploaded archive contains an invalid file name")

            extracted_file = archive.extractfile(member)
            if extracted_file is None:
                raise ValueError("Uploaded archive contains an empty file entry")

            return _ExtractedArchiveAsset(file_name=extracted_name, content=extracted_file.read())

    raise ValueError("Uploaded archive must be a .zip, .tgz, or .tar.gz file")


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
    request = UrlRequest(source_url, headers={"User-Agent": "DQ-UI-Registry-Importer/1.0"})

    with urlopen(request, timeout=30) as response:
        content = response.read()
        content_type = response.headers.get_content_type() if response.headers is not None else None

    target_file_name = _sanitize_filename(source_url, filename)
    return _store_ui_registry_asset(
        kind_segment=kind_segment,
        source_url=source_url,
        target_file_name=target_file_name,
        content=content,
        content_type=content_type,
    )


def import_uploaded_ui_registry_asset(*, content: bytes, upload_filename: str, kind: str) -> ImportedUiRegistryAsset:
    kind_segment = _asset_kind_segment(kind)
    extracted = _extract_uploaded_archive(upload_filename, content)
    target_file_name = _sanitize_filename(upload_filename, extracted.file_name)

    return _store_ui_registry_asset(
        kind_segment=kind_segment,
        source_url=f"upload://{Path(upload_filename).name or 'ui-registry-asset'}",
        target_file_name=target_file_name,
        content=extracted.content,
        content_type=mimetypes.guess_type(extracted.file_name)[0],
    )


def resolve_ui_registry_asset_path(kind: str, file_name: str) -> Path:
    kind_segment = _asset_kind_segment(kind)
    asset_root = _asset_root()
    candidate = (asset_root / kind_segment / file_name).resolve()
    if asset_root not in candidate.parents and candidate != asset_root:
        raise ValueError("Invalid UI registry asset path")
    return candidate