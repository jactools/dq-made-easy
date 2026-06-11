from app.infrastructure.repositories.in_memory_app_config_repository import InMemoryAppConfigRepository


def test_in_memory_app_config_applies_sso_overrides(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "https://issuer.example/realms/dq")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")

    repository = InMemoryAppConfigRepository()
    config = repository.get_app_config()

    assert config.ssoEnabled is True
    assert config.ssoIssuer == "https://issuer.example/realms/dq"
    assert config.ssoClientId == "dq-rules-ui"


def test_in_memory_app_config_persists_updates(
    app_config_update_payload: dict[str, object],
    clone_payload,
) -> None:
    repository = InMemoryAppConfigRepository()

    payload = clone_payload(app_config_update_payload)
    payload["assistanceRequestItsmAuthToken"] = "zammad-api-token"
    payload["alertingSlackWebhookUrl"] = "https://hooks.slack.com/services/T000/B000/XXXXX"
    payload["alertingPagerDutyRoutingKey"] = "pagerduty-routing-key"
    payload["feature_rule_dsl_v2"] = "true"
    payload["exceptionFactJitRequestTimeoutMinutes"] = 45

    config = repository.set_app_config(payload)

    assert config.maintenanceMode is True
    assert config.maintenanceMessage == "scheduled"
    assert config.defaultPageSize == 40
    assert config.apiVersion == "v1"
    assert config.assistanceRequestItsmAuthToken == "zammad-api-token"
    assert config.alertingSlackWebhookUrl == "https://hooks.slack.com/services/T000/B000/XXXXX"
    assert config.alertingPagerDutyRoutingKey == "pagerduty-routing-key"
    assert config.exceptionFactJitRoleMaxDurationMinutes == 180
    assert config.exceptionFactJitRequestTimeoutMinutes == 45
    assert config.featureRuleDslV2 is True


def test_in_memory_app_config_exposes_playground_bundle_policy() -> None:
    repository = InMemoryAppConfigRepository()

    config = repository.get_app_config()

    assert config.playgroundSourceBundlePolicy == {
        "default_allow": True,
        "allowed_bundle_ids": [],
        "blocked_bundle_ids": [],
    }


def test_in_memory_app_config_exposes_incident_governance_policy() -> None:
    repository = InMemoryAppConfigRepository()

    config = repository.get_app_config()

    assert config.incidentGovernance == {
        "default_assigned_to": "dq-made-easy-support@jaccloud.nl",
        "default_escalation_label": "dq-made-easy-support",
        "rules": [
            {
                "incident_kinds": ["technical_run_error"],
                "assigned_to": "dq-made-easy-support@jaccloud.nl",
                "escalation_label": "engine-on-call",
                "escalate_after_minutes": 15,
            },
            {
                "incident_kinds": ["functional_violation"],
                "assigned_to": "data-governance",
                "escalation_label": "governance-triage",
                "escalate_after_minutes": 60,
            },
        ],
    }
