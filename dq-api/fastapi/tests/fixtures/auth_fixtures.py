import base64
import json
from types import SimpleNamespace

import pytest

from tests.fixtures.shared_fixtures import load_fixture_dict


@pytest.fixture
def jwt_token_builder():
    def _jwt(payload: dict[str, object]) -> str:
        header = {"alg": "none", "typ": "JWT"}

        def encode(value: dict[str, object]) -> str:
            encoded = base64.urlsafe_b64encode(json.dumps(value).encode("utf-8")).decode("utf-8")
            return encoded.rstrip("=")

        return f"{encode(header)}.{encode(payload)}.signature"

    return _jwt


@pytest.fixture
def auth_scope_payload() -> dict[str, object]:
    return load_fixture_dict("auth_scope_payload", {
        "scope": "dq:rules:read",
        "scp": ["dq:profiling:request"],
        "realm_access": {"roles": ["admin"]},
    })


@pytest.fixture
def auth_principal_claims() -> dict[str, object]:
    return load_fixture_dict("auth_principal_claims", {
        "sub": "user-42",
        "preferred_username": "analyst",
        "iss": "http://keycloak.local:8080/realms/jaccloud",
        "aud": ["dq-rules-ui"],
        "scope": "dq:rules:read dq:rules:edit",
    })


@pytest.fixture
def auth_wrong_issuer_claims() -> dict[str, object]:
    return load_fixture_dict("auth_wrong_issuer_claims", {
        "sub": "user-42",
        "iss": "http://other-issuer/realm",
        "aud": ["dq-rules-ui"],
    })


@pytest.fixture
def auth_gateway_request() -> SimpleNamespace:
    return SimpleNamespace(headers=load_fixture_dict("auth_gateway_request", {"x-auth-request-access-token": "gateway-token"}))


@pytest.fixture
def auth_endpoint_user_claims() -> dict[str, object]:
    return load_fixture_dict("auth_endpoint_user_claims", {"sub": "user-1", "email": "user@example.com"})


@pytest.fixture
def auth_endpoint_fallback_claims() -> dict[str, object]:
    return load_fixture_dict("auth_endpoint_fallback_claims", {"sub": "fallback-user", "email": "fallback@example.com"})


@pytest.fixture
def auth_local_user_payload() -> dict[str, object]:
    return load_fixture_dict("auth_local_user_payload", {
        "id": "user-1",
        "name": "Local User",
        "roles": ["admin"],
        "granted_scopes": ["dq:admin"],
    })


@pytest.fixture
def auth_sso_runtime_config() -> dict[str, object]:
    return load_fixture_dict("auth_sso_runtime_config", {
        "ssoIssuer": "http://keycloak.local:8080/realms/jaccloud",
        "ssoClientId": "dq-rules-ui",
    })
