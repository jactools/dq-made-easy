"""classification: unit"""

import pytest

from app.core import auth_scopes


pytestmark = pytest.mark.unit


def test_auth_scopes_delegate_to_shared_scope_resolver() -> None:
    payload = {
        "scope": "dq:rules:read dq:rules:write",
        "realm_access": {"roles": ["admin"]},
    }

    scopes = auth_scopes.get_scopes_from_payload(payload)
    assert "dq:rules:read" in scopes
    assert "dq:rules:write" in scopes
    assert "admin" in scopes

    expanded = auth_scopes.expand_granted_scopes(["dq:rules:write"])
    assert "dq:rules:read" in expanded
    assert "dq:rules:approve" in expanded

    assert auth_scopes.has_required_scope(["dq:rules:write"], ["dq:rules:read"]) is True
    assert auth_scopes.has_required_scope(["dq:rules:*"], ["dq:rules:write"]) is True
    assert auth_scopes.has_required_scope(["dq:admin"], ["dq:config:manage"]) is False
