from app.core.auth import (
    build_principal,
    build_principal_trusted,
    expand_granted_scopes,
    get_bearer_token,
    get_required_scopes,
    get_scopes_from_payload,
    has_required_scope,
    is_public_route,
    normalize_auth_path,
)
from app.core.config import Settings


def test_normalize_auth_path_strips_api_prefix() -> None:
    assert normalize_auth_path("/api/rulebuilder/v1/rules/demo") == "/rulebuilder/v1/rules/demo"
    assert normalize_auth_path("/rulebuilder/v1/rules/demo") == "/rulebuilder/v1/rules/demo"
    assert normalize_auth_path("/api/system/v1/version-catalog/") == "/system/v1/version-catalog"
    assert normalize_auth_path("/api//system//v1//version-catalog") == "/system/v1/version-catalog"


def test_public_route_allows_homepage_and_auth_endpoints() -> None:
    assert is_public_route("/") is True
    assert is_public_route("/health") is True
    assert is_public_route("/auth/v1/login") is True
    assert is_public_route("/auth/v1/logout") is True
    assert is_public_route("/auth/v1/redirect") is True
    assert is_public_route("/auth/v1/callback") is True
    assert is_public_route("/api/auth/v1/redirect") is True
    assert is_public_route("/system/v1/health") is True
    assert is_public_route("/api/system/v1/readiness") is True
    assert is_public_route("/metrics") is False
    assert is_public_route("/api/rulebuilder/v1/rules/demo") is False


def test_required_scopes_follow_current_mapping() -> None:
    assert get_required_scopes("GET", "/auth/v1/redirect") == []
    assert get_required_scopes("GET", "/auth/v1/callback") == []
    assert get_required_scopes("POST", "/auth/v1/login") == []
    assert get_required_scopes("POST", "/auth/v1/logout") == []
    assert get_required_scopes("GET", "/metrics") == ["dq:rules:read"]
    assert get_required_scopes("GET", "/api/rulebuilder/v1/rules/demo") == ["dq:rules:read"]
    assert get_required_scopes("POST", "/rulebuilder/v1/rules") == ["dq:rules:create", "dq:rules:write"]
    assert get_required_scopes("PATCH", "/system/v1/app-config") == ["dq:config:manage"]
    assert get_required_scopes("GET", "/system/v1/app-config") == ["dq:admin:read"]
    assert get_required_scopes("GET", "/agent/v1/openapi") == ["dq:rules:read"]
    assert get_required_scopes("POST", "/agent/v1/rules/execute-batch") == ["dq:rules:write"]
    assert get_required_scopes("GET", "/agent/v1/audit/events") == ["dq:admin:read"]
    assert get_required_scopes("PUT", "/admin/v1/me") == []
    assert get_required_scopes("GET", "/admin/v1/users") == ["dq:admin:read", "dq:workspace:read"]
    assert get_required_scopes("GET", "/admin/v1/roles") == ["dq:admin:read", "dq:workspace:read"]
    assert get_required_scopes("POST", "/admin/v1/rules/rule-1/recover") == ["dq:users:manage"]
    assert get_required_scopes("GET", "/data-catalog/v1/metadata-registry/external-parties") == ["dq:rules:read", "dq:data_catalog:read"]
    assert get_required_scopes("POST", "/data-catalog/v1/metadata-registry/external-parties/workspace:retail-banking/approve") == ["dq:users:manage"]
    assert get_required_scopes("GET", "/data-catalog/v1/metadata-registry/access-grants") == ["dq:rules:read", "dq:data_catalog:read"]
    assert get_required_scopes("POST", "/data-catalog/v1/metadata-registry/access-grants") == ["dq:users:manage"]
    assert get_required_scopes("POST", "/data-catalog/v1/metadata-registry/external-parties/workspace:retail-banking/access-grants") == ["dq:users:manage"]
    assert get_required_scopes("GET", "/system/v1/version-catalog") == []
    assert get_required_scopes("GET", "/system/v1/version-catalog/") == []
    assert get_required_scopes("GET", "/api/system/v1/version-catalog/") == []
    assert get_required_scopes("GET", "/rulebuilder/v1/notifications") == ["dq:notifications:read"]


def test_scope_collection_and_expansion(auth_scope_payload: dict[str, object]) -> None:
    payload = auth_scope_payload

    scopes = get_scopes_from_payload(payload)
    assert "dq:rules:read" in scopes
    assert "dq:profiling:request" in scopes
    assert "admin" in scopes

    expanded = expand_granted_scopes(["dq:rules:write"])
    assert "dq:rules:read" in expanded
    assert "dq:rules:approve" in expanded
    assert has_required_scope(["dq:config:manage"], ["dq:config:manage"]) is True
    assert has_required_scope(["dq:*"], ["dq:config:manage"]) is True
    assert has_required_scope(["dq:config:*"], ["dq:config:manage"]) is True
    assert has_required_scope(["dq:admin"], ["dq:config:manage"]) is False

def test_build_principal_accepts_expected_jwt(
    jwt_token_builder,
    auth_principal_claims: dict[str, object],
) -> None:
    settings = Settings(
        sso_enabled=True,
        sso_issuer="http://keycloak.local:8080/realms/jaccloud",
        sso_client_id="dq-rules-ui",
    )
    token = jwt_token_builder(auth_principal_claims)

    principal = build_principal(token, "authorization", settings)

    assert principal is not None
    assert principal.user_id == "user-42"
    assert "dq:rules:read" in principal.scopes
    assert "dq:rules:edit" in principal.scopes


def test_build_principal_rejects_wrong_issuer(
    jwt_token_builder,
    auth_wrong_issuer_claims: dict[str, object],
) -> None:
    settings = Settings(
        sso_enabled=True,
        sso_issuer="http://keycloak.local:8080/realms/jaccloud",
        sso_client_id="dq-rules-ui",
    )
    token = jwt_token_builder(auth_wrong_issuer_claims)

    assert build_principal(token, "authorization", settings) is None


def test_get_bearer_token_supports_gateway_headers(auth_gateway_request) -> None:
    request = auth_gateway_request

    token, source = get_bearer_token(request)

    assert token == "gateway-token"
    assert source == "x-auth-request-access-token"


def test_build_principal_trusted_captures_consumer_groups() -> None:
    payload = {
        "sub": "u1",
        "preferred_username": "analyst",
        "scope": "dq:rules:read",
    }
    token = "{}.{}.".format(
        "e30",
        __import__("base64").urlsafe_b64encode(__import__("json").dumps(payload).encode()).decode().rstrip("="),
    )

    principal = build_principal_trusted(token, "authorization", ["viewer", "analyst"])

    assert principal is not None
    assert principal.consumer_groups == ["viewer", "analyst"]