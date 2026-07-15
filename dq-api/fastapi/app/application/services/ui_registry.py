"""UI registry contract and loader for API-managed UI configuration."""

from __future__ import annotations

import json
import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import urlopen


logger = logging.getLogger(__name__)

REGISTRY_SCHEMA_VERSION = "1.0.0"


def _is_local_stylesheet_href(value: str | None) -> bool:
    if not value:
        return False

    normalized = value.strip()
    if not normalized:
        return False

    if normalized.startswith(("/", "./", "../")):
        return True

    parsed = urlparse(normalized)
    return not parsed.scheme and not parsed.netloc


class RegistrySource(Enum):
    """Supported sources for registry configuration."""

    ENVIRONMENT = "environment"
    FILE = "file"
    URL = "url"
    DEFAULT = "default"


class RegistryValidationError(Exception):
    """Raised when registry validation fails."""

    def __init__(self, message: str, entry_id: str | None = None, entry_type: str | None = None):
        self.entry_id = entry_id
        self.entry_type = entry_type
        prefix = f"{entry_type}: " if entry_type else ""
        super().__init__(f"{prefix}{message}")


class RegistryLoadError(Exception):
    """Raised when registry loading fails."""


@dataclass
class RegistryConfiguration:
    """Resolved registry loader configuration.

    Explicit source selection wins. When the source is default, the
    configuration falls back to a concrete source in this precedence order:
    environment JSON, file path, remote URL, then built-in default manifest.
    """

    source: RegistrySource | None = None
    json_payload: str | None = None
    file_path: str | Path | None = None
    url: str | None = None
    expected_version: str = REGISTRY_SCHEMA_VERSION
    cache_ttl_seconds: int = 300
    fallback_manifest: RegistryManifest | None = None

    @classmethod
    def from_settings(
        cls,
        settings: Any,
        *,
        fallback_manifest: RegistryManifest | None = None,
    ) -> RegistryConfiguration:
        source_value = str(getattr(settings, "ui_registry_source", "default") or "default").strip().lower()
        try:
            source = RegistrySource(source_value)
        except ValueError as exc:
            raise RegistryLoadError(f"Unsupported UI registry source: {source_value}") from exc

        return cls(
            source=source,
            json_payload=str(getattr(settings, "ui_registry_json", "") or "").strip() or None,
            file_path=str(getattr(settings, "ui_registry_file", "") or "").strip() or None,
            url=str(getattr(settings, "ui_registry_url", "") or "").strip() or None,
            expected_version=str(getattr(settings, "ui_registry_manifest_version", REGISTRY_SCHEMA_VERSION) or REGISTRY_SCHEMA_VERSION).strip(),
            cache_ttl_seconds=max(int(getattr(settings, "ui_registry_cache_ttl_seconds", 300) or 300), 1),
            fallback_manifest=fallback_manifest,
        )

    def resolve_source(self) -> RegistrySource:
        if self.source is not None and self.source != RegistrySource.DEFAULT:
            return self.source
        if self.json_payload:
            return RegistrySource.ENVIRONMENT
        if self.file_path:
            return RegistrySource.FILE
        if self.url:
            return RegistrySource.URL
        return RegistrySource.DEFAULT


@dataclass
class StyleEntry:
    id: str
    label: str
    description: str | None = None
    source_ref: str | None = None
    css_url: str | None = None
    fallback: str = "ignore"
    priority: int = 0
    is_active: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "description": self.description,
            "source_ref": self.source_ref,
            "css_url": self.css_url,
            "fallback": self.fallback,
            "priority": self.priority,
            "is_active": self.is_active,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StyleEntry:
        return cls(
            id=str(data["id"]),
            label=str(data["label"]),
            description=data.get("description"),
            source_ref=data.get("source_ref"),
            css_url=data.get("css_url"),
            fallback=str(data.get("fallback", "ignore")),
            priority=int(data.get("priority", 0)),
            is_active=bool(data.get("is_active", True)),
        )


@dataclass
class ComponentBundleEntry:
    id: str
    label: str
    description: str | None = None
    adapter: str | None = None
    fallback: str = "ignore"
    priority: int = 0
    is_active: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "description": self.description,
            "adapter": self.adapter,
            "fallback": self.fallback,
            "priority": self.priority,
            "is_active": self.is_active,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ComponentBundleEntry:
        return cls(
            id=str(data["id"]),
            label=str(data["label"]),
            description=data.get("description"),
            adapter=data.get("adapter"),
            fallback=str(data.get("fallback", "ignore")),
            priority=int(data.get("priority", 0)),
            is_active=bool(data.get("is_active", True)),
        )


@dataclass
class RegistryEntry:
    id: str
    label: str
    type: str
    description: str | None = None
    priority: int = 0
    is_active: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "type": self.type,
            "description": self.description,
            "priority": self.priority,
            "is_active": self.is_active,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RegistryEntry:
        return cls(
            id=str(data["id"]),
            label=str(data["label"]),
            type=str(data["type"]),
            description=data.get("description"),
            priority=int(data.get("priority", 0)),
            is_active=bool(data.get("is_active", True)),
        )


@dataclass
class RegistryManifest:
    version: str = "1.0.0"
    created: str | None = None
    updated: str | None = None
    styles: list[StyleEntry] = field(default_factory=list)
    component_bundles: list[ComponentBundleEntry] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "created": self.created,
            "updated": self.updated,
            "styles": [entry.to_dict() for entry in self.styles],
            "component_bundles": [entry.to_dict() for entry in self.component_bundles],
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RegistryManifest:
        manifest = cls(
            version=str(data.get("version", "1.0.0")),
            created=data.get("created"),
            updated=data.get("updated"),
            metadata=dict(data.get("metadata", {})),
        )
        if "styles" in data:
            manifest.styles = [StyleEntry.from_dict(entry) for entry in data["styles"]]
        if "component_bundles" in data:
            manifest.component_bundles = [
                ComponentBundleEntry.from_dict(entry) for entry in data["component_bundles"]
            ]
        return manifest

    def validate_contract(self, expected_version: str | None = None) -> None:
        if expected_version and self.version != expected_version:
            raise RegistryValidationError(
                f"Registry schema version '{self.version}' does not match expected '{expected_version}'"
            )


class RegistryLoader(ABC):
    @abstractmethod
    def load(self) -> RegistryManifest:
        raise NotImplementedError


class EnvironmentLoader(RegistryLoader):
    def __init__(self, json_payload: str | None = None):
        self.json_payload = json_payload

    def load(self) -> RegistryManifest:
        json_str = self.json_payload or os.environ.get("DQ_UI_REGISTRY_JSON")
        if not json_str:
            raise RegistryLoadError("DQ_UI_REGISTRY_JSON environment variable is required")

        try:
            return RegistryManifest.from_dict(json.loads(json_str))
        except json.JSONDecodeError as exc:
            raise RegistryLoadError(f"Invalid JSON in environment variable: {exc}") from exc


class FileLoader(RegistryLoader):
    def __init__(self, file_path: str | Path):
        self.file_path = Path(file_path)

    def load(self) -> RegistryManifest:
        if not self.file_path.exists():
            raise RegistryLoadError(f"Registry file not found: {self.file_path}")

        try:
            content = self.file_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise RegistryLoadError(f"Failed to read registry file: {exc}") from exc

        try:
            return RegistryManifest.from_dict(json.loads(content))
        except json.JSONDecodeError as exc:
            raise RegistryLoadError(f"Failed to parse JSON registry: {exc}") from exc


class URLLoader(RegistryLoader):
    def __init__(self, url: str):
        self.url = str(url)

    def load(self) -> RegistryManifest:
        if not self.url:
            raise RegistryLoadError("Registry URL is required")

        try:
            with urlopen(self.url, timeout=30) as response:
                content = response.read().decode("utf-8")
        except URLError as exc:
            raise RegistryLoadError(f"Failed to fetch registry from {self.url}: {exc}") from exc

        try:
            return RegistryManifest.from_dict(json.loads(content))
        except json.JSONDecodeError as exc:
            raise RegistryLoadError(f"Invalid JSON in registry from {self.url}: {exc}") from exc


class RegistryManager:
    DEFAULT_SOURCE: RegistrySource = RegistrySource.DEFAULT

    def __init__(
        self,
        source: RegistrySource | None = None,
        default_manifest: RegistryManifest | None = None,
        configuration: RegistryConfiguration | None = None,
        repository: Any | None = None,
        clock: Any | None = None,
    ):
        self.configuration = configuration or RegistryConfiguration(source=source)
        self.source = self.configuration.resolve_source()
        self.default_manifest = default_manifest or self.configuration.fallback_manifest or RegistryManifest()
        self.repository = repository
        self.current_manifest: RegistryManifest | None = None
        self._loaded = False
        self._loaded_at: datetime | None = None
        self._clock = clock or datetime.now

    @classmethod
    def from_configuration(
        cls,
        configuration: RegistryConfiguration,
        *,
        repository: Any | None = None,
    ) -> RegistryManager:
        return cls(configuration=configuration, repository=repository)

    @classmethod
    def from_settings(cls, settings: Any, *, repository: Any | None = None) -> RegistryManager:
        return cls.from_configuration(RegistryConfiguration.from_settings(settings), repository=repository)

    def load(self) -> RegistryManifest:
        if self._loaded and self.current_manifest is not None and self._cache_is_valid():
            return self.current_manifest

        try:
            if self.source == RegistrySource.DEFAULT and self.repository is not None:
                manifest = self.repository.get_current_manifest() or self.default_manifest
            elif self.source == RegistrySource.DEFAULT:
                manifest = self.default_manifest
            else:
                loader = self._get_loader(self.source)
                manifest = loader.load()
            self.current_manifest = self._persist_manifest_snapshot(self._validate_and_normalize(manifest))
            self._loaded_at = self._clock()
        except (RegistryLoadError, RegistryValidationError) as exc:
            logger.warning("UI registry load failed; falling back to default manifest: %s", exc)
            self.current_manifest = self._persist_manifest_snapshot(self._validate_and_normalize(self.default_manifest))
            self._loaded_at = self._clock()
        self._loaded = True
        return self.current_manifest

    def _persist_manifest_snapshot(self, manifest: RegistryManifest) -> RegistryManifest:
        if self.repository is None:
            return manifest

        source_type = self.source.value if self.source is not None else RegistrySource.DEFAULT.value
        return self.repository.upsert_current_manifest(
            manifest,
            source_type=source_type,
            source_ref=self._describe_source_ref(),
        )

    def _describe_source_ref(self) -> str | None:
        if self.source == RegistrySource.ENVIRONMENT:
            return "DQ_UI_REGISTRY_JSON"
        if self.source == RegistrySource.FILE:
            return str(self.configuration.file_path or os.environ.get("DQ_UI_REGISTRY_FILE", "/etc/ui-registry.json"))
        if self.source == RegistrySource.URL:
            return str(self.configuration.url or os.environ.get("DQ_UI_REGISTRY_URL", "")) or None
        return "built-in-default"

    def _cache_is_valid(self) -> bool:
        if self._loaded_at is None:
            return False
        elapsed = self._clock() - self._loaded_at
        return elapsed.total_seconds() < self.configuration.cache_ttl_seconds

    def _get_loader(self, source: RegistrySource) -> RegistryLoader:
        if source == RegistrySource.ENVIRONMENT:
            return EnvironmentLoader(self.configuration.json_payload)
        if source == RegistrySource.FILE:
            return FileLoader(self.configuration.file_path or os.environ.get("DQ_UI_REGISTRY_FILE", "/etc/ui-registry.json"))
        if source == RegistrySource.URL:
            return URLLoader(self.configuration.url or os.environ.get("DQ_UI_REGISTRY_URL", ""))
        raise RegistryLoadError(f"Unknown registry source: {source}")

    def _validate_entry(self, entry: RegistryEntry, entry_type: str) -> list[str]:
        errors: list[str] = []
        if not entry.id:
            errors.append("id is required")
        if not entry.label:
            errors.append("label is required")
        if entry.type not in {"style", "component_bundle"}:
            errors.append(f"Invalid entry type: {entry.type}")

        if entry_type == "style":
            if not getattr(entry, "css_url", None):
                errors.append("css_url is required for styles")
            elif not _is_local_stylesheet_href(getattr(entry, "css_url", None)):
                errors.append("css_url must reference a local site path")
            fallback = getattr(entry, "fallback", "ignore")
            if fallback not in {"ignore", "fallback", "replace"}:
                errors.append(f"Invalid fallback value: {fallback}")
        elif entry_type == "component_bundle":
            if getattr(entry, "adapter", None) is None:
                errors.append("adapter is required for component bundles")
            fallback = getattr(entry, "fallback", "ignore")
            if fallback not in {"ignore", "fallback", "replace"}:
                errors.append(f"Invalid fallback value: {fallback}")

        return errors

    def _validate_and_normalize(self, manifest: RegistryManifest) -> RegistryManifest:
        manifest.validate_contract(self.configuration.expected_version)
        errors: list[str] = []

        for entry in manifest.styles:
            entry_errors = []
            if not entry.id:
                entry_errors.append("id is required")
            if not entry.label:
                entry_errors.append("label is required")
            if not entry.css_url:
                entry_errors.append("css_url is required for styles")
            elif not _is_local_stylesheet_href(entry.css_url):
                entry_errors.append("css_url must reference a local site path")
            if entry.fallback not in {"ignore", "fallback", "replace"}:
                entry_errors.append(f"Invalid fallback value: {entry.fallback}")
            if entry_errors:
                errors.append(f"Style '{entry.id}': {entry_errors}")

        for entry in manifest.component_bundles:
            entry_errors = []
            if not entry.id:
                entry_errors.append("id is required")
            if not entry.label:
                entry_errors.append("label is required")
            if entry.adapter is None:
                entry_errors.append("adapter is required for component bundles")
            if entry.fallback not in {"ignore", "fallback", "replace"}:
                entry_errors.append(f"Invalid fallback value: {entry.fallback}")
            if entry_errors:
                errors.append(f"Component bundle '{entry.id}': {entry_errors}")

        if errors:
            raise RegistryValidationError(f"Registry validation failed: {errors}")

        manifest.styles.sort(key=lambda entry: entry.priority)
        manifest.component_bundles.sort(key=lambda entry: entry.priority)
        manifest.metadata["validated_at"] = datetime.now().isoformat()
        return manifest

    def get_active_styles(self) -> list[StyleEntry]:
        if self.current_manifest is None:
            return []
        return [entry for entry in self.current_manifest.styles if entry.is_active]

    def get_active_component_bundles(self) -> list[ComponentBundleEntry]:
        if self.current_manifest is None:
            return []
        return [entry for entry in self.current_manifest.component_bundles if entry.is_active]

    def refresh(self) -> RegistryManifest:
        self._loaded = False
        return self.load()

    def save_manifest(self, manifest: RegistryManifest) -> RegistryManifest:
        self.current_manifest = self._persist_manifest_snapshot(self._validate_and_normalize(manifest))
        self._loaded = True
        self._loaded_at = self._clock()
        return self.current_manifest

    def update_manifest(self, manifest: RegistryManifest) -> None:
        self.current_manifest = manifest
        self._loaded = False