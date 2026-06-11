from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import HTTPException

from app.application.services.delivery_storage import DeliveryStorageService
from app.application.services.delivery_storage import S3DeliveryStorageService
from app.domain.entities.connector import ConnectorConfigurationEntity
from app.domain.entities.connector import ConnectorDiscoveryItemEntity
from app.domain.entities.connector import ConnectorDiscoveryResultEntity
from app.domain.entities.connector import ConnectorErrorEntity
from app.domain.entities.connector import ConnectorHealthResultEntity
from app.domain.entities.connector import ConnectorSecureConfigurationEntity
from app.domain.entities.connector import ConnectorSyncResultEntity
from app.domain.entities.connector import ConnectorValidationResultEntity
from app.domain.entities.connector import S3BlobConnectorConfigurationEntity
from app.domain.entities.connector import get_connector_registry_entry


class S3BlobConnector:
    provider = "s3_blob"
    capabilities = get_connector_registry_entry("s3_blob").capabilities

    def __init__(
        self,
        *,
        storage_service_factory: Callable[[], DeliveryStorageService] | None = None,
        sync_sink: Callable[[ConnectorConfigurationEntity, ConnectorDiscoveryResultEntity], None] | None = None,
    ) -> None:
        self._storage_service_factory = storage_service_factory or S3DeliveryStorageService
        self._sync_sink = sync_sink

    def configure(self, configuration: ConnectorConfigurationEntity) -> ConnectorConfigurationEntity:
        if isinstance(configuration, S3BlobConnectorConfigurationEntity):
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
            storage_service = self._storage_service_factory()
        except HTTPException as exc:
            return ConnectorDiscoveryResultEntity(
                provider=self.provider,
                errors=(
                    ConnectorErrorEntity(
                        kind="connection",
                        message=f"S3/Blob storage service could not be initialized: {exc.detail if isinstance(exc.detail, str) else exc.detail}",
                        code="s3_blob_storage_unavailable",
                        retryable=False,
                    ),
                ),
            )
        except Exception as exc:
            return ConnectorDiscoveryResultEntity(
                provider=self.provider,
                errors=(
                    ConnectorErrorEntity(
                        kind="connection",
                        message=f"S3/Blob storage service could not be initialized: {exc}",
                        code="s3_blob_storage_unavailable",
                        retryable=False,
                    ),
                ),
            )

        discovered_items: list[ConnectorDiscoveryItemEntity] = []
        discovered_keys: set[tuple[str, str]] = set()

        for delivery_location in secure_configuration.delivery_locations:
            normalized_delivery_location = self._normalize_delivery_location(delivery_location)
            try:
                object_names = list(storage_service.inspect(normalized_delivery_location).get("file_names") or [])
            except HTTPException as exc:
                return ConnectorDiscoveryResultEntity(
                    provider=self.provider,
                    errors=(
                        ConnectorErrorEntity(
                            kind="connection",
                            message=f"S3/Blob inventory check failed for '{normalized_delivery_location}': {exc.detail if isinstance(exc.detail, str) else exc.detail}",
                            code="s3_blob_inventory_check_failed",
                            retryable=False,
                            details={"delivery_location": normalized_delivery_location},
                        ),
                    ),
                )
            except Exception as exc:
                return ConnectorDiscoveryResultEntity(
                    provider=self.provider,
                    errors=(
                        ConnectorErrorEntity(
                            kind="connection",
                            message=f"S3/Blob inventory check failed for '{normalized_delivery_location}': {exc}",
                            code="s3_blob_inventory_check_failed",
                            retryable=False,
                            details={"delivery_location": normalized_delivery_location},
                        ),
                    ),
                )

            bucket, prefix = S3DeliveryStorageService._parse_s3a_uri(normalized_delivery_location)
            self._append_container_item(secure_configuration, bucket, discovered_items, discovered_keys, normalized_delivery_location)
            if prefix:
                self._append_folder_item(secure_configuration, bucket, prefix, discovered_items, discovered_keys, normalized_delivery_location)

            for object_name in object_names:
                self._append_object_items(
                    secure_configuration,
                    bucket,
                    prefix,
                    object_name,
                    discovered_items,
                    discovered_keys,
                    normalized_delivery_location,
                )

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

        return ConnectorHealthResultEntity(
            provider=self.provider,
            status="healthy",
            details={
                "container_count": len([item for item in discovery.items if item.kind == "bucket"]),
                "folder_count": len([item for item in discovery.items if item.kind == "folder"]),
                "object_count": len([item for item in discovery.items if item.kind == "object"]),
                "item_count": len(discovery.items),
            },
        )

    def _coerce_secure_configuration(self, configuration: ConnectorConfigurationEntity) -> S3BlobConnectorConfigurationEntity | None:
        if isinstance(configuration, S3BlobConnectorConfigurationEntity) and self._normalized_text(configuration.provider) == self.provider:
            return configuration
        return None

    def _configuration_errors(self, configuration: ConnectorConfigurationEntity) -> list[ConnectorErrorEntity]:
        errors: list[ConnectorErrorEntity] = []
        if not isinstance(configuration, S3BlobConnectorConfigurationEntity):
            errors.append(
                ConnectorErrorEntity(
                    kind="configuration",
                    message="S3/Blob connector requires S3BlobConnectorConfigurationEntity",
                    code="s3_blob_secure_configuration_required",
                    field="configuration",
                )
            )
            return errors

        if self._normalized_text(configuration.provider) != self.provider:
            errors.append(
                ConnectorErrorEntity(
                    kind="configuration",
                    message="S3/Blob connector only accepts the 's3_blob' provider",
                    code="s3_blob_provider_mismatch",
                    field="provider",
                )
            )

        if not configuration.delivery_locations:
            errors.append(
                ConnectorErrorEntity(
                    kind="configuration",
                    message="S3/Blob connector requires delivery_locations",
                    code="s3_blob_missing_delivery_locations",
                    field="delivery_locations",
                )
            )

        seen_locations: set[str] = set()
        for delivery_location in configuration.delivery_locations:
            try:
                normalized = self._normalize_delivery_location(delivery_location)
            except ValueError as exc:
                errors.append(
                    ConnectorErrorEntity(
                        kind="configuration",
                        message=str(exc),
                        code="s3_blob_invalid_delivery_location",
                        field="delivery_locations",
                    )
                )
                continue
            if normalized in seen_locations:
                errors.append(
                    ConnectorErrorEntity(
                        kind="configuration",
                        message=f"S3/Blob connector duplicates delivery location '{normalized}'",
                        code="s3_blob_duplicate_delivery_location",
                        field="delivery_locations",
                    )
                )
                continue
            seen_locations.add(normalized)

        return errors

    def _append_container_item(
        self,
        configuration: S3BlobConnectorConfigurationEntity,
        bucket: str,
        discovered_items: list[ConnectorDiscoveryItemEntity],
        discovered_keys: set[tuple[str, str]],
        delivery_location: str,
    ) -> None:
        identifier = f"s3a://{bucket}"
        key = ("bucket", identifier)
        if key in discovered_keys:
            return
        discovered_items.append(
            ConnectorDiscoveryItemEntity(
                identifier=identifier,
                kind="bucket",
                name=bucket,
                workspace_id=configuration.workspace_id,
                metadata={
                    "bucket": bucket,
                    "delivery_location": delivery_location,
                    "source": "listed",
                },
            )
        )
        discovered_keys.add(key)

    def _append_folder_item(
        self,
        configuration: S3BlobConnectorConfigurationEntity,
        bucket: str,
        prefix: str,
        discovered_items: list[ConnectorDiscoveryItemEntity],
        discovered_keys: set[tuple[str, str]],
        delivery_location: str,
    ) -> None:
        normalized_prefix = prefix.strip("/")
        if not normalized_prefix:
            return
        identifier = f"s3a://{bucket}/{normalized_prefix}"
        key = ("folder", identifier)
        if key in discovered_keys:
            return
        discovered_items.append(
            ConnectorDiscoveryItemEntity(
                identifier=identifier,
                kind="folder",
                name=normalized_prefix.rsplit("/", 1)[-1],
                workspace_id=configuration.workspace_id,
                metadata={
                    "bucket": bucket,
                    "prefix": normalized_prefix,
                    "delivery_location": delivery_location,
                    "source": "listed",
                },
            )
        )
        discovered_keys.add(key)

    def _append_object_items(
        self,
        configuration: S3BlobConnectorConfigurationEntity,
        bucket: str,
        prefix: str,
        object_name: str,
        discovered_items: list[ConnectorDiscoveryItemEntity],
        discovered_keys: set[tuple[str, str]],
        delivery_location: str,
    ) -> None:
        normalized_prefix = prefix.strip("/")
        normalized_object_name = object_name.strip("/")
        if not normalized_object_name:
            return

        path_parts = [part for part in normalized_object_name.split("/") if part]
        if len(path_parts) > 1:
            folder_path = self._join_path(normalized_prefix, normalized_object_name.rsplit("/", 1)[0])
            folder_identifier = f"s3a://{bucket}/{folder_path}"
            folder_key = ("folder", folder_identifier)
            if folder_key not in discovered_keys:
                discovered_items.append(
                    ConnectorDiscoveryItemEntity(
                        identifier=folder_identifier,
                        kind="folder",
                        name=folder_path.rsplit("/", 1)[-1],
                        workspace_id=configuration.workspace_id,
                        metadata={
                            "bucket": bucket,
                            "prefix": folder_path,
                            "delivery_location": delivery_location,
                            "source": "listed",
                        },
                    )
                )
                discovered_keys.add(folder_key)

        object_identifier = f"s3a://{bucket}/{normalized_prefix + '/' if normalized_prefix else ''}{normalized_object_name}"
        object_key = ("object", object_identifier)
        if object_key in discovered_keys:
            return
        discovered_items.append(
            ConnectorDiscoveryItemEntity(
                identifier=object_identifier,
                kind="object",
                name=normalized_object_name.rsplit("/", 1)[-1],
                workspace_id=configuration.workspace_id,
                metadata={
                    "bucket": bucket,
                    "prefix": normalized_prefix,
                    "object_name": normalized_object_name,
                    "delivery_location": delivery_location,
                    "source": "listed",
                },
            )
        )
        discovered_keys.add(object_key)

    def _normalize_delivery_location(self, delivery_location: str) -> str:
        normalized = str(delivery_location or "").strip()
        if not normalized:
            raise ValueError("S3/Blob connector requires non-empty delivery locations")
        if normalized.startswith("s3://"):
            return "s3a://" + normalized[len("s3://") :]
        if normalized.startswith("s3a://"):
            return normalized
        raise ValueError("S3/Blob connector delivery locations must use s3:// or s3a://")

    def _join_path(self, prefix: str, suffix: str) -> str:
        prefix_text = str(prefix or "").strip().strip("/")
        suffix_text = str(suffix or "").strip().strip("/")
        if prefix_text and suffix_text:
            return f"{prefix_text}/{suffix_text}"
        if prefix_text:
            return prefix_text
        return suffix_text

    def _normalized_text(self, value: Any) -> str | None:
        text = str(value or "").strip()
        return text or None


__all__ = ["S3BlobConnector"]