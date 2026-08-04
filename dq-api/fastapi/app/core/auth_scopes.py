from __future__ import annotations

from typing import Any

from platform_auth import create_dq_scope_resolver
from platform_auth import get_scopes_from_claims


_DQ_SCOPE_RESOLVER = create_dq_scope_resolver()


def get_scopes_from_payload(payload: dict[str, Any]) -> list[str]:
    """Extract scopes from JWT claims using the shared platform helper."""
    return get_scopes_from_claims(payload)


def expand_granted_scopes(granted: list[str]) -> set[str]:
    """Expand DQ scopes using the shared DQ scope resolver."""
    return _DQ_SCOPE_RESOLVER.expand_scopes(granted)


def has_required_scope(granted: list[str], required: list[str]) -> bool:
    """Check whether the granted scopes satisfy any required DQ scope."""
    return _DQ_SCOPE_RESOLVER.has_any_scope(granted, required)
