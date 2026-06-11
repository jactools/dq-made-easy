from __future__ import annotations

from types import SimpleNamespace
from contextlib import contextmanager

import app.infrastructure.repositories.postgres_admin_repository as admin_mod
from app.infrastructure.repositories.postgres_admin_repository import PostgresAdminRepository
from app.infrastructure.orm.models import UserRow


@contextmanager
def _scope(session):
    yield session


class _Session:
    def __init__(self, scalar_values=None, gets=None):
        self.scalar_values = list(scalar_values or [])
        self.gets = dict(gets or {})

    def execute(self, _stmt):
        if self.scalar_values:
            value = self.scalar_values.pop(0)
            class _ScalarResult:
                def __init__(self, v):
                    self._v = v

                def scalar_one_or_none(self):
                    if isinstance(self._v, list):
                        return self._v[0] if self._v else None
                    return self._v

            return _ScalarResult(value)
        class _Empty:
            def scalar_one_or_none(self):
                return None

        return _Empty()

    def get(self, _model, key):
        return self.gets.get(key)


def test_find_current_user_resolves_subject_and_enriches_from_claims(monkeypatch) -> None:
    # Create a DB row that has an external_id matching the OIDC subject but
    # missing name parts/email. The repository should return a dict populated
    # with first/last name and email taken from the claims when resolving by
    # subject.
    subject = "oidc-subject-123"

    user_row = UserRow(
        id="u-oidc",
        first_name="",
        last_name="",
        email=None,
        external_id=subject,
        workspaces=None,
        preferences=None,
    )

    # The repository will execute a select on external_id; provide that result.
    session = _Session(scalar_values=[[user_row]])
    monkeypatch.setattr(admin_mod, "session_scope", lambda _dsn: _scope(session))

    repo = PostgresAdminRepository("postgresql://example")

    # Include an email claim but simulate no DB row found by email or
    # preferred_username so the subject-based select runs and returns the
    # user_row. The repository should then enrich missing fields from claims.
    session = _Session(scalar_values=[None, None, [user_row]])
    monkeypatch.setattr(admin_mod, "session_scope", lambda _dsn: _scope(session))

    claims = {"sub": subject, "email": "oidc@example.com", "name": "OIDC User", "preferred_username": "oidc"}

    result = repo._find_current_user(None, claims)

    assert result is not None
    assert result["external_id"] == subject
    # Ensure missing fields were enriched from claims.
    assert result["email"] == "oidc@example.com"
    assert result["first_name"] == "OIDC"
    assert result["last_name"] == "User"
