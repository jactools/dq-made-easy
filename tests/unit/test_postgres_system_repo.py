from types import SimpleNamespace
from datetime import datetime, timezone

import app.infrastructure.repositories.postgres_system_repository as psr


def test_get_system_info_monkeypatched_fetch_all(monkeypatch):
    repo = psr.PostgresSystemRepository(database_url="sqlite:///:memory:")

    fake_rows = [
        {"info_key": "db_schema_version", "info_value": "v1", "description": None, "updated_at": None},
        {"info_key": "db_schema_updated", "info_value": "2026-01-01", "description": None, "updated_at": None},
        {"info_key": "db_git_commit", "info_value": "abc123", "description": None, "updated_at": None},
    ]

    monkeypatch.setattr(repo, "_fetch_all", lambda: fake_rows)

    info = repo.get_system_info()
    assert info.db_schema_version == "v1"
    assert info.db_schema_updated == "2026-01-01"
    assert info.db_git_commit == "abc123"


def test_get_suggestions_metrics_summary_monkeypatched_session(monkeypatch):
    repo = psr.PostgresSystemRepository(database_url="sqlite:///:memory:")

    # Create fake rows with action and created_at
    now = datetime.now(timezone.utc)
    row1 = SimpleNamespace(action="CLICK", created_at=now)
    row2 = SimpleNamespace(action=None, created_at=None)

    class FakeResult:
        def __init__(self, rows):
            self._rows = rows

        def scalars(self):
            class All:
                def __init__(self, rows):
                    self._rows = rows

                def all(self):
                    return self._rows

            return All(self._rows)

    class FakeSession:
        def execute(self, stmt):
            return FakeResult([row1, row2])

    class FakeCtx:
        def __init__(self, session):
            self._session = session

        def __enter__(self):
            return self._session

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(psr, "session_scope", lambda db: FakeCtx(FakeSession()))

    summary = repo.get_suggestions_metrics_summary()
    assert summary.total == 2
    assert summary.successful == 2
    assert isinstance(summary.operations, list)
