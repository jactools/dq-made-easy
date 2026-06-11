from app.infrastructure.repositories.in_memory_app_config_repository import InMemoryAppConfigRepository


def test_get_app_config_defaults():
    repo = InMemoryAppConfigRepository()
    cfg = repo.get_app_config()
    # default value from APP_CONFIG_DEFAULTS
    assert hasattr(cfg, "defaultRuleThresholdPct")
    assert float(cfg.defaultRuleThresholdPct) == 0.0


def test_set_app_config_number_and_empty_sso_provider():
    repo = InMemoryAppConfigRepository()
    # set numeric via string and empty sso_provider (should fall back to default)
    updated = repo.set_app_config({"defaultRuleThresholdPct": "25", "sso_provider": ""})
    assert float(updated.defaultRuleThresholdPct) == 25.0
    # empty sso_provider should revert to default 'none'
    assert updated.ssoProvider == "none"
