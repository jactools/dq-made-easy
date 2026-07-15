from __future__ import annotations

# Centralised re-exports used by all Postgres rules mixin modules.
# Tests patch `session_scope` and reference `UserRow` here so a single
# monkeypatch covers all mixin call sites.
from app.infrastructure.orm.models import UserRow as UserRow  # noqa: F401
from app.infrastructure.orm.session import session_scope as session_scope  # noqa: F401
