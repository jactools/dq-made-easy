import json
import os
from pathlib import Path
from typing import Any

from fastapi import Request

from app.domain.interfaces import AppConfigRepository

_VERSION_MANIFEST_FILENAMES = ("VERSION_MANIFEST.json", "version-manifest.json")


def _candidate_package_json_paths(source_file: Path) -> list[Path]:
    candidates: list[Path] = []

    # Known candidates for local/dev and containerized layouts.
    for parent_index in (5, 4):
        if parent_index < len(source_file.parents):
            candidates.append(source_file.parents[parent_index] / "package.json")

    # Also inspect ancestor package.json files to be resilient to path differences.
    for parent in source_file.parents:
        candidate = parent / "package.json"
        if candidate not in candidates:
            candidates.append(candidate)

    return candidates


def _read_version_from_package_json(package_json_path: Path) -> str | None:
    try:
        with package_json_path.open("r", encoding="utf-8") as package_file:
            payload = json.load(package_file)
        version = payload.get("version")
        if isinstance(version, str) and version.strip():
            return version.strip()
    except Exception:
        return None
    return None


def _read_api_version() -> str:
    source_file = Path(__file__).resolve()

    for candidate in _candidate_package_json_paths(source_file):
        resolved = _read_version_from_package_json(candidate)
        if resolved:
            return resolved

    return "unknown"


def _read_version_manifest() -> dict[str, dict[str, str]]:
    source_file = Path(__file__).resolve()
    for parent in source_file.parents:
        for manifest_name in _VERSION_MANIFEST_FILENAMES:
            manifest_path = parent / manifest_name
            if not manifest_path.exists():
                continue
            try:
                payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(payload, dict):
                continue
            apps = payload.get("apps")
            components = payload.get("components")
            return {
                "apps": apps if isinstance(apps, dict) else {},
                "components": components if isinstance(components, dict) else {},
            }
    return {"apps": {}, "components": {}}


def resolve_api_version(request: Request | None) -> str:
    manifest = _read_version_manifest()
    api_from_manifest = str(manifest.get("apps", {}).get("api") or "").strip()
    if api_from_manifest:
        return api_from_manifest

    # Prefer package metadata when available, and fallback to app version metadata.
    package_version = _read_api_version()
    if package_version != "unknown":
        return package_version

    if request is not None:
        app_version = getattr(request.app, "version", None)
        if isinstance(app_version, str) and app_version.strip() and app_version.strip() != "unknown":
            return app_version.strip()

        try:
            openapi_info = request.app.openapi().get("info", {})
            openapi_version = str(openapi_info.get("version") or "").strip()
            if openapi_version and openapi_version != "unknown":
                return openapi_version
        except Exception:
            pass

    env_version = os.getenv("APP_VERSION")
    if isinstance(env_version, str) and env_version.strip():
        return env_version.strip()

    for env_key in ("API_VERSION", "SERVICE_VERSION", "OTEL_SERVICE_VERSION"):
        value = os.getenv(env_key)
        if isinstance(value, str) and value.strip() and value.strip() != "unknown":
            return value.strip()

    return "unknown"


def resolve_ui_version() -> str:
    manifest = _read_version_manifest()
    ui_from_manifest = str(manifest.get("apps", {}).get("ui") or "").strip()
    if ui_from_manifest:
        return ui_from_manifest

    env_ui_version = os.getenv("UI_VERSION")
    if isinstance(env_ui_version, str) and env_ui_version.strip():
        return env_ui_version.strip()

    return "unknown"


def _normalize_component_map(raw_components: Any) -> dict[str, str]:
    components: dict[str, str] = {}
    if isinstance(raw_components, dict):
        for key, value in raw_components.items():
            key_text = str(key).strip()
            value_text = str(value).strip()
            if key_text and value_text:
                components[key_text] = value_text
    return components


def build_version_catalog(
    request: Request | None,
    app_config_repository: AppConfigRepository | None = None,
) -> dict[str, object]:
    del request

    if app_config_repository is None:
        return {
            "apps": {
                "ui": "unknown",
                "api": "unknown",
            },
            "components": {},
        }

    try:
        app_config = app_config_repository.get_app_config()
    except Exception:
        return {
            "apps": {
                "ui": "unknown",
                "api": "unknown",
            },
            "components": {},
        }

    db_api = str(getattr(app_config, "versionCatalogApi", "") or "").strip()
    db_ui = str(getattr(app_config, "versionCatalogUi", "") or "").strip()
    db_components = _normalize_component_map(getattr(app_config, "versionCatalogComponents", None))

    resolved_api = db_api or "unknown"
    resolved_ui = db_ui or "unknown"

    return {
        "apps": {
            "ui": resolved_ui,
            "api": resolved_api,
        },
        "components": db_components,
    }
