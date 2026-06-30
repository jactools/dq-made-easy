import time
import base64
import json
from types import SimpleNamespace

from app.core import auth
from app.core.config import Settings


def _make_token(payload: dict) -> str:
    seg = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    return f"h.{seg}.s"


def test_normalize_and_public_routes():
    assert auth.normalize_auth_path("") == "/"
    assert auth.normalize_auth_path("/api/v1/foo/") == "/v1/foo"
    assert auth.normalize_auth_path("//v1//a//") == "/v1/a"
    assert auth.normalize_auth_path("/admin/v1/me?x=1") == "/admin/v1/me"

    assert auth.is_public_route("/")
    assert auth.is_public_route("/auth/v1/login")
    assert not auth.is_public_route("/v1/secure")


def test_get_bearer_token_variants():
    req = SimpleNamespace(headers={"authorization": "Bearer tok1"})
    token, src = auth.get_bearer_token(req)
    assert token == "tok1" and src == "authorization"

    req = SimpleNamespace(headers={"x-auth-request-access-token": "tok2"})
    token, src = auth.get_bearer_token(req)
    assert token == "tok2" and src == "x-auth-request-access-token"

    req = SimpleNamespace(headers={})
    assert auth.get_bearer_token(req) == (None, None)


def test_decode_jwt_payload_and_build_principal():
    payload = {"sub": "user-1", "exp": int(time.time()) + 600, "nbf": int(time.time()) - 10, "scope": "dq:rules:read dq:rules:write"}
    token = _make_token(payload)

    parsed = auth.decode_jwt_payload(token)
    assert parsed is not None and parsed.get("sub") == "user-1"

    settings = Settings(sso_enabled=False)
    principal = auth.build_principal(token, "authorization", settings)
    assert principal is not None
    assert principal.user_id == "user-1"
    assert any(s.startswith("dq:rules") for s in principal.scopes)


def test_is_jwt_payload_valid_and_sso_checks(monkeypatch):
    now = int(time.time())
    good = {"exp": now + 100, "nbf": now - 10, "iss": "https://iss", "aud": "client-1"}
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "https://iss")
    settings = Settings(sso_enabled=True, sso_issuer="https://iss", sso_client_id="client-1", sso_allowed_client_ids="")
    assert auth.is_jwt_payload_valid(good, settings)

    internal_issuer = {"exp": now + 100, "nbf": now - 10, "iss": "http://iss:8080", "aud": "client-1"}
    assert auth.is_jwt_payload_valid(internal_issuer, settings)

    expired = {"exp": now - 1}
    assert not auth.is_jwt_payload_valid(expired, settings)

    future_nbf = {"exp": now + 100, "nbf": now + 1000}
    assert not auth.is_jwt_payload_valid(future_nbf, settings)

    wrong_iss = {"exp": now + 100, "nbf": now - 10, "iss": "https://other", "aud": "client-1"}
    assert not auth.is_jwt_payload_valid(wrong_iss, settings)

    wrong_aud = {"exp": now + 100, "nbf": now - 10, "iss": "https://iss", "aud": ["other"]}
    assert not auth.is_jwt_payload_valid(wrong_aud, settings)


def test_is_jwt_payload_valid_allows_azp_allowlist(monkeypatch):
    now = int(time.time())
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "https://iss")
    settings = Settings(
        sso_enabled=True,
        sso_issuer="https://iss",
        sso_client_id="dq-rules-ui",
        sso_allowed_client_ids="dq-rules-ui,dq-engine-gx-worker",
    )

    service_token = {
        "exp": now + 100,
        "nbf": now - 10,
        "iss": "https://iss",
        "aud": "account",
        "azp": "dq-engine-gx-worker",
    }
    assert auth.is_jwt_payload_valid(service_token, settings)

    wrong_azp = dict(service_token)
    wrong_azp["azp"] = "some-other-client"
    assert not auth.is_jwt_payload_valid(wrong_azp, settings)


def test_scopes_collection_and_hierarchy():
    payload = {
        "scope": "a b",
        "scp": ["c", "d"],
        "roles": "e f",
        "realm_access": {"roles": ["g"]},
        "resource_access": {"account": {"roles": ["h"]}},
    }
    scopes = auth.get_scopes_from_payload(payload)
    assert set(scopes) >= {"a", "b", "c", "d", "e", "f", "g", "h"}

    expanded = auth.expand_granted_scopes(["dq:rules:write"])
    assert "dq:rules:read" in expanded and "dq:rules:write" in expanded

    assert auth.has_required_scope(["dq:*"], ["dq:rules:test"]) is True
    assert auth.has_required_scope(["dq:rules:*"], ["dq:rules:write"]) is True
    assert auth.has_required_scope(["dq:rules:write"], ["dq:rules:read"]) is True


def test_build_principal_trusted():
    payload = {"preferred_username": "bob", "scope": "x y"}
    token = _make_token(payload)
    principal = auth.build_principal_trusted(token, "authorization", ["analyst"])
    assert principal is not None
    assert principal.user_id == "bob"
    assert "x" in principal.scopes
    assert principal.consumer_groups == ["analyst"]
import base64
import json
import time
from types import SimpleNamespace

from app.core.auth import (
    normalize_auth_path,
    is_public_route,
    get_required_scopes,
    get_bearer_token,
    decode_jwt_payload,
    is_jwt_payload_valid,
    get_scopes_from_payload,
    expand_granted_scopes,
    has_required_scope,
    build_principal_trusted,
)
from app.core.config import Settings


def _b64url(obj: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(obj, separators=(",", ":")).encode()).decode("ascii").rstrip("=")


def test_normalize_and_public_route_and_required_scopes():
    assert normalize_auth_path("/api/auth/v1/login") == "/auth/v1/login"
    assert is_public_route("/")
    assert is_public_route("/api/auth/v1/login")

    assert get_required_scopes("GET", "/admin/v1/me") == []
    assert get_required_scopes("GET", "/user/v1/me") == []
    assert get_required_scopes("GET", "/system/v1/app-config") == ["dq:admin:read"]
    assert get_required_scopes("POST", "/system/v1/app-config") == ["dq:config:manage"]
    assert get_required_scopes("GET", "/agent/v1/openapi") == ["dq:rules:read"]
    assert get_required_scopes("POST", "/agent/v1/rules/execute-batch") == ["dq:rules:write"]
    assert get_required_scopes("GET", "/agent/v1/audit/events") == ["dq:admin:read"]
    assert get_required_scopes("POST", "/agent/v1/audit/events") == ["dq:rules:write"]
    assert get_required_scopes("GET", "/admin/v1/users") == ["dq:admin:read", "dq:workspace:read"]
    assert get_required_scopes("GET", "/admin/v1/roles") == ["dq:admin:read", "dq:workspace:read"]
    assert get_required_scopes("GET", "/data-catalog/v1/metadata-registry/external-parties") == ["dq:rules:read", "dq:data_catalog:read"]
    assert get_required_scopes("POST", "/data-catalog/v1/metadata-registry/external-parties/workspace:retail-banking/approve") == ["dq:users:manage"]
    assert get_required_scopes("GET", "/data-catalog/v1/metadata-registry/access-grants") == ["dq:rules:read", "dq:data_catalog:read"]
    assert get_required_scopes("POST", "/data-catalog/v1/metadata-registry/access-grants") == ["dq:users:manage"]
    assert get_required_scopes("POST", "/data-catalog/v1/metadata-registry/external-parties/workspace:retail-banking/access-grants") == ["dq:users:manage"]
    assert get_required_scopes("GET", "/rulebuilder/v1/workspaces") == ["dq:rules:read", "dq:workspace:manage"]
    assert get_required_scopes("POST", "/rulebuilder/v1/approvals") == ["dq:rules:approve"]
    assert get_required_scopes("POST", "/data-catalog/v1/profiling/requests") == [
        "dq:profiling:request",
        "dq:rules:test",
    ]
    assert get_required_scopes("POST", "/data-catalog/v1/suggestions/natural-language-rule-previews") == [
        "dq:rules:create",
        "dq:rules:write",
    ]
    assert get_required_scopes("POST", "/data-catalog/v1/materialization-requests") == [
        "dq:rules:test",
        "dq:rules:write",
    ]
    assert get_required_scopes("GET", "/data-catalog/v1/materialization-requests/tdm-1") == [
        "dq:rules:test",
        "dq:rules:write",
    ]
    assert get_required_scopes("POST", "/rulebuilder/v1/rules") == ["dq:rules:create", "dq:rules:write"]
    assert get_required_scopes("POST", "/v1/other") == ["dq:rules:edit", "dq:rules:write"]
    assert get_required_scopes("GET", "/rulebuilder/v1/notifications") == ["dq:notifications:read"]


def test_bearer_token_and_decode_and_validation_and_scopes(monkeypatch):
    # Bearer header
    req = SimpleNamespace(headers={"authorization": "Bearer abc.def.ghi"})
    token, src = get_bearer_token(req)
    assert token == "abc.def.ghi"
    assert src == "authorization"

    # Build JWT-like token and decode
    payload = {"sub": "user-1", "exp": time.time() + 1000, "iss": "https://iss", "aud": "client-1", "scope": "a b"}
    token = f"{_b64url({'alg':'none'})}.{_b64url(payload)}."
    decoded = decode_jwt_payload(token)
    assert isinstance(decoded, dict) and decoded.get("sub") == "user-1"

    # Valid with matching settings
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "https://iss")
    settings = Settings(sso_enabled=True, sso_issuer="https://iss", sso_client_id="client-1", sso_allowed_client_ids="")
    assert is_jwt_payload_valid(decoded, settings)

    # Expired
    decoded_expired = dict(decoded)
    decoded_expired["exp"] = time.time() - 10
    assert not is_jwt_payload_valid(decoded_expired, settings)

    # NBF in future
    decoded_nbf = dict(decoded)
    decoded_nbf["nbf"] = time.time() + 10000
    assert not is_jwt_payload_valid(decoded_nbf, settings)

    # Wrong issuer
    decoded_wrong_iss = dict(decoded)
    decoded_wrong_iss["iss"] = "https://other"
    assert not is_jwt_payload_valid(decoded_wrong_iss, settings)


def test_get_scopes_and_expand_and_has_required_scope_and_build_principal_trusted():
    payload = {
        "scope": "a b",
        "scp": "c d",
        "roles": "r1 r2",
        "permissions": "p1",
        "realm_access": {"roles": ["realm1"]},
        "resource_access": {"account": {"roles": ["acct1"]}},
    }
    scopes = get_scopes_from_payload(payload)
    assert set(scopes) >= {"a", "b", "c", "d", "r1", "r2", "p1", "realm1", "acct1"}

    expanded = expand_granted_scopes(["dq:rules:write"])
    assert "dq:rules:read" in expanded and "dq:rules:create" in expanded

    assert has_required_scope(["dq:*"], ["dq:rules:edit"]) is True
    assert has_required_scope(["dq:rules:write"], ["dq:rules:read"]) is True

    # build_principal_trusted should decode token without validation
    payload2 = {"sub": "p1", "scope": "s1 s2"}
    token = f"{_b64url({'alg':'none'})}.{_b64url(payload2)}."
    principal = build_principal_trusted(token, "authorization")
    assert principal is not None and principal.user_id == "p1"
