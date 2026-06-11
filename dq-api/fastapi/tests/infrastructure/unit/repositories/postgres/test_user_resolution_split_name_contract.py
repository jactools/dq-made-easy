from __future__ import annotations

from app.infrastructure.repositories.postgres_profiling_repository import PostgresProfilingRepository
from app.infrastructure.repositories.postgres_suggestions_repository import PostgresSuggestionsRepository


class _NoUserResult:
    def scalar_one_or_none(self):
        return None


class _UserResult:
    def __init__(self, user) -> None:
        self.user = user

    def scalar_one_or_none(self):
        return self.user


class _Session:
    def __init__(self, results=None) -> None:
        self.added = []
        self.results = list(results or [])

    def execute(self, _statement):
        if self.results:
            return self.results.pop(0)
        return _NoUserResult()

    def add(self, row) -> None:
        self.added.append(row)


def test_suggestions_user_resolution_creates_split_name_user_for_external_email() -> None:
    session = _Session()
    repository = PostgresSuggestionsRepository("postgresql://example")

    user_id = repository._resolve_or_create_user_id(session, "alice@jaccloud.nl")

    assert user_id == "alice@jaccloud.nl"
    assert len(session.added) == 1
    user = session.added[0]
    assert user.id == "alice@jaccloud.nl"
    assert user.first_name == "alice"
    assert user.last_name == "alice"
    assert user.email == "alice@jaccloud.nl"
    assert user.external_id == "alice@jaccloud.nl"


def test_suggestions_user_resolution_matches_existing_email_user() -> None:
    existing_user = type("User", (), {"id": "user-1", "external_id": "oidc-subject"})()
    session = _Session(results=[_NoUserResult(), _NoUserResult(), _UserResult(existing_user)])
    repository = PostgresSuggestionsRepository("postgresql://example")

    user_id = repository._resolve_or_create_user_id(session, "alice@jaccloud.nl")

    assert user_id == "user-1"
    assert session.added == []


def test_profiling_user_resolution_creates_split_name_user_for_external_email() -> None:
    session = _Session()
    repository = PostgresProfilingRepository("postgresql://example")

    user_id = repository._resolve_or_create_user_id(session, "alice@jaccloud.nl")

    assert user_id == "alice@jaccloud.nl"
    assert len(session.added) == 1
    user = session.added[0]
    assert user.id == "alice@jaccloud.nl"
    assert user.first_name == "alice"
    assert user.last_name == "alice"
    assert user.email == "alice@jaccloud.nl"
    assert user.external_id == "alice@jaccloud.nl"


def test_profiling_user_resolution_matches_existing_email_user() -> None:
    existing_user = type("User", (), {"id": "user-1", "external_id": "oidc-subject"})()
    session = _Session(results=[_NoUserResult(), _NoUserResult(), _UserResult(existing_user)])
    repository = PostgresProfilingRepository("postgresql://example")

    user_id = repository._resolve_or_create_user_id(session, "alice@jaccloud.nl")

    assert user_id == "user-1"
    assert session.added == []