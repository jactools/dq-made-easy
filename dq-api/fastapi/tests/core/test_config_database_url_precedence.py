import pytest

from app.core.config import Settings


def test_settings_prefer_compose_database_url_over_local_and_internal(monkeypatch) -> None:
    monkeypatch.setenv("COMPOSE_DATABASE_URL", "postgresql://postgres:postgres@db:5432/dq")
    monkeypatch.setenv("DQ_DB_LOCAL_URL", "postgresql://postgres:postgres@127.0.0.1:5432/dq")
    monkeypatch.setenv("DQ_DB_INTERNAL_URL", "postgresql://postgres:postgres@db:5432/dq")

    settings = Settings()

    assert settings.database_url == "postgresql://postgres:postgres@db:5432/dq"


def test_settings_normalizes_blank_database_url_to_none(monkeypatch) -> None:
    monkeypatch.setenv("COMPOSE_DATABASE_URL", "   ")

    settings = Settings()

    assert settings.database_url is None


def test_settings_database_url_validator_returns_none_for_none_input() -> None:
    assert Settings._normalize_database_url(None) is None


def test_settings_splits_cors_origins_and_ignores_empty_entries() -> None:
    settings = Settings(cors_allow_origins=" http://a.test , ,http://b.test ")

    assert settings.cors_origins_list == ["http://a.test", "http://b.test"]


def test_settings_prefer_explicit_sso_allowed_client_ids_over_sso_client_id() -> None:
    settings = Settings(sso_allowed_client_ids=" ui, api ", sso_client_id="fallback-client")

    assert settings.sso_allowed_client_ids_list == ["ui", "api"]


def test_settings_sso_allowed_client_ids_falls_back_to_sso_client_id() -> None:
    settings = Settings()
    settings.sso_allowed_client_ids = " "
    settings.sso_client_id = "frontend-app"

    assert settings.sso_allowed_client_ids_list == ["frontend-app"]


def test_settings_sso_allowed_client_ids_empty_when_unconfigured() -> None:
    settings = Settings(sso_allowed_client_ids="   ", sso_client_id=None)

    assert settings.sso_allowed_client_ids_list == []


def test_validate_runtime_requirements_fails_fast_when_database_is_required(monkeypatch) -> None:
    monkeypatch.delenv("COMPOSE_DATABASE_URL", raising=False)
    monkeypatch.delenv("DQ_DB_LOCAL_URL", raising=False)
    monkeypatch.delenv("DQ_DB_INTERNAL_URL", raising=False)
    settings = Settings()
    settings.require_database = True
    settings.database_url = None

    with pytest.raises(RuntimeError, match="DQ_DB_INTERNAL_URL or DQ_DB_LOCAL_URL"):
        settings.validate_runtime_requirements()


def test_validate_runtime_requirements_allows_runtime_when_database_not_required() -> None:
    settings = Settings(require_database=False, database_url=None)

    settings.validate_runtime_requirements()