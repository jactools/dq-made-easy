from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi import HTTPException
from starlette.requests import Request
from starlette.responses import Response

from app.api.v1.endpoints import auth as auth_endpoints
from app.domain.entities.admin import AdminUserEntity, UserWorkspaceRoleEntity


class _Repo:
    def __init__(self, login_user=None, oidc_error: Exception | None = None) -> None:
        self._login_user = login_user
        self._oidc_error = oidc_error

    def resolve_login_user(self, payload, sso=False):
        return self._login_user

    def find_or_create_user_from_oidc(self, profile, allow_signup, default_role):
        if self._oidc_error:
            raise self._oidc_error
        return self._login_user


class _ConfigRepo:
    def __init__(self, cfg) -> None:
        self._cfg = cfg

    def get_app_config(self):
        return self._cfg


def _config(**overrides):
    base = {
        "ssoEnabled": True,
        "ssoIssuer": "http://issuer.local/realms/demo",
        "ssoClientId": "dq-ui",
        "allowSignup": True,
        "defaultUserRole": "viewer",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


class _SessionRepo:
    def __init__(self) -> None:
        self.sessions: dict[str, dict[str, object]] = {}

    def create_session(self, sid, user_id, **kwargs):
        self.sessions[str(sid)] = {"user_id": user_id, **kwargs}

    def delete_session(self, sid):
        self.sessions.pop(str(sid), None)


def _request(path: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "headers": [],
            "query_string": b"",
            "scheme": "http",
            "server": ("testserver", 80),
            "client": ("testclient", 50000),
        }
    )


@pytest.mark.anyio
async def test_login_and_logout_paths(monkeypatch) -> None:
    user = AdminUserEntity(
        id="u1",
        first_name="Alice",
        last_name="Admin",
        email="alice@example.com",
        roles=["admin"],
        workspaces=["retail-banking", "corporate-banking"],
        workspace_roles=[
            UserWorkspaceRoleEntity(workspace_id="retail-banking", role="analyst"),
            UserWorkspaceRoleEntity(workspace_id="corporate-banking", role="data-steward"),
        ],
    )
    repo = _Repo(login_user=user)
    cfg_repo = _ConfigRepo(_config())
    session_repo = _SessionRepo()

    out = await auth_endpoints.login(
        {"email": "alice@example.com"},
        request=_request("/api/auth/v1/login"),
        response=Response(),
        repository=repo,
        config_repository=cfg_repo,
        session_repository=session_repo,
    )
    assert out.id == "u1"
    assert out.token
    assert len(out.workspace_roles) == 2
    assert out.workspace_roles[0].workspace_id == "retail-banking"

    with pytest.raises(HTTPException) as sso_disabled:
        await auth_endpoints.login(
            {"sso": True},
            request=_request("/api/auth/v1/login"),
            response=Response(),
            repository=repo,
            config_repository=_ConfigRepo(_config(ssoEnabled=False)),
            session_repository=session_repo,
        )
    assert sso_disabled.value.status_code == 400

    missing_repo = _Repo(login_user=None)
    with pytest.raises(HTTPException) as missing_local:
        await auth_endpoints.login(
            {"email": "missing@example.com"},
            request=_request("/api/auth/v1/login"),
            response=Response(),
            repository=missing_repo,
            config_repository=cfg_repo,
            session_repository=session_repo,
        )
    assert missing_local.value.detail == "User not found"

    with pytest.raises(HTTPException) as missing_sso_by_email:
        await auth_endpoints.login(
            {"sso": True, "email": "missing@example.com"},
            request=_request("/api/auth/v1/login"),
            response=Response(),
            repository=missing_repo,
            config_repository=cfg_repo,
            session_repository=session_repo,
        )
    assert missing_sso_by_email.value.detail == "SSO user not found"

    with pytest.raises(HTTPException) as missing_sso_generic:
        await auth_endpoints.login(
            {"sso": True},
            request=_request("/api/auth/v1/login"),
            response=Response(),
            repository=missing_repo,
            config_repository=cfg_repo,
            session_repository=session_repo,
        )
    assert missing_sso_generic.value.detail == "No users available for SSO"

    logout = await auth_endpoints.logout(
        request=_request("/api/auth/v1/logout"),
        response=Response(),
        config_repository=cfg_repo,
        session_repository=session_repo,
    )
    assert logout.ok is True


def test_build_local_token_does_not_infer_scope_from_role_name() -> None:
    token = auth_endpoints._build_local_token(
        {
            "id": "u1",
            "first_name": "Unknown",
            "last_name": "User",
            "email": "u1@example.com",
            "roles": ["unknown-role"],
            "granted_scopes": [],
        },
        {"ssoIssuer": "http://issuer", "ssoClientId": "client"},
    )
    claims = auth_endpoints._decode_jwt_claims(token)
    assert claims is not None
    assert str(claims.get("scope") or "") == ""


@pytest.mark.anyio
async def test_auth_redirect_and_callback_paths(monkeypatch) -> None:
    user = AdminUserEntity(
        id="u1",
        first_name="Alice",
        last_name="Admin",
        email="alice@example.com",
        roles=["admin"],
        workspaces=["default"],
    )
    with pytest.raises(HTTPException) as not_configured:
        await auth_endpoints.auth_redirect(config_repository=_ConfigRepo(_config(ssoEnabled=False)))
    assert not_configured.value.status_code == 400

    async def fake_fetch(issuer: str) -> dict[str, object]:
        return {"authorization_endpoint": f"{issuer.rstrip('/')}/protocol/openid-connect/auth"}

    monkeypatch.setattr(auth_endpoints, "_fetch_oidc_metadata", fake_fetch)
    monkeypatch.setattr(auth_endpoints, "_get_public_api_base", lambda: "https://api.example.test")

    redirect = await auth_endpoints.auth_redirect(frontend="https://frontend.local/x", config_repository=_ConfigRepo(_config()))
    assert redirect.status_code == 302
    assert "protocol/openid-connect/auth" in redirect.headers["location"]
    state = parse_qs(urlparse(redirect.headers["location"]).query)["state"][0]
    session_repo = _SessionRepo()

    with pytest.raises(HTTPException) as missing_code:
        await auth_endpoints.auth_callback(
            request=_request("/api/auth/v1/callback"),
            code=None,
            state=state,
            repository=_Repo(),
            config_repository=_ConfigRepo(_config()),
            session_repository=session_repo,
        )
    assert missing_code.value.detail == "Missing code"

    with pytest.raises(HTTPException) as invalid_state:
        await auth_endpoints.auth_callback(
            request=_request("/api/auth/v1/callback"),
            code="abc",
            state="unknown",
            repository=_Repo(),
            config_repository=_ConfigRepo(_config()),
            session_repository=session_repo,
        )
    assert invalid_state.value.detail == "Invalid state"

    async def no_token_exchange(*args, **kwargs):
        return {"id_token": "x"}

    monkeypatch.setattr(auth_endpoints, "_exchange_oidc_code", no_token_exchange)
    with pytest.raises(HTTPException) as no_access:
        await auth_endpoints.auth_callback(
            request=_request("/api/auth/v1/callback"),
            code="abc",
            state=state,
            repository=_Repo(),
            config_repository=_ConfigRepo(_config()),
            session_repository=session_repo,
        )
    assert no_access.value.detail == "No access token from provider"

    async def fake_exchange(*args, **kwargs):
        return {"access_token": "tok", "id_token": "idtok"}

    async def fake_profile(*args, **kwargs):
        return {}

    monkeypatch.setattr(auth_endpoints, "_exchange_oidc_code", fake_exchange)
    monkeypatch.setattr(auth_endpoints, "_load_oidc_profile", fake_profile)
    with pytest.raises(HTTPException) as no_profile:
        await auth_endpoints.auth_callback(
            request=_request("/api/auth/v1/callback"),
            code="abc",
            state=state,
            repository=_Repo(),
            config_repository=_ConfigRepo(_config()),
            session_repository=session_repo,
        )
    assert no_profile.value.detail == "Failed to fetch user info"

    async def ok_profile(*args, **kwargs):
        return {"sub": "u1", "email": "alice@example.com"}

    monkeypatch.setattr(auth_endpoints, "_load_oidc_profile", ok_profile)
    with pytest.raises(HTTPException) as forbidden:
        await auth_endpoints.auth_callback(
            request=_request("/api/auth/v1/callback"),
            code="abc",
            state=state,
            repository=_Repo(oidc_error=PermissionError("blocked")),
            config_repository=_ConfigRepo(_config()),
            session_repository=session_repo,
        )
    assert forbidden.value.status_code == 403

    with pytest.raises(HTTPException) as bad_request:
        await auth_endpoints.auth_callback(
            request=_request("/api/auth/v1/callback"),
            code="abc",
            state=state,
            repository=_Repo(oidc_error=ValueError("invalid")),
            config_repository=_ConfigRepo(_config()),
            session_repository=session_repo,
        )
    assert bad_request.value.status_code == 400

    response = await auth_endpoints.auth_callback(
        request=_request("/api/auth/v1/callback"),
        code="abc",
        state=state,
        repository=_Repo(login_user=user),
        config_repository=_ConfigRepo(_config()),
        session_repository=session_repo,
    )
    body = response.body.decode("utf-8")
    assert response.status_code == 200
    assert "window.location.replace" in body
    assert "auth_token" in body
    assert "tok" in body
    assert "auth_id_token" in body


@pytest.mark.anyio
async def test_auth_callback_emits_custom_spans(monkeypatch) -> None:
    calls: list[tuple[str, dict[str, object]]] = []
    user = AdminUserEntity(
        id="u1",
        first_name="Alice",
        last_name="Admin",
        email="alice@example.com",
        roles=["admin"],
        workspaces=["default"],
    )

    class _Span:
        def __init__(self, attrs: dict[str, object]) -> None:
            self.attrs = attrs

        def is_recording(self) -> bool:
            return True

        def set_attribute(self, key: str, value: object) -> None:
            self.attrs[key] = value

        def record_exception(self, exc: Exception) -> None:
            return None

        def set_status(self, status) -> None:
            return None

    @contextmanager
    def _fake_traced_span(name: str, **attrs: object):
        calls.append((name, dict(attrs)))
        yield _Span(calls[-1][1])

    async def fake_exchange(*args, **kwargs):
        return {"access_token": "tok", "id_token": "idtok"}

    async def fake_profile(*args, **kwargs):
        return {"sub": "u1", "email": "alice@example.com"}

    monkeypatch.setattr(auth_endpoints, "traced_span", _fake_traced_span)
    monkeypatch.setattr(auth_endpoints, "_exchange_oidc_code", fake_exchange)
    monkeypatch.setattr(auth_endpoints, "_load_oidc_profile", fake_profile)

    async def fake_fetch(issuer: str) -> dict[str, object]:
        return {"authorization_endpoint": f"{issuer.rstrip('/')}/protocol/openid-connect/auth"}

    monkeypatch.setattr(auth_endpoints, "_fetch_oidc_metadata", fake_fetch)
    monkeypatch.setattr(auth_endpoints, "_get_public_api_base", lambda: "https://api.example.test")

    redirect = await auth_endpoints.auth_redirect(frontend="https://frontend.local/x", config_repository=_ConfigRepo(_config()))
    state = parse_qs(urlparse(redirect.headers["location"]).query)["state"][0]
    session_repo = _SessionRepo()

    response = await auth_endpoints.auth_callback(
        request=_request("/api/auth/v1/callback"),
        code="abc",
        state=state,
        repository=_Repo(login_user=user),
        config_repository=_ConfigRepo(_config()),
        session_repository=session_repo,
    )

    assert response.status_code == 200
    assert [name for name, _ in calls] == [
        "auth.callback",
        "auth.callback.exchange_code",
        "auth.callback.load_profile",
        "auth.callback.resolve_user",
    ]
    assert calls[0][1]["endpoint_group"] == "auth"
    assert calls[0][1]["operation"] == "callback"
    assert calls[0][1]["auth_callback_state"] == "complete"
