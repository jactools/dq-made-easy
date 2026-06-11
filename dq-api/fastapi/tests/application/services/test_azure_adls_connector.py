from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest
from pydantic import SecretStr

from app.application.services.azure_adls_connector import AzureAdlsConnector
from app.domain.entities.connector import AzureAdlsConnectorConfigurationEntity
from app.domain.entities.connector import ConnectorDiscoveryResultEntity
from app.domain.entities.connector import ConnectorSecretReferenceEntity
from app.domain.entities.connector import ConnectorSecretValueEntity


class _FakeFileSystemClient:
    def __init__(self, entries_by_prefix: dict[str | None, list[dict[str, Any]]]) -> None:
        self.entries_by_prefix = entries_by_prefix

    def get_paths(self, path: str | None = None, recursive: bool = True) -> list[dict[str, Any]]:
        return self.entries_by_prefix.get(path, [])


class _FakeServiceClient:
    def __init__(self) -> None:
        self.file_system_names = ["warehouse", "curated"]
        self.file_system_clients = {
            "warehouse": _FakeFileSystemClient(
                {
                    None: [
                        {
                            "name": "raw",
                            "is_directory": True,
                            "content_length": None,
                            "last_modified": datetime(2026, 6, 6, 0, 0, tzinfo=timezone.utc),
                        },
                        {
                            "name": "raw/orders.csv",
                            "is_directory": False,
                            "content_length": 128,
                            "last_modified": datetime(2026, 6, 6, 0, 1, tzinfo=timezone.utc),
                        },
                    ],
                    "raw": [
                        {
                            "name": "raw/landing",
                            "is_directory": True,
                            "content_length": None,
                            "last_modified": datetime(2026, 6, 6, 0, 2, tzinfo=timezone.utc),
                        },
                        {
                            "name": "raw/landing/customers.parquet",
                            "is_directory": False,
                            "content_length": 256,
                            "last_modified": datetime(2026, 6, 6, 0, 3, tzinfo=timezone.utc),
                        },
                    ],
                }
            ),
            "curated": _FakeFileSystemClient({None: []}),
        }

    def list_file_systems(self) -> list[dict[str, str]]:
        return [{"name": name} for name in self.file_system_names]

    def get_file_system_client(self, file_system: str) -> _FakeFileSystemClient:
        return self.file_system_clients[file_system]


@pytest.fixture
def sync_calls() -> list[tuple[AzureAdlsConnectorConfigurationEntity, ConnectorDiscoveryResultEntity]]:
    return []


@pytest.fixture
def connector(sync_calls: list[tuple[AzureAdlsConnectorConfigurationEntity, ConnectorDiscoveryResultEntity]]) -> AzureAdlsConnector:
    def sync_sink(
        configuration: AzureAdlsConnectorConfigurationEntity,
        discovery: ConnectorDiscoveryResultEntity,
    ) -> None:
        sync_calls.append((configuration, discovery))

    return AzureAdlsConnector(
        client_factory=lambda configuration: _FakeServiceClient(),
        sync_sink=sync_sink,
    )


@pytest.fixture
def secure_configuration() -> AzureAdlsConnectorConfigurationEntity:
    return AzureAdlsConnectorConfigurationEntity(
        provider="azure_adls",
        account_url="https://account.dfs.core.windows.net",
        file_systems=("warehouse",),
        path_prefixes=("raw",),
        secret_refs=(
            ConnectorSecretReferenceEntity(
                name="account_key_ref",
                secret_ref="vault://connectors/azure-adls/account-key",
                secret_store="vault",
            ),
        ),
        credentials=(
            ConnectorSecretValueEntity(name="account_key", value=SecretStr("super-secret"), secret_store="vault"),
        ),
    )


def test_azure_adls_connector_configure_redacts_secret_values(
    connector: AzureAdlsConnector,
    secure_configuration: AzureAdlsConnectorConfigurationEntity,
) -> None:
    public_configuration = connector.configure(secure_configuration)

    assert public_configuration.secret_refs == secure_configuration.secret_refs
    assert "credentials" not in public_configuration.model_dump(mode="json")


def test_azure_adls_connector_discovers_filesystems_directories_and_files(
    connector: AzureAdlsConnector,
    secure_configuration: AzureAdlsConnectorConfigurationEntity,
) -> None:
    result = connector.discover(secure_configuration)

    assert result.errors == ()
    assert {item.kind for item in result.items} == {"filesystem", "directory", "file"}
    assert {item.identifier for item in result.items} == {
        "https://account.dfs.core.windows.net::warehouse",
        "https://account.dfs.core.windows.net::warehouse/raw/landing",
        "https://account.dfs.core.windows.net::warehouse/raw/landing/customers.parquet",
    }
    file_item = next(item for item in result.items if item.kind == "file")
    assert file_item.metadata == {
        "account_url": "https://account.dfs.core.windows.net",
        "file_system": "warehouse",
        "path": "raw/landing/customers.parquet",
        "kind": "file",
        "content_length": 256,
        "last_modified": "2026-06-06T00:03:00+00:00",
        "source": "discovered",
    }


def test_azure_adls_connector_sync_calls_sink_with_public_configuration(
    connector: AzureAdlsConnector,
    secure_configuration: AzureAdlsConnectorConfigurationEntity,
    sync_calls: list[tuple[AzureAdlsConnectorConfigurationEntity, ConnectorDiscoveryResultEntity]],
) -> None:
    result = connector.sync(secure_configuration)

    assert result.errors == ()
    assert result.synced_count == 3
    assert len(sync_calls) == 1
    synced_configuration, synced_discovery = sync_calls[0]
    assert "credentials" not in synced_configuration.model_dump(mode="json")
    assert synced_discovery.items == result.items


def test_azure_adls_connector_rejects_invalid_account_url() -> None:
    with pytest.raises(ValueError, match="requires account_url"):
        AzureAdlsConnectorConfigurationEntity(provider="azure_adls", account_url="")