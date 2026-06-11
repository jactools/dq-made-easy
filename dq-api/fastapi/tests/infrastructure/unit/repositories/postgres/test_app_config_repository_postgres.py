from app.core import dependencies
from app.core.config import get_settings
import os
import app.infrastructure.repositories.postgres_app_config_repository as appcfg_mod
import app.infrastructure.repositories.app_config_defaults as appcfg_defaults_mod
from app.infrastructure.repositories.postgres_app_config_repository import PostgresAppConfigRepository
from app.infrastructure.repositories.app_config_defaults import serialize_app_config_value
from app.infrastructure.security import EntityFieldEncryptor
from types import SimpleNamespace


APP_CONFIG_ENCRYPTION_TEST_KEY = "i0aU2BE0dzqEVAWxfEsvffw5zw93FjFZrr24RPVyo8c="


class _Ctx:
    def __init__(self, session):
        self.session = session

    def __enter__(self):
        return self.session

    def __exit__(self, exc_type, exc, tb):
        return False


def test_postgres_app_config_parses_key_value_rows(
    postgres_dsn: str,
    app_config_kv_rows: list[dict[str, object]],
    clone_payload,
) -> None:
    repository = PostgresAppConfigRepository(postgres_dsn)
    repository._fetch_all = lambda: clone_payload({"rows": app_config_kv_rows})["rows"]  # type: ignore[method-assign]

    config = repository.get_app_config()

    assert config.apiVersion == "v2"
    assert config.defaultPageSize == 50
    assert config.enableAnalytics is False


def test_postgres_app_config_returns_defaults_when_no_rows(postgres_dsn: str) -> None:
    repository = PostgresAppConfigRepository(postgres_dsn)
    repository._fetch_all = lambda: []  # type: ignore[method-assign]

    config = repository.get_app_config()

    assert config.apiVersion == "v1"
    assert config.defaultPageSize == 20
    assert config.exceptionFactJitRoleMaxDurationMinutes == 240
    # Test environment enables SSO via env overrides (see tests/conftest.py).
    assert config.ssoEnabled is True


def test_postgres_app_config_parses_alternate_key_value_fields(
    postgres_dsn: str,
    app_config_alt_kv_rows: list[dict[str, object]],
    clone_payload,
) -> None:
    repository = PostgresAppConfigRepository(postgres_dsn)
    repository._fetch_all = lambda: clone_payload({"rows": app_config_alt_kv_rows})["rows"]  # type: ignore[method-assign]

    config = repository.get_app_config()

    assert config.maintenanceMessage == "planned"
    assert config.enableExport is True


def test_postgres_app_config_coercion_helpers_cover_json_and_invalid_number(postgres_dsn: str) -> None:
    repository = PostgresAppConfigRepository(postgres_dsn)

    assert repository._coerce_value("not-a-number", "number") is None
    assert repository._coerce_value("true", "boolean") is True
    assert repository._coerce_value('{"enabled": true}', "json") == {"enabled": True}
    assert repository._coerce_value("[{'checkId': 'DQ1_EMPTY_EXPRESSION', 'enabled': True}]", "json") == [
        {"checkId": "DQ1_EMPTY_EXPRESSION", "enabled": True}
    ]
    assert repository._coerce_value("{oops", "json") is None


def test_postgres_app_config_parses_legacy_validation_policies_string(postgres_dsn: str) -> None:
    repository = PostgresAppConfigRepository(postgres_dsn)
    repository._fetch_all = lambda: [  # type: ignore[method-assign]
        {
            "config_key": "validation_policies",
            "config_value": "[{'checkId': 'DQ1_EMPTY_EXPRESSION', 'enabled': True, 'severityOverride': None, 'scope': 'all'}]",
            "value_type": "json",
        }
    ]

    config = repository.get_app_config()

    assert config.validationPolicies is not None
    assert len(config.validationPolicies) == 1
    assert config.validationPolicies[0].checkId == "DQ1_EMPTY_EXPRESSION"
    assert config.validationPolicies[0].enabled is True


def test_postgres_app_config_ignores_legacy_string_type_for_validation_policies(postgres_dsn: str) -> None:
    repository = PostgresAppConfigRepository(postgres_dsn)
    repository._fetch_all = lambda: [  # type: ignore[method-assign]
        {
            "config_key": "validation_policies",
            "config_value": "[{'checkId': 'DQ1_EMPTY_EXPRESSION', 'enabled': True, 'severityOverride': None, 'scope': 'all'}]",
            "value_type": "string",
        }
    ]

    config = repository.get_app_config()

    assert config.validationPolicies is not None
    assert config.validationPolicies[0].scope == "all"


def test_serialize_app_config_value_emits_json_for_validation_policies() -> None:
    payload = [{"checkId": "DQ1_EMPTY_EXPRESSION", "enabled": True, "severityOverride": None, "scope": "all"}]

    serialized = serialize_app_config_value(payload, "json")

    assert serialized == '[{"checkId": "DQ1_EMPTY_EXPRESSION", "enabled": true, "severityOverride": null, "scope": "all"}]'


def test_postgres_app_config_builds_upsert_queries_for_updates(
    postgres_dsn: str,
    app_config_repo_merged: dict[str, object],
    clone_payload,
) -> None:
    repository = PostgresAppConfigRepository(postgres_dsn)
    captured: list[tuple[str, str, str]] = []

    repository._upsert = lambda key, value, kind: captured.append((key, value, kind)) or None  # type: ignore[method-assign]
    repository.get_app_config = lambda: clone_payload(app_config_repo_merged)  # type: ignore[method-assign]

    result = repository.set_app_config(clone_payload(app_config_repo_merged))

    assert result == app_config_repo_merged
    assert ("maintenance_mode", "true", "boolean") in captured
    assert ("default_page_size", "40", "number") in captured
    assert ("exception_fact_jit_role_max_duration_minutes", "180", "number") in captured
    assert ("exception_fact_jit_request_timeout_minutes", "15", "number") in captured


def test_postgres_app_config_encrypts_support_password_on_write_and_decrypts_on_read(
    postgres_dsn: str,
    app_config_repo_merged: dict[str, object],
    clone_payload,
    monkeypatch,
) -> None:
    monkeypatch.setenv("APP_CONFIG_ENCRYPTION_KEY", APP_CONFIG_ENCRYPTION_TEST_KEY)
    repository = PostgresAppConfigRepository(postgres_dsn)
    encryptor = EntityFieldEncryptor.from_key(APP_CONFIG_ENCRYPTION_TEST_KEY)
    captured: list[tuple[str, str | None, str]] = []

    repository._upsert = lambda key, value, kind: captured.append((key, value, kind)) or None  # type: ignore[method-assign]

    payload = clone_payload(app_config_repo_merged)
    payload["supportEmailSmtpPassword"] = "super-secret-password"
    payload["assistanceRequestItsmAuthToken"] = "zammad-api-token"
    payload["alertingSlackWebhookUrl"] = "https://hooks.slack.com/services/T000/B000/XXXXX"
    payload["alertingPagerDutyRoutingKey"] = "pagerduty-routing-key"
    repository.get_app_config = lambda: clone_payload(payload)  # type: ignore[method-assign]

    result = repository.set_app_config(payload)

    assert result["supportEmailSmtpPassword"] == "super-secret-password"
    assert result["assistanceRequestItsmAuthToken"] == "zammad-api-token"
    assert result["alertingSlackWebhookUrl"] == "https://hooks.slack.com/services/T000/B000/XXXXX"
    assert result["alertingPagerDutyRoutingKey"] == "pagerduty-routing-key"

    encrypted_password = next(value for key, value, _ in captured if key == "support_email_smtp_password")
    assert encrypted_password is not None
    assert encrypted_password.startswith("enc:v1:")
    assert encrypted_password != "super-secret-password"

    encrypted_token = next(value for key, value, _ in captured if key == "assistance_request_itsm_auth_token")
    assert encrypted_token is not None
    assert encrypted_token.startswith("enc:v1:")
    assert encrypted_token != "zammad-api-token"

    encrypted_slack = next(value for key, value, _ in captured if key == "alerting_slack_webhook_url")
    assert encrypted_slack is not None
    assert encrypted_slack.startswith("enc:v1:")
    assert encrypted_slack != "https://hooks.slack.com/services/T000/B000/XXXXX"

    encrypted_pagerduty = next(value for key, value, _ in captured if key == "alerting_pagerduty_routing_key")
    assert encrypted_pagerduty is not None
    assert encrypted_pagerduty.startswith("enc:v1:")
    assert encrypted_pagerduty != "pagerduty-routing-key"

    repository._fetch_all = lambda: [  # type: ignore[method-assign]
        {
            "config_key": "support_email_smtp_password",
            "config_value": encryptor.encrypt_value("super-secret-password"),
            "value_type": "string",
        },
        {
            "config_key": "assistance_request_itsm_auth_token",
            "config_value": encryptor.encrypt_value("zammad-api-token"),
            "value_type": "string",
        },
        {
            "config_key": "alerting_slack_webhook_url",
            "config_value": encryptor.encrypt_value("https://hooks.slack.com/services/T000/B000/XXXXX"),
            "value_type": "string",
        },
        {
            "config_key": "alerting_pagerduty_routing_key",
            "config_value": encryptor.encrypt_value("pagerduty-routing-key"),
            "value_type": "string",
        }
    ]
    repository.get_app_config = lambda: PostgresAppConfigRepository.get_app_config(repository)  # type: ignore[method-assign]

    config = repository.get_app_config()

    assert config.supportEmailSmtpPassword == "super-secret-password"
    assert config.assistanceRequestItsmAuthToken == "zammad-api-token"
    assert config.alertingSlackWebhookUrl == "https://hooks.slack.com/services/T000/B000/XXXXX"
    assert config.alertingPagerDutyRoutingKey == "pagerduty-routing-key"


def test_postgres_app_config_requires_encryption_key(monkeypatch, postgres_dsn: str) -> None:
    monkeypatch.delenv("APP_CONFIG_ENCRYPTION_KEY", raising=False)

    try:
        PostgresAppConfigRepository(postgres_dsn)
    except RuntimeError as error:
        assert "APP_CONFIG_ENCRYPTION_KEY" in str(error)
    else:
        raise AssertionError("Expected RuntimeError when APP_CONFIG_ENCRYPTION_KEY is missing")


def test_postgres_app_config_raises_on_write_failure(
    postgres_dsn: str,
    app_config_enable_maintenance_payload: dict[str, object],
) -> None:
    repository = PostgresAppConfigRepository(postgres_dsn)
    repository._upsert = lambda key, value, kind: (_ for _ in ()).throw(RuntimeError("database unavailable"))  # type: ignore[method-assign]

    try:
        repository.set_app_config(app_config_enable_maintenance_payload)
    except RuntimeError as error:
        assert str(error) == "database unavailable"
    else:
        raise AssertionError("Expected RuntimeError for app-config write failure")


def test_app_config_dependency_uses_postgres_with_database(monkeypatch, postgres_dependency_url: str) -> None:
    monkeypatch.setenv("DQ_DB_LOCAL_URL", postgres_dependency_url)
    get_settings.cache_clear()
    dependencies._get_postgres_app_config_repository.cache_clear()

    repository = dependencies.get_app_config_repository()

    assert repository.__class__.__name__ == "PostgresAppConfigRepository"

    # If a higher-scope test set DQ_DB_LOCAL_URL (e.g. tests/conftest), preserve it.
    if os.environ.get("DQ_DB_LOCAL_URL") is not None:
        monkeypatch.setenv("DQ_DB_LOCAL_URL", os.environ["DQ_DB_LOCAL_URL"])
    else:
        monkeypatch.delenv("DQ_DB_LOCAL_URL", raising=False)
    get_settings.cache_clear()
    dependencies._get_postgres_app_config_repository.cache_clear()


def test_postgres_app_config_coerce_value_additional_branches(postgres_dsn: str) -> None:
    repository = PostgresAppConfigRepository(postgres_dsn)

    assert repository._coerce_value(True, "boolean") is True
    assert repository._coerce_value("yes", "boolean") is True
    assert repository._coerce_value("no", "boolean") is False
    assert repository._coerce_value({"k": "v"}, "json") == {"k": "v"}
    assert repository._coerce_value(123, "json") == 123
    assert repository._coerce_value("raw", "string") == "raw"


def test_postgres_app_config_coerce_json_non_string_passthrough(postgres_dsn: str, monkeypatch) -> None:
    repository = PostgresAppConfigRepository(postgres_dsn)

    def _boom(_value):
        raise ValueError("bad json")

    monkeypatch.setattr(appcfg_mod.json, "loads", _boom)
    assert repository._coerce_value(10, "json") == 10


def test_postgres_app_config_get_supports_value_field_fallback(postgres_dsn: str) -> None:
    repository = PostgresAppConfigRepository(postgres_dsn)
    repository._fetch_all = lambda: [  # type: ignore[method-assign]
        {
            "config_key": "api_version",
            "value": "v3",
            "value_type": "string",
        },
        {
            "config_key": "default_page_size",
            "value": "30",
            "value_type": "number",
        },
    ]

    config = repository.get_app_config()

    assert config.apiVersion == "v3"
    assert config.defaultPageSize == 30


def test_postgres_app_config_parses_alert_routing_policy_as_json(postgres_dsn: str) -> None:
    repository = PostgresAppConfigRepository(postgres_dsn)
    repository._fetch_all = lambda: [  # type: ignore[method-assign]
        {
            "config_key": "alert_routing_policy",
            "config_value": "{'deliveryTarget': 'app', 'channels': ['in_app'], 'mandatoryCategories': [], 'mandatoryRoles': []}",
            "value_type": "string",
        }
    ]

    config = repository.get_app_config()

    assert config.alertRoutingPolicy == {
        "deliveryTarget": "app",
        "channels": ["in_app"],
        "mandatoryCategories": [],
        "mandatoryRoles": [],
    }


def test_postgres_app_config_fetch_all_and_upsert_session_paths(monkeypatch) -> None:
    repository = PostgresAppConfigRepository("postgresql://example")
    rows = [
        SimpleNamespace(config_key="api_version", config_value="v1", value_type="string"),
        SimpleNamespace(config_key="enable_export", config_value="true", value_type="boolean"),
    ]
    state = {"executed": 0, "commits": 0}

    class _FakeStmt:
        class _Excluded:
            config_value = "v2"
            value_type = "string"

        excluded = _Excluded()

        def values(self, **_kwargs):
            return self

        def on_conflict_do_update(self, **_kwargs):
            return self

    class _Session:
        def execute(self, _stmt):
            state["executed"] += 1
            return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: rows))

        def commit(self):
            state["commits"] += 1

    monkeypatch.setattr(appcfg_mod, "session_scope", lambda _dsn: _Ctx(_Session()))
    monkeypatch.setattr(appcfg_mod, "insert", lambda _model: _FakeStmt())

    fetched = repository._fetch_all()
    repository._upsert("api_version", "v2", "string")

    assert fetched[0]["config_key"] == "api_version"
    assert state["executed"] >= 2
    assert state["commits"] == 1


def test_app_config_default_env_helpers_and_sso_overrides(monkeypatch) -> None:
    monkeypatch.delenv("SSO_PUBLIC_ISSUER_URL", raising=False)
    monkeypatch.delenv("SSO_CLIENT_ID", raising=False)
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "  https://issuer.example/realms/main  ")
    monkeypatch.setenv("ALLOW_LOCAL_AUTH", "0")
    monkeypatch.setenv("SSO_ENABLED", "yes")
    monkeypatch.setenv("SSO_PROVIDER", "oidc")
    monkeypatch.setenv("KEYCLOAK_CLIENT_ID", "dq-ui")
    monkeypatch.setenv("BLANK_ENV", "   ")

    assert appcfg_defaults_mod._get_env_string("MISSING_ENV", "SSO_PUBLIC_ISSUER_URL") == "https://issuer.example/realms/main"
    assert appcfg_defaults_mod._get_env_string("BLANK_ENV", "SSO_PUBLIC_ISSUER_URL") == "https://issuer.example/realms/main"
    assert appcfg_defaults_mod._get_env_boolean_or_none("ALLOW_LOCAL_AUTH") is False
    assert appcfg_defaults_mod._get_env_boolean_or_none("UNSET_BOOLEAN_ENV") is None

    merged = appcfg_defaults_mod.apply_env_sso_overrides({
        "ssoProvider": "none",
        "ssoIssuer": None,
        "ssoClientId": None,
        "ssoEnabled": False,
        "allowLocalAuth": True,
    })

    assert merged == {
        "ssoProvider": "oidc",
        "ssoIssuer": "https://issuer.example/realms/main",
        "ssoClientId": "dq-ui",
        "ssoEnabled": True,
        "allowLocalAuth": False,
    }


def test_infer_app_config_value_type_and_serialize_helpers_cover_remaining_branches() -> None:
    assert appcfg_defaults_mod.infer_app_config_value_type("defaultPageSize") == "number"
    assert appcfg_defaults_mod.infer_app_config_value_type("enableExport") == "boolean"
    assert appcfg_defaults_mod.infer_app_config_value_type("siemEnabled") == "boolean"
    assert appcfg_defaults_mod.infer_app_config_value_type("supportEmailSmtpHost") == "string"
    assert appcfg_defaults_mod.infer_app_config_value_type("siemEndpointUrl") == "string"
    assert appcfg_defaults_mod.infer_app_config_value_type("validationPolicies") == "json"
    assert appcfg_defaults_mod.infer_app_config_value_type("incidentGovernance") == "json"
    assert appcfg_defaults_mod.infer_app_config_value_type("unmappedKey") == "string"

    assert serialize_app_config_value(None, "string") is None
    assert serialize_app_config_value(0, "boolean") == "false"
    assert serialize_app_config_value({"enabled": True}, "json") == '{"enabled": true}'
    assert serialize_app_config_value("raw", "string") == "raw"


def test_normalize_app_config_payload_covers_number_boolean_json_and_string_branches(monkeypatch) -> None:
    monkeypatch.delenv("SSO_PROVIDER", raising=False)
    monkeypatch.delenv("SSO_PUBLIC_ISSUER_URL", raising=False)
    monkeypatch.delenv("SSO_CLIENT_ID", raising=False)
    monkeypatch.delenv("KEYCLOAK_CLIENT_ID", raising=False)
    monkeypatch.delenv("SSO_ENABLED", raising=False)
    monkeypatch.delenv("ALLOW_LOCAL_AUTH", raising=False)

    normalized = appcfg_defaults_mod.normalize_app_config_payload(
        {
            "defaultPageSize": "42",
            "api_retry_delay": "12.5",
            "maxRulesPerWorkspace": object(),
            "enableExport": True,
            "metrics_forwarding_enabled": 0,
            "siem_enabled": True,
            "siem_endpoint_url": "https://siem.example/api",
            "siem_api_token": " secret-token ",
            "featureRuleSuggestions": " yes ",
            "feature_rule_dsl_v2": "true",
            "ssoProvider": "",
            "sso_issuer": "",
            "ssoClientId": "",
            "assistanceRequestDestinations": ["email", "teams"],
            "status_governance": {"enabled": True},
            "incident_governance": {"default_assigned_to": "engine-on-call"},
            "maintenanceMessage": 123,
            "log_level": "debug",
            "deploymentVerifiedBy": None,
        }
    )

    assert normalized["defaultPageSize"] == 42
    assert normalized["apiRetryDelay"] == 12.5
    assert normalized["maxRulesPerWorkspace"] == appcfg_defaults_mod.APP_CONFIG_DEFAULTS["maxRulesPerWorkspace"]
    assert normalized["enableExport"] is True
    assert normalized["metricsForwardingEnabled"] is False
    assert normalized["siemEnabled"] is True
    assert normalized["siemEndpointUrl"] == "https://siem.example/api"
    assert normalized["siemApiToken"] == " secret-token "
    assert normalized["featureRuleSuggestions"] is True
    assert normalized["featureRuleDslV2"] is True
    assert normalized["ssoProvider"] == appcfg_defaults_mod.APP_CONFIG_DEFAULTS["ssoProvider"]
    assert normalized["ssoIssuer"] == appcfg_defaults_mod.APP_CONFIG_DEFAULTS["ssoIssuer"]
    assert normalized["ssoClientId"] == appcfg_defaults_mod.APP_CONFIG_DEFAULTS["ssoClientId"]
    assert normalized["assistanceRequestDestinations"] == ["email", "teams"]
    assert normalized["statusGovernance"] == {"enabled": True}
    assert normalized["incidentGovernance"] == {"default_assigned_to": "engine-on-call"}
    assert normalized["maintenanceMessage"] == "123"
    assert normalized["logLevel"] == "debug"
    assert normalized["deploymentVerifiedBy"] == appcfg_defaults_mod.APP_CONFIG_DEFAULTS["deploymentVerifiedBy"]
