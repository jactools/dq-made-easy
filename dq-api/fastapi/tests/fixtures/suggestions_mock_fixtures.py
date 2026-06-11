import pytest
from tests.fixtures.shared_fixtures import load_fixture_dict

@pytest.fixture
def mock_data_source_row() -> dict[str, object]:
    return load_fixture_dict("mock_data_source_row", {
        "id": "mock-data-id",
        "data_source_id": "mock-data",
        "name": "Mock Data",
        "source_type": "mock-data",
        "record_count": 1000,
    })
