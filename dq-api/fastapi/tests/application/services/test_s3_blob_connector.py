from __future__ import annotations

from typing import Any

import pytest
from pydantic import SecretStr

from app.application.services.s3_blob_connector import S3BlobConnector
from app.domain.entities.connector import ConnectorDiscoveryResultEntity
from app.domain.entities.connector import ConnectorSecretReferenceEntity
from app.domain.entities.connector import ConnectorSecretValueEntity
from app.domain.entities.connector import S3BlobConnectorConfigurationEntity


class _FakeStorageService:
    def __init__(self, inventory: dict[str, list[str]]) -> None:
        self.inventory = inventory
        self.calls: list[str] = []

    def inspect(self, delivery_location: str) -> dict[str, Any]:
        self.calls.append(delivery_location)
        return {
            "storage_exists": True,
            "storage_object_count": len(self.inventory.get(delivery_location, [])),
            "file_names": self.inventory.get(delivery_location, []),
        }


@pytest.fixture
def fake_storage() -> _FakeStorageService:
    return _FakeStorageService(
        {
            "s3a://dq-test-data/landing": ["orders.parquet", "raw/customers.csv"],
            "s3a://archive-bucket": ["exports/daily/report.json"],
        }
    )


@pytest.fixture
def sync_calls() -> list[tuple[S3BlobConnectorConfigurationEntity, ConnectorDiscoveryResultEntity]]:
    return []


@pytest.fixture
def connector(
    fake_storage: _FakeStorageService,
    sync_calls: list[tuple[S3BlobConnectorConfigurationEntity, ConnectorDiscoveryResultEntity]],
) -> S3BlobConnector:
    def sync_sink(
        configuration: S3BlobConnectorConfigurationEntity,
        discovery: ConnectorDiscoveryResultEntity,
    ) -> None:
        sync_calls.append((configuration, discovery))

    return S3BlobConnector(storage_service_factory=lambda: fake_storage, sync_sink=sync_sink)


@pytest.fixture
def secure_configuration() -> S3BlobConnectorConfigurationEntity:
    return S3BlobConnectorConfigurationEntity(
        provider="s3_blob",
        workspace_id="workspace-1",
        delivery_locations=("s3://dq-test-data/landing",),
        secret_refs=(
            ConnectorSecretReferenceEntity(
                name="access_key_ref",
                secret_ref="vault://connectors/s3/access-key",
                secret_store="vault",
            ),
        ),
        credentials=(
            ConnectorSecretValueEntity(name="access_key", value=SecretStr("super-secret"), secret_store="vault"),
        ),
    )


def test_s3_blob_connector_configure_redacts_secret_values(
    connector: S3BlobConnector,
    secure_configuration: S3BlobConnectorConfigurationEntity,
) -> None:
    public_configuration = connector.configure(secure_configuration)

    assert public_configuration.secret_refs == secure_configuration.secret_refs
    assert "credentials" not in public_configuration.model_dump(mode="json")


def test_s3_blob_connector_discovers_bucket_folders_and_objects(
    connector: S3BlobConnector,
    secure_configuration: S3BlobConnectorConfigurationEntity,
    fake_storage: _FakeStorageService,
) -> None:
    result = connector.discover(secure_configuration)

    assert result.errors == ()
    assert fake_storage.calls == ["s3a://dq-test-data/landing"]
    assert {item.kind for item in result.items} == {"bucket", "folder", "object"}
    assert {item.identifier for item in result.items} == {
        "s3a://dq-test-data",
        "s3a://dq-test-data/landing",
        "s3a://dq-test-data/landing/orders.parquet",
        "s3a://dq-test-data/landing/raw",
        "s3a://dq-test-data/landing/raw/customers.csv",
    }
    object_item = next(item for item in result.items if item.identifier.endswith("orders.parquet"))
    assert object_item.metadata == {
        "bucket": "dq-test-data",
        "prefix": "landing",
        "object_name": "orders.parquet",
        "delivery_location": "s3a://dq-test-data/landing",
        "source": "listed",
    }


def test_s3_blob_connector_sync_calls_sink_with_public_configuration(
    connector: S3BlobConnector,
    secure_configuration: S3BlobConnectorConfigurationEntity,
    sync_calls: list[tuple[S3BlobConnectorConfigurationEntity, ConnectorDiscoveryResultEntity]],
) -> None:
    result = connector.sync(secure_configuration)

    assert result.errors == ()
    assert len(sync_calls) == 1
    synced_configuration, synced_discovery = sync_calls[0]
    assert "credentials" not in synced_configuration.model_dump(mode="json")
    assert synced_configuration.delivery_locations == secure_configuration.delivery_locations
    assert synced_discovery.items == result.items


def test_s3_blob_connector_rejects_empty_delivery_locations() -> None:
    with pytest.raises(ValueError, match="requires delivery_locations"):
        S3BlobConnectorConfigurationEntity(provider="s3_blob")