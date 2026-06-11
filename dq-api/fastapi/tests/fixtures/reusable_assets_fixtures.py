import pytest

from tests.fixtures.shared_fixtures import load_fixture_dict
from tests.fixtures.shared_fixtures import load_fixture_rows


def _require_fixture_data(fixture_name: str) -> dict[str, object]:
    payload = load_fixture_dict(fixture_name, {})
    if not payload:
        raise RuntimeError(
            f"Missing required fixture data for '{fixture_name}'. "
            f"Provide tests/fixtures/data/{fixture_name}.csv"
        )
    return payload


def _require_fixture_rows(fixture_name: str) -> list[dict[str, object]]:
    rows = load_fixture_rows(fixture_name, [])
    if not rows:
        raise RuntimeError(
            f"Missing required fixture rows for '{fixture_name}'. "
            f"Provide tests/fixtures/data/{fixture_name}.csv"
        )
    return rows


@pytest.fixture
def reusable_filter_create_payload() -> dict[str, object]:
    return _require_fixture_data("reusable_filter_create_payload")


@pytest.fixture
def reusable_filter_update_payload() -> dict[str, object]:
    return _require_fixture_data("reusable_filter_update_payload")


@pytest.fixture
def reusable_filter_validation_cases() -> list[dict[str, str]]:
    return [
        {
            "expression": str(row["expression"]),
            "expected_error": str(row["expected_error"]),
        }
        for row in _require_fixture_rows("reusable_filter_validation_cases")
    ]


@pytest.fixture
def reusable_join_definition() -> dict[str, object]:
    return _require_fixture_data("reusable_join_definition")


@pytest.fixture
def reusable_join_update_payload() -> dict[str, object]:
    return _require_fixture_data("reusable_join_update_payload")


@pytest.fixture
def reusable_join_json_string(reusable_join_definition: dict[str, object]) -> str:
    import json

    return json.dumps(reusable_join_definition)
