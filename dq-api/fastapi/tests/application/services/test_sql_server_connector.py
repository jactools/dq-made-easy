from __future__ import annotations

from typing import Any

import pytest
from pydantic import SecretStr

from app.application.services.sql_server_connector import SQLServerConnector
from app.domain.entities.connector import ConnectorConfigurationEntity
from app.domain.entities.connector import ConnectorDiscoveryResultEntity
from app.domain.entities.connector import ConnectorSecureConfigurationEntity
from app.domain.entities.connector import ConnectorSecretReferenceEntity
from app.domain.entities.connector import ConnectorSecretValueEntity


class _FakeEngine:
    def __init__(self, url: Any) -> None:
        self.url = url


class _FakeInspector:
    def __init__(self, engine: _FakeEngine) -> None:
        self.engine = engine

    def get_schema_names(self) -> list[str]:
        return ["dbo", "warehouse", "sys", "INFORMATION_SCHEMA"]

    def get_table_names(self, schema: str | None = None) -> list[str]:
        return {
            "dbo": ["customers"],
            "warehouse": ["orders"],
        }.get(schema or "", [])

    def get_columns(self, table_name: str, schema: str | None = None) -> list[dict[str, str]]:
        if schema == "dbo" and table_name == "customers":
            return [{"name": "customer_id"}, {"name": "customer_name"}]
        if schema == "warehouse" and table_name == "orders":
            return [{"name": "order_id"}, {"name": "created_at"}]
        return []


@pytest.fixture
def secure_configuration() -> ConnectorSecureConfigurationEntity:
    return ConnectorSecureConfigurationEntity(
        provider="sql_server",
        workspace_id="workspace-1",
        parameters={
            "host": "sql.example.com",
            "port": 1433,
            "database": "warehouse",
            "username": "dq_user",
            "driver": "ODBC Driver 18 for SQL Server",
            "encrypt": "yes",
            "trust_server_certificate": "yes",
        },
        secret_refs=(
            ConnectorSecretReferenceEntity(
                name="password_ref",
                secret_ref="vault://connectors/sql_server/password",
                secret_store="vault",
            ),
        ),
        credentials=(
            ConnectorSecretValueEntity(name="password", value=SecretStr("super-secret"), secret_store="vault"),
        ),
    )


@pytest.fixture
def sync_calls() -> list[tuple[ConnectorSecureConfigurationEntity, ConnectorDiscoveryResultEntity]]:
    return []


@pytest.fixture
def connector(sync_calls: list[tuple[ConnectorSecureConfigurationEntity, ConnectorDiscoveryResultEntity]]) -> SQLServerConnector:
    def engine_factory(url: Any) -> _FakeEngine:
        return _FakeEngine(url)

    def sync_sink(
        configuration: ConnectorSecureConfigurationEntity,
        discovery: ConnectorDiscoveryResultEntity,
    ) -> None:
        sync_calls.append((configuration, discovery))

    return SQLServerConnector(
        engine_factory=engine_factory,
        inspector_factory=_FakeInspector,
        sync_sink=sync_sink,
    )


def test_sql_server_connector_configure_redacts_secret_values(
    connector: SQLServerConnector,
    secure_configuration: ConnectorSecureConfigurationEntity,
) -> None:
    public_configuration = connector.configure(secure_configuration)

    assert isinstance(public_configuration, ConnectorConfigurationEntity)
    assert "credentials" not in public_configuration.model_dump(mode="json")
    assert public_configuration.secret_refs == secure_configuration.secret_refs
    assert public_configuration.parameters == secure_configuration.parameters


def test_sql_server_connector_discovers_schemas_and_tables(
    connector: SQLServerConnector,
    secure_configuration: ConnectorSecureConfigurationEntity,
) -> None:
    result = connector.discover(secure_configuration)

    assert result.errors == ()
    assert {item.identifier for item in result.items} == {
        "warehouse.dbo",
        "warehouse.dbo.customers",
        "warehouse.warehouse",
        "warehouse.warehouse.orders",
    }
    orders_table = next(item for item in result.items if item.identifier == "warehouse.warehouse.orders")
    assert orders_table.kind == "table"
    assert orders_table.metadata == {
        "database": "warehouse",
        "schema": "warehouse",
        "table": "orders",
        "column_count": 2,
        "column_names": ["order_id", "created_at"],
    }


def test_sql_server_connector_sync_calls_sink_with_discovery_results(
    connector: SQLServerConnector,
    secure_configuration: ConnectorSecureConfigurationEntity,
    sync_calls: list[tuple[ConnectorSecureConfigurationEntity, ConnectorDiscoveryResultEntity]],
) -> None:
    result = connector.sync(secure_configuration)

    assert result.errors == ()
    assert result.synced_count == 4
    assert len(sync_calls) == 1
    synced_configuration, synced_discovery = sync_calls[0]
    assert synced_configuration == secure_configuration
    assert synced_discovery.items == result.items


def test_sql_server_connector_validate_reports_missing_database(
    connector: SQLServerConnector,
) -> None:
    invalid_configuration = ConnectorSecureConfigurationEntity(
        provider="sql_server",
        parameters={
            "host": "sql.example.com",
            "username": "dq_user",
        },
    )

    validation = connector.validate(invalid_configuration)

    assert validation.valid is False
    assert validation.errors[0].field == "database"
    assert validation.errors[0].code == "sql_server_missing_database"