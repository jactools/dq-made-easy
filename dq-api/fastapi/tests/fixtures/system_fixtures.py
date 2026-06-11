import pytest

from tests.fixtures.shared_fixtures import load_fixture_rows


@pytest.fixture
def system_info_rows() -> list[dict[str, object]]:
    return load_fixture_rows("system_info_rows", [
        {"info_key": "db_schema_version", "info_value": "2.5.0"},
        {"info_key": "db_schema_updated", "info_value": "2026-03-01T10:00:00Z"},
        {"info_key": "db_git_commit", "info_value": "abc123"},
    ])
