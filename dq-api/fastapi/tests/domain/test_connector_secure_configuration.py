from __future__ import annotations

import pytest

from pydantic import SecretStr

from app.domain.entities.connector import ConnectorSecretReferenceEntity
from app.domain.entities.connector import ConnectorSecretValueEntity
from app.domain.entities.connector import ConnectorSecureConfigurationEntity


def test_connector_secure_configuration_redacts_inline_secret_values() -> None:
    configuration = ConnectorSecureConfigurationEntity(
        provider="postgresql",
        workspace_id="workspace-1",
        parameters={"host": "postgres.example.com", "port": 5432},
        credentials=(
            ConnectorSecretValueEntity(
                name="password",
                value=SecretStr("super-secret"),
                secret_store="vault",
            ),
        ),
    )

    payload = configuration.model_dump(mode="json", exclude_none=True)

    assert payload["provider"] == "postgresql"
    assert payload["credentials"][0]["value"] == "**********"
    assert payload["credentials"][0]["secret_store"] == "vault"
    assert payload["credentials"][0]["name"] == "password"


def test_connector_secure_configuration_keeps_secret_references_in_public_configuration() -> None:
    configuration = ConnectorSecureConfigurationEntity(
        provider="postgresql",
        display_name="Warehouse Connector",
        parameters={"sslmode": "require"},
        secret_refs=(
            ConnectorSecretReferenceEntity(
                name="password",
                secret_ref="vault://connectors/postgresql/password",
                secret_store="vault",
            ),
        ),
    )

    public_configuration = configuration.without_secret_values()

    assert public_configuration.provider == "postgresql"
    assert public_configuration.display_name == "Warehouse Connector"
    assert public_configuration.parameters == {"sslmode": "require"}
    assert public_configuration.secret_refs == (
        ConnectorSecretReferenceEntity(
            name="password",
            secret_ref="vault://connectors/postgresql/password",
            secret_store="vault",
        ),
    )
    assert configuration.secret_reference_names() == ("password",)
    assert configuration.credential_names() == ()


def test_connector_secure_configuration_rejects_duplicate_secret_names() -> None:
    with pytest.raises(ValueError, match="duplicate secure connector credential 'password'"):
        ConnectorSecureConfigurationEntity(
            provider="postgresql",
            credentials=(
                ConnectorSecretValueEntity(name="password", value=SecretStr("one")),
            ),
            secret_refs=(
                ConnectorSecretReferenceEntity(name="password", secret_ref="vault://connectors/postgresql/password"),
            ),
        )


def test_connector_secret_value_rejects_empty_values() -> None:
    with pytest.raises(ValueError, match="missing secret value for api_key"):
        ConnectorSecretValueEntity(name="api_key", value=SecretStr("   "))