from __future__ import annotations

import importlib
from functools import lru_cache
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import ConfigDict, Field, ValidationError

from app.core.dependencies import get_connector_audit_repository
from app.core.dependencies import get_connector_instance_repository
from app.core.dependencies import get_connector_registry_repository
from app.core.request_context import get_correlation_id
from app.core.request_context import get_user_id
from app.domain.entities.connector import AzureAdlsConnectorConfigurationEntity
from app.domain.entities.connector import ConnectorConfigurationEntity
from app.domain.entities.connector import ConnectorDiscoveryResultEntity
from app.domain.entities.connector import ConnectorInstanceEntity
from app.domain.entities.connector import ConnectorHealthResultEntity
from app.domain.entities.connector import ConnectorSecureConfigurationEntity
from app.domain.entities.connector import ConnectorRegistryEntryEntity
from app.domain.entities.connector import ExternalApiConnectorConfigurationEntity
from app.domain.entities.connector import S3BlobConnectorConfigurationEntity
from app.domain.entities.connector import ConnectorSyncResultEntity
from app.domain.entities.connector import get_connector_registry_entry
from app.domain.entities.connector_audit import ConnectorAuditEntity
from app.domain.entities.connector_audit import build_connector_audit_entity
from app.domain.interfaces import ConnectorAuditRepository
from app.domain.interfaces import ConnectorInstanceRepository
from app.domain.interfaces import ConnectorRegistryRepository
from app.schemas.pydantic_base import SnakeModel, to_snake_alias


router = APIRouter(tags=["connectors"])

_HEADER_REQUEST_ID = "x-request-id"
_HEADER_CORRELATION_ID = "x-correlation-id"


class ConnectorOperationRequestView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    configuration: dict[str, Any] = Field(default_factory=dict)
    connector_instance_id: str | None = None


class ConnectorInstanceCreateRequestView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    configuration: dict[str, Any] = Field(default_factory=dict)


class ConnectorSyncJobView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    jobId: str
    provider: str
    status: str
    requestedAt: str
    startedAt: str
    completedAt: str
    syncedCount: int
    result: ConnectorSyncResultEntity
    correlationId: str


def _header_value(request: Request, name: str) -> str | None:
    value = request.headers.get(name)
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _normalized_provider(provider: str) -> str:
    normalized = str(provider or "").strip().lower()
    if not normalized:
        raise HTTPException(status_code=400, detail=_build_error_detail("connector_provider_required", provider, "Connector provider is required"))
    return normalized


def _build_error_detail(error_code: str, provider: str, message: str, *, errors: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    detail: dict[str, Any] = {
        "error": error_code,
        "provider": provider,
        "service": f"connector:{provider}",
        "message": message,
        "correlation_id": get_correlation_id() or "unknown",
    }
    if errors:
        detail["errors"] = errors
    return detail


def _redacted_configuration(configuration: ConnectorConfigurationEntity) -> dict[str, Any]:
    safe_configuration = configuration.without_secret_values() if isinstance(configuration, ConnectorSecureConfigurationEntity) else configuration
    return safe_configuration.model_dump(mode="json", by_alias=False, exclude_none=True)


def _connector_audit_details(
    *,
    provider: str,
    connector_instance_id: str | None = None,
    configuration: ConnectorConfigurationEntity | None = None,
    validation: Any | None = None,
    result: Any | None = None,
    error_detail: Any | None = None,
) -> dict[str, Any]:
    details: dict[str, Any] = {"provider": provider}
    if connector_instance_id is not None:
        details["connector_instance_id"] = connector_instance_id
    if configuration is not None:
        details["configuration"] = _redacted_configuration(configuration)
    if validation is not None:
        details["validation"] = validation.model_dump(mode="json", by_alias=False, exclude_none=True)
    if result is not None:
        details["result"] = result.model_dump(mode="json", by_alias=False, exclude_none=True)
    if error_detail is not None:
        details["error"] = error_detail if isinstance(error_detail, dict) else {"detail": error_detail}
    return details


async def _record_connector_audit_event(
    *,
    request: Request,
    repository: ConnectorAuditRepository,
    action: str,
    response_type: str,
    status_code: int,
    success: bool,
    provider: str,
    connector_instance_id: str | None,
    details: dict[str, Any],
) -> ConnectorAuditEntity:
    event = build_connector_audit_entity(
        action=action,
        provider=provider,
        endpoint=str(request.url.path),
        method=str(request.method),
        response_type=response_type,
        status_code=status_code,
        success=success,
        request_id=_header_value(request, _HEADER_REQUEST_ID),
        actor_id=get_user_id(),
        correlation_id=_header_value(request, _HEADER_CORRELATION_ID) or get_correlation_id(),
        connector_instance_id=connector_instance_id,
        details=details,
    )
    return await repository.record_event(event)


def _resolve_connector_instance(
    provider: str,
    connector_instance_id: str | None,
    repository: ConnectorInstanceRepository,
) -> ConnectorInstanceEntity | None:
    normalized_instance_id = str(connector_instance_id or "").strip()
    if not normalized_instance_id:
        return None

    instance = repository.get_instance(normalized_instance_id)
    if instance is None:
        raise HTTPException(
            status_code=404,
            detail=_build_error_detail(
                "connector_instance_not_found",
                provider,
                f"Connector instance '{normalized_instance_id}' is not registered",
            ),
        )

    if instance.provider != provider:
        raise HTTPException(
            status_code=400,
            detail=_build_error_detail(
                "connector_instance_provider_mismatch",
                provider,
                f"Connector instance '{normalized_instance_id}' belongs to provider '{instance.provider}' not '{provider}'",
            ),
        )

    return instance


def _configuration_model_for_provider(provider: str) -> type[ConnectorConfigurationEntity]:
    if provider in {"postgresql", "sql_server"}:
        return ConnectorSecureConfigurationEntity
    if provider == "external_api":
        return ExternalApiConnectorConfigurationEntity
    if provider == "azure_adls":
        return AzureAdlsConnectorConfigurationEntity
    if provider == "s3_blob":
        return S3BlobConnectorConfigurationEntity
    raise KeyError(provider)


def _build_connector_configuration(provider: str, configuration_payload: dict[str, Any]) -> ConnectorConfigurationEntity:
    normalized_provider = _normalized_provider(provider)
    payload = dict(configuration_payload)
    payload_provider = _normalized_provider(payload.get("provider") or normalized_provider)
    if payload_provider != normalized_provider:
        raise HTTPException(
            status_code=400,
            detail=_build_error_detail(
                "connector_provider_mismatch",
                normalized_provider,
                f"Connector payload provider '{payload_provider}' does not match route provider '{normalized_provider}'",
            ),
        )
    payload["provider"] = normalized_provider

    try:
        configuration_model = _configuration_model_for_provider(normalized_provider)
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail=_build_error_detail(
                "connector_provider_not_found",
                normalized_provider,
                f"Connector provider '{normalized_provider}' is not registered",
            ),
        ) from exc

    try:
        return configuration_model.model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(
            status_code=400,
            detail=_build_error_detail(
                "connector_configuration_invalid",
                normalized_provider,
                f"Connector configuration for '{normalized_provider}' is invalid",
                errors=exc.errors(),
            ),
        ) from exc


def _build_connector_instance(configuration: ConnectorConfigurationEntity) -> ConnectorInstanceEntity:
    try:
        registry_entry = get_connector_registry_entry(configuration.provider)
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail=_build_error_detail(
                "connector_provider_not_found",
                configuration.provider,
                f"Connector provider '{configuration.provider}' is not registered",
            ),
        ) from exc

    safe_configuration = _redacted_configuration(configuration)
    display_name = str(safe_configuration.get("display_name") or "").strip() or registry_entry.display_name
    now = datetime.now(UTC).isoformat()
    return ConnectorInstanceEntity(
        id=str(uuid4()),
        provider=configuration.provider,
        display_name=display_name,
        workspace_id=configuration.workspace_id,
        tenant_id=configuration.tenant_id,
        configuration=safe_configuration,
        created_at=now,
        updated_at=now,
    )


@lru_cache(maxsize=None)
def _load_connector_class(provider: str) -> type[Any]:
    normalized_provider = _normalized_provider(provider)
    try:
        entry = get_connector_registry_entry(normalized_provider)
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail=_build_error_detail(
                "connector_provider_not_found",
                normalized_provider,
                f"Connector provider '{normalized_provider}' is not registered",
            ),
        ) from exc

    if not entry.implementation_path:
        raise HTTPException(
            status_code=503,
            detail=_build_error_detail(
                "connector_provider_unavailable",
                normalized_provider,
                f"Connector provider '{normalized_provider}' does not declare an implementation path",
            ),
        )

    module_path, class_name = entry.implementation_path.rsplit(".", 1)
    try:
        module = importlib.import_module(module_path)
        return getattr(module, class_name)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=_build_error_detail(
                "connector_provider_unavailable",
                normalized_provider,
                f"Connector provider '{normalized_provider}' could not be loaded",
            ),
        ) from exc


def _build_connector(provider: str) -> Any:
    connector_class = _load_connector_class(provider)
    return connector_class()


def _build_health_failure(result: ConnectorHealthResultEntity) -> HTTPException:
    error_status_code = 503 if any(error.kind in {"connection", "authentication", "discovery", "health"} for error in result.errors) else 400
    return HTTPException(
        status_code=error_status_code,
        detail=_build_error_detail(
            "connector_test_connection_failed" if error_status_code == 503 else "connector_test_connection_invalid",
            result.provider,
            f"Connector '{result.provider}' test connection failed",
            errors=[error.model_dump(mode="json") for error in result.errors],
        ),
    )


def _build_discovery_failure(result: ConnectorDiscoveryResultEntity) -> HTTPException:
    error_status_code = 503 if any(error.kind in {"connection", "authentication", "discovery"} for error in result.errors) else 400
    return HTTPException(
        status_code=error_status_code,
        detail=_build_error_detail(
            "connector_discovery_failed" if error_status_code == 503 else "connector_discovery_invalid",
            result.provider,
            f"Connector '{result.provider}' discovery failed",
            errors=[error.model_dump(mode="json") for error in result.errors],
        ),
    )


def _build_sync_failure(result: ConnectorSyncResultEntity) -> HTTPException:
    error_status_code = 503 if any(error.kind in {"connection", "authentication", "discovery", "sync"} for error in result.errors) else 400
    return HTTPException(
        status_code=error_status_code,
        detail=_build_error_detail(
            "connector_sync_failed" if error_status_code == 503 else "connector_sync_invalid",
            result.provider,
            f"Connector '{result.provider}' sync failed",
            errors=[error.model_dump(mode="json") for error in result.errors],
        ),
    )


@router.post(
    "/connectors/{provider}/test-connection",
    response_model=ConnectorHealthResultEntity,
    responses={
        200: {"description": "Validate the connector configuration and test the live connection."},
        400: {"description": "The connector configuration is invalid."},
        404: {"description": "The connector provider is not registered."},
        503: {"description": "The connector provider is unavailable."},
    },
)
async def test_connector_connection(
    provider: str,
    request: Request,
    body: ConnectorOperationRequestView,
    audit_repository: ConnectorAuditRepository = Depends(get_connector_audit_repository),
    instance_repository: ConnectorInstanceRepository = Depends(get_connector_instance_repository),
) -> ConnectorHealthResultEntity:
    configuration: ConnectorConfigurationEntity | None = None
    validation: Any | None = None
    result: ConnectorHealthResultEntity | None = None
    normalized_provider = _normalized_provider(provider)

    try:
        connector_instance = _resolve_connector_instance(normalized_provider, body.connector_instance_id, instance_repository)
        connector = _build_connector(normalized_provider)
        configuration = _build_connector_configuration(normalized_provider, body.configuration)

        validation = connector.validate(configuration)
        if not validation.valid:
            raise HTTPException(
                status_code=400,
                detail=_build_error_detail(
                    "connector_configuration_invalid",
                    validation.provider,
                    f"Connector configuration for '{validation.provider}' is invalid",
                    errors=[error.model_dump(mode="json") for error in validation.errors],
                ),
            )

        result = connector.health(configuration)
        if result.errors:
            raise _build_health_failure(result)

        await _record_connector_audit_event(
            request=request,
            repository=audit_repository,
            action="connector_test_connection",
            response_type="connector_health_result",
            status_code=200,
            success=True,
            provider=result.provider,
            connector_instance_id=connector_instance.id if connector_instance is not None else None,
            details=_connector_audit_details(
                provider=result.provider,
                connector_instance_id=connector_instance.id if connector_instance is not None else None,
                configuration=configuration,
                validation=validation,
                result=result,
            ),
        )
        return result
    except HTTPException as error:
        await _record_connector_audit_event(
            request=request,
            repository=audit_repository,
            action="connector_test_connection",
            response_type="connector_error",
            status_code=error.status_code,
            success=False,
            provider=configuration.provider if configuration is not None else normalized_provider,
            connector_instance_id=body.connector_instance_id,
            details=_connector_audit_details(
                provider=configuration.provider if configuration is not None else normalized_provider,
                connector_instance_id=body.connector_instance_id,
                configuration=configuration,
                validation=validation,
                result=result,
                error_detail=error.detail,
            ),
        )
        raise


@router.post(
    "/connectors/{provider}/discover-assets",
    response_model=ConnectorDiscoveryResultEntity,
    responses={
        200: {"description": "Discover assets exposed by the connector."},
        400: {"description": "The connector configuration is invalid."},
        404: {"description": "The connector provider is not registered."},
        503: {"description": "The connector provider is unavailable."},
    },
)
async def discover_connector_assets(
    provider: str,
    request: Request,
    body: ConnectorOperationRequestView,
    audit_repository: ConnectorAuditRepository = Depends(get_connector_audit_repository),
    instance_repository: ConnectorInstanceRepository = Depends(get_connector_instance_repository),
) -> ConnectorDiscoveryResultEntity:
    configuration: ConnectorConfigurationEntity | None = None
    validation: Any | None = None
    result: ConnectorDiscoveryResultEntity | None = None
    normalized_provider = _normalized_provider(provider)

    try:
        connector_instance = _resolve_connector_instance(normalized_provider, body.connector_instance_id, instance_repository)
        connector = _build_connector(normalized_provider)
        configuration = _build_connector_configuration(normalized_provider, body.configuration)

        validation = connector.validate(configuration)
        if not validation.valid:
            raise HTTPException(
                status_code=400,
                detail=_build_error_detail(
                    "connector_configuration_invalid",
                    validation.provider,
                    f"Connector configuration for '{validation.provider}' is invalid",
                    errors=[error.model_dump(mode="json") for error in validation.errors],
                ),
            )

        result = connector.discover(configuration)
        if result.errors:
            raise _build_discovery_failure(result)

        await _record_connector_audit_event(
            request=request,
            repository=audit_repository,
            action="connector_discover_assets",
            response_type="connector_discovery_result",
            status_code=200,
            success=True,
            provider=result.provider,
            connector_instance_id=connector_instance.id if connector_instance is not None else None,
            details=_connector_audit_details(
                provider=result.provider,
                connector_instance_id=connector_instance.id if connector_instance is not None else None,
                configuration=configuration,
                validation=validation,
                result=result,
            ),
        )
        return result
    except HTTPException as error:
        await _record_connector_audit_event(
            request=request,
            repository=audit_repository,
            action="connector_discover_assets",
            response_type="connector_error",
            status_code=error.status_code,
            success=False,
            provider=configuration.provider if configuration is not None else normalized_provider,
            connector_instance_id=body.connector_instance_id,
            details=_connector_audit_details(
                provider=configuration.provider if configuration is not None else normalized_provider,
                connector_instance_id=body.connector_instance_id,
                configuration=configuration,
                validation=validation,
                result=result,
                error_detail=error.detail,
            ),
        )
        raise


@router.post(
    "/connectors/{provider}/sync",
    response_model=ConnectorSyncJobView,
    responses={
        200: {"description": "Synchronize connector metadata and return the completed job record."},
        400: {"description": "The connector configuration is invalid."},
        404: {"description": "The connector provider is not registered."},
        503: {"description": "The connector provider is unavailable."},
    },
)
async def sync_connector_assets(
    provider: str,
    request: Request,
    body: ConnectorOperationRequestView,
    audit_repository: ConnectorAuditRepository = Depends(get_connector_audit_repository),
    instance_repository: ConnectorInstanceRepository = Depends(get_connector_instance_repository),
) -> ConnectorSyncJobView:
    configuration: ConnectorConfigurationEntity | None = None
    validation: Any | None = None
    result: ConnectorSyncResultEntity | None = None
    normalized_provider = _normalized_provider(provider)

    try:
        connector_instance = _resolve_connector_instance(normalized_provider, body.connector_instance_id, instance_repository)
        connector = _build_connector(normalized_provider)
        configuration = _build_connector_configuration(normalized_provider, body.configuration)

        validation = connector.validate(configuration)
        if not validation.valid:
            raise HTTPException(
                status_code=400,
                detail=_build_error_detail(
                    "connector_configuration_invalid",
                    validation.provider,
                    f"Connector configuration for '{validation.provider}' is invalid",
                    errors=[error.model_dump(mode="json") for error in validation.errors],
                ),
            )

        result = connector.sync(configuration)
        if result.errors:
            raise _build_sync_failure(result)

        timestamp = datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")
        job = ConnectorSyncJobView(
            jobId=f"connector-sync-{uuid4().hex[:12]}",
            provider=result.provider,
            status="completed",
            requestedAt=timestamp,
            startedAt=timestamp,
            completedAt=timestamp,
            syncedCount=result.synced_count,
            result=result,
            correlationId=get_correlation_id() or "unknown",
        )
        await _record_connector_audit_event(
            request=request,
            repository=audit_repository,
            action="connector_sync_assets",
            response_type="connector_sync_job",
            status_code=200,
            success=True,
            provider=job.provider,
            connector_instance_id=connector_instance.id if connector_instance is not None else None,
            details=_connector_audit_details(
                provider=job.provider,
                connector_instance_id=connector_instance.id if connector_instance is not None else None,
                configuration=configuration,
                validation=validation,
                result=job,
            ),
        )
        return job
    except HTTPException as error:
        await _record_connector_audit_event(
            request=request,
            repository=audit_repository,
            action="connector_sync_assets",
            response_type="connector_error",
            status_code=error.status_code,
            success=False,
            provider=configuration.provider if configuration is not None else normalized_provider,
            connector_instance_id=body.connector_instance_id,
            details=_connector_audit_details(
                provider=configuration.provider if configuration is not None else normalized_provider,
                connector_instance_id=body.connector_instance_id,
                configuration=configuration,
                validation=validation,
                result=result,
                error_detail=error.detail,
            ),
        )
        raise


@router.get(
    "/connectors/audit-events",
    response_model=list[ConnectorAuditEntity],
    responses={
        200: {"description": "Return the connector audit trail."},
        503: {"description": "The connector audit repository is unavailable."},
    },
)
async def list_connector_audit_events(
    provider: str | None = Query(default=None),
    limit: int = Query(default=100, ge=0),
    offset: int = Query(default=0, ge=0),
    audit_repository: ConnectorAuditRepository = Depends(get_connector_audit_repository),
) -> list[ConnectorAuditEntity]:
    return await audit_repository.list_events(provider=provider, limit=limit, offset=offset)


@router.get(
    "/connectors/registry",
    response_model=list[ConnectorRegistryEntryEntity],
    responses={
        200: {"description": "Return the persisted connector registry."},
        503: {"description": "The connector registry repository is unavailable."},
    },
)
async def list_connector_registry_entries(
    registry_repository: ConnectorRegistryRepository = Depends(get_connector_registry_repository),
) -> list[ConnectorRegistryEntryEntity]:
    return registry_repository.list_entries()


@router.get(
    "/connectors/instances",
    response_model=list[ConnectorInstanceEntity],
    responses={
        200: {"description": "Return the persisted connector instances."},
        503: {"description": "The connector instance repository is unavailable."},
    },
)
async def list_connector_instances(
    provider: str | None = Query(default=None),
    workspace_id: str | None = Query(default=None),
    tenant_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=0),
    offset: int = Query(default=0, ge=0),
    instance_repository: ConnectorInstanceRepository = Depends(get_connector_instance_repository),
) -> list[ConnectorInstanceEntity]:
    return instance_repository.list_instances(
        provider=provider,
        workspace_id=workspace_id,
        tenant_id=tenant_id,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/connectors/instances",
    response_model=ConnectorInstanceEntity,
    responses={
        200: {"description": "Persist a connector instance."},
        400: {"description": "The connector payload is invalid."},
        404: {"description": "The connector provider is not registered."},
        503: {"description": "The connector instance repository is unavailable."},
    },
)
async def create_connector_instance(
    body: ConnectorInstanceCreateRequestView,
    instance_repository: ConnectorInstanceRepository = Depends(get_connector_instance_repository),
) -> ConnectorInstanceEntity:
    configuration = _build_connector_configuration(_normalized_provider(body.configuration.get("provider") or ""), body.configuration)
    instance = _build_connector_instance(configuration)
    return instance_repository.upsert_instance(instance)


# Connector sync job, schedule and staleness endpoints live in
# connector_sync_jobs.py to keep this file under the 1000-line limit.