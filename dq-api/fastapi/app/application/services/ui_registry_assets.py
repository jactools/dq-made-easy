from __future__ import annotations

import json
import mimetypes
import tarfile
import zipfile
from io import BytesIO
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse
from urllib.request import Request as UrlRequest, urlopen
from uuid import uuid4
from typing import Any

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


def _archive_name(upload_filename: str) -> str:
    return Path(upload_filename or "").name.lower()


def _normalize_archive_member_path(member_name: str) -> str:
    normalized = str(member_name or "").strip().replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    normalized = normalized.lstrip("/")
    path = PurePosixPath(normalized)

    if not normalized or path.is_absolute() or any(part == ".." for part in path.parts):
        raise ValueError("Uploaded archive contains an invalid file name")

    return str(path)


def _read_uploaded_archive_files(upload_filename: str, content: bytes) -> dict[str, bytes]:
    archive_name = _archive_name(upload_filename)
    extracted_files: dict[str, bytes] = {}

    if archive_name.endswith(".zip"):
        try:
            with zipfile.ZipFile(BytesIO(content)) as archive:
                for member in archive.infolist():
                    if member.is_dir():
                        continue

                    relative_path = _normalize_archive_member_path(member.filename)
                    if relative_path in extracted_files:
                        raise ValueError("Uploaded archive contains duplicate file names")

                    extracted_files[relative_path] = archive.read(member)
        except (OSError, zipfile.BadZipFile) as exc:
            raise ValueError("Uploaded archive is not a valid .zip file") from exc

        if not extracted_files:
            raise ValueError("Uploaded archive must contain at least one file")

        return extracted_files

    if archive_name.endswith(".tgz") or archive_name.endswith(".tar.gz"):
        try:
            with tarfile.open(fileobj=BytesIO(content), mode="r:*") as archive:
                for member in archive.getmembers():
                    if not member.isfile():
                        continue

                    relative_path = _normalize_archive_member_path(member.name)
                    if relative_path in extracted_files:
                        raise ValueError("Uploaded archive contains duplicate file names")

                    extracted_file = archive.extractfile(member)
                    if extracted_file is None:
                        raise ValueError("Uploaded archive contains an empty file entry")

                    extracted_files[relative_path] = extracted_file.read()
        except (OSError, tarfile.TarError) as exc:
            raise ValueError("Uploaded archive is not a valid .tgz or .tar.gz file") from exc

        if not extracted_files:
            raise ValueError("Uploaded archive must contain at least one file")

        return extracted_files

    raise ValueError("Uploaded archive must be a .zip, .tgz, or .tar.gz file")


def _strip_single_archive_root(files: dict[str, bytes]) -> dict[str, bytes]:
    package_json_paths = [PurePosixPath(path) for path in files if PurePosixPath(path).name == "package.json"]
    root_candidates = [path.parts[0] for path in package_json_paths if len(path.parts) > 1]

    if len(root_candidates) != 1:
        return files

    root = root_candidates[0]
    if not all(len(PurePosixPath(path).parts) == 1 or PurePosixPath(path).parts[0] == root for path in files):
        return files

    stripped_files: dict[str, bytes] = {}
    for relative_path, content in files.items():
        path = PurePosixPath(relative_path)
        if len(path.parts) > 1 and path.parts[0] == root:
            stripped_files[str(PurePosixPath(*path.parts[1:]))] = content
        else:
            stripped_files[relative_path] = content

    return stripped_files


def _package_slug(package_name: str | None) -> str | None:
    if not package_name:
        return None

    slug = str(package_name).strip()
    if not slug:
        return None

    if slug.startswith("@") and "/" in slug:
        slug = slug.rsplit("/", 1)[-1]
    elif "/" in slug:
        slug = slug.rsplit("/", 1)[-1]

    slug = slug.strip().strip(".")
    return slug or None


def _style_candidate_paths(directory: str, package_name: str | None) -> list[str]:
    normalized_directory = str(PurePosixPath(directory)).strip().rstrip("/")
    if not normalized_directory:
        return []

    candidates: list[str] = []
    slug = _package_slug(package_name)
    if slug:
        candidates.append(f"{normalized_directory}/{slug}.css")
    candidates.extend(
        [
            f"{normalized_directory}/theme.css",
            f"{normalized_directory}/index.css",
            f"{normalized_directory}/styles.css",
        ]
    )
    return candidates


def _match_style_entry_in_directory(directory: str, available_files: set[str], package_name: str | None) -> str | None:
    normalized_directory = str(PurePosixPath(directory)).strip().rstrip("/")
    if not normalized_directory:
        return None

    for candidate in _style_candidate_paths(normalized_directory, package_name):
        if candidate in available_files:
            return candidate

    directory_matches = sorted(
        path for path in available_files if path.startswith(f"{normalized_directory}/") and path.endswith(".css")
    )
    if len(directory_matches) == 1:
        return directory_matches[0]

    return None


def _select_style_entry_path(files: dict[str, bytes]) -> str:
    available_files = set(files)
    package_json_bytes = files.get("package.json")
    package_json: dict[str, Any] | None = None

    if package_json_bytes is not None:
        try:
            package_json = json.loads(package_json_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("Uploaded archive contains an invalid package.json") from exc

    if package_json is not None:
        for field_name in ("style", "css", "stylesheet", "main", "module"):
            value = package_json.get(field_name)
            if not isinstance(value, str):
                continue

            normalized_value = str(PurePosixPath(value)).strip().lstrip("./")
            if normalized_value in available_files and normalized_value.endswith(".css"):
                return normalized_value

        files_field = package_json.get("files")
        if isinstance(files_field, list):
            for entry in files_field:
                if not isinstance(entry, str):
                    continue

                normalized_entry = str(PurePosixPath(entry)).strip().lstrip("./")
                if not normalized_entry:
                    continue

                if normalized_entry in available_files and normalized_entry.endswith(".css"):
                    return normalized_entry

                matched_directory = _match_style_entry_in_directory(normalized_entry, available_files, package_json.get("name"))
                if matched_directory is not None:
                    return matched_directory

    css_files = sorted(path for path in available_files if path.endswith(".css"))
    if len(css_files) == 1:
        return css_files[0]

    package_name = package_json.get("name") if package_json is not None else None
    for candidate_directory in ("css", "dist", "build", "lib"):
        matched_directory = _match_style_entry_in_directory(candidate_directory, available_files, package_name)
        if matched_directory is not None:
            return matched_directory

    raise ValueError("Uploaded style archive must include a discoverable stylesheet")


def _sanitize_bundle_directory(source_url: str, filename: str | None = None) -> str:
    explicit_name = str(filename or "").strip()
    if explicit_name:
        candidate = Path(explicit_name).stem
    else:
        parsed = urlparse(source_url)
        candidate = Path(parsed.path).stem

    base_name = candidate.strip().strip(".")
    if not base_name:
        base_name = "bundle"

    return f"{uuid4().hex}-{base_name}"


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


def _looks_like_archive_filename(file_name: str | None) -> bool:
    lowered = str(file_name or "").lower()
    return lowered.endswith(".zip") or lowered.endswith(".tgz") or lowered.endswith(".tar.gz")


def _store_uploaded_style_bundle(
    *,
    content: bytes,
    upload_filename: str,
    source_url: str,
    kind_segment: str,
) -> ImportedUiRegistryAsset:
    archive_files = _strip_single_archive_root(_read_uploaded_archive_files(upload_filename, content))
    entry_relative_path = _select_style_entry_path(archive_files)
    bundle_directory = _sanitize_bundle_directory(source_url, upload_filename)

    asset_dir = _asset_root() / kind_segment / bundle_directory
    asset_dir.mkdir(parents=True, exist_ok=True)

    for relative_path, file_content in archive_files.items():
        target_path = asset_dir / relative_path
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(file_content)

    entry_asset_path = asset_dir / entry_relative_path
    if not entry_asset_path.exists() or not entry_asset_path.is_file():
        raise ValueError("Uploaded style archive did not include the selected stylesheet")

    public_file_name = f"{bundle_directory}/{entry_relative_path}"
    entry_content = entry_asset_path.read_bytes()

    return ImportedUiRegistryAsset(
        kind=kind_segment,
        source_url=source_url,
        file_name=public_file_name,
        content_type=mimetypes.guess_type(entry_asset_path.name)[0],
        asset_path=str(entry_asset_path),
        public_url=_public_url(kind_segment, public_file_name),
        byte_count=len(entry_content),
    )


def _extract_uploaded_archive(upload_filename: str, content: bytes) -> _ExtractedArchiveAsset:
    archive_files = _read_uploaded_archive_files(upload_filename, content)
    if len(archive_files) != 1:
        raise ValueError("Uploaded archive must contain exactly one file")

    extracted_name, extracted_content = next(iter(archive_files.items()))
    return _ExtractedArchiveAsset(file_name=Path(extracted_name).name, content=extracted_content)


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

    remote_filename = filename or Path(urlparse(source_url).path).name
    if kind_segment == "styles" and _looks_like_archive_filename(remote_filename):
        return _store_uploaded_style_bundle(
            content=content,
            upload_filename=remote_filename or "ui-registry-asset.tgz",
            source_url=source_url,
            kind_segment=kind_segment,
        )

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
    if kind_segment == "styles":
        return _store_uploaded_style_bundle(
            content=content,
            upload_filename=upload_filename,
            source_url=f"upload://{Path(upload_filename).name or 'ui-registry-asset'}",
            kind_segment=kind_segment,
        )

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