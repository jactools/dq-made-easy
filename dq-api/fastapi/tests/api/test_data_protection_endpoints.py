from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.dependencies import get_admin_repository
from app.core.dependencies import get_data_catalog_repository
from app.core.dependencies import get_data_protection_repository
from app.infrastructure.repositories.in_memory_admin_repository import InMemoryAdminRepository
from app.infrastructure.repositories.in_memory_data_catalog_repository import InMemoryDataCatalogRepository
from app.infrastructure.repositories.in_memory_data_protection_repository import InMemoryDataProtectionRepository
from app.main import app


@pytest.fixture(autouse=True)
def isolated_data_protection_dependencies() -> tuple[
    InMemoryAdminRepository,
    InMemoryDataCatalogRepository,
    InMemoryDataProtectionRepository,
]:
    admin_repository = InMemoryAdminRepository()
    data_catalog_repository = InMemoryDataCatalogRepository()
    data_protection_repository = InMemoryDataProtectionRepository()
    app.dependency_overrides[get_admin_repository] = lambda: admin_repository
    app.dependency_overrides[get_data_catalog_repository] = lambda: data_catalog_repository
    app.dependency_overrides[get_data_protection_repository] = lambda: data_protection_repository

    yield admin_repository, data_catalog_repository, data_protection_repository

    app.dependency_overrides.pop(get_admin_repository, None)
    app.dependency_overrides.pop(get_data_catalog_repository, None)
    app.dependency_overrides.pop(get_data_protection_repository, None)


def test_encryption_keys_list_and_create(client: TestClient, auth_headers) -> None:
    response = client.get("/system/v1/encryption-keys", headers=auth_headers("dq:config:manage"))

    assert response.status_code == 200
    initial_payload = response.json()
    assert initial_payload
    assert initial_payload[0]["key_name"] == "Default app key"

    create_response = client.post(
        "/system/v1/encryption-keys",
        headers=auth_headers("dq:config:manage"),
        json={
            "key_name": "Workspace protection key",
            "key_scope": "workspace",
            "workspace_id": "retail-banking",
            "key_algorithm": "fernet",
            "key_material": "secret-workspace-key",
            "is_active": True,
        },
    )

    assert create_response.status_code == 200
    created_payload = create_response.json()
    assert created_payload["key_name"] == "Workspace protection key"
    assert created_payload["key_scope"] == "workspace"
    assert created_payload["workspace_id"] == "retail-banking"
    assert created_payload["key_algorithm"] == "fernet"
    assert created_payload["is_active"] is True
    assert "key_material" not in created_payload

    refreshed_response = client.get("/system/v1/encryption-keys", headers=auth_headers("dq:config:manage"))
    assert refreshed_response.status_code == 200
    assert len(refreshed_response.json()) == len(initial_payload) + 1


def test_attribute_protection_update_persists_masking_and_encryption(
    client: TestClient,
    auth_headers,
    isolated_data_protection_dependencies,
) -> None:
    _, data_catalog_repository, data_protection_repository = isolated_data_protection_dependencies
    attribute = data_catalog_repository.list_attributes_catalog()[0]
    encryption_key = data_protection_repository.list_encryption_keys()[0]

    response = client.put(
        f"/data-catalog/v1/attributes-catalog/{attribute.id}/protection",
        headers=auth_headers("dq:config:manage"),
        json={
            "masking_method": "redact",
            "encryption_required": True,
            "encryption_key_id": encryption_key.id,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["masking_method"] == "redact"
    assert payload["encryption_required"] is True
    assert payload["encryption_key_id"] == encryption_key.id
    assert payload["protection_configured_by"] == "user-admin"
