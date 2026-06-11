import json

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints import auth as auth_endpoints
from app.core.config import get_settings


def test_decode_claims_state_and_origin_helpers(
    monkeypatch,
    jwt_token_builder,
    auth_endpoint_user_claims: dict[str, object],
) -> None:
    token = jwt_token_builder(auth_endpoint_user_claims)
    state = auth_endpoints._to_base64_url(
        json.dumps({"nonce": "nonce-1", "issuedAt": 123, "frontendOrigin": "https://example.com/path"})
    )

    assert auth_endpoints._decode_jwt_claims(token)["sub"] == "user-1"
    assert auth_endpoints._decode_jwt_claims("invalid") is None
    assert auth_endpoints._decode_jwt_claims(None) is None
    assert auth_endpoints._normalize_frontend_origin("ftp://example.com") is None
    assert auth_endpoints._normalize_frontend_origin(None) is None
    assert auth_endpoints._decode_oidc_state(state) == {
        "nonce": "nonce-1",
        "issuedAt": 123,
        "frontendOrigin": "https://example.com",
    }
    assert auth_endpoints._decode_oidc_state("bad-state") == {
        "nonce": "",
        "issuedAt": None,
        "frontendOrigin": None,
    }


def test_build_local_token_and_backend_issuer_paths(
    monkeypatch,
    auth_local_user_payload: dict[str, object],
    auth_sso_runtime_config: dict[str, object],
) -> None:
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    token = auth_endpoints._build_local_token(
        auth_local_user_payload,
        auth_sso_runtime_config,
    )
    claims = auth_endpoints._decode_jwt_claims(token)

    assert claims is not None
    assert claims["preferred_username"] == "Local User"
    assert "dq:admin" in claims["scope"]

    monkeypatch.setenv("SSO_INTERNAL_ISSUER_URL", "http://keycloak-internal:8080")
    assert auth_endpoints._build_backend_issuer("http://localhost:8080/realms/jaccloud") == "http://keycloak-internal:8080/realms/jaccloud"

    monkeypatch.delenv("SSO_INTERNAL_ISSUER_URL", raising=False)
    assert auth_endpoints._build_backend_issuer("http://localhost:8080/realms/jaccloud") == "http://keycloak:8080/realms/jaccloud"
    assert auth_endpoints._build_backend_issuer("https://issuer.example.com/realms/jaccloud") == "https://issuer.example.com/realms/jaccloud"


@pytest.mark.anyio
async def test_exchange_oidc_code_success_and_failure(monkeypatch) -> None:
    class FakeResponse:
        def __init__(self, status_code: int, payload: dict[str, object]) -> None:
            self.status_code = status_code
            self._payload = payload

        def json(self) -> dict[str, object]:
            return dict(self._payload)

    class FakeClient:
        def __init__(self, response: FakeResponse) -> None:
            self._response = response
            self._discovery = FakeResponse(
                200,
                {
                    "authorization_endpoint": "http://issuer/protocol/openid-connect/auth",
                    "token_endpoint": "http://issuer/protocol/openid-connect/token",
                    "userinfo_endpoint": "http://issuer/protocol/openid-connect/userinfo",
                    "end_session_endpoint": "http://issuer/protocol/openid-connect/logout",
                },
            )

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, *args, **kwargs):
            return self._discovery

        async def post(self, *args, **kwargs):
            return self._response

    monkeypatch.setattr(auth_endpoints.httpx, "AsyncClient", lambda timeout=15.0: FakeClient(FakeResponse(200, {"access_token": "abc"})))
    payload = await auth_endpoints._exchange_oidc_code("http://issuer", "client", "code", "http://redirect")
    assert payload == {"access_token": "abc"}

    monkeypatch.setattr(auth_endpoints.httpx, "AsyncClient", lambda timeout=15.0: FakeClient(FakeResponse(400, {})))
    with pytest.raises(HTTPException) as error:
        await auth_endpoints._exchange_oidc_code("http://issuer", "client", "code", "http://redirect")
    assert error.value.detail == "Token exchange failed"


@pytest.mark.anyio
async def test_load_oidc_profile_uses_userinfo_and_token_fallback(
    monkeypatch,
    jwt_token_builder,
    auth_endpoint_fallback_claims: dict[str, object],
) -> None:
    class FakeResponse:
        def __init__(self, status_code: int, payload: dict[str, object]) -> None:
            self.status_code = status_code
            self._payload = payload

        def json(self) -> dict[str, object]:
            return dict(self._payload)

    class FakeClient:
        def __init__(self, response: FakeResponse) -> None:
            self._response = response
            self._discovery = FakeResponse(
                200,
                {
                    "authorization_endpoint": "http://issuer/protocol/openid-connect/auth",
                    "token_endpoint": "http://issuer/protocol/openid-connect/token",
                    "userinfo_endpoint": "http://issuer/protocol/openid-connect/userinfo",
                    "end_session_endpoint": "http://issuer/protocol/openid-connect/logout",
                },
            )

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, *args, **kwargs):
            if args and isinstance(args[0], str) and args[0].endswith("/.well-known/openid-configuration"):
                return self._discovery
            return self._response

    monkeypatch.setattr(auth_endpoints.httpx, "AsyncClient", lambda timeout=15.0: FakeClient(FakeResponse(200, {"sub": "user-1"})))
    assert await auth_endpoints._load_oidc_profile("http://issuer", "access", None) == {"sub": "user-1"}

    fallback_token = jwt_token_builder(auth_endpoint_fallback_claims)
    monkeypatch.setattr(auth_endpoints.httpx, "AsyncClient", lambda timeout=15.0: FakeClient(FakeResponse(401, {})))
    assert await auth_endpoints._load_oidc_profile("http://issuer", fallback_token, fallback_token) == {
        "sub": "fallback-user",
        "email": "fallback@example.com",
    }