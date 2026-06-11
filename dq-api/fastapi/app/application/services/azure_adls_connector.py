from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any
from urllib.parse import urlsplit

from app.domain.entities.connector import AzureAdlsConnectorConfigurationEntity
from app.domain.entities.connector import ConnectorConfigurationEntity
from app.domain.entities.connector import ConnectorDiscoveryItemEntity
from app.domain.entities.connector import ConnectorDiscoveryResultEntity
from app.domain.entities.connector import ConnectorErrorEntity
from app.domain.entities.connector import ConnectorHealthResultEntity
from app.domain.entities.connector import ConnectorSecureConfigurationEntity
from app.domain.entities.connector import ConnectorSyncResultEntity
from app.domain.entities.connector import ConnectorValidationResultEntity
from app.domain.entities.connector import get_connector_registry_entry


class AzureAdlsConnector:
    provider = "azure_adls"
    capabilities = get_connector_registry_entry("azure_adls").capabilities

    def __init__(
        self,
        *,
        client_factory: Callable[[AzureAdlsConnectorConfigurationEntity], Any] | None = None,
        sync_sink: Callable[[ConnectorConfigurationEntity, ConnectorDiscoveryResultEntity], None] | None = None,
    ) -> None:
        self._client_factory = client_factory or self._build_service_client
        self._sync_sink = sync_sink

    def configure(self, configuration: ConnectorConfigurationEntity) -> ConnectorConfigurationEntity:
        if isinstance(configuration, AzureAdlsConnectorConfigurationEntity):
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

        try:
            client = self._client_factory(secure_configuration)
        except Exception as exc:
            return ConnectorDiscoveryResultEntity(
                provider=self.provider,
                errors=(
                    ConnectorErrorEntity(
                        kind="connection",
                        message=f"Azure ADLS client initialization failed: {exc}",
                        code="azure_adls_client_unavailable",
                        retryable=False,
                    ),
                ),
            )

        discovered_items: list[ConnectorDiscoveryItemEntity] = []
        discovered_keys: set[tuple[str, str]] = set()

        file_system_names = self._file_system_names(client)
        configured_file_systems = self._normalized_names(secure_configuration.file_systems)
        configured_prefixes = self._normalized_names(secure_configuration.path_prefixes)

        if configured_file_systems:
            file_system_names = [name for name in file_system_names if name in configured_file_systems]

        for file_system_name in file_system_names:
            self._append_file_system_item(secure_configuration, file_system_name, discovered_items, discovered_keys)
            prefixes = configured_prefixes or (None,)
            file_system_client = self._get_file_system_client(client, file_system_name)
            for prefix in prefixes:
                try:
                    paths = file_system_client.get_paths(path=prefix, recursive=True)
                except Exception as exc:
                    return ConnectorDiscoveryResultEntity(
                        provider=self.provider,
                        errors=(
                            ConnectorErrorEntity(
                                kind="discovery",
                                message=f"Azure ADLS path discovery failed for file_system '{file_system_name}': {exc}",
                                code="azure_adls_path_discovery_failed",
                                retryable=False,
                                details={"file_system": file_system_name, "path_prefix": prefix},
                            ),
                        ),
                    )
                for entry in paths:
                    path_name = self._normalized_text(entry.get("name"))
                    if not path_name:
                        continue
                    kind = "directory" if bool(entry.get("is_directory")) else "file"
                    item = ConnectorDiscoveryItemEntity(
                        identifier=f"{self._normalized_text(secure_configuration.account_url)}::{file_system_name}/{path_name}",
                        kind=kind,
                        name=path_name.rsplit("/", 1)[-1],
                        workspace_id=secure_configuration.workspace_id,
                        metadata={
                            "account_url": self._normalized_text(secure_configuration.account_url),
                            "file_system": file_system_name,
                            "path": path_name,
                            "kind": kind,
                            "content_length": entry.get("content_length"),
                            "last_modified": self._serialize_datetime(entry.get("last_modified")),
                            "source": "discovered",
                        },
                    )
                    key = (item.kind, item.identifier)
                    if key in discovered_keys:
                        continue
                    discovered_items.append(item)
                    discovered_keys.add(key)

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

        filesystem_count = len([item for item in discovery.items if item.kind == "filesystem"])
        directory_count = len([item for item in discovery.items if item.kind == "directory"])
        file_count = len([item for item in discovery.items if item.kind == "file"])
        return ConnectorHealthResultEntity(
            provider=self.provider,
            status="healthy",
            details={
                "filesystem_count": filesystem_count,
                "directory_count": directory_count,
                "file_count": file_count,
                "item_count": len(discovery.items),
            },
        )

    def _coerce_secure_configuration(self, configuration: ConnectorConfigurationEntity) -> AzureAdlsConnectorConfigurationEntity | None:
        if isinstance(configuration, AzureAdlsConnectorConfigurationEntity) and self._normalized_text(configuration.provider) == self.provider:
            return configuration
        return None

    def _configuration_errors(self, configuration: ConnectorConfigurationEntity) -> list[ConnectorErrorEntity]:
        errors: list[ConnectorErrorEntity] = []
        if not isinstance(configuration, AzureAdlsConnectorConfigurationEntity):
            errors.append(
                ConnectorErrorEntity(
                    kind="configuration",
                    message="Azure ADLS connector requires AzureAdlsConnectorConfigurationEntity",
                    code="azure_adls_secure_configuration_required",
                    field="configuration",
                )
            )
            return errors

        if self._normalized_text(configuration.provider) != self.provider:
            errors.append(
                ConnectorErrorEntity(
                    kind="configuration",
                    message="Azure ADLS connector only accepts the 'azure_adls' provider",
                    code="azure_adls_provider_mismatch",
                    field="provider",
                )
            )

        if not self._is_https_url(configuration.account_url):
            errors.append(
                ConnectorErrorEntity(
                    kind="configuration",
                    message="Azure ADLS connector requires account_url to use http or https",
                    code="azure_adls_invalid_account_url",
                    field="account_url",
                )
            )

        if configuration.request_timeout_seconds < 1:
            errors.append(
                ConnectorErrorEntity(
                    kind="configuration",
                    message="Azure ADLS connector requires request_timeout_seconds >= 1",
                    code="azure_adls_invalid_timeout",
                    field="request_timeout_seconds",
                )
            )

        seen_file_systems: set[str] = set()
        for file_system_name in configuration.file_systems:
            normalized = self._normalized_text(file_system_name)
            if not normalized:
                errors.append(
                    ConnectorErrorEntity(
                        kind="configuration",
                        message="Azure ADLS connector file_systems entries must not be empty",
                        code="azure_adls_missing_file_system",
                        field="file_systems",
                    )
                )
                continue
            if normalized in seen_file_systems:
                errors.append(
                    ConnectorErrorEntity(
                        kind="configuration",
                        message=f"Azure ADLS connector duplicates file system '{normalized}'",
                        code="azure_adls_duplicate_file_system",
                        field="file_systems",
                    )
                )
                continue
            seen_file_systems.add(normalized)

        seen_prefixes: set[str] = set()
        for prefix in configuration.path_prefixes:
            normalized = self._normalized_text(prefix)
            if normalized in seen_prefixes:
                errors.append(
                    ConnectorErrorEntity(
                        kind="configuration",
                        message=f"Azure ADLS connector duplicates path prefix '{normalized}'",
                        code="azure_adls_duplicate_path_prefix",
                        field="path_prefixes",
                    )
                )
                continue
            if normalized:
                seen_prefixes.add(normalized)

        return errors

    def _build_service_client(self, configuration: AzureAdlsConnectorConfigurationEntity) -> Any:
        try:
            from azure.storage.filedatalake import DataLakeServiceClient
        except Exception as exc:  # pragma: no cover
            raise RuntimeError("Python package 'azure-storage-file-datalake' is required for Azure ADLS discovery") from exc

        credential = self._resolve_credential(configuration)
        if not credential:
            raise RuntimeError("Azure ADLS connector requires an account_key or sas_token credential")
        return DataLakeServiceClient(account_url=configuration.account_url, credential=credential)

    def _resolve_credential(self, configuration: AzureAdlsConnectorConfigurationEntity) -> str | None:
        for credential in configuration.credentials:
            name = self._normalized_text(credential.name)
            if name in {"account_key", "sas_token"}:
                value = self._normalized_text(credential.value.get_secret_value())
                if value:
                    return value
        return None

    def _file_system_names(self, client: Any) -> list[str]:
        raw_file_systems = client.list_file_systems()
        names: list[str] = []
        for entry in raw_file_systems:
            name = self._normalized_text(entry.get("name") if isinstance(entry, dict) else getattr(entry, "name", None))
            if name:
                names.append(name)
        return names

    def _get_file_system_client(self, client: Any, file_system_name: str) -> Any:
        if not hasattr(client, "get_file_system_client"):
            raise RuntimeError("Azure ADLS service client must provide get_file_system_client")
        return client.get_file_system_client(file_system_name)

    def _append_file_system_item(
        self,
        configuration: AzureAdlsConnectorConfigurationEntity,
        file_system_name: str,
        discovered_items: list[ConnectorDiscoveryItemEntity],
        discovered_keys: set[tuple[str, str]],
    ) -> None:
        identifier = f"{self._normalized_text(configuration.account_url)}::{file_system_name}"
        key = ("filesystem", identifier)
        if key in discovered_keys:
            return
        discovered_items.append(
            ConnectorDiscoveryItemEntity(
                identifier=identifier,
                kind="filesystem",
                name=file_system_name,
                workspace_id=configuration.workspace_id,
                metadata={
                    "account_url": self._normalized_text(configuration.account_url),
                    "file_system": file_system_name,
                    "source": "listed",
                },
            )
        )
        discovered_keys.add(key)

    def _normalized_names(self, values: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(normalized for normalized in (self._normalized_text(value) for value in values) if normalized)

    def _serialize_datetime(self, value: Any) -> str | None:
        if isinstance(value, datetime):
            return value.replace(microsecond=0).isoformat()
        text = self._normalized_text(value)
        return text

    def _normalized_text(self, value: Any) -> str | None:
        text = str(value or "").strip()
        return text or None

    def _is_https_url(self, value: str | None) -> bool:
        parsed = urlsplit(str(value or "").strip())
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


__all__ = ["AzureAdlsConnector"]