from __future__ import annotations

import pytest

from app.domain.entities.connector import CONNECTOR_REGISTRY
from app.domain.entities.connector import ConnectorCapabilityEntity
from app.domain.entities.connector import ConnectorConfigurationEntity
from app.domain.entities.connector import ConnectorDiscoveryResultEntity
from app.domain.entities.connector import ConnectorHealthResultEntity
from app.domain.entities.connector import ConnectorRegistry
from app.domain.entities.connector import ConnectorSyncResultEntity
from app.domain.entities.connector import ConnectorValidationResultEntity
from app.domain.entities.connector import get_connector_registry_entry
from app.domain.interfaces.v1.connector import Connector


class _FakeConnector:
    provider = "postgresql"
    capabilities = ConnectorCapabilityEntity()

    def configure(self, configuration: ConnectorConfigurationEntity) -> ConnectorConfigurationEntity:
        return configuration

    def validate(self, configuration: ConnectorConfigurationEntity) -> ConnectorValidationResultEntity:
        return ConnectorValidationResultEntity(provider=configuration.provider)

    def discover(self, configuration: ConnectorConfigurationEntity) -> ConnectorDiscoveryResultEntity:
        return ConnectorDiscoveryResultEntity(provider=configuration.provider)

    def sync(self, configuration: ConnectorConfigurationEntity) -> ConnectorSyncResultEntity:
        return ConnectorSyncResultEntity(provider=configuration.provider)

    def health(self, configuration: ConnectorConfigurationEntity) -> ConnectorHealthResultEntity:
        return ConnectorHealthResultEntity(provider=configuration.provider)


def test_connector_registry_exposes_planned_provider_catalog() -> None:
    registry = CONNECTOR_REGISTRY

    assert registry.provider_names() == ("postgresql", "sql_server", "external_api", "azure_adls", "s3_blob")
    entry = get_connector_registry_entry("postgresql")
    assert entry.display_name == "PostgreSQL"
    assert entry.description == "Relational database connector for schema and table discovery."
    assert entry.implementation_path == "app.application.services.postgresql_connector.PostgreSQLConnector"
    assert entry.supported_asset_kinds == ("database", "schema", "table")
    sql_server_entry = get_connector_registry_entry("sql_server")
    assert sql_server_entry.display_name == "SQL Server"
    assert sql_server_entry.implementation_path == "app.application.services.sql_server_connector.SQLServerConnector"
    external_api_entry = get_connector_registry_entry("external_api")
    assert external_api_entry.display_name == "External API"
    assert external_api_entry.implementation_path == "app.application.services.external_api_connector.ExternalApiConnector"
    azure_adls_entry = get_connector_registry_entry("azure_adls")
    assert azure_adls_entry.display_name == "Azure ADLS"
    assert azure_adls_entry.implementation_path == "app.application.services.azure_adls_connector.AzureAdlsConnector"
    s3_blob_entry = get_connector_registry_entry("s3_blob")
    assert s3_blob_entry.display_name == "S3/Blob"
    assert s3_blob_entry.implementation_path == "app.application.services.s3_blob_connector.S3BlobConnector"
    assert registry.supports("postgresql", "discover") is True
    assert registry.supports("postgresql", "supports_secret_refs") is True
    assert registry.supports("postgresql", "supports_incremental_sync") is False


def test_connector_registry_loads_entries_by_provider() -> None:
    observed: dict[str, str] = {}

    def loader(entry):
        observed["provider"] = entry.provider
        observed["display_name"] = entry.display_name
        return (entry.provider, entry.display_name)

    loaded = CONNECTOR_REGISTRY.load("postgresql", loader)

    assert loaded == ("postgresql", "PostgreSQL")
    assert observed == {"provider": "postgresql", "display_name": "PostgreSQL"}


def test_connector_registry_rejects_duplicate_provider_entries() -> None:
    entry = CONNECTOR_REGISTRY.entries[0]

    with pytest.raises(ValueError, match="duplicate connector entry for provider postgresql"):
        ConnectorRegistry(entries=(entry, entry))


def test_connector_protocol_accepts_a_complete_connector() -> None:
    connector = _FakeConnector()
    configuration = ConnectorConfigurationEntity(provider="postgresql")

    assert isinstance(connector, Connector)
    assert connector.configure(configuration) == configuration
    assert connector.validate(configuration) == ConnectorValidationResultEntity(provider="postgresql")
    assert connector.discover(configuration) == ConnectorDiscoveryResultEntity(provider="postgresql")
    assert connector.sync(configuration) == ConnectorSyncResultEntity(provider="postgresql")
    assert connector.health(configuration) == ConnectorHealthResultEntity(provider="postgresql")