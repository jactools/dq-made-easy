import pytest

from tests.fixtures.shared_fixtures import load_fixture_dict, load_fixture_rows, load_fixture_scalar_list


@pytest.fixture
def testing_rule_ids() -> list[str]:
    return load_fixture_scalar_list("testing_rule_ids", ["rule-email-format", "rule-phone-format"])


@pytest.fixture
def testing_contains_rule_row() -> dict[str, object]:
    return load_fixture_dict("testing_contains_rule_row", {
        "id": "r1",
        "name": "Email contains",
        "dimension": "validity",
        "description": "desc",
        "expression": "email contains '@'",
    })


@pytest.fixture
def testing_version_entity_row() -> dict[str, object]:
    return load_fixture_dict("testing_version_entity_row", {"id": "v1", "version": 2, "data_object_id": "o1"})


@pytest.fixture
def testing_attribute_entity_rows() -> list[dict[str, object]]:
    return load_fixture_rows("testing_attribute_entity_rows", [
        {"id": "a1", "name": "email", "type": "text"},
        {"id": "a2", "name": "is_active", "type": "boolean"},
    ])


@pytest.fixture
def testing_batch_request_row() -> dict[str, object]:
    return load_fixture_dict("testing_batch_request_row", {
        "id": "b1",
        "rule_id": "r1",
        "requested_by": "u1",
        "requested_at": "2024-01-01T00:00:00+00:00",
        "test_data_config": {"sampleCount": 10},
        "status": "pending",
        "workspace": "w1",
        "completed_at": None,
        "proof_id": None,
    })


@pytest.fixture
def testing_proof_row() -> dict[str, object]:
    return load_fixture_dict("testing_proof_row", {
        "id": "p1",
        "rule_id": "r1",
        "test_date": "2024-01-01T00:00:00+00:00",
        "coverage": 95.5,
        "passed": True,
        "records_tested_count": 100,
        "failures_found": 5,
    })


@pytest.fixture
def testing_request_row() -> dict[str, object]:
    return load_fixture_dict("testing_request_row", {"id": "req-1"})


@pytest.fixture
def testing_version_row() -> dict[str, object]:
    return load_fixture_dict("testing_version_row", {"id": "dov-23", "version": 3, "data_object_id": "do-2"})


@pytest.fixture
def testing_attribute_rows() -> list[dict[str, object]]:
    return load_fixture_rows("testing_attribute_rows", [
        {"id": "attr-201", "name": "email", "type": "string"},
        {"id": "attr-202", "name": "status", "type": "string"},
    ])


@pytest.fixture
def testing_rule_row() -> dict[str, object]:
    return load_fixture_dict("testing_rule_row", {
        "id": "rule-email-format",
        "name": "Email Format",
        "dimension": "validity",
        "description": "Valid email pattern",
        "expression": "email contains '@'",
    })


@pytest.fixture
def testing_regex_rule_row() -> dict[str, object]:
    return load_fixture_dict("testing_regex_rule_row", {
        "id": "rule-email-format",
        "name": "Email Format Regex",
        "dimension": "validity",
        "description": "Valid email regex pattern",
        "expression": "email ~ '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}$'",
    })


@pytest.fixture
def testing_status_rule_row() -> dict[str, object]:
    return load_fixture_dict("testing_status_rule_row", {
        "id": "rule-status-active",
        "name": "Status Active",
        "dimension": "validity",
        "description": "Status must contain active",
        "expression": "status contains 'active'",
    })


@pytest.fixture
def testing_status_sample_data() -> list[dict[str, object]]:
    return load_fixture_rows(
        "testing_status_sample_data",
        [{"status": "active"}, {"status": "inactive"}, {"email": "missing-status@example.com"}],
    )


@pytest.fixture
def testing_proof_payload() -> dict[str, object]:
    return load_fixture_dict("testing_proof_payload", {
        "coverage": 0.95,
        "passed": True,
        "recordsTestedCount": 100,
        "failuresFound": 5,
        "proofData": {"suite": "smoke"},
    })


@pytest.fixture
def testing_sample_data() -> list[dict[str, object]]:
    return load_fixture_rows("testing_sample_data", [{"email": "valid@example.com"}, {"email": "invalid_email"}])
