from __future__ import annotations

from collections.abc import Callable
from collections.abc import Sequence
from typing import Any, Literal, TypeVar

from pydantic import ConfigDict, Field, SecretStr, model_validator

from app.domain.entities.base import EntityModel


ConnectorOperation = Literal["configure", "validate", "discover", "sync", "health"]
ConnectorErrorKind = Literal[
    "connection",
    "authentication",
    "schema",
    "configuration",
    "discovery",
    "sync",
    "health",
    "validation",
    "unsupported",
]
ConnectorHealthStatus = Literal["healthy", "degraded", "unhealthy", "unknown"]

KNOWN_CONNECTOR_PROVIDERS: tuple[str, ...] = ("postgresql", "sql_server", "external_api", "azure_adls", "s3_blob")

_CONNECTOR_CAPABILITY_ATTRIBUTE_BY_OPERATION: dict[str, str] = {
    "configure": "can_configure",
    "validate": "can_validate",
    "discover": "can_discover",
    "sync": "can_sync",
    "health": "can_health",
}

TConnector = TypeVar("TConnector")


def _normalized_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


class ConnectorModel(EntityModel):
    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True,
        extra="forbid",
        frozen=True,
    )


class ConnectorCapabilityEntity(ConnectorModel):
    can_configure: bool = True
    can_validate: bool = True
    can_discover: bool = True
    can_sync: bool = True
    can_health: bool = True
    supports_secret_refs: bool = True
    supports_incremental_sync: bool = False


class ConnectorSecretReferenceEntity(ConnectorModel):
    name: str
    secret_ref: str
    secret_store: str | None = None


class ConnectorSecretValueEntity(ConnectorModel):
    name: str
    value: SecretStr
    secret_store: str | None = None

    @model_validator(mode="after")
    def _require_non_empty_secret(self) -> ConnectorSecretValueEntity:
        if not self.value.get_secret_value().strip():
            raise ValueError(f"missing secret value for {self.name}")
        return self


class ConnectorConfigurationEntity(ConnectorModel):
    provider: str
    workspace_id: str | None = None
    tenant_id: str | None = None
    display_name: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    secret_refs: tuple[ConnectorSecretReferenceEntity, ...] = Field(default_factory=tuple)


class ConnectorSecureConfigurationEntity(ConnectorConfigurationEntity):
    credentials: tuple[ConnectorSecretValueEntity, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def _require_unique_secret_names(self) -> ConnectorSecureConfigurationEntity:
        seen: set[str] = set()
        for credential in self.credentials:
            if credential.name in seen:
                raise ValueError(f"duplicate secure connector credential '{credential.name}'")
            seen.add(credential.name)
        for secret_ref in self.secret_refs:
            if secret_ref.name in seen:
                raise ValueError(f"duplicate secure connector credential '{secret_ref.name}'")
            seen.add(secret_ref.name)
        return self

    def without_secret_values(self) -> ConnectorConfigurationEntity:
        return ConnectorConfigurationEntity(
            provider=self.provider,
            workspace_id=self.workspace_id,
            tenant_id=self.tenant_id,
            display_name=self.display_name,
            parameters=dict(self.parameters),
            secret_refs=self.secret_refs,
        )

    def credential_names(self) -> tuple[str, ...]:
        return tuple(credential.name for credential in self.credentials)

    def secret_reference_names(self) -> tuple[str, ...]:
        return tuple(secret_ref.name for secret_ref in self.secret_refs)


ConnectorApiMethod = Literal["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]


class ConnectorApiOperationEntity(ConnectorModel):
    name: str
    method: ConnectorApiMethod
    path: str
    description: str | None = None
    tags: tuple[str, ...] = Field(default_factory=tuple)
    required: bool = True
    response_content_type: str | None = None


class ExternalApiConnectorConfigurationEntity(ConnectorSecureConfigurationEntity):
    base_url: str
    api_operations: tuple[ConnectorApiOperationEntity, ...] = Field(default_factory=tuple)
    openapi_url: str | None = None
    request_timeout_seconds: int = 30

    @model_validator(mode="after")
    def _require_api_inventory(self) -> ExternalApiConnectorConfigurationEntity:
        if not _normalized_text(self.base_url):
            raise ValueError("external API connector requires base_url")
        if self.request_timeout_seconds < 1:
            raise ValueError("external API connector requires request_timeout_seconds >= 1")
        if not self.api_operations and not _normalized_text(self.openapi_url):
            raise ValueError("external API connector requires api_operations or openapi_url")
        return self

    def without_secret_values(self) -> ExternalApiConnectorPublicConfigurationEntity:
        return ExternalApiConnectorPublicConfigurationEntity(
            provider=self.provider,
            workspace_id=self.workspace_id,
            tenant_id=self.tenant_id,
            display_name=self.display_name,
            parameters=dict(self.parameters),
            secret_refs=self.secret_refs,
            base_url=self.base_url,
            api_operations=self.api_operations,
            openapi_url=self.openapi_url,
            request_timeout_seconds=self.request_timeout_seconds,
        )


class ExternalApiConnectorPublicConfigurationEntity(ConnectorConfigurationEntity):
    base_url: str
    api_operations: tuple[ConnectorApiOperationEntity, ...] = Field(default_factory=tuple)
    openapi_url: str | None = None
    request_timeout_seconds: int = 30


class AzureAdlsConnectorConfigurationEntity(ConnectorSecureConfigurationEntity):
    account_url: str
    file_systems: tuple[str, ...] = Field(default_factory=tuple)
    path_prefixes: tuple[str, ...] = Field(default_factory=tuple)
    request_timeout_seconds: int = 30

    @model_validator(mode="after")
    def _require_valid_configuration(self) -> AzureAdlsConnectorConfigurationEntity:
        if not _normalized_text(self.account_url):
            raise ValueError("azure ADLS connector requires account_url")
        if self.request_timeout_seconds < 1:
            raise ValueError("azure ADLS connector requires request_timeout_seconds >= 1")
        return self

    def without_secret_values(self) -> AzureAdlsConnectorPublicConfigurationEntity:
        return AzureAdlsConnectorPublicConfigurationEntity(
            provider=self.provider,
            workspace_id=self.workspace_id,
            tenant_id=self.tenant_id,
            display_name=self.display_name,
            parameters=dict(self.parameters),
            secret_refs=self.secret_refs,
            account_url=self.account_url,
            file_systems=self.file_systems,
            path_prefixes=self.path_prefixes,
            request_timeout_seconds=self.request_timeout_seconds,
        )


class AzureAdlsConnectorPublicConfigurationEntity(ConnectorConfigurationEntity):
    account_url: str
    file_systems: tuple[str, ...] = Field(default_factory=tuple)
    path_prefixes: tuple[str, ...] = Field(default_factory=tuple)
    request_timeout_seconds: int = 30


class S3BlobConnectorConfigurationEntity(ConnectorSecureConfigurationEntity):
    delivery_locations: tuple[str, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def _require_delivery_locations(self) -> S3BlobConnectorConfigurationEntity:
        if not self.delivery_locations:
            raise ValueError("s3/blob connector requires delivery_locations")
        for delivery_location in self.delivery_locations:
            if not _normalized_text(delivery_location):
                raise ValueError("s3/blob connector requires non-empty delivery_locations")
        return self

    def without_secret_values(self) -> S3BlobConnectorPublicConfigurationEntity:
        return S3BlobConnectorPublicConfigurationEntity(
            provider=self.provider,
            workspace_id=self.workspace_id,
            tenant_id=self.tenant_id,
            display_name=self.display_name,
            parameters=dict(self.parameters),
            secret_refs=self.secret_refs,
            delivery_locations=self.delivery_locations,
        )


class S3BlobConnectorPublicConfigurationEntity(ConnectorConfigurationEntity):
    delivery_locations: tuple[str, ...] = Field(default_factory=tuple)


class ConnectorErrorEntity(ConnectorModel):
    kind: ConnectorErrorKind
    message: str
    code: str | None = None
    field: str | None = None
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class ConnectorDiscoveryItemEntity(ConnectorModel):
    identifier: str
    kind: str
    name: str | None = None
    workspace_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConnectorValidationResultEntity(ConnectorModel):
    provider: str
    valid: bool = True
    errors: tuple[ConnectorErrorEntity, ...] = Field(default_factory=tuple)


class ConnectorDiscoveryResultEntity(ConnectorModel):
    provider: str
    items: tuple[ConnectorDiscoveryItemEntity, ...] = Field(default_factory=tuple)
    errors: tuple[ConnectorErrorEntity, ...] = Field(default_factory=tuple)


class ConnectorSyncResultEntity(ConnectorModel):
    provider: str
    synced_count: int = 0
    items: tuple[ConnectorDiscoveryItemEntity, ...] = Field(default_factory=tuple)
    errors: tuple[ConnectorErrorEntity, ...] = Field(default_factory=tuple)


class ConnectorHealthResultEntity(ConnectorModel):
    provider: str
    status: ConnectorHealthStatus = "unknown"
    details: dict[str, Any] = Field(default_factory=dict)
    errors: tuple[ConnectorErrorEntity, ...] = Field(default_factory=tuple)


class ConnectorRegistryEntryEntity(ConnectorModel):
    provider: str
    display_name: str
    description: str | None = None
    implementation_path: str | None = None
    capabilities: ConnectorCapabilityEntity = Field(default_factory=ConnectorCapabilityEntity)
    supported_asset_kinds: tuple[str, ...] = Field(default_factory=tuple)


class ConnectorRegistry(ConnectorModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    entries: tuple[ConnectorRegistryEntryEntity, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _require_unique_providers(self) -> ConnectorRegistry:
        seen: set[str] = set()
        for entry in self.entries:
            provider = entry.provider
            if provider in seen:
                raise ValueError(f"duplicate connector entry for provider {provider}")
            seen.add(provider)
        return self

    def get_entry(self, provider: str) -> ConnectorRegistryEntryEntity:
        normalized_provider = _normalized_text(provider)
        if not normalized_provider:
            raise KeyError("Connector provider is required")
        for entry in self.entries:
            if entry.provider == normalized_provider:
                return entry
        raise KeyError(f"No connector entry registered for {normalized_provider}")

    def supports(self, provider: str, capability: ConnectorOperation | str) -> bool:
        entry = self.get_entry(provider)
        capability_name = _CONNECTOR_CAPABILITY_ATTRIBUTE_BY_OPERATION.get(str(capability), str(capability))
        if not hasattr(entry.capabilities, capability_name):
            raise KeyError(f"Unknown connector capability '{capability_name}'")
        return bool(getattr(entry.capabilities, capability_name))

    def register(self, entry: ConnectorRegistryEntryEntity) -> ConnectorRegistry:
        return type(self)(entries=self.entries + (entry,))

    def load(self, provider: str, loader: Callable[[ConnectorRegistryEntryEntity], TConnector]) -> TConnector:
        return loader(self.get_entry(provider))

    def provider_names(self) -> tuple[str, ...]:
        return tuple(entry.provider for entry in self.entries)

    def matrix_by_provider(self) -> dict[str, dict[str, Any]]:
        matrix: dict[str, dict[str, Any]] = {}
        for entry in self.entries:
            matrix[entry.provider] = entry.model_dump(mode="json", exclude_none=True)
        return matrix


class ConnectorInstanceEntity(ConnectorModel):
    id: str
    provider: str
    display_name: str
    workspace_id: str | None = None
    tenant_id: str | None = None
    configuration: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str


CONNECTOR_REGISTRY = ConnectorRegistry(
    entries=(
        ConnectorRegistryEntryEntity(
            provider="postgresql",
            display_name="PostgreSQL",
            description="Relational database connector for schema and table discovery.",
            implementation_path="app.application.services.postgresql_connector.PostgreSQLConnector",
            capabilities=ConnectorCapabilityEntity(
                can_configure=True,
                can_validate=True,
                can_discover=True,
                can_sync=True,
                can_health=True,
                supports_secret_refs=True,
                supports_incremental_sync=False,
            ),
            supported_asset_kinds=("database", "schema", "table"),
        ),
        ConnectorRegistryEntryEntity(
            provider="sql_server",
            display_name="SQL Server",
            description="Enterprise relational database connector for schema and table discovery.",
            implementation_path="app.application.services.sql_server_connector.SQLServerConnector",
            capabilities=ConnectorCapabilityEntity(
                can_configure=True,
                can_validate=True,
                can_discover=True,
                can_sync=True,
                can_health=True,
                supports_secret_refs=True,
                supports_incremental_sync=False,
            ),
            supported_asset_kinds=("database", "schema", "table"),
        ),
        ConnectorRegistryEntryEntity(
            provider="external_api",
            display_name="External API",
            description="API connector for systems exposed through explicit operations with optional OpenAPI augmentation.",
            implementation_path="app.application.services.external_api_connector.ExternalApiConnector",
            capabilities=ConnectorCapabilityEntity(
                can_configure=True,
                can_validate=True,
                can_discover=True,
                can_sync=True,
                can_health=True,
                supports_secret_refs=True,
                supports_incremental_sync=False,
            ),
            supported_asset_kinds=("api_operation", "openapi_document"),
        ),
        ConnectorRegistryEntryEntity(
            provider="azure_adls",
            display_name="Azure ADLS",
            description="Azure Data Lake Storage connector for warehouse and file-system discovery.",
            implementation_path="app.application.services.azure_adls_connector.AzureAdlsConnector",
            capabilities=ConnectorCapabilityEntity(
                can_configure=True,
                can_validate=True,
                can_discover=True,
                can_sync=True,
                can_health=True,
                supports_secret_refs=True,
                supports_incremental_sync=False,
            ),
            supported_asset_kinds=("filesystem", "container", "directory", "file"),
        ),
        ConnectorRegistryEntryEntity(
            provider="s3_blob",
            display_name="S3/Blob",
            description="Object storage connector for dataset-level metadata ingestion.",
            implementation_path="app.application.services.s3_blob_connector.S3BlobConnector",
            capabilities=ConnectorCapabilityEntity(
                can_configure=True,
                can_validate=True,
                can_discover=True,
                can_sync=True,
                can_health=True,
                supports_secret_refs=True,
                supports_incremental_sync=False,
            ),
            supported_asset_kinds=("bucket", "container", "folder", "object"),
        ),
    )
)


def build_connector_registry() -> ConnectorRegistry:
    return CONNECTOR_REGISTRY


def load_connector_registry(entries: Sequence[ConnectorRegistryEntryEntity]) -> ConnectorRegistry:
    global CONNECTOR_REGISTRY
    CONNECTOR_REGISTRY = ConnectorRegistry(entries=tuple(entries))
    return CONNECTOR_REGISTRY


def get_connector_registry_entry(provider: str) -> ConnectorRegistryEntryEntity:
    return CONNECTOR_REGISTRY.get_entry(provider)


def connector_registry_matrix() -> dict[str, dict[str, Any]]:
    return CONNECTOR_REGISTRY.matrix_by_provider()


__all__ = [
    "CONNECTOR_REGISTRY",
    "ConnectorCapabilityEntity",
    "ConnectorApiMethod",
    "ConnectorApiOperationEntity",
    "ConnectorConfigurationEntity",
    "ConnectorDiscoveryItemEntity",
    "ConnectorDiscoveryResultEntity",
    "ConnectorErrorEntity",
    "ConnectorErrorKind",
    "ConnectorHealthResultEntity",
    "AzureAdlsConnectorConfigurationEntity",
    "AzureAdlsConnectorPublicConfigurationEntity",
    "ConnectorHealthStatus",
    "ConnectorModel",
    "ConnectorOperation",
    "ConnectorRegistry",
    "ConnectorInstanceEntity",
    "ConnectorRegistryEntryEntity",
    "ConnectorSecretReferenceEntity",
    "ConnectorSecretValueEntity",
    "ConnectorSecureConfigurationEntity",
    "ExternalApiConnectorConfigurationEntity",
    "S3BlobConnectorConfigurationEntity",
    "S3BlobConnectorPublicConfigurationEntity",
    "ConnectorSyncResultEntity",
    "ConnectorValidationResultEntity",
    "KNOWN_CONNECTOR_PROVIDERS",
    "build_connector_registry",
    "load_connector_registry",
    "connector_registry_matrix",
    "get_connector_registry_entry",
]