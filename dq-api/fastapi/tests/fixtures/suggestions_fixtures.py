import pytest

from tests.fixtures.shared_fixtures import load_fixture_dict


def _require_fixture_data(fixture_name: str) -> dict[str, object]:
    payload = load_fixture_dict(fixture_name, {})
    if not payload:
        raise RuntimeError(
            f"Missing required fixture data for '{fixture_name}'. "
            f"Provide tests/fixtures/data/{fixture_name}.csv"
        )
    return payload


@pytest.fixture
def suggestions_auth_claims() -> dict[str, object]:
    return _require_fixture_data("suggestions_auth_claims")


@pytest.fixture
def suggestions_list_row() -> dict[str, object]:
    return _require_fixture_data("suggestions_list_row")


@pytest.fixture
def suggestions_rate_limit_payload() -> dict[str, object]:
    return _require_fixture_data("suggestions_rate_limit_payload")


@pytest.fixture
def suggestions_apply_payload() -> dict[str, object]:
    return _require_fixture_data("suggestions_apply_payload")


@pytest.fixture
def suggestions_apply_success_payload() -> dict[str, object]:
    return _require_fixture_data("suggestions_apply_success_payload")
