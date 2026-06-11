import pytest

from tests.fixtures.shared_fixtures import load_fixture_dict, load_fixture_rows


@pytest.fixture
def app_config_update_payload() -> dict[str, object]:
    return load_fixture_dict("app_config_update_payload", {
        "maintenanceMode": True,
        "maintenanceMessage": "scheduled",
        "default_page_size": 40,
        "exceptionFactJitRoleMaxDurationMinutes": 180,
        "exceptionFactJitRequestTimeoutMinutes": 15,
    })


@pytest.fixture
def app_config_kv_rows() -> list[dict[str, object]]:
    return load_fixture_rows("app_config_kv_rows", [
        {"config_key": "api_version", "config_value": "v2", "value_type": "string"},
        {"config_key": "default_page_size", "config_value": "50", "value_type": "number"},
        {"config_key": "enable_analytics", "config_value": "false", "value_type": "boolean"},
    ])


@pytest.fixture
def app_config_legacy_row() -> dict[str, object]:
    return load_fixture_dict("app_config_legacy_row", {
        "api_version": "v3",
        "default_page_size": "25",
        "enable_export": "false",
        "maintenance_message": "scheduled",
    })


@pytest.fixture
def app_config_alt_kv_rows() -> list[dict[str, object]]:
    return load_fixture_rows("app_config_alt_kv_rows", [
        {"configKey": "maintenance_message", "configValue": "planned", "valueType": "string"},
        {"configKey": "enable_export", "value": "true", "valueType": "boolean"},
        {"configKey": "unknown_setting", "configValue": "ignored", "valueType": "string"},
    ])


@pytest.fixture
def app_config_repo_merged() -> dict[str, object]:
    return load_fixture_dict(
        "app_config_repo_merged",
        {
            "maintenanceMode": True,
            "defaultPageSize": 40,
            "exceptionFactJitRoleMaxDurationMinutes": 180,
            "exceptionFactJitRequestTimeoutMinutes": 15,
        },
    )


@pytest.fixture
def app_config_enable_maintenance_payload() -> dict[str, object]:
    return load_fixture_dict("app_config_enable_maintenance_payload", {"maintenanceMode": True})
