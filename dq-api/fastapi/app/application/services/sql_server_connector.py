from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from sqlalchemy import inspect
from sqlalchemy.engine import Engine
from sqlalchemy.engine import URL

from app.domain.entities.connector import ConnectorConfigurationEntity
from app.domain.entities.connector import ConnectorDiscoveryItemEntity
from app.domain.entities.connector import ConnectorDiscoveryResultEntity
from app.domain.entities.connector import ConnectorErrorEntity
from app.domain.entities.connector import ConnectorHealthResultEntity
from app.domain.entities.connector import ConnectorSecureConfigurationEntity
from app.domain.entities.connector import ConnectorSyncResultEntity
from app.domain.entities.connector import ConnectorValidationResultEntity
from app.domain.entities.connector import get_connector_registry_entry
from app.infrastructure.orm.session import get_engine


_SYSTEM_SCHEMAS = frozenset({"sys", "INFORMATION_SCHEMA"})
_DEFAULT_PORT = 1433
_DEFAULT_DRIVER = "ODBC Driver 18 for SQL Server"


def _default_engine_factory(database_url: URL) -> Engine:
    return get_engine(database_url.render_as_string(hide_password=False))


class SQLServerConnector:
    provider = "sql_server"
    capabilities = get_connector_registry_entry("sql_server").capabilities

    def __init__(
        self,
        *,
        engine_factory: Callable[[URL], Engine] = _default_engine_factory,
        inspector_factory: Callable[[Engine], Any] = inspect,
        sync_sink: Callable[[ConnectorSecureConfigurationEntity, ConnectorDiscoveryResultEntity], None] | None = None,
    ) -> None:
        self._engine_factory = engine_factory
        self._inspector_factory = inspector_factory
        self._sync_sink = sync_sink

    def configure(self, configuration: ConnectorConfigurationEntity) -> ConnectorConfigurationEntity:
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
            engine = self._engine_factory(self._build_database_url(secure_configuration))
            inspector = self._inspector_factory(engine)
            items, _, _ = self._discover_items(inspector, secure_configuration)
        except Exception as exc:
            return ConnectorDiscoveryResultEntity(
                provider=self.provider,
                errors=(
                    ConnectorErrorEntity(
                        kind="connection",
                        message=f"SQL Server discovery failed: {exc}",
                        code="sql_server_discovery_failed",
                        retryable=True,
                        details={"provider": self.provider},
                    ),
                ),
            )

        return ConnectorDiscoveryResultEntity(provider=self.provider, items=tuple(items))

    def sync(self, configuration: ConnectorConfigurationEntity) -> ConnectorSyncResultEntity:
        secure_configuration = self._coerce_secure_configuration(configuration)
        if secure_configuration is None:
            return ConnectorSyncResultEntity(provider=self.provider, errors=tuple(self._configuration_errors(configuration)))

        discovery = self.discover(secure_configuration)
        if discovery.errors:
            return ConnectorSyncResultEntity(provider=self.provider, errors=discovery.errors)

        if self._sync_sink is not None:
            self._sync_sink(secure_configuration, discovery)

        return ConnectorSyncResultEntity(provider=self.provider, synced_count=len(discovery.items), items=discovery.items)

    def health(self, configuration: ConnectorConfigurationEntity) -> ConnectorHealthResultEntity:
        validation = self.validate(configuration)
        if not validation.valid:
            return ConnectorHealthResultEntity(provider=self.provider, status="unhealthy", errors=validation.errors)

        discovery = self.discover(configuration)
        if discovery.errors:
            return ConnectorHealthResultEntity(provider=self.provider, status="degraded", errors=discovery.errors)

        schema_count = len({item.metadata.get("schema") for item in discovery.items if item.kind == "schema"})
        table_count = len([item for item in discovery.items if item.kind == "table"])
        return ConnectorHealthResultEntity(
            provider=self.provider,
            status="healthy",
            details={"schema_count": schema_count, "table_count": table_count},
        )

    def _coerce_secure_configuration(self, configuration: ConnectorConfigurationEntity) -> ConnectorSecureConfigurationEntity | None:
        if not isinstance(configuration, ConnectorSecureConfigurationEntity):
            return None
        if self._normalized_text(configuration.provider) != self.provider:
            return None
        return configuration

    def _configuration_errors(self, configuration: ConnectorConfigurationEntity) -> list[ConnectorErrorEntity]:
        errors: list[ConnectorErrorEntity] = []
        if not isinstance(configuration, ConnectorSecureConfigurationEntity):
            errors.append(
                ConnectorErrorEntity(
                    kind="configuration",
                    message="SQL Server connector requires ConnectorSecureConfigurationEntity",
                    code="sql_server_secure_configuration_required",
                    field="credentials",
                )
            )
            return errors

        if self._normalized_text(configuration.provider) != self.provider:
            errors.append(
                ConnectorErrorEntity(
                    kind="configuration",
                    message="SQL Server connector only accepts the 'sql_server' provider",
                    code="sql_server_provider_mismatch",
                    field="provider",
                )
            )

        parameters = configuration.parameters
        host = self._normalized_text(parameters.get("host") or parameters.get("server"))
        database = self._normalized_text(parameters.get("database"))
        username = self._normalized_text(parameters.get("username"))
        password = self._credential_value(configuration, "password")

        if not host:
            errors.append(
                ConnectorErrorEntity(
                    kind="configuration",
                    message="SQL Server connector requires 'host'",
                    code="sql_server_missing_host",
                    field="host",
                )
            )
        if not database:
            errors.append(
                ConnectorErrorEntity(
                    kind="configuration",
                    message="SQL Server connector requires 'database'",
                    code="sql_server_missing_database",
                    field="database",
                )
            )
        if not username:
            errors.append(
                ConnectorErrorEntity(
                    kind="configuration",
                    message="SQL Server connector requires 'username'",
                    code="sql_server_missing_username",
                    field="username",
                )
            )
        if not password:
            errors.append(
                ConnectorErrorEntity(
                    kind="configuration",
                    message="SQL Server connector requires a password credential named 'password'",
                    code="sql_server_missing_password",
                    field="credentials",
                )
            )

        return errors

    def _build_database_url(self, configuration: ConnectorSecureConfigurationEntity) -> URL:
        parameters = configuration.parameters
        driver = self._normalized_text(parameters.get("driver")) or _DEFAULT_DRIVER
        encrypt = self._normalized_text(parameters.get("encrypt"))
        trust_server_certificate = self._normalized_text(parameters.get("trust_server_certificate"))

        query: dict[str, Any] = {"driver": driver}
        if encrypt:
            query["encrypt"] = encrypt
        if trust_server_certificate:
            query["TrustServerCertificate"] = trust_server_certificate

        return URL.create(
            "mssql+pyodbc",
            username=self._normalized_text(parameters.get("username")) or "",
            password=self._credential_value(configuration, "password") or "",
            host=self._normalized_text(parameters.get("host") or parameters.get("server")) or "",
            port=self._coerce_int(parameters.get("port"), default=_DEFAULT_PORT),
            database=self._normalized_text(parameters.get("database")) or "",
            query=query,
        )

    def _discover_items(
        self,
        inspector: Any,
        configuration: ConnectorSecureConfigurationEntity,
    ) -> tuple[list[ConnectorDiscoveryItemEntity], int, int]:
        database_name = self._normalized_text(configuration.parameters.get("database")) or "sql_server"
        include_schemas = self._selected_names(
            configuration.parameters.get("schemas")
            or configuration.parameters.get("schema_names")
            or configuration.parameters.get("include_schemas")
        )
        exclude_schemas = set(self._selected_names(configuration.parameters.get("exclude_schemas")))

        schema_names = [
            name
            for name in sorted(self._normalized_name_list(inspector.get_schema_names()))
            if name not in _SYSTEM_SCHEMAS and not name.startswith("sys")
        ]
        if include_schemas:
            schema_names = [schema_name for schema_name in schema_names if schema_name in include_schemas]
        if exclude_schemas:
            schema_names = [schema_name for schema_name in schema_names if schema_name not in exclude_schemas]

        items: list[ConnectorDiscoveryItemEntity] = []
        table_count = 0
        for schema_name in schema_names:
            items.append(
                ConnectorDiscoveryItemEntity(
                    identifier=f"{database_name}.{schema_name}",
                    kind="schema",
                    name=schema_name,
                    workspace_id=configuration.workspace_id,
                    metadata={"database": database_name, "schema": schema_name},
                )
            )
            table_names = sorted(self._normalized_name_list(inspector.get_table_names(schema=schema_name)))
            for table_name in table_names:
                columns = inspector.get_columns(table_name, schema=schema_name)
                column_names = [self._normalized_text(column.get("name")) for column in columns if isinstance(column, dict)]
                items.append(
                    ConnectorDiscoveryItemEntity(
                        identifier=f"{database_name}.{schema_name}.{table_name}",
                        kind="table",
                        name=table_name,
                        workspace_id=configuration.workspace_id,
                        metadata={
                            "database": database_name,
                            "schema": schema_name,
                            "table": table_name,
                            "column_count": len(column_names),
                            "column_names": [name for name in column_names if name],
                        },
                    )
                )
                table_count += 1

        return items, len(schema_names), table_count

    def _credential_value(self, configuration: ConnectorSecureConfigurationEntity, name: str) -> str | None:
        for credential in configuration.credentials:
            if self._normalized_text(credential.name) == name:
                return self._normalized_text(credential.value.get_secret_value())
        return None

    def _selected_names(self, value: Any) -> tuple[str, ...]:
        if isinstance(value, str):
            normalized = self._normalized_text(value)
            return (normalized,) if normalized else ()
        if isinstance(value, Sequence):
            return tuple(
                normalized
                for normalized in (self._normalized_text(item) for item in value)
                if normalized
            )
        return ()

    def _normalized_name_list(self, names: Any) -> list[str]:
        if not isinstance(names, list):
            return []
        return [normalized for normalized in (self._normalized_text(name) for name in names) if normalized]

    def _normalized_text(self, value: Any) -> str | None:
        text = str(value or "").strip()
        return text or None

    def _coerce_int(self, value: Any, *, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default


__all__ = ["SQLServerConnector"]