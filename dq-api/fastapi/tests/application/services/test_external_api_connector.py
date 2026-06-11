from __future__ import annotations

from typing import Any

import pytest
from pydantic import SecretStr

from app.application.services.external_api_connector import ExternalApiConnector
from app.domain.entities.connector import ConnectorApiOperationEntity
from app.domain.entities.connector import ConnectorDiscoveryResultEntity
from app.domain.entities.connector import ConnectorSecretReferenceEntity
from app.domain.entities.connector import ConnectorSecretValueEntity
from app.domain.entities.connector import ExternalApiConnectorConfigurationEntity


def _build_spec() -> dict[str, Any]:
    return {
        "openapi": "3.0.3",
        "info": {"title": "Retail API", "version": "1.0.0"},
        "paths": {
            "/customers": {
                "get": {
                    "operationId": "listCustomers",
                    "summary": "List customers",
                    "tags": ["customers"],
                    "responses": {"200": {"content": {"application/json": {}}}},
                }
            },
            "/orders": {
                "post": {
                    "summary": "Create order",
                    "responses": {"201": {"content": {"application/json": {}}}},
                }
            },
        },
    }


@pytest.fixture
def sync_calls() -> list[tuple[ExternalApiConnectorConfigurationEntity, ConnectorDiscoveryResultEntity]]:
    return []


@pytest.fixture
def configured_connector(sync_calls: list[tuple[ExternalApiConnectorConfigurationEntity, ConnectorDiscoveryResultEntity]]) -> ExternalApiConnector:
    def sync_sink(
        configuration: ExternalApiConnectorConfigurationEntity,
        discovery: ConnectorDiscoveryResultEntity,
    ) -> None:
        sync_calls.append((configuration, discovery))

    return ExternalApiConnector(
        spec_loader=lambda openapi_url, timeout_seconds: _build_spec() if openapi_url else {},
        sync_sink=sync_sink,
    )


@pytest.fixture
def secure_configuration() -> ExternalApiConnectorConfigurationEntity:
    return ExternalApiConnectorConfigurationEntity(
        provider="external_api",
        base_url="https://api.example.com",
        workspace_id="workspace-1",
        api_operations=(
            ConnectorApiOperationEntity(name="list_customers", method="GET", path="/customers", description="Configured list customers"),
        ),
        openapi_url="https://api.example.com/openapi.json",
        request_timeout_seconds=30,
        secret_refs=(
            ConnectorSecretReferenceEntity(
                name="token_ref",
                secret_ref="vault://connectors/external-api/token",
                secret_store="vault",
            ),
        ),
        credentials=(
            ConnectorSecretValueEntity(name="token", value=SecretStr("super-secret"), secret_store="vault"),
        ),
    )


def test_external_api_connector_configure_redacts_secret_values(
    configured_connector: ExternalApiConnector,
    secure_configuration: ExternalApiConnectorConfigurationEntity,
) -> None:
    public_configuration = configured_connector.configure(secure_configuration)

    assert public_configuration.secret_refs == secure_configuration.secret_refs
    assert "credentials" not in public_configuration.model_dump(mode="json")


def test_external_api_connector_discovers_configured_and_openapi_operations(
    configured_connector: ExternalApiConnector,
    secure_configuration: ExternalApiConnectorConfigurationEntity,
) -> None:
    result = configured_connector.discover(secure_configuration)

    assert result.errors == ()
    assert {item.identifier for item in result.items} == {
        "https://api.example.com::GET:/customers",
        "https://api.example.com::POST:/orders",
    }
    list_customers = next(item for item in result.items if item.name == "list_customers")
    assert list_customers.metadata["source"] == "configured"
    assert list_customers.metadata["method"] == "GET"
    assert list_customers.metadata["path"] == "/customers"


def test_external_api_connector_sync_calls_sink_with_public_configuration(
    configured_connector: ExternalApiConnector,
    secure_configuration: ExternalApiConnectorConfigurationEntity,
    sync_calls: list[tuple[ExternalApiConnectorConfigurationEntity, ConnectorDiscoveryResultEntity]],
) -> None:
    result = configured_connector.sync(secure_configuration)

    assert result.errors == ()
    assert result.synced_count == 2
    assert len(sync_calls) == 1
    synced_configuration, synced_discovery = sync_calls[0]
    assert "credentials" not in synced_configuration.model_dump(mode="json")
    assert synced_configuration.secret_refs == secure_configuration.secret_refs
    assert synced_discovery.items == result.items


def test_external_api_connector_validation_requires_inventory() -> None:
    with pytest.raises(ValueError, match="requires api_operations or openapi_url"):
        ExternalApiConnectorConfigurationEntity(provider="external_api", base_url="https://api.example.com")