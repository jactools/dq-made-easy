import pytest

from tests.fixtures.shared_fixtures import load_fixture_dict


@pytest.fixture
def approval_create_payload() -> dict[str, object]:
    return load_fixture_dict("approval_create_payload", {
        "rule_id": "rule-new",
        "workspace_id": "default",
        "status": "pending",
    })


@pytest.fixture
def approval_status_update_payload() -> dict[str, object]:
    return load_fixture_dict("approval_status_update_payload", {"status": "approved"})


@pytest.fixture
def approval_pg_row() -> dict[str, object]:
    return load_fixture_dict("approval_pg_row", {
        "id": "approval-1",
        "business_key": "approval-1",
        "ruleid": "rule-1",
        "effectivestatus": "activated",
        "status": "pending",
        "requesterid": "user-1",
        "workspace_id": "default",
    })


@pytest.fixture
def approval_requester_only_row() -> dict[str, object]:
    return load_fixture_dict("approval_requester_only_row", {"id": "approval-1", "business_key": "approval-1", "requesterid": "requester"})


@pytest.fixture
def approval_created_row() -> dict[str, object]:
    return load_fixture_dict("approval_created_row", {
        "id": "approval-1",
        "business_key": "approval-1",
        "ruleid": "rule-new",
        "effectivestatus": "activated",
        "status": "pending",
        "requesterid": "user-admin",
        "workspace_id": "default",
    })
