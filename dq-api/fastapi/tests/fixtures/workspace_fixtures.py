import pytest

from tests.fixtures.shared_fixtures import load_fixture_dict


@pytest.fixture
def workspace_create_payload() -> dict[str, object]:
    return load_fixture_dict("workspace_create_payload", {
        "id": "workspace-unit-test",
        "name": "Unit Test Workspace",
        "description": "Created in unit test",
    })


@pytest.fixture
def workspace_duplicate_payload() -> dict[str, object]:
    return load_fixture_dict("workspace_duplicate_payload", {"id": "default", "name": "Duplicate"})


@pytest.fixture
def workspace_overflow_payload() -> dict[str, object]:
    return load_fixture_dict("workspace_overflow_payload", {"id": "workspace-overflow"})


@pytest.fixture
def workspace_pg_create_payload() -> dict[str, object]:
    return load_fixture_dict("workspace_pg_create_payload", {"id": "workspace-pg", "name": "PG Workspace"})


@pytest.fixture
def workspace_pg_update_payload() -> dict[str, object]:
    return load_fixture_dict("workspace_pg_update_payload", {"name": "Default Updated"})


@pytest.fixture
def workspace_pg_default_row() -> dict[str, object]:
    return load_fixture_dict(
        "workspace_pg_default_row",
        {"id": "default", "name": "Default", "description": "Default workspace"},
    )


@pytest.fixture
def workspace_pg_desc_row() -> dict[str, object]:
    return load_fixture_dict("workspace_pg_desc_row", {"id": "default", "name": "Default", "description": "Desc"})
