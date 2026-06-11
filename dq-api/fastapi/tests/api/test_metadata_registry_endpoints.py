from __future__ import annotations

from typing import Any

import pytest

from app.application.services.registry_definition_resolver import RegistryDefinitionLookupError
from app.core.dependencies import get_data_catalog_repository
from app.core.dependencies import get_federated_metadata_registry_repository
from app.core.dependencies import get_registry_definition_resolver
from app.infrastructure.repositories.in_memory_data_catalog_repository import InMemoryDataCatalogRepository
from app.infrastructure.repositories.in_memory_federated_metadata_registry_repository import InMemoryFederatedMetadataRegistryRepository
from app.main import app


class _FakeRegistryDefinitionResolver:
    def __init__(self) -> None:
        self.resolved_definitions: list[str] = []

    async def resolve_definition(self, definition_id: str) -> dict[str, Any]:
        normalized_definition_id = str(definition_id or "").strip()
        self.resolved_definitions.append(normalized_definition_id)
        if normalized_definition_id == "def.attribute.customer_id":
            return {
                "definition_id": normalized_definition_id,
                "definition_type": "attribute",
                "definition_name": "Customer Identifier",
                "business_definition": "A stable identifier assigned to a customer record.",
                "glossary_id": "glossary-retail",
                "glossary_name": "Retail Banking Glossary",
                "object_class": "Customer",
                "property": "customer_id",
                "representation_term": "Identifier",
                "value_domain": {
                    "type": "string",
                    "format": "uuid",
                    "unit": None,
                    "allowed_values": [],
                    "constraints": {},
                },
                "status": "approved",
                "owner": "Data Steward",
                "synonyms": ["client_id"],
                "parent_definition_id": "",
                "parent_definition_name": "",
                "child_definition_ids": [],
                "child_definition_names": [],
                "child_definition_count": 0,
                "source_system": "openmetadata",
                "openmetadata_entity_id": "om-term-customer-id",
                "openmetadata_entity_type": "glossary_term",
                "version": "1",
                "provenance": {
                    "created_by": "data.steward@example.com",
                    "approved_by": "data.steward@example.com",
                    "created_at": "2026-01-01T08:00:00Z",
                    "approved_at": "2026-01-02T08:00:00Z",
                    "change_reason": "approved",
                },
                "applies_to": ["customer"],
            }
        if normalized_definition_id == "def.attribute.customer_active_flag":
            return {
                "definition_id": normalized_definition_id,
                "definition_type": "attribute",
                "definition_name": "Customer Active Flag",
                "business_definition": "A boolean flag indicating whether the customer is active.",
                "glossary_id": "glossary-retail",
                "glossary_name": "Retail Banking Glossary",
                "object_class": "Customer",
                "property": "is_active",
                "representation_term": "Indicator",
                "value_domain": {
                    "type": "boolean",
                    "format": None,
                    "unit": None,
                    "allowed_values": ["true", "false"],
                    "constraints": {},
                },
                "status": "approved",
                "owner": "Data Steward",
                "synonyms": ["active_flag"],
                "parent_definition_id": "",
                "parent_definition_name": "",
                "child_definition_ids": [],
                "child_definition_names": [],
                "child_definition_count": 0,
                "source_system": "openmetadata",
                "openmetadata_entity_id": "om-term-customer-active-flag",
                "openmetadata_entity_type": "glossary_term",
                "version": "1",
                "provenance": {
                    "created_by": "data.steward@example.com",
                    "approved_by": "data.steward@example.com",
                    "created_at": "2026-01-01T08:00:00Z",
                    "approved_at": "2026-01-02T08:00:00Z",
                    "change_reason": "approved",
                },
                "applies_to": ["customer"],
            }
        raise RegistryDefinitionLookupError(
            f"Registry definition '{normalized_definition_id}' was not found in the test resolver",
            status_code=404,
        )


@pytest.fixture
def data_catalog_repository() -> InMemoryDataCatalogRepository:
    return InMemoryDataCatalogRepository()


@pytest.fixture
def federated_metadata_registry_repository() -> InMemoryFederatedMetadataRegistryRepository:
    return InMemoryFederatedMetadataRegistryRepository()


@pytest.fixture
def registry_definition_resolver() -> _FakeRegistryDefinitionResolver:
    return _FakeRegistryDefinitionResolver()


@pytest.fixture(autouse=True)
def override_metadata_registry_dependencies(
    data_catalog_repository: InMemoryDataCatalogRepository,
    registry_definition_resolver: _FakeRegistryDefinitionResolver,
    federated_metadata_registry_repository: InMemoryFederatedMetadataRegistryRepository,
) -> None:
    app.dependency_overrides[get_data_catalog_repository] = lambda: data_catalog_repository
    app.dependency_overrides[get_registry_definition_resolver] = lambda: registry_definition_resolver
    app.dependency_overrides[get_federated_metadata_registry_repository] = lambda: federated_metadata_registry_repository
    yield
    app.dependency_overrides.pop(get_data_catalog_repository, None)
    app.dependency_overrides.pop(get_registry_definition_resolver, None)
    app.dependency_overrides.pop(get_federated_metadata_registry_repository, None)


def test_push_metadata_registry_package(client, auth_headers, registry_definition_resolver) -> None:
    response = client.post(
        "/api/data-catalog/v1/metadata-registry/push",
        json={"workspace_id": "retail-banking", "data_product_id": "prod-1"},
        headers=auth_headers("dq:data_catalog:read"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["package_kind"] == "federated_metadata_package"
    assert payload["workspace_id"] == "retail-banking"
    assert payload["data_product_id"] == "prod-1"
    assert payload["manifest"]["data_product_count"] == len(payload["data_products"])
    assert payload["manifest"]["registry_definition_count"] == len(payload["registry_definitions"])
    assert {definition["definition_id"] for definition in payload["registry_definitions"]} == {
        "def.attribute.customer_active_flag",
    }
    assert registry_definition_resolver.resolved_definitions == [
        "def.attribute.customer_active_flag",
    ]

def test_register_metadata_registry_external_party_records_workspace_identity_and_scope(client, auth_headers, federated_metadata_registry_repository) -> None:
    response = client.post(
        "/api/data-catalog/v1/metadata-registry/external-parties",
        json={
            "workspace_id": "retail-banking",
            "display_name": "Retail Banking Exchange Partner",
            "governing_scope": {
                "data_product_ids": ["prod-1"],
                "metadata_structure_ids": ["customer-profile"],
                "metadata_item_ids": ["customer.profile.name"],
            },
        },
        headers=auth_headers("dq:data_catalog:read"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == "workspace:retail-banking"
    assert payload["workspace_id"] == "retail-banking"
    assert payload["tenant_id"] is None
    assert payload["display_name"] == "Retail Banking Exchange Partner"
    assert payload["approval_status"] == "pending"
    assert payload["approved_at"] is None
    assert payload["approved_by"] is None
    assert payload["approval_notes"] is None
    assert payload["governing_scope"]["data_product_ids"] == ["prod-1"]
    assert payload["governing_scope"]["metadata_structure_ids"] == ["customer-profile"]
    assert payload["governing_scope"]["metadata_item_ids"] == ["customer.profile.name"]

    parties = federated_metadata_registry_repository.list_federated_metadata_registry_external_parties(
        workspace_id="retail-banking",
    )
    assert len(parties) == 1
    assert parties[0].id == "workspace:retail-banking"
    assert parties[0].approval_status == "pending"
    assert parties[0].governing_scope.data_product_ids == ["prod-1"]


def test_admin_can_view_and_approve_external_party_registration(client, auth_headers, federated_metadata_registry_repository) -> None:
    register_response = client.post(
        "/api/data-catalog/v1/metadata-registry/external-parties",
        json={
            "workspace_id": "retail-banking",
            "display_name": "Pending Exchange Partner",
            "governing_scope": {
                "metadata_structure_ids": ["customer-profile"],
            },
        },
        headers=auth_headers("dq:data_catalog:read"),
    )

    assert register_response.status_code == 200
    party_id = register_response.json()["id"]

    pending_response = client.get(
        "/api/data-catalog/v1/metadata-registry/external-parties",
        params={"approval_status": "pending"},
        headers=auth_headers("dq:data_catalog:read"),
    )
    assert pending_response.status_code == 200
    assert any(item["id"] == party_id for item in pending_response.json())

    approve_response = client.post(
        f"/api/data-catalog/v1/metadata-registry/external-parties/{party_id}/approve",
        json={"approval_notes": "Approved for exchange"},
        headers=auth_headers("dq:users:manage"),
    )

    assert approve_response.status_code == 200
    approved_payload = approve_response.json()
    assert approved_payload["id"] == party_id
    assert approved_payload["approval_status"] == "approved"
    assert approved_payload["approved_by"] == "user-admin"
    assert approved_payload["approved_at"] is not None
    assert approved_payload["approval_notes"] == "Approved for exchange"

    stored_parties = federated_metadata_registry_repository.list_federated_metadata_registry_external_parties(
        party_id=party_id,
    )
    assert len(stored_parties) == 1
    assert stored_parties[0].approval_status == "approved"
    assert stored_parties[0].approved_by == "user-admin"
    assert stored_parties[0].approval_notes == "Approved for exchange"

    approved_response = client.get(
        "/api/data-catalog/v1/metadata-registry/external-parties",
        params={"approval_status": "approved"},
        headers=auth_headers("dq:data_catalog:read"),
    )
    assert approved_response.status_code == 200
    assert any(item["id"] == party_id for item in approved_response.json())


def test_admin_can_grant_and_report_external_party_access(client, auth_headers, federated_metadata_registry_repository) -> None:
    register_response = client.post(
        "/api/data-catalog/v1/metadata-registry/external-parties",
        json={
            "workspace_id": "retail-banking",
            "display_name": "Access Partner",
            "governing_scope": {
                "metadata_structure_ids": ["customer-profile"],
                "metadata_item_ids": ["customer.profile.name"],
            },
        },
        headers=auth_headers("dq:data_catalog:read"),
    )
    assert register_response.status_code == 200
    party_id = register_response.json()["id"]

    approve_response = client.post(
        f"/api/data-catalog/v1/metadata-registry/external-parties/{party_id}/approve",
        json={"approval_notes": "Approved for access grants"},
        headers=auth_headers("dq:users:manage"),
    )
    assert approve_response.status_code == 200

    grant_response = client.post(
        f"/api/data-catalog/v1/metadata-registry/external-parties/{party_id}/access-grants",
        json={
            "target_kind": "metadata_structure",
            "target_id": "customer-profile",
            "subscribed": True,
            "can_push": True,
            "can_pull": False,
            "notes": "Allowed to publish metadata package updates",
        },
        headers=auth_headers("dq:users:manage"),
    )
    assert grant_response.status_code == 200
    grant_payload = grant_response.json()
    assert grant_payload["external_party_id"] == party_id
    assert grant_payload["target_kind"] == "metadata_structure"
    assert grant_payload["target_id"] == "customer-profile"
    assert grant_payload["subscribed"] is True
    assert grant_payload["can_push"] is True
    assert grant_payload["can_pull"] is False
    assert grant_payload["notes"] == "Allowed to publish metadata package updates"

    report_response = client.get(
        "/api/data-catalog/v1/metadata-registry/access-grants",
        params={"target_kind": "metadata_structure", "target_id": "customer-profile"},
        headers=auth_headers("dq:data_catalog:read"),
    )
    assert report_response.status_code == 200
    report_payload = report_response.json()
    assert len(report_payload) == 1
    assert report_payload[0]["external_party_id"] == party_id
    assert report_payload[0]["can_push"] is True

    party_report_response = client.get(
        "/api/data-catalog/v1/metadata-registry/access-grants",
        params={"party_id": party_id},
        headers=auth_headers("dq:data_catalog:read"),
    )
    assert party_report_response.status_code == 200
    assert any(item["target_id"] == "customer-profile" for item in party_report_response.json())


def test_external_party_access_grant_rejects_unapproved_party(client, auth_headers) -> None:
    register_response = client.post(
        "/api/data-catalog/v1/metadata-registry/external-parties",
        json={
            "workspace_id": "retail-banking",
            "governing_scope": {
                "metadata_structure_ids": ["customer-profile"],
            },
        },
        headers=auth_headers("dq:data_catalog:read"),
    )
    assert register_response.status_code == 200

    grant_response = client.post(
        f"/api/data-catalog/v1/metadata-registry/external-parties/{register_response.json()['id']}/access-grants",
        json={
            "target_kind": "metadata_structure",
            "target_id": "customer-profile",
            "subscribed": True,
        },
        headers=auth_headers("dq:users:manage"),
    )

    assert grant_response.status_code == 409
    assert grant_response.json()["detail"]["error"] == "federated_metadata_registry_external_party_not_approved"


def test_approve_metadata_registry_external_party_requires_manage_scope(client, auth_headers) -> None:
    register_response = client.post(
        "/api/data-catalog/v1/metadata-registry/external-parties",
        json={
            "workspace_id": "retail-banking",
            "governing_scope": {
                "metadata_structure_ids": ["customer-profile"],
            },
        },
        headers=auth_headers("dq:data_catalog:read"),
    )
    assert register_response.status_code == 200

    approve_response = client.post(
        f"/api/data-catalog/v1/metadata-registry/external-parties/{register_response.json()['id']}/approve",
        json={},
        headers=auth_headers("dq:data_catalog:read"),
    )

    assert approve_response.status_code == 403


def test_access_grants_reject_invalid_target_kind(client, auth_headers) -> None:
    register_response = client.post(
        "/api/data-catalog/v1/metadata-registry/external-parties",
        json={
            "workspace_id": "retail-banking",
            "governing_scope": {
                "metadata_structure_ids": ["customer-profile"],
            },
        },
        headers=auth_headers("dq:data_catalog:read"),
    )
    assert register_response.status_code == 200

    approve_response = client.post(
        f"/api/data-catalog/v1/metadata-registry/external-parties/{register_response.json()['id']}/approve",
        json={},
        headers=auth_headers("dq:users:manage"),
    )
    assert approve_response.status_code == 200

    grant_response = client.post(
        f"/api/data-catalog/v1/metadata-registry/external-parties/{register_response.json()['id']}/access-grants",
        json={
            "target_kind": "invalid_target",
            "target_id": "customer-profile",
            "subscribed": True,
        },
        headers=auth_headers("dq:users:manage"),
    )

    assert grant_response.status_code == 400
    assert grant_response.json()["detail"]["error"] == "federated_metadata_registry_invalid_access_grant"


def test_register_metadata_registry_external_party_accepts_tenant_identity(client, auth_headers) -> None:
    response = client.post(
        "/api/data-catalog/v1/metadata-registry/external-parties",
        json={
            "tenant_id": "tenant-42",
            "governing_scope": {
                "metadata_structure_ids": ["tenant-shared-profile"],
            },
        },
        headers=auth_headers("dq:data_catalog:read"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == "tenant:tenant-42"
    assert payload["workspace_id"] is None
    assert payload["tenant_id"] == "tenant-42"
    assert payload["approval_status"] == "pending"
    assert payload["governing_scope"]["metadata_structure_ids"] == ["tenant-shared-profile"]


def test_register_metadata_registry_external_party_rejects_missing_identity_or_scope(client, auth_headers) -> None:
    response = client.post(
        "/api/data-catalog/v1/metadata-registry/external-parties",
        json={"display_name": "Incomplete External Party"},
        headers=auth_headers("dq:data_catalog:read"),
    )

    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "federated_metadata_registry_invalid_external_party"


def test_push_metadata_registry_package_records_exchange_snapshot(client, auth_headers, federated_metadata_registry_repository) -> None:
    response = client.post(
        "/api/data-catalog/v1/metadata-registry/push",
        json={"workspace_id": "retail-banking", "data_product_id": "prod-1"},
        headers=auth_headers("dq:data_catalog:read"),
    )

    assert response.status_code == 200
    snapshots = federated_metadata_registry_repository.list_federated_metadata_registry_exchange_snapshots(
        workspace_id="retail-banking",
        data_product_id="prod-1",
    )
    assert len(snapshots) == 1
    assert snapshots[0].exchange_kind == "push"
    assert snapshots[0].accepted is True
    assert snapshots[0].package_id == response.json()["package_id"]


def test_pull_metadata_registry_package_accepts_exported_package(client, auth_headers) -> None:
    push_response = client.post(
        "/api/data-catalog/v1/metadata-registry/push",
        json={"workspace_id": "retail-banking", "data_product_id": "prod-1"},
        headers=auth_headers("dq:data_catalog:read"),
    )
    assert push_response.status_code == 200

    pull_response = client.post(
        "/api/data-catalog/v1/metadata-registry/pull",
        json=push_response.json(),
        headers=auth_headers("dq:data_catalog:read"),
    )

    assert pull_response.status_code == 200
    payload = pull_response.json()
    assert payload["accepted"] is True
    assert payload["package"]["package_id"] == push_response.json()["package_id"]
    assert payload["package"]["manifest"] == push_response.json()["manifest"]


def test_pull_metadata_registry_package_records_exchange_snapshot(client, auth_headers, federated_metadata_registry_repository) -> None:
    push_response = client.post(
        "/api/data-catalog/v1/metadata-registry/push",
        json={"workspace_id": "retail-banking", "data_product_id": "prod-1"},
        headers=auth_headers("dq:data_catalog:read"),
    )
    assert push_response.status_code == 200

    pull_response = client.post(
        "/api/data-catalog/v1/metadata-registry/pull",
        json=push_response.json(),
        headers=auth_headers("dq:data_catalog:read"),
    )

    assert pull_response.status_code == 200
    snapshots = federated_metadata_registry_repository.list_federated_metadata_registry_exchange_snapshots(
        workspace_id="retail-banking",
        data_product_id="prod-1",
    )
    assert [snapshot.exchange_kind for snapshot in snapshots] == ["pull", "push"]
    assert snapshots[0].accepted is True
    assert snapshots[0].package_id == push_response.json()["package_id"]


def test_pull_metadata_registry_package_rejects_tampered_manifest(client, auth_headers) -> None:
    push_response = client.post(
        "/api/data-catalog/v1/metadata-registry/push",
        json={"workspace_id": "retail-banking", "data_product_id": "prod-1"},
        headers=auth_headers("dq:data_catalog:read"),
    )
    assert push_response.status_code == 200

    tampered_package = push_response.json()
    tampered_package["manifest"]["attribute_count"] += 1

    pull_response = client.post(
        "/api/data-catalog/v1/metadata-registry/pull",
        json=tampered_package,
        headers=auth_headers("dq:data_catalog:read"),
    )

    assert pull_response.status_code == 400
    assert pull_response.json()["detail"]["error"] == "federated_metadata_registry_invalid_package"


def test_pull_metadata_registry_package_records_rejected_snapshot(client, auth_headers, federated_metadata_registry_repository) -> None:
    push_response = client.post(
        "/api/data-catalog/v1/metadata-registry/push",
        json={"workspace_id": "retail-banking", "data_product_id": "prod-1"},
        headers=auth_headers("dq:data_catalog:read"),
    )
    assert push_response.status_code == 200

    tampered_package = push_response.json()
    tampered_package["manifest"]["attribute_count"] += 1

    pull_response = client.post(
        "/api/data-catalog/v1/metadata-registry/pull",
        json=tampered_package,
        headers=auth_headers("dq:data_catalog:read"),
    )

    assert pull_response.status_code == 400
    snapshots = federated_metadata_registry_repository.list_federated_metadata_registry_exchange_snapshots(
        workspace_id="retail-banking",
        data_product_id="prod-1",
    )
    assert snapshots[0].exchange_kind == "pull"
    assert snapshots[0].accepted is False
    assert snapshots[0].validation_error == "attribute_count does not match the exported attributes list"


def test_list_metadata_registry_exchanges_returns_audit_history(client, auth_headers) -> None:
    push_response = client.post(
        "/api/data-catalog/v1/metadata-registry/push",
        json={"workspace_id": "retail-banking", "data_product_id": "prod-1"},
        headers=auth_headers("dq:data_catalog:read"),
    )
    assert push_response.status_code == 200

    history_response = client.get(
        "/api/data-catalog/v1/metadata-registry/exchanges",
        params={"workspace_id": "retail-banking", "data_product_id": "prod-1"},
        headers=auth_headers("dq:data_catalog:read"),
    )

    assert history_response.status_code == 200
    history = history_response.json()
    assert len(history) == 1
    assert history[0]["exchange_kind"] == "push"
    assert history[0]["package_id"] == push_response.json()["package_id"]