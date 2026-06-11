import pytest

from tests.fixtures.shared_fixtures import load_fixture_dict, load_fixture_rows, load_fixture_tuple_rows


@pytest.fixture
def data_catalog_row() -> dict[str, object]:
    return load_fixture_dict("data_catalog_row", {"id": "row-1"})


@pytest.fixture
def data_catalog_product_row() -> dict[str, object]:
    return load_fixture_dict("data_catalog_product_row", {
        "id": "p1",
        "name": "Product",
        "description": "Desc",
        "owner": "owner",
        "created_at": "2024-01-01T00:00:00+00:00",
        "icon": "db",
        "workspace_id": "w1",
    })


@pytest.fixture
def data_catalog_set_row() -> dict[str, object]:
    return load_fixture_dict("data_catalog_set_row", {
        "id": "s1",
        "product_id": "p1",
        "name": "Set",
        "description": "Desc",
        "owner": "owner",
        "created_at": "2024-01-02T00:00:00+00:00",
        "workspace_id": "w1",
    })


@pytest.fixture
def data_catalog_rule_attribute_row() -> dict[str, object]:
    return load_fixture_dict("data_catalog_rule_attribute_row", {"rule_id": "r1", "attribute_id": "a1"})


@pytest.fixture
def data_catalog_add_entries() -> list[dict[str, object]]:
    return load_fixture_rows("data_catalog_add_entries", [
        {"ruleId": "r1", "attributeId": "a1"},
        {"ruleId": "r2", "attributeId": "a2"},
        {"ruleId": "r3"},
    ])


@pytest.fixture
def data_catalog_object_version_row() -> dict[str, object]:
    return load_fixture_dict("data_catalog_object_version_row", {
        "id": "v1",
        "data_object_id": "o1",
        "version": 3,
        "created_at": "2024-01-01T00:00:00+00:00",
        "schema_hash": "abc",
        "attribute_count": 7,
        "storage_uri": None,
        "storage_format": None,
        "storage_options_json": {
            "retention_policy": {
                "exception_fact_retention_days": 30,
                "exception_fact_archive_retention_days": 90,
                "exception_analytics_projection_retention_days": 365,
                "exception_fact_purge_batch_size": 1000,
            }
        },
    })


@pytest.fixture
def data_catalog_attribute_counts_rows() -> list[tuple[str | None, int]]:
    return load_fixture_tuple_rows(
        "data_catalog_attribute_counts_rows",
        ("attribute_id", "rule_count"),
        [("a1", 2), ("a2", 5), (None, 1)],
    )


@pytest.fixture
def data_catalog_delivery_row() -> dict[str, object]:
    return load_fixture_dict("data_catalog_delivery_row", {
        "id": "d1",
        "data_object_id": "o1",
        "data_object_version_id": "v1",
        "version": 1,
        "timestamp": "2024-01-01T00:00:00+00:00",
        "layer": "standardized",
        "delivery_location": "standardized/bucket/schema/object/v1/LOAD_DTS=20240101T000000000Z",
        "record_count": 100,
        "size_bytes": 200,
        "status": "completed",
        "attributes_count": 8,
    })
