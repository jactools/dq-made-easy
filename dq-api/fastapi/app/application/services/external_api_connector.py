from __future__ import annotations

import json
from typing import Any, cast
from urllib.error import HTTPError
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import Request as UrlRequest
from urllib.request import urlopen

from app.domain.entities.connector import ConnectorApiMethod
from app.domain.entities.connector import ConnectorApiOperationEntity
from app.domain.entities.connector import ConnectorConfigurationEntity
from app.domain.entities.connector import ConnectorDiscoveryItemEntity
from app.domain.entities.connector import ConnectorDiscoveryResultEntity
from app.domain.entities.connector import ConnectorErrorEntity
from app.domain.entities.connector import ConnectorHealthResultEntity
from app.domain.entities.connector import ConnectorSecureConfigurationEntity
from app.domain.entities.connector import ConnectorSyncResultEntity
from app.domain.entities.connector import ConnectorValidationResultEntity
from app.domain.entities.connector import ExternalApiConnectorConfigurationEntity
from app.domain.entities.connector import get_connector_registry_entry


_ALLOWED_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"})


class ExternalApiConnector:
    provider = "external_api"
    capabilities = get_connector_registry_entry("external_api").capabilities

    def __init__(
        self,
        *,
        spec_loader: Any | None = None,
        sync_sink: Any | None = None,
    ) -> None:
        self._spec_loader = spec_loader or self._load_openapi_spec
        self._sync_sink = sync_sink

    def configure(self, configuration: ConnectorConfigurationEntity) -> ConnectorConfigurationEntity:
        if isinstance(configuration, ExternalApiConnectorConfigurationEntity):
            return configuration.without_secret_values()
        if isinstance(configuration, ConnectorSecureConfigurationEntity):
            return configuration.without_secret_values()
        return configuration

    def validate(self, configuration: ConnectorConfigurationEntity) -> ConnectorValidationResultEntity:
        errors = self._configuration_errors(configuration)
        return ConnectorValidationResultEntity(provider=self.provider, valid=not errors, errors=tuple(errors))

    def discover(self, configuration: ConnectorConfigurationEntity) -> ConnectorDiscoveryResultEntity:
        secure_configuration = self._coerce_secure_configuration(configuration)
        if secure_configuration is None:
            return ConnectorDiscoveryResultEntity(provider=self.provider, errors=tuple(self._configuration_errors(configuration)))

        validation_errors = self._configuration_errors(secure_configuration)
        if validation_errors:
            return ConnectorDiscoveryResultEntity(provider=self.provider, errors=tuple(validation_errors))

        discovered_items = [self._build_discovered_item(secure_configuration, operation, source="configured") for operation in secure_configuration.api_operations]
        discovered_keys = {self._operation_key(item.metadata.get("method"), item.metadata.get("path")) for item in discovered_items}

        if secure_configuration.openapi_url:
            spec_error = self._discover_from_openapi(secure_configuration, discovered_items, discovered_keys)
            if spec_error is not None and not discovered_items:
                return ConnectorDiscoveryResultEntity(provider=self.provider, errors=(spec_error,))

        return ConnectorDiscoveryResultEntity(provider=self.provider, items=tuple(discovered_items))

    def sync(self, configuration: ConnectorConfigurationEntity) -> ConnectorSyncResultEntity:
        secure_configuration = self._coerce_secure_configuration(configuration)
        if secure_configuration is None:
            return ConnectorSyncResultEntity(provider=self.provider, errors=tuple(self._configuration_errors(configuration)))

        discovery = self.discover(secure_configuration)
        if discovery.errors:
            return ConnectorSyncResultEntity(provider=self.provider, errors=discovery.errors)

        public_configuration = self.configure(secure_configuration)
        if self._sync_sink is not None:
            self._sync_sink(public_configuration, discovery)

        return ConnectorSyncResultEntity(provider=self.provider, synced_count=len(discovery.items), items=discovery.items)

    def health(self, configuration: ConnectorConfigurationEntity) -> ConnectorHealthResultEntity:
        validation = self.validate(configuration)
        if not validation.valid:
            return ConnectorHealthResultEntity(provider=self.provider, status="unhealthy", errors=validation.errors)

        discovery = self.discover(configuration)
        if discovery.errors:
            return ConnectorHealthResultEntity(provider=self.provider, status="degraded", errors=discovery.errors)

        configured_count = len([item for item in discovery.items if item.metadata.get("source") == "configured"])
        openapi_count = len([item for item in discovery.items if item.metadata.get("source") == "openapi"])
        return ConnectorHealthResultEntity(
            provider=self.provider,
            status="healthy",
            details={
                "configured_operation_count": configured_count,
                "openapi_operation_count": openapi_count,
                "operation_count": len(discovery.items),
            },
        )

    def _coerce_secure_configuration(self, configuration: ConnectorConfigurationEntity) -> ExternalApiConnectorConfigurationEntity | None:
        if isinstance(configuration, ExternalApiConnectorConfigurationEntity) and self._normalized_text(configuration.provider) == self.provider:
            return configuration
        return None

    def _configuration_errors(self, configuration: ConnectorConfigurationEntity) -> list[ConnectorErrorEntity]:
        errors: list[ConnectorErrorEntity] = []
        if not isinstance(configuration, ExternalApiConnectorConfigurationEntity):
            errors.append(
                ConnectorErrorEntity(
                    kind="configuration",
                    message="External API connector requires ExternalApiConnectorConfigurationEntity",
                    code="external_api_secure_configuration_required",
                    field="configuration",
                )
            )
            return errors

        if self._normalized_text(configuration.provider) != self.provider:
            errors.append(
                ConnectorErrorEntity(
                    kind="configuration",
                    message="External API connector only accepts the 'external_api' provider",
                    code="external_api_provider_mismatch",
                    field="provider",
                )
            )

        if not self._normalized_text(configuration.base_url):
            errors.append(
                ConnectorErrorEntity(
                    kind="configuration",
                    message="External API connector requires 'base_url'",
                    code="external_api_missing_base_url",
                    field="base_url",
                )
            )
        elif not self._is_http_url(configuration.base_url):
            errors.append(
                ConnectorErrorEntity(
                    kind="configuration",
                    message="External API connector requires base_url to use http or https",
                    code="external_api_invalid_base_url",
                    field="base_url",
                )
            )

        if configuration.openapi_url and not self._is_http_url(configuration.openapi_url):
            errors.append(
                ConnectorErrorEntity(
                    kind="configuration",
                    message="External API connector requires openapi_url to use http or https",
                    code="external_api_invalid_openapi_url",
                    field="openapi_url",
                )
            )

        if configuration.request_timeout_seconds < 1:
            errors.append(
                ConnectorErrorEntity(
                    kind="configuration",
                    message="External API connector requires request_timeout_seconds >= 1",
                    code="external_api_invalid_timeout",
                    field="request_timeout_seconds",
                )
            )

        if not configuration.api_operations and not self._normalized_text(configuration.openapi_url):
            errors.append(
                ConnectorErrorEntity(
                    kind="configuration",
                    message="External API connector requires api_operations or openapi_url",
                    code="external_api_missing_operation_inventory",
                    field="api_operations",
                )
            )

        seen_keys: set[tuple[str, str]] = set()
        for operation in configuration.api_operations:
            if not self._normalized_text(operation.name):
                errors.append(
                    ConnectorErrorEntity(
                        kind="configuration",
                        message="External API connector operations require a name",
                        code="external_api_missing_operation_name",
                        field="api_operations",
                    )
                )
                continue
            if operation.method not in _ALLOWED_METHODS:
                errors.append(
                    ConnectorErrorEntity(
                        kind="configuration",
                        message=f"External API connector does not support HTTP method '{operation.method}'",
                        code="external_api_invalid_operation_method",
                        field="api_operations",
                    )
                )
            normalized_path = self._normalize_path(operation.path)
            if not normalized_path:
                errors.append(
                    ConnectorErrorEntity(
                        kind="configuration",
                        message="External API connector operations require a path",
                        code="external_api_missing_operation_path",
                        field="api_operations",
                    )
                )
                continue
            key = (operation.method, normalized_path)
            if key in seen_keys:
                errors.append(
                    ConnectorErrorEntity(
                        kind="configuration",
                        message=f"External API connector duplicates operation {operation.method} {normalized_path}",
                        code="external_api_duplicate_operation",
                        field="api_operations",
                    )
                )
                continue
            seen_keys.add(key)

        return errors

    def _discover_from_openapi(
        self,
        configuration: ExternalApiConnectorConfigurationEntity,
        discovered_items: list[ConnectorDiscoveryItemEntity],
        discovered_keys: set[tuple[str, str]],
    ) -> ConnectorErrorEntity | None:
        try:
            spec = self._spec_loader(configuration.openapi_url, configuration.request_timeout_seconds)
        except (HTTPError, URLError, ValueError, json.JSONDecodeError) as exc:
            return ConnectorErrorEntity(
                kind="discovery",
                message=f"External API connector could not load OpenAPI document: {exc}",
                code="external_api_openapi_unavailable",
                retryable=False,
                details={"openapi_url": configuration.openapi_url},
            )

        paths = spec.get("paths")
        if not isinstance(paths, dict):
            return ConnectorErrorEntity(
                kind="discovery",
                message="External API connector OpenAPI document is missing paths",
                code="external_api_openapi_missing_paths",
                retryable=False,
                details={"openapi_url": configuration.openapi_url},
            )

        for raw_path, path_item in paths.items():
            path_text = self._normalize_path(raw_path)
            if not path_text or not isinstance(path_item, dict):
                continue
            for method, raw_operation in path_item.items():
                normalized_method = self._normalized_text(method)
                if not normalized_method:
                    continue
                normalized_method = normalized_method.upper()
                if normalized_method not in _ALLOWED_METHODS or not isinstance(raw_operation, dict):
                    continue
                key = (normalized_method, path_text)
                if key in discovered_keys:
                    continue
                operation = self._openapi_operation_from_spec(normalized_method, path_text, raw_operation)
                discovered_items.append(self._build_discovered_item(configuration, operation, source="openapi"))
                discovered_keys.add(key)

        return None

    def _openapi_operation_from_spec(self, method: str, path: str, raw_operation: dict[str, Any]) -> ConnectorApiOperationEntity:
        operation_name = self._normalized_text(raw_operation.get("operationId")) or f"{method.lower()}_{path.strip('/').replace('/', '_').replace('{', '').replace('}', '')}"
        summary = self._normalized_text(raw_operation.get("summary") or raw_operation.get("description"))
        tags = tuple(self._normalized_text(tag) for tag in raw_operation.get("tags") or [] if self._normalized_text(tag))
        response_content_type = self._first_response_content_type(raw_operation)
        return ConnectorApiOperationEntity(
            name=operation_name,
            method=cast(ConnectorApiMethod, method),
            path=path,
            description=summary,
            tags=tags,
            required=bool(raw_operation.get("requestBody")),
            response_content_type=response_content_type,
        )

    def _build_discovered_item(
        self,
        configuration: ExternalApiConnectorConfigurationEntity,
        operation: ConnectorApiOperationEntity,
        *,
        source: str,
    ) -> ConnectorDiscoveryItemEntity:
        path = self._normalize_path(operation.path) or operation.path
        method = operation.method.upper()
        return ConnectorDiscoveryItemEntity(
            identifier=f"{self._normalized_text(configuration.base_url)}::{method}:{path}",
            kind="api_operation",
            name=operation.name,
            workspace_id=configuration.workspace_id,
            metadata={
                "base_url": self._normalized_text(configuration.base_url),
                "method": method,
                "path": path,
                "description": operation.description,
                "tags": list(operation.tags),
                "required": operation.required,
                "response_content_type": operation.response_content_type,
                "source": source,
            },
        )

    def _load_openapi_spec(self, openapi_url: str, timeout_seconds: int) -> dict[str, Any]:
        request = UrlRequest(openapi_url, headers={"Accept": "application/json"})
        with urlopen(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("invalid external API OpenAPI document: expected object")
        return payload

    def _first_response_content_type(self, operation: dict[str, Any]) -> str | None:
        responses = operation.get("responses")
        if not isinstance(responses, dict):
            return None
        for response in responses.values():
            if not isinstance(response, dict):
                continue
            content = response.get("content")
            if not isinstance(content, dict):
                continue
            for content_type in content:
                normalized = self._normalized_text(content_type)
                if normalized:
                    return normalized
        return None

    def _operation_key(self, method: Any, path: Any) -> tuple[str, str]:
        return (self._normalized_text(method).upper() if self._normalized_text(method) else "", self._normalize_path(path) or "")

    def _normalize_path(self, path: Any) -> str | None:
        text = self._normalized_text(path)
        if not text:
            return None
        if not text.startswith("/"):
            text = f"/{text}"
        return text

    def _normalized_text(self, value: Any) -> str | None:
        text = str(value or "").strip()
        return text or None

    def _is_http_url(self, value: str | None) -> bool:
        parsed = urlsplit(str(value or "").strip())
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


__all__ = ["ExternalApiConnector"]