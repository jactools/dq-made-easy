from app.core import dependencies
from app.core.config import get_settings
from fastapi import HTTPException
import os
import pytest
from app.infrastructure.repositories.postgres_system_repository import PostgresSystemRepository


def test_postgres_system_repository_parses_info_map(
    postgres_dsn: str,
    system_info_rows: list[dict[str, object]],
    clone_payload,
) -> None:
    repository = PostgresSystemRepository(postgres_dsn)
    repository._fetch_all = lambda: [clone_payload(row) for row in system_info_rows]  # type: ignore[method-assign]

    info = repository.get_system_info()

    assert info.db_schema_version == "2.5.0"
    assert info.db_schema_updated == "2026-03-01T10:00:00Z"
    assert info.db_git_commit == "abc123"


def test_system_dependency_fails_without_database(monkeypatch) -> None:
    monkeypatch.setenv("DQ_DB_LOCAL_URL", "")
    monkeypatch.setenv("REQUIRE_DATABASE", "false")
    get_settings.cache_clear()
    dependencies._get_postgres_system_repository.cache_clear()

    with pytest.raises(HTTPException) as exc:
        dependencies.get_system_repository()

    assert exc.value.status_code == 503
    assert exc.value.detail["error"] == "repository_unavailable"
    assert exc.value.detail["service"] == "system-repository"


def test_system_dependency_uses_postgres_with_database(monkeypatch, postgres_dependency_url: str) -> None:
    monkeypatch.setenv("DQ_DB_LOCAL_URL", postgres_dependency_url)
    get_settings.cache_clear()
    dependencies._get_postgres_system_repository.cache_clear()

    repository = dependencies.get_system_repository()

    assert isinstance(repository, PostgresSystemRepository)

    # Preserve DQ_DB_LOCAL_URL if supplied by outer test configuration.
    if os.environ.get("DQ_DB_LOCAL_URL") is not None:
        monkeypatch.setenv("DQ_DB_LOCAL_URL", os.environ["DQ_DB_LOCAL_URL"])
    else:
        monkeypatch.delenv("DQ_DB_LOCAL_URL", raising=False)
    get_settings.cache_clear()
    dependencies._get_postgres_system_repository.cache_clear()