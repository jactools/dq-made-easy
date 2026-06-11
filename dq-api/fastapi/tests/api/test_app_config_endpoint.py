import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.core.config import get_settings
from app.core.dependencies import get_app_config_repository
from app.infrastructure.repositories import InMemoryAppConfigRepository
from app.main import app


@pytest.fixture(autouse=True)
def app_config_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DQ_DB_LOCAL_URL", "")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    repository = InMemoryAppConfigRepository()
    monkeypatch.setattr(main_module, "get_app_config_repository", lambda: repository)
    monkeypatch.setattr(main_module, "bootstrap_connector_registry", lambda: None)
    app.dependency_overrides[get_app_config_repository] = lambda: repository
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_app_config_requires_auth_when_sso_enabled(client) -> None:
    response = client.get("/api/system/v1/app-config")

    assert response.status_code == 401


def test_app_config_returns_defaults(client, auth_headers) -> None:
    response = client.get("/system/v1/app-config", headers=auth_headers("dq:admin:read"))

    assert response.status_code == 200
    payload = response.json()
    assert payload["style_package"] == "data-web-css"
    assert payload["api_version"] == "v1"
    assert payload["default_page_size"] == 20
    assert payload["feature_rule_dsl_v2"] is False
    assert payload["exception_fact_jit_role_max_duration_minutes"] == 240
    assert payload["exception_fact_jit_request_timeout_minutes"] == 30
    assert payload["session_timeout_minutes"] == 60
    assert payload["agent_session_timeout_minutes"] == 60
    assert payload["max_tool_calls_per_session"] == 100
    assert payload["exception_fact_retention_days"] == 30
    assert payload["exception_fact_archive_retention_days"] == 180
    assert payload["exception_analytics_projection_retention_days"] == 365
    assert payload["exception_fact_purge_batch_size"] == 5000
    assert payload["alerting_slack_webhook_url"] == ""
    assert payload["alerting_pagerduty_routing_key"] == ""
    assert payload["playground_source_bundle_policy"] == {
        "default_allow": True,
        "allowed_bundle_ids": [],
        "blocked_bundle_ids": [],
    }
    assert payload["agent_platform_allowlist"] == ["mistral_ai", "microsoft_copilot"]
    assert payload["agent_access_policy"] == {
        "default_action": "deny",
        "allowed_agents": [],
    }
    assert payload["sso_enabled"] is True
    assert payload["sso_issuer"] == "http://keycloak.local:8080/realms/jaccloud"
    assert payload["sso_client_id"] == "dq-rules-ui"
    assert payload["assistance_request_itsm_auth_token"] == ""
    assert "sessionTimeoutMinutes" not in payload
    assert "assistanceRequestMode" not in payload


def test_put_app_config_updates_values(client, auth_headers) -> None:
    response = client.put(
        "/api/system/v1/app-config",
        headers=auth_headers("dq:config:manage"),
        json={
            "style_package": "astrowind",
            "maintenance_mode": True,
            "maintenance_message": "planned maintenance",
            "agent_platform_allowlist": ["mistral_ai", "slack"],
            "agent_access_policy": {
                "default_action": "deny",
                "allowed_agents": [
                    {
                        "agent_type": "mcp",
                        "agent_source": "dq-made-easy-mcp",
                    }
                ],
            },
            "default_page_size": 40,
            "exception_fact_retention_days": 45,
            "exception_fact_archive_retention_days": 365,
            "exception_analytics_projection_retention_days": 730,
            "exception_fact_purge_batch_size": 2500,
            "exception_fact_jit_role_max_duration_minutes": 180,
            "exception_fact_jit_request_timeout_minutes": 45,
            "agent_session_timeout_minutes": 75,
            "max_tool_calls_per_session": 250,
            "feature_rule_suggestions": True,
            "feature_rule_dsl_v2": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["style_package"] == "astrowind"
    assert payload["maintenance_mode"] is True
    assert payload["maintenance_message"] == "planned maintenance"
    assert payload["agent_platform_allowlist"] == ["mistral_ai", "slack"]
    assert payload["agent_access_policy"]["default_action"] == "deny"
    assert payload["agent_access_policy"]["allowed_agents"][0]["agent_source"] == "dq-made-easy-mcp"
    assert payload["default_page_size"] == 40
    assert payload["exception_fact_retention_days"] == 45
    assert payload["exception_fact_archive_retention_days"] == 365
    assert payload["exception_analytics_projection_retention_days"] == 730
    assert payload["exception_fact_purge_batch_size"] == 2500
    assert payload["exception_fact_jit_role_max_duration_minutes"] == 180
    assert payload["exception_fact_jit_request_timeout_minutes"] == 45
    assert payload["agent_session_timeout_minutes"] == 75
    assert payload["max_tool_calls_per_session"] == 250
    assert payload["feature_rule_suggestions"] is True
    assert payload["feature_rule_dsl_v2"] is True
    assert payload["sso_enabled"] is True

    get_response = client.get("/system/v1/app-config", headers=auth_headers("dq:admin:read"))

    assert get_response.status_code == 200
    assert get_response.json()["style_package"] == "astrowind"


def test_put_app_config_redacts_support_email_password(client, auth_headers) -> None:
    response = client.put(
        "/api/system/v1/app-config",
        headers=auth_headers("dq:config:manage"),
        json={
            "maintenance_mode": True,
            "support_email_smtp_password": "super-secret-password",
            "assistance_request_itsm_auth_token": "zammad-api-token",
            "alerting_slack_webhook_url": "https://hooks.slack.com/services/T000/B000/XXXXX",
            "alerting_pagerduty_routing_key": "pagerduty-routing-key",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["maintenance_mode"] is True
    assert payload["support_email_smtp_password"] == ""
    assert payload["assistance_request_itsm_auth_token"] == ""
    assert payload["alerting_slack_webhook_url"] == ""
    assert payload["alerting_pagerduty_routing_key"] == ""


def test_put_app_config_requires_manage_scope(client, auth_headers) -> None:
    response = client.put(
        "/api/system/v1/app-config",
        headers=auth_headers("dq:rules:read"),
        json={"maintenance_mode": True},
    )

    assert response.status_code == 403
