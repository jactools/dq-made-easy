import pytest
from tests.fixtures.suggestions_mock_fixtures import mock_data_source_row
from tests.fixtures.shared_fixtures import load_fixture_dict


@pytest.fixture
def admin_update_payload() -> dict[str, object]:
    return load_fixture_dict("admin_update_payload", {
        "email": "updated@example.com",
        "roles": ["viewer"],
        "workspaces": ["default"],
    })


@pytest.fixture
def oidc_existing_claims() -> dict[str, object]:
    return load_fixture_dict("oidc_existing_claims", {
        "sub": "oidc-existing",
        "email": "existing@example.com",
        "preferred_username": "existing",
    })


@pytest.fixture
def oidc_created_claims() -> dict[str, object]:
    return load_fixture_dict("oidc_created_claims", {
        "sub": "oidc-created",
        "email": "created@example.com",
        "preferred_username": "created",
        "name": "Created User",
    })


@pytest.fixture
def me_lookup_claims() -> dict[str, object]:
    return load_fixture_dict("me_lookup_claims", {"email": "person@example.com"})


@pytest.fixture
def me_update_payload() -> dict[str, object]:
    return load_fixture_dict("me_update_payload", {"preferences": {"display": {"theme": "light"}}})


@pytest.fixture
def admin_user_row() -> dict[str, object]:
    return load_fixture_dict("admin_user_row", {
        "id": "u1",
        "first_name": "Alice",
        "last_name": "Admin",
        "email": "a@example.com",
        "external_id": "ext-1",
        "preferences": '{"theme":"dark"}',
        "workspaces": "w1;w2",
    })


@pytest.fixture
def me_current_user_row() -> dict[str, object]:
    return load_fixture_dict("me_current_user_row", {
        "id": "u1",
        "first_name": "Alice",
        "last_name": "Admin",
        "email": "a@example.com",
        "preferences": '{"theme":"dark"}',
        "workspaces": "w1",
        "external_id": None,
    })


@pytest.fixture
def me_current_user_initial_row() -> dict[str, object]:
    return load_fixture_dict("me_current_user_initial_row", {
        "id": "u1",
        "first_name": "Alice",
        "last_name": "Admin",
        "email": "a@example.com",
        "preferences": None,
        "workspaces": "w1",
        "external_id": None,
    })


@pytest.fixture
def profiling_user_row():
    return load_fixture_dict("profiling_user_row", {
        "id": "user-profiling",
        "first_name": "Test",
        "last_name": "User",
        "email": "test@example.com",
        "external_id": "user-profiling",
    })
