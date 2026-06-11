from __future__ import annotations

from types import SimpleNamespace

import pytest

import app.api.v1.endpoints.connectors as connector_endpoints
from app.core.dependencies import get_connector_audit_repository
from app.core.dependencies import get_connector_instance_repository
from app.core.dependencies import get_connector_registry_repository
from app.domain.entities.connector import ConnectorDiscoveryItemEntity
from app.domain.entities.connector import ConnectorDiscoveryResultEntity
from app.domain.entities.connector import ConnectorHealthResultEntity
from app.domain.entities.connector import ConnectorInstanceEntity
from app.domain.entities.connector import ConnectorRegistryEntryEntity
from app.domain.entities.connector import ConnectorValidationResultEntity
from app.domain.entities.connector import ConnectorSyncResultEntity
from app.main import app


class _FakeConnector:
    def __init__(self, *, health_result: ConnectorHealthResultEntity, discovery_result: ConnectorDiscoveryResultEntity) -> None:
        self.health_result = health_result
        self.discovery_result = discovery_result
        self.sync_result = ConnectorSyncResultEntity(
            provider=discovery_result.provider,
            synced_count=len(discovery_result.items),
            items=discovery_result.items,
        )
        self.validate_calls: list[dict] = []
        self.health_calls: list[dict] = []
        self.discover_calls: list[dict] = []
        self.sync_calls: list[dict] = []

    def validate(self, configuration):
        self.validate_calls.append(configuration.model_dump(mode="json"))
        return ConnectorValidationResultEntity(provider=configuration.provider, valid=True, errors=())

    def health(self, configuration):
        self.health_calls.append(configuration.model_dump(mode="json"))
        return self.health_result

    def discover(self, configuration):
        self.discover_calls.append(configuration.model_dump(mode="json"))
        return self.discovery_result

    def sync(self, configuration):
        self.sync_calls.append(configuration.model_dump(mode="json"))
        return self.sync_result


class _FakeConnectorAuditRepository:
    def __init__(self) -> None:
        self.events: list[object] = []

    async def record_event(self, event):
        self.events.append(event)
        return event

    async def list_events(self, *, provider: str | None = None, limit: int = 100, offset: int = 0):
        rows = self.events
        if provider is not None:
            normalized_provider = provider.strip().lower()
            rows = [event for event in rows if getattr(event, "provider", "").strip().lower() == normalized_provider]
        return rows[offset : offset + limit]


class _FakeConnectorRegistryRepository:
    def __init__(self) -> None:
        self.entries = [
            ConnectorRegistryEntryEntity(
                provider="external_api",
                display_name="External API",
                description="API connector for systems exposed through explicit operations with optional OpenAPI augmentation.",
                implementation_path="app.application.services.external_api_connector.ExternalApiConnector",
                supported_asset_kinds=("api_operation", "openapi_document"),
            )
        ]

    def upsert_entry(self, entry: ConnectorRegistryEntryEntity) -> ConnectorRegistryEntryEntity:
        self.entries = [existing for existing in self.entries if existing.provider != entry.provider]
        self.entries.append(entry)
        return entry

    def list_entries(self) -> list[ConnectorRegistryEntryEntity]:
        return list(self.entries)

    def get_entry(self, provider: str) -> ConnectorRegistryEntryEntity | None:
        normalized_provider = provider.strip().lower()
        for entry in self.entries:
            if entry.provider == normalized_provider:
                return entry
        return None


class _FakeConnectorInstanceRepository:
    def __init__(self) -> None:
        self.instances: list[ConnectorInstanceEntity] = []

    def upsert_instance(self, instance: ConnectorInstanceEntity) -> ConnectorInstanceEntity:
        self.instances = [existing for existing in self.instances if existing.id != instance.id]
        self.instances.append(instance)
        return instance

    def list_instances(
        self,
        *,
        provider: str | None = None,
        workspace_id: str | None = None,
        tenant_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ConnectorInstanceEntity]:
        rows = self.instances
        if provider is not None:
            normalized_provider = provider.strip().lower()
            rows = [instance for instance in rows if instance.provider.strip().lower() == normalized_provider]
        if workspace_id is not None:
            normalized_workspace_id = workspace_id.strip().lower()
            rows = [instance for instance in rows if (instance.workspace_id or "").strip().lower() == normalized_workspace_id]
        if tenant_id is not None:
            normalized_tenant_id = tenant_id.strip().lower()
            rows = [instance for instance in rows if (instance.tenant_id or "").strip().lower() == normalized_tenant_id]
        safe_limit = max(0, min(limit, 1000))
        if safe_limit == 0:
            return []
        return rows[offset : offset + safe_limit]

    def get_instance(self, instance_id: str) -> ConnectorInstanceEntity | None:
        normalized_instance_id = instance_id.strip()
        for instance in self.instances:
            if instance.id == normalized_instance_id:
                return instance
        return None


@pytest.fixture
def connector_request_payload() -> dict[str, object]:
    return {
        "configuration": {
            "provider": "external_api",
            "base_url": "https://api.example.com",
            "api_operations": [
                {
                    "name": "list_customers",
                    "method": "GET",
                    "path": "/customers",
                }
            ],
            "request_timeout_seconds": 30,
        }
    }


@pytest.fixture
def fake_connector() -> _FakeConnector:
    discovery_result = ConnectorDiscoveryResultEntity(
        provider="external_api",
        items=(
            ConnectorDiscoveryItemEntity(
                identifier="https://api.example.com::GET:/customers",
                kind="api_operation",
                name="list_customers",
                metadata={"method": "GET", "path": "/customers", "source": "configured"},
            ),
        ),
    )
    health_result = ConnectorHealthResultEntity(
        provider="external_api",
        status="healthy",
        details={"operation_count": 1},
    )
    return _FakeConnector(health_result=health_result, discovery_result=discovery_result)


@pytest.fixture
def connector_audit_repository_override() -> _FakeConnectorAuditRepository:
    repository = _FakeConnectorAuditRepository()
    app.dependency_overrides[get_connector_audit_repository] = lambda: repository
    try:
        yield repository
    finally:
        app.dependency_overrides.pop(get_connector_audit_repository, None)


@pytest.fixture
def connector_registry_repository_override() -> _FakeConnectorRegistryRepository:
    repository = _FakeConnectorRegistryRepository()
    app.dependency_overrides[get_connector_registry_repository] = lambda: repository
    try:
        yield repository
    finally:
        app.dependency_overrides.pop(get_connector_registry_repository, None)


@pytest.fixture
def connector_instance_repository_override() -> _FakeConnectorInstanceRepository:
    repository = _FakeConnectorInstanceRepository()
    app.dependency_overrides[get_connector_instance_repository] = lambda: repository
    try:
        yield repository
    finally:
        app.dependency_overrides.pop(get_connector_instance_repository, None)


def test_connector_test_connection_records_audit_event(
    client,
    auth_headers,
    monkeypatch,
    connector_request_payload,
    fake_connector,
    connector_audit_repository_override,
    connector_instance_repository_override,
) -> None:
    monkeypatch.setattr(connector_endpoints, "_build_connector", lambda provider: fake_connector)

    connector_instance_repository_override.upsert_instance(
        ConnectorInstanceEntity(
            id="connector-instance-1",
            provider="external_api",
            display_name="External API",
            workspace_id="workspace-1",
            tenant_id=None,
            configuration={"provider": "external_api"},
            created_at="2026-06-06T00:00:00Z",
            updated_at="2026-06-06T00:00:00Z",
        ),
    )
    request_payload = {**connector_request_payload, "connector_instance_id": "connector-instance-1"}

    response = client.post(
        "/api/rulebuilder/v1/connectors/external_api/test-connection",
        json=request_payload,
        headers=auth_headers("dq:rules:read", "dq:rules:edit", "dq:rules:write"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "external_api"
    assert payload["status"] == "healthy"
    assert payload["details"]["operation_count"] == 1
    assert len(fake_connector.health_calls) == 1
    assert fake_connector.health_calls[0]["provider"] == "external_api"
    assert len(connector_audit_repository_override.events) == 1
    event = connector_audit_repository_override.events[0]
    assert event.action == "connector_test_connection"
    assert event.provider == "external_api"
    assert event.connector_instance_id == "connector-instance-1"
    assert event.success is True
    assert event.details["provider"] == "external_api"
    assert event.details["connector_instance_id"] == "connector-instance-1"
    assert event.details["configuration"]["provider"] == "external_api"


def test_connector_audit_events_list_returns_records(
    client,
    auth_headers,
    monkeypatch,
    connector_request_payload,
    fake_connector,
    connector_audit_repository_override,
    connector_instance_repository_override,
) -> None:
    monkeypatch.setattr(connector_endpoints, "_build_connector", lambda provider: fake_connector)

    response = client.post(
        "/api/rulebuilder/v1/connectors/external_api/test-connection",
        json=connector_request_payload,
        headers=auth_headers("dq:rules:read", "dq:rules:edit", "dq:rules:write"),
    )

    assert response.status_code == 200

    audit_response = client.get(
        "/api/rulebuilder/v1/connectors/audit-events",
        headers=auth_headers("dq:rules:read", "dq:rules:edit", "dq:rules:write"),
    )

    assert audit_response.status_code == 200
    audit_payload = audit_response.json()
    assert len(audit_payload) == 1
    assert audit_payload[0]["action"] == "connector_test_connection"
    assert audit_payload[0]["provider"] == "external_api"


def test_connector_registry_list_returns_records(client, auth_headers, connector_registry_repository_override) -> None:
    response = client.get(
        "/api/rulebuilder/v1/connectors/registry",
        headers=auth_headers("dq:rules:read", "dq:rules:edit", "dq:rules:write"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["provider"] == "external_api"
    assert payload[0]["display_name"] == "External API"


def test_connector_instances_create_and_list_returns_records(
    client,
    auth_headers,
    connector_request_payload,
    connector_instance_repository_override,
) -> None:
    create_response = client.post(
        "/api/rulebuilder/v1/connectors/instances",
        json=connector_request_payload,
        headers=auth_headers("dq:rules:read", "dq:rules:edit", "dq:rules:write"),
    )

    assert create_response.status_code == 200
    create_payload = create_response.json()
    assert create_payload["provider"] == "external_api"
    assert create_payload["display_name"] == "External API"
    assert create_payload["configuration"]["provider"] == "external_api"
    assert len(connector_instance_repository_override.instances) == 1

    list_response = client.get(
        "/api/rulebuilder/v1/connectors/instances",
        headers=auth_headers("dq:rules:read", "dq:rules:edit", "dq:rules:write"),
    )

    assert list_response.status_code == 200
    list_payload = list_response.json()
    assert len(list_payload) == 1
    assert list_payload[0]["id"] == create_payload["id"]
    assert list_payload[0]["provider"] == "external_api"


def test_connector_discover_assets_returns_discovery_result(
    client,
    auth_headers,
    monkeypatch,
    connector_request_payload,
    fake_connector,
    connector_instance_repository_override,
) -> None:
    monkeypatch.setattr(connector_endpoints, "_build_connector", lambda provider: fake_connector)

    response = client.post(
        "/api/rulebuilder/v1/connectors/external_api/discover-assets",
        json=connector_request_payload,
        headers=auth_headers("dq:rules:read", "dq:rules:edit", "dq:rules:write"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "external_api"
    assert payload["items"][0]["identifier"] == "https://api.example.com::GET:/customers"
    assert len(fake_connector.discover_calls) == 1
    assert fake_connector.discover_calls[0]["provider"] == "external_api"


def test_connector_sync_returns_completed_job(
    client,
    auth_headers,
    monkeypatch,
    connector_request_payload,
    fake_connector,
    connector_instance_repository_override,
) -> None:
    monkeypatch.setattr(connector_endpoints, "_build_connector", lambda provider: fake_connector)

    response = client.post(
        "/api/rulebuilder/v1/connectors/external_api/sync",
        json=connector_request_payload,
        headers=auth_headers("dq:rules:read", "dq:rules:edit", "dq:rules:write"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "external_api"
    assert payload["status"] == "completed"
    assert payload["synced_count"] == 1
    assert payload["result"]["provider"] == "external_api"
    assert len(fake_connector.sync_calls) == 1
    assert fake_connector.sync_calls[0]["provider"] == "external_api"


def test_connector_routes_reject_provider_mismatch(client, auth_headers, monkeypatch, connector_request_payload, fake_connector) -> None:
    monkeypatch.setattr(connector_endpoints, "_build_connector", lambda provider: fake_connector)
    mismatched_payload = {
        "configuration": {
            **connector_request_payload["configuration"],
            "provider": "sql_server",
        }
    }

    response = client.post(
        "/api/rulebuilder/v1/connectors/external_api/test-connection",
        json=mismatched_payload,
        headers=auth_headers("dq:rules:read", "dq:rules:edit", "dq:rules:write"),
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["detail"]["error"] == "connector_provider_mismatch"
    assert payload["detail"]["provider"] == "external_api"