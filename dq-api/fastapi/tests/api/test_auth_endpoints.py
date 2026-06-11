from collections.abc import Generator
from urllib.parse import parse_qs
from urllib.parse import urlparse
import asyncio
import json
import time

import pytest
from fastapi.testclient import TestClient

from app.api.v1.endpoints import auth as auth_endpoints
from app.core import dependencies
from app.core.dependencies import get_admin_repository
from app.core.dependencies import get_app_config_repository
from app.core.dependencies import get_session_repository
from app.core.config import get_settings
from app.infrastructure.repositories.in_memory_admin_repository import InMemoryAdminRepository
from app.infrastructure.repositories.in_memory_app_config_repository import InMemoryAppConfigRepository
from app.infrastructure.repositories.in_memory_sessions_repository import InMemorySessionsRepository
from app.main import app

client = TestClient(app)


def _reset_app_config_repository() -> None:
    dependencies._app_config_repository = InMemoryAppConfigRepository()


def _patch_oidc_discovery(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResponse:
        def __init__(self, status_code: int, payload: dict[str, object]) -> None:
            self.status_code = status_code
            self._payload = payload

        def json(self) -> dict[str, object]:
            return dict(self._payload)

    class FakeClient:
        def __init__(self) -> None:
            self._discovery = FakeResponse(
                200,
                {
                    "authorization_endpoint": "http://keycloak.local:8080/realms/jaccloud/protocol/openid-connect/auth",
                    "token_endpoint": "http://keycloak.local:8080/realms/jaccloud/protocol/openid-connect/token",
                    "userinfo_endpoint": "http://keycloak.local:8080/realms/jaccloud/protocol/openid-connect/userinfo",
                    "end_session_endpoint": "http://keycloak.local:8080/realms/jaccloud/protocol/openid-connect/logout",
                },
            )

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, *args, **kwargs):
            return self._discovery

    monkeypatch.setattr(auth_endpoints.httpx, "AsyncClient", lambda timeout=15.0: FakeClient())


def setup_module() -> None:
    get_settings.cache_clear()
    _reset_app_config_repository()


def teardown_module() -> None:
    get_settings.cache_clear()
    _reset_app_config_repository()


@pytest.fixture(autouse=True)
def isolated_auth_dependencies(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    app_config_repository = InMemoryAppConfigRepository()
    admin_repository = InMemoryAdminRepository()
    session_repository = InMemorySessionsRepository()

    app.dependency_overrides[get_admin_repository] = lambda: admin_repository
    app.dependency_overrides[get_app_config_repository] = lambda: app_config_repository
    app.dependency_overrides[get_session_repository] = lambda: session_repository
    monkeypatch.setattr(dependencies, "get_app_config_repository", lambda: app_config_repository)
    monkeypatch.setenv("OIDC_REDIRECT_BASE_URL", "http://dq-made-easy.local:9111")

    yield

    app.dependency_overrides.pop(get_admin_repository, None)
    app.dependency_overrides.pop(get_app_config_repository, None)
    app.dependency_overrides.pop(get_session_repository, None)


def test_login_returns_local_token_for_known_user(monkeypatch) -> None:
    _reset_app_config_repository()
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.post("/api/auth/v1/login", json={"email": "admin@example.com"})

    assert response.status_code == 200
    assert "dq_session=" in response.headers.get("set-cookie", "")
    payload = response.json()
    assert payload["id"] == "user-admin"
    assert payload["token"].count(".") == 2
    assert sorted(payload["workspaces"]) == ["default", "retail-banking"]


def test_login_returns_not_found_for_missing_user(monkeypatch) -> None:
    _reset_app_config_repository()
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.post("/auth/v1/login", json={"email": "missing@example.com"})

    assert response.status_code == 404
    assert response.json()["detail"] == "User not found"


def test_login_supports_sso_shortcut_when_enabled(monkeypatch) -> None:
    _reset_app_config_repository()
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.post("/api/auth/v1/login", json={"sso": True, "email": "analyst@example.com"})

    assert response.status_code == 200
    assert response.json()["id"] == "user-analyst"


def test_login_rejects_sso_when_not_configured(monkeypatch) -> None:
    _reset_app_config_repository()
    monkeypatch.delenv("SSO_ENABLED", raising=False)
    monkeypatch.delenv("SSO_PUBLIC_ISSUER_URL", raising=False)
    monkeypatch.delenv("SSO_CLIENT_ID", raising=False)
    get_settings.cache_clear()

    response = client.post("/api/auth/v1/login", json={"sso": True})

    assert response.status_code == 400
    assert response.json()["detail"] == "SSO not enabled"


def test_logout_returns_ok_without_auth(monkeypatch) -> None:
    _reset_app_config_repository()
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.post("/api/auth/v1/logout")

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_auth_redirect_returns_provider_url(monkeypatch) -> None:
    _reset_app_config_repository()
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    monkeypatch.setenv("OIDC_REDIRECT_BASE_URL", "http://dq-made-easy.local:9111")
    get_settings.cache_clear()
    _patch_oidc_discovery(monkeypatch)

    response = client.get(
        "/api/auth/v1/redirect?frontend=http://localhost:5173",
        follow_redirects=False,
    )

    assert response.status_code == 302
    location = response.headers["location"]
    parsed = urlparse(location)
    query = parse_qs(parsed.query)
    assert parsed.path.endswith("/protocol/openid-connect/auth")
    assert query["client_id"] == ["dq-rules-ui"]
    assert query["redirect_uri"] == ["http://dq-made-easy.local:9111/auth/v1/callback"]
    assert query["scope"] == ["openid profile email"]
    assert "state" in query


def test_auth_redirect_rewrites_public_hostname_and_port_from_internal_discovery(monkeypatch) -> None:
    _reset_app_config_repository()
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "https://keycloak.jac.dot:9444/realms/jaccloud")
    monkeypatch.setenv("SSO_INTERNAL_ISSUER_URL", "http://keycloak:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    monkeypatch.setenv("OIDC_REDIRECT_BASE_URL", "http://dq-made-easy.local:9111")
    get_settings.cache_clear()

    async def fake_fetch(backend_issuer: str) -> dict[str, object]:
        if backend_issuer == "https://keycloak.jac.dot:9444/realms/jaccloud":
            raise auth_endpoints.HTTPException(status_code=503, detail="OIDC discovery failed")
        if backend_issuer == "http://keycloak:8080/realms/jaccloud":
            return {
                "authorization_endpoint": "http://keycloak.jac.dot:8080/realms/jaccloud/protocol/openid-connect/auth",
                "token_endpoint": "http://keycloak.jac.dot:8080/realms/jaccloud/protocol/openid-connect/token",
                "userinfo_endpoint": "http://keycloak.jac.dot:8080/realms/jaccloud/protocol/openid-connect/userinfo",
            }
        raise AssertionError(f"Unexpected issuer: {backend_issuer}")

    monkeypatch.setattr(auth_endpoints, "_fetch_oidc_metadata", fake_fetch)

    response = client.get(
        "/api/auth/v1/redirect?frontend=http://localhost:5173",
        follow_redirects=False,
    )

    assert response.status_code == 302
    location = response.headers["location"]
    assert location.startswith("https://keycloak.jac.dot:9444/realms/jaccloud/protocol/openid-connect/auth")


def test_auth_redirect_fails_fast_when_oidc_discovery_raises(monkeypatch) -> None:
    _reset_app_config_repository()
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    monkeypatch.setenv("OIDC_REDIRECT_BASE_URL", "http://dq-made-easy.local:9111")
    get_settings.cache_clear()

    async def fake_fetch(_issuer: str) -> dict[str, object]:
        raise auth_endpoints.HTTPException(status_code=503, detail="OIDC discovery failed")

    monkeypatch.setattr(auth_endpoints, "_fetch_oidc_metadata", fake_fetch)

    response = client.get("/api/auth/v1/redirect?frontend=http://localhost:5173", follow_redirects=False)

    assert response.status_code == 503
    assert response.json()["detail"] == "OIDC discovery failed"


def test_logout_redirect_fails_fast_when_oidc_discovery_raises(monkeypatch) -> None:
    _reset_app_config_repository()
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    monkeypatch.setenv("OIDC_REDIRECT_BASE_URL", "http://dq-made-easy.local:9111")
    get_settings.cache_clear()

    async def fake_fetch(_issuer: str) -> dict[str, object]:
        raise auth_endpoints.HTTPException(status_code=503, detail="OIDC discovery failed")

    monkeypatch.setattr(auth_endpoints, "_fetch_oidc_metadata", fake_fetch)

    response = client.get("/api/auth/v1/logout?frontend=http://localhost:5173", follow_redirects=False)

    assert response.status_code == 503
    assert response.json()["detail"] == "OIDC discovery failed"


def test_auth_redirect_prefers_explicit_public_callback_base(monkeypatch) -> None:
    _reset_app_config_repository()
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    monkeypatch.setenv("OIDC_REDIRECT_BASE_URL", "https://api.example.test")
    get_settings.cache_clear()
    _patch_oidc_discovery(monkeypatch)

    response = client.get(
        "/api/auth/v1/redirect?frontend=http://localhost:5173",
        follow_redirects=False,
    )

    assert response.status_code == 302
    location = response.headers["location"]
    parsed = urlparse(location)
    query = parse_qs(parsed.query)
    assert parsed.path.endswith("/protocol/openid-connect/auth")
    assert query["redirect_uri"] == ["https://api.example.test/auth/v1/callback"]


def test_auth_callback_sets_session_cookie_and_redirects_frontend(monkeypatch) -> None:
    _reset_app_config_repository()
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    monkeypatch.setenv("OIDC_REDIRECT_BASE_URL", "http://dq-made-easy.local:9111")
    get_settings.cache_clear()
    _patch_oidc_discovery(monkeypatch)

    redirect_response = client.get(
        "/api/auth/v1/redirect?frontend=http://localhost:5173",
        follow_redirects=False,
    )
    state = parse_qs(urlparse(redirect_response.headers["location"]).query)["state"][0]

    async def fake_exchange(*args, **kwargs):
        return {
            "access_token": "provider.access.token",
            "id_token": "provider.id.token",
            "refresh_token": "refresh-token-1",
        }

    async def fake_profile(*args, **kwargs):
        return {
            "sub": "oidc-123",
            "email": "new.user@example.com",
            "preferred_username": "new.user",
            "name": "New User",
        }

    monkeypatch.setattr(auth_endpoints, "_build_local_token", lambda *args, **kwargs: "local.app.token")

    monkeypatch.setattr(auth_endpoints, "_exchange_oidc_code", fake_exchange)
    monkeypatch.setattr(auth_endpoints, "_load_oidc_profile", fake_profile)

    response = client.get(
        f"/api/auth/v1/callback?code=auth-code&state={state}",
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert "dq_session=" in response.headers.get("set-cookie", "")
    assert "window.location.replace" in response.text
    assert 'const frontendOrigin = "http://localhost:5173/"' in response.text
    assert "provider.access.token" in response.text
    assert "local.app.token" not in response.text


def test_auth_callback_rejects_invalid_state(monkeypatch) -> None:
    _reset_app_config_repository()
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    monkeypatch.setenv("OIDC_REDIRECT_BASE_URL", "http://dq-made-easy.local:9111")
    get_settings.cache_clear()

    response = client.get("/api/auth/v1/callback?code=auth-code&state=missing")

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid state"


def test_auth_redirect_rejects_missing_sso_configuration(monkeypatch) -> None:
    _reset_app_config_repository()
    monkeypatch.delenv("SSO_ENABLED", raising=False)
    monkeypatch.delenv("SSO_PUBLIC_ISSUER_URL", raising=False)
    monkeypatch.delenv("SSO_CLIENT_ID", raising=False)
    get_settings.cache_clear()

    response = client.get("/api/auth/v1/redirect", follow_redirects=False)

    assert response.status_code == 400
    assert response.json()["detail"] == "SSO not configured"


def test_auth_callback_requires_access_token(monkeypatch) -> None:
    _reset_app_config_repository()
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    monkeypatch.setenv("OIDC_REDIRECT_BASE_URL", "http://dq-made-easy.local:9111")
    get_settings.cache_clear()
    _patch_oidc_discovery(monkeypatch)

    redirect_response = client.get(
        "/api/auth/v1/redirect?frontend=http://localhost:5173",
        follow_redirects=False,
    )
    state = parse_qs(urlparse(redirect_response.headers["location"]).query)["state"][0]

    async def fake_exchange(*args, **kwargs):
        return {"id_token": "header.payload.signature"}

    monkeypatch.setattr(auth_endpoints, "_exchange_oidc_code", fake_exchange)

    response = client.get(
        f"/api/auth/v1/callback?code=auth-code&state={state}",
        follow_redirects=False,
    )

    assert response.status_code == 500
    assert response.json()["detail"] == "No access token from provider"


def test_auth_callback_rejects_disabled_signup(monkeypatch) -> None:
    _reset_app_config_repository()
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    monkeypatch.setenv("OIDC_REDIRECT_BASE_URL", "http://dq-made-easy.local:9111")
    get_settings.cache_clear()
    _patch_oidc_discovery(monkeypatch)

    config_repository = dependencies.get_app_config_repository()
    config_repository.set_app_config({"allowSignup": False})

    redirect_response = client.get(
        "/api/auth/v1/redirect?frontend=http://localhost:5173",
        follow_redirects=False,
    )
    state = parse_qs(urlparse(redirect_response.headers["location"]).query)["state"][0]

    async def fake_exchange(*args, **kwargs):
        return {"access_token": "header.payload.signature", "id_token": "header.payload.signature"}

    async def fake_profile(*args, **kwargs):
        return {
            "sub": "oidc-404",
            "email": "signup.blocked@example.com",
            "preferred_username": "signup.blocked",
        }

    monkeypatch.setattr(auth_endpoints, "_exchange_oidc_code", fake_exchange)
    monkeypatch.setattr(auth_endpoints, "_load_oidc_profile", fake_profile)

    response = client.get(
        f"/api/auth/v1/callback?code=auth-code&state={state}",
        follow_redirects=False,
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "User signup is disabled"


def test_decode_jwt_claims_returns_none_for_invalid_payload() -> None:
    assert auth_endpoints._decode_jwt_claims("header.bad-payload.signature") is None


def test_normalize_frontend_origin_rejects_non_http_values() -> None:
    assert auth_endpoints._normalize_frontend_origin("ftp://example.com") is None
    assert auth_endpoints._normalize_frontend_origin("localhost:5173") is None


def test_build_backend_issuer_handles_parser_exception(monkeypatch) -> None:
    def _raise(_: str):
        raise ValueError("boom")

    monkeypatch.setattr(auth_endpoints, "urlparse", _raise)
    assert auth_endpoints._build_backend_issuer("https://issuer.example/realm") == "https://issuer.example/realm"


def test_build_backend_issuer_uses_canonical_internal_issuer(monkeypatch) -> None:
    monkeypatch.setenv("SSO_INTERNAL_ISSUER_URL", "http://keycloak:8080/iam/realms/jaccloud")

    assert (
        auth_endpoints._build_backend_issuer("https://dq-made-easy.nl/iam/realms/jaccloud")
        == "http://keycloak:8080/iam/realms/jaccloud"
    )


def test_rewrite_oidc_endpoint_to_backend_preserves_discovered_endpoint_path() -> None:
    assert auth_endpoints._rewrite_oidc_endpoint_to_backend(
        "http://dq-made-easy.nl:8080/iam/realms/jaccloud/protocol/openid-connect/token",
        "http://keycloak:8080/iam/realms/jaccloud",
    ) == "http://keycloak:8080/iam/realms/jaccloud/protocol/openid-connect/token"


def test_serialize_login_user_adds_granted_scopes_and_workspace(monkeypatch) -> None:
    class _DummyUser:
        granted_scopes = ["dq:rules:read"]

        @staticmethod
        def model_dump() -> dict:
            return {
                "id": "user-x",
                "email": "user@example.com",
                "name": "User X",
                "workspaces": ["retail-banking", "default"],
            }

    payload = auth_endpoints._serialize_login_user(_DummyUser(), "token-123")
    assert sorted(payload["workspaces"]) == ["default", "retail-banking"]
    assert payload["workspace"] == "retail-banking"
    assert payload["granted_scopes"] == ["dq:rules:read"]
    assert payload["token"] == "token-123"


def test_auth_logout_redirect_returns_frontend_when_sso_not_configured(monkeypatch) -> None:
    _reset_app_config_repository()
    monkeypatch.delenv("SSO_ENABLED", raising=False)
    monkeypatch.delenv("SSO_PUBLIC_ISSUER_URL", raising=False)
    monkeypatch.delenv("SSO_CLIENT_ID", raising=False)
    get_settings.cache_clear()

    response = client.get("/api/auth/v1/logout?frontend=http://localhost:5173", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"] == "http://localhost:5173"


def test_auth_logout_redirect_includes_id_token_hint_when_present(monkeypatch) -> None:
    _reset_app_config_repository()
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    _patch_oidc_discovery(monkeypatch)
    get_settings.cache_clear()

    response = client.get(
        "/api/auth/v1/logout?id_token=abc.def.ghi&frontend=http://localhost:5173",
        follow_redirects=False,
    )

    assert response.status_code == 302
    location = response.headers["location"]
    query = parse_qs(urlparse(location).query)
    assert query["client_id"] == ["dq-rules-ui"]
    assert query["post_logout_redirect_uri"] == ["http://localhost:5173"]
    assert query["id_token_hint"] == ["abc.def.ghi"]


def test_auth_callback_rejects_missing_state(monkeypatch) -> None:
    _reset_app_config_repository()
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.get("/api/auth/v1/callback?code=auth-code")

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid state"


def test_auth_callback_rejects_expired_state(monkeypatch) -> None:
    _reset_app_config_repository()
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    expired_issued_at = int(time.time() * 1000) - (11 * 60 * 1000)
    state = auth_endpoints._to_base64_url(
        json.dumps(
            {
                "nonce": f"{expired_issued_at}-0.1",
                "issuedAt": expired_issued_at,
                "frontendOrigin": "http://localhost:5173",
            }
        )
    )

    response = client.get(f"/api/auth/v1/callback?code=auth-code&state={state}")

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid state"


def test_auth_callback_rejects_when_sso_config_missing_after_state_validation(monkeypatch) -> None:
    _reset_app_config_repository()
    monkeypatch.delenv("SSO_ENABLED", raising=False)
    monkeypatch.delenv("SSO_PUBLIC_ISSUER_URL", raising=False)
    monkeypatch.delenv("SSO_CLIENT_ID", raising=False)
    get_settings.cache_clear()

    issued_at = int(time.time() * 1000)
    state = auth_endpoints._to_base64_url(
        json.dumps(
            {
                "nonce": f"{issued_at}-0.2",
                "issuedAt": issued_at,
                "frontendOrigin": "http://localhost:5173",
            }
        )
    )
    response = client.get(f"/api/auth/v1/callback?code=auth-code&state={state}")

    assert response.status_code == 400
    assert response.json()["detail"] == "SSO not configured"


def test_auth_callback_redirect_omits_id_token_when_provider_does_not_return_it(monkeypatch) -> None:
    _reset_app_config_repository()
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()
    _patch_oidc_discovery(monkeypatch)

    redirect_response = client.get(
        "/api/auth/v1/redirect?frontend=http://localhost:5173",
        follow_redirects=False,
    )
    state = parse_qs(urlparse(redirect_response.headers["location"]).query)["state"][0]

    async def fake_exchange(*args, **kwargs):
        return {"access_token": "header.payload.signature"}

    async def fake_profile(*args, **kwargs):
        return {
            "sub": "oidc-123",
            "email": "new.user@example.com",
            "preferred_username": "new.user",
            "name": "New User",
        }

    monkeypatch.setattr(auth_endpoints, "_exchange_oidc_code", fake_exchange)
    monkeypatch.setattr(auth_endpoints, "_load_oidc_profile", fake_profile)

    response = client.get(
        f"/api/auth/v1/callback?code=auth-code&state={state}",
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert "dq_session=" in response.headers.get("set-cookie", "")
    assert 'const frontendOrigin = "http://localhost:5173/"' in response.text


def test_auth_refresh_requires_refresh_token(monkeypatch) -> None:
    _reset_app_config_repository()
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.post("/api/auth/v1/refresh", json={})

    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "refresh_token_required"


def test_auth_refresh_returns_new_tokens(monkeypatch) -> None:
    _reset_app_config_repository()
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    async def fake_refresh(*args, **kwargs):
        return {"access_token": "new-access", "refresh_token": "new-refresh"}

    monkeypatch.setattr(auth_endpoints, "_refresh_oidc_token", fake_refresh)

    response = client.post("/api/auth/v1/refresh", json={"refresh_token": "refresh-token-1"})

    assert response.status_code == 200
    body = response.json()
    assert body["token"] == "new-access"
    assert body["refresh_token"] == "new-refresh"


def test_refresh_uses_client_secret_when_configured(monkeypatch) -> None:
    _reset_app_config_repository()
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    monkeypatch.setenv("KEYCLOAK_CLIENT_SECRET", "super-secret")
    get_settings.cache_clear()

    class FakeResponse:
        def __init__(self, status_code: int, payload: dict[str, object]) -> None:
            self.status_code = status_code
            self._payload = payload

        def json(self) -> dict[str, object]:
            return dict(self._payload)

    class FakeClient:
        def __init__(self) -> None:
            self.sent_content = None

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, *args, **kwargs):
            self.sent_content = kwargs.get("content")
            return FakeResponse(200, {"access_token": "new-access"})

    async def fake_fetch(backend_issuer: str) -> dict[str, object]:
        return {"token_endpoint": "http://keycloak.local:8080/realms/jaccloud/protocol/openid-connect/token"}

    fake_client = FakeClient()
    monkeypatch.setattr(auth_endpoints, "_fetch_oidc_metadata", fake_fetch)
    monkeypatch.setattr(auth_endpoints.httpx, "AsyncClient", lambda timeout=15.0: fake_client)

    result = asyncio.run(
        auth_endpoints._refresh_oidc_token(
            "http://keycloak.local:8080/realms/jaccloud",
            "dq-rules-ui",
            "refresh-token-1",
        )
    )

    assert result is not None
    assert "client_secret=super-secret" in fake_client.sent_content


def test_exchange_code_uses_client_secret_when_configured(monkeypatch) -> None:
    _reset_app_config_repository()
    monkeypatch.setenv("KEYCLOAK_CLIENT_SECRET", "super-secret")

    class FakeResponse:
        def __init__(self, status_code: int, payload: dict[str, object]) -> None:
            self.status_code = status_code
            self._payload = payload

        def json(self) -> dict[str, object]:
            return dict(self._payload)

    class FakeClient:
        def __init__(self) -> None:
            self.sent_content = None

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, *args, **kwargs):
            self.sent_content = kwargs.get("content")
            return FakeResponse(200, {"access_token": "new-access"})

    async def fake_fetch(backend_issuer: str) -> dict[str, object]:
        return {"token_endpoint": "http://keycloak.local:8080/realms/jaccloud/protocol/openid-connect/token"}

    fake_client = FakeClient()
    monkeypatch.setattr(auth_endpoints, "_fetch_oidc_metadata", fake_fetch)
    monkeypatch.setattr(auth_endpoints.httpx, "AsyncClient", lambda timeout=15.0: fake_client)

    result = asyncio.run(
        auth_endpoints._exchange_oidc_code(
            "http://keycloak.local:8080/realms/jaccloud",
            "dq-rules-ui",
            "code-123",
            "http://dq-made-easy.local/auth/v1/callback",
        )
    )

    assert result is not None
    assert "client_secret=super-secret" in fake_client.sent_content


def test_auth_refresh_fails_fast_when_sso_is_not_configured(monkeypatch) -> None:
    _reset_app_config_repository()
    monkeypatch.setenv("SSO_ENABLED", "false")
    monkeypatch.delenv("SSO_PUBLIC_ISSUER_URL", raising=False)
    monkeypatch.delenv("SSO_CLIENT_ID", raising=False)
    get_settings.cache_clear()

    response = client.post("/api/auth/v1/refresh", json={"refresh_token": "refresh-token-1"})

    assert response.status_code == 501
    assert response.json()["detail"]["error"] == "refresh_not_supported"