import pytest

from app.core.dependencies import get_master_data_repository
from app.infrastructure.repositories.in_memory_master_data_repository import InMemoryMasterDataRepository
from app.main import app


@pytest.fixture(autouse=True)
def isolated_master_data_dependencies() -> InMemoryMasterDataRepository:
    repository = InMemoryMasterDataRepository()
    app.dependency_overrides[get_master_data_repository] = lambda: repository
    yield repository
    app.dependency_overrides.pop(get_master_data_repository, None)


def test_master_records_return_rows(client, auth_headers) -> None:
    response = client.get(
        "/api/master-data/v1/master-records",
        headers=auth_headers("dq:rules:read"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["pagination"]["total"] == 4
    assert payload["data"][0]["id"] == "mr-001"
    assert payload["data"][0]["resolution_status"] == "golden"


def test_master_records_can_filter_by_workspace(client, auth_headers) -> None:
    response = client.get(
        "/api/master-data/v1/master-records?workspace_id=corporate-banking",
        headers=auth_headers("dq:rules:read"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["pagination"]["total"] == 2
    assert all(row["workspace_id"] == "corporate-banking" for row in payload["data"])
