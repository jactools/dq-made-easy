from __future__ import annotations

from typing import Any

import pytest
from pydantic import SecretStr

from app.application.services.postgresql_connector import PostgreSQLConnector
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
        return ["public", "analytics", "pg_catalog"]

    def get_table_names(self, schema: str | None = None) -> list[str]:
        return {
            "analytics": ["events"],
            "public": ["customers"],
        }.get(schema or "", [])

    def get_columns(self, table_name: str, schema: str | None = None) -> list[dict[str, str]]:
        if schema == "analytics" and table_name == "events":
            return [{"name": "event_id"}, {"name": "occurred_at"}]
        if schema == "public" and table_name == "customers":
            return [{"name": "id"}, {"name": "name"}]
        return []


@pytest.fixture
def secure_configuration() -> ConnectorSecureConfigurationEntity:
    return ConnectorSecureConfigurationEntity(
        provider="postgresql",
        workspace_id="workspace-1",
        parameters={
            "host": "db.example.com",
            "port": 5432,
            "database": "catalog",
            "username": "dq_user",
            "sslmode": "require",
        },
        secret_refs=(
            ConnectorSecretReferenceEntity(
                name="password_ref",
                secret_ref="vault://connectors/postgresql/password",
                secret_store="vault",
            ),
        ),
        credentials=(
            ConnectorSecretValueEntity(name="password", value=SecretStr("super-secret"), secret_store="vault"),
        ),
    )


@pytest.fixture
def connector(sync_calls: list[tuple[ConnectorSecureConfigurationEntity, ConnectorDiscoveryResultEntity]]) -> PostgreSQLConnector:
    def engine_factory(url: Any) -> _FakeEngine:
        return _FakeEngine(url)

    def sync_sink(
        configuration: ConnectorSecureConfigurationEntity,
        discovery: ConnectorDiscoveryResultEntity,
    ) -> None:
        sync_calls.append((configuration, discovery))

    return PostgreSQLConnector(
        engine_factory=engine_factory,
        inspector_factory=_FakeInspector,
        sync_sink=sync_sink,
    )


@pytest.fixture
def sync_calls() -> list[tuple[ConnectorSecureConfigurationEntity, ConnectorDiscoveryResultEntity]]:
    return []


def test_postgresql_connector_configure_redacts_secret_values(
    connector: PostgreSQLConnector,
    secure_configuration: ConnectorSecureConfigurationEntity,
) -> None:
    public_configuration = connector.configure(secure_configuration)

    assert isinstance(public_configuration, ConnectorConfigurationEntity)
    assert "credentials" not in public_configuration.model_dump(mode="json")
    assert public_configuration.secret_refs == secure_configuration.secret_refs
    assert public_configuration.parameters == secure_configuration.parameters


def test_postgresql_connector_discovers_schemas_and_tables(
    connector: PostgreSQLConnector,
    secure_configuration: ConnectorSecureConfigurationEntity,
) -> None:
    result = connector.discover(secure_configuration)

    assert result.errors == ()
    assert {item.identifier for item in result.items} == {
        "catalog.analytics",
        "catalog.analytics.events",
        "catalog.public",
        "catalog.public.customers",
    }
    analytics_table = next(item for item in result.items if item.identifier == "catalog.analytics.events")
    assert analytics_table.kind == "table"
    assert analytics_table.metadata == {
        "database": "catalog",
        "schema": "analytics",
        "table": "events",
        "column_count": 2,
        "column_names": ["event_id", "occurred_at"],
    }


def test_postgresql_connector_sync_calls_sink_with_discovery_results(
    connector: PostgreSQLConnector,
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


def test_postgresql_connector_validate_reports_missing_password(
    connector: PostgreSQLConnector,
) -> None:
    invalid_configuration = ConnectorSecureConfigurationEntity(
        provider="postgresql",
        parameters={
            "host": "db.example.com",
            "database": "catalog",
            "username": "dq_user",
        },
    )

    validation = connector.validate(invalid_configuration)

    assert validation.valid is False
    assert validation.errors[0].field == "credentials"
    assert validation.errors[0].code == "postgresql_missing_password"