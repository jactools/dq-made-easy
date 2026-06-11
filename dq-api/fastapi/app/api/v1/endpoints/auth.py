from __future__ import annotations

import base64
import json
import logging
import os
import random
import re
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote
from urllib.parse import urlencode
from urllib.parse import urlparse
from urllib.parse import urlunparse

import httpx
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse

from app.api.v1.schemas import LoginResponseView, LogoutResponseView
from app.application.resolvers import resolve_login_response_view
from app.core.auth import SESSION_COOKIE_NAME, expand_granted_scopes
from app.core.auth_login_metrics import record_login_event
from app.core.config import get_settings
from app.core.dependencies import get_admin_repository
from app.core.dependencies import get_app_config_repository
from app.core.dependencies import get_session_repository
from app.core.log_event import log_event
from app.core.telemetry import set_span_attributes, traced_span
from app.api.presenters.auth import (
    build_oidc_state_entity,
    build_oidc_token_response_entity,
    normalize_auth_frontend_origin,
)
from app.domain.entities.admin import AdminUserEntity
from app.domain.entities.app_config import AppConfigEntity
from app.domain.interfaces import AdminRepository
from app.domain.interfaces import AppConfigRepository
from app.domain.user_names import compose_user_display_name
from app.domain.interfaces.v1.session_repository import SessionRepository

router = APIRouter(tags=["auth"])
_log = logging.getLogger(__name__)


def _to_base64_url(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode("utf-8")).decode("utf-8").rstrip("=")


def _from_base64_url(value: str) -> str:
    padding = "=" * ((4 - (len(value) % 4)) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}").decode("utf-8")


def _decode_jwt_claims(token: str | None) -> dict[str, Any] | None:
    if not token:
        return None
    parts = str(token).split(".")
    if len(parts) < 2:
        return None
    try:
        return json.loads(_from_base64_url(parts[1]))
    except Exception:
        return None


def _normalize_frontend_origin(value: str | None) -> str | None:
    return normalize_auth_frontend_origin(value)


def _normalize_issuer_url(value: str | None) -> str:
    normalized = str(value or '').strip().rstrip('/')
    if not normalized:
        return normalized

    normalized = re.sub(r'^(https?)://(https?)//', r'\2://', normalized, count=1)
    normalized = re.sub(r'^(https?)://(https?)://', r'\2://', normalized, count=1)
    normalized = re.sub(r'^(https?)//', r'\1://', normalized, count=1)
    return normalized


def _join_issuer_path(base_path: str, suffix_path: str) -> str:
    normalized_base = base_path.rstrip('/') or '/'
    normalized_suffix = suffix_path.lstrip('/')
    if not normalized_suffix:
        return normalized_base
    if normalized_base == '/':
        return f'/{normalized_suffix}'
    return f'{normalized_base}/{normalized_suffix}'


def _decode_oidc_state(state: str) -> dict[str, str | None]:
    try:
        parsed = json.loads(_from_base64_url(state))
    except Exception:
        parsed = {}
    entity = build_oidc_state_entity(parsed)
    return entity.model_dump() if entity is not None else {
        "nonce": "",
        "issuedAt": None,
        "frontendOrigin": None,
    }


def _get_public_api_base() -> str:
    configured = str(
        os.getenv("OIDC_REDIRECT_BASE_URL")
        or os.getenv("KONG_PUBLIC_URL")
        or ""
    ).strip()

    if not configured:
        raise RuntimeError(
            "Missing public API base URL: set OIDC_REDIRECT_BASE_URL (preferred) or KONG_PUBLIC_URL"
        )

    return configured.rstrip("/")


def _request_is_secure(request: Request) -> bool:
    forwarded_proto = str(request.headers.get("x-forwarded-proto") or "").strip().lower()
    if forwarded_proto:
        return forwarded_proto == "https"
    return request.url.scheme == "https"


def _token_expiry_datetime(token: str | None) -> datetime | None:
    claims = _decode_jwt_claims(token)
    exp = claims.get("exp") if isinstance(claims, dict) else None
    try:
        exp_int = int(exp)
    except Exception:
        return None
    if exp_int <= 0:
        return None
    # Keep DB storage naive-UTC for now (matches existing schema), but avoid
    # deprecated utcfromtimestamp().
    return datetime.fromtimestamp(exp_int, tz=timezone.utc).replace(tzinfo=None)


def _build_local_token(user: AdminUserEntity | dict[str, Any], config: AppConfigEntity | dict[str, Any], session_id: str | None = None) -> str:
    settings = get_settings()
    if isinstance(user, dict):
        roles = [str(role).strip() for role in user.get("roles", []) if str(role).strip()]
        granted = [str(scope).strip() for scope in user.get("granted_scopes", []) if str(scope).strip()]
        user_id = str(user.get("id") or "")
        first_name = user.get("first_name")
        last_name = user.get("last_name")
        user_email = str(user.get("email") or "").strip()
    else:
        roles = [str(role).strip() for role in user.roles if str(role).strip()]
        granted = [str(scope).strip() for scope in user.granted_scopes if str(scope).strip()]
        user_id = str(user.id or "")
        first_name = user.first_name
        last_name = user.last_name
        user_email = str(user.email or "").strip()

    user_name = compose_user_display_name(first_name, last_name, fallback=user_email or user_id or "user")

    if isinstance(config, dict):
        issuer_value = _normalize_issuer_url(config.get("ssoIssuer") or settings.sso_issuer or "http://local-auth.invalid")
        client_id_value = str(config.get("ssoClientId") or settings.sso_client_id or "dq-rules-ui")
    else:
        issuer_value = _normalize_issuer_url(config.ssoIssuer or settings.sso_issuer or "http://local-auth.invalid")
        client_id_value = str(config.ssoClientId or settings.sso_client_id or "dq-rules-ui")

    scope_value = " ".join(sorted(expand_granted_scopes(granted)))
    now = int(time.time())
    email = user_email
    preferred_username = email.split("@", 1)[0] if "@" in email else str(user_name or user_id or "user")
    payload = {
        "sub": user_id,
        "email": email or None,
        "name": user_name,
        "preferred_username": preferred_username,
        "iss": issuer_value,
        "aud": [client_id_value],
        "scope": scope_value,
        "roles": roles,
        "iat": now,
        "exp": now + 8 * 60 * 60,
    }
    if session_id:
        payload["sid"] = session_id
    header = {"alg": "none", "typ": "JWT"}
    return f"{_to_base64_url(json.dumps(header))}.{_to_base64_url(json.dumps(payload))}.signature"


def _serialize_login_user(user: AdminUserEntity, token: str) -> dict[str, Any]:
    result = user.model_dump()
    workspaces = result.get("workspaces")
    if isinstance(workspaces, list):
        workspace_values = [str(item).strip() for item in workspaces if str(item).strip()]
        result["workspaces"] = workspace_values
        if workspace_values and "workspace" not in result:
            result["workspace"] = workspace_values[0]
    elif isinstance(workspaces, str):
        workspace_values = [item.strip() for item in workspaces.split(";") if item and item.strip()]
        result["workspaces"] = workspace_values
        if workspace_values and "workspace" not in result:
            result["workspace"] = workspace_values[0]
    # Ensure granted_scopes is always present so the frontend doesn't need to
    # parse the JWT to discover what the user is allowed to do.
    if "granted_scopes" not in result:
        result["granted_scopes"] = list(user.granted_scopes)
    result["token"] = token
    return result


def _extract_login_role_sources(user: AdminUserEntity) -> list[str]:
    role_sources = [str(role).strip() for role in user.roles if str(role).strip()]
    role_sources.extend(str(role.role).strip() for role in user.workspace_roles if str(role.role).strip())
    return role_sources


def _build_auth_callback_html(
    frontend_origin: str,
    auth_token: str,
    id_token: str | None,
    refresh_token: str | None,
) -> str:
    auth_payload = {
        "auth_token": auth_token,
        "auth_id_token": id_token or "",
        "refresh_token": refresh_token or "",
    }
    safe_payload = json.dumps(auth_payload)
    safe_frontend_origin = json.dumps(frontend_origin.rstrip("/") + "/")
    return f"""<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\"/>
  <title>Signing in...</title>
</head>
<body>
  <script>
    const tokens = {safe_payload};
    const frontendOrigin = {safe_frontend_origin};
    const params = new URLSearchParams();
    if (tokens.auth_token) params.set("auth_token", tokens.auth_token);
    if (tokens.auth_id_token) params.set("auth_id_token", tokens.auth_id_token);
    if (tokens.refresh_token) params.set("refresh_token", tokens.refresh_token);
    const redirectUrl = frontendOrigin + "?" + params.toString();
    window.location.replace(redirectUrl);
  </script>
  <noscript>
    <p>Signing in... Please enable JavaScript.</p>
  </noscript>
</body>
</html>"""


def _build_backend_issuer(issuer: str) -> str:
    normalized = _normalize_issuer_url(issuer)
    internal_base = _normalize_issuer_url(os.getenv("SSO_INTERNAL_ISSUER_URL"))
    try:
        parsed = urlparse(normalized)
    except Exception:
        return normalized

    if internal_base:
        return internal_base.rstrip("/")
    if parsed.hostname in {"localhost", "127.0.0.1"}:
        return f"{parsed.scheme}://keycloak:{parsed.port or 8080}{parsed.path}"
    return normalized


async def _fetch_oidc_metadata(backend_issuer: str) -> dict[str, Any]:
    discovery_url = f"{backend_issuer.rstrip('/')}/.well-known/openid-configuration"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(discovery_url)
    except httpx.RequestError as exc:
        raise HTTPException(status_code=503, detail="OIDC discovery failed") from exc

    if response.status_code >= 400:
        raise HTTPException(status_code=503, detail="OIDC discovery failed")
    json_body = response.json()
    if not isinstance(json_body, dict):
        raise HTTPException(status_code=503, detail="OIDC discovery returned invalid metadata")
    return json_body


def _require_oidc_endpoint(metadata: dict[str, Any], key: str) -> str:
    endpoint = metadata.get(key)
    if isinstance(endpoint, str) and endpoint.strip():
        return endpoint.strip()
    raise HTTPException(status_code=503, detail=f"OIDC discovery metadata missing {key}")


def _rewrite_oidc_endpoint_to_public(endpoint: str, backend_issuer: str, public_issuer: str) -> str:
    try:
        endpoint = _normalize_issuer_url(endpoint)
        backend_issuer = _normalize_issuer_url(backend_issuer)
        public_issuer = _normalize_issuer_url(public_issuer)
        parsed_endpoint = urlparse(endpoint)
        parsed_backend = urlparse(backend_issuer)
        parsed_public = urlparse(public_issuer)
    except Exception:
        return endpoint

    if not parsed_endpoint.scheme or not parsed_endpoint.netloc:
        return endpoint

    backend_path = parsed_backend.path.rstrip('/') or '/'
    if parsed_endpoint.path.startswith(backend_path):
        relative_path = parsed_endpoint.path[len(backend_path):]
        return urlunparse(
            parsed_public._replace(
                path=_join_issuer_path(parsed_public.path, relative_path),
                params=parsed_endpoint.params,
                query=parsed_endpoint.query,
                fragment=parsed_endpoint.fragment,
            )
        )

    if parsed_endpoint.hostname == parsed_public.hostname and parsed_endpoint.netloc != parsed_public.netloc:
        return urlunparse(
            parsed_public._replace(
                path=parsed_endpoint.path,
                params=parsed_endpoint.params,
                query=parsed_endpoint.query,
                fragment=parsed_endpoint.fragment,
            )
        )

    return endpoint


def _rewrite_oidc_endpoint_to_backend(endpoint: str, backend_issuer: str) -> str:
    try:
        endpoint = _normalize_issuer_url(endpoint)
        backend_issuer = _normalize_issuer_url(backend_issuer)
        parsed_endpoint = urlparse(endpoint)
        parsed_backend = urlparse(backend_issuer)
    except Exception:
        return endpoint

    if not parsed_endpoint.scheme or not parsed_endpoint.netloc:
        return endpoint

    backend_path = parsed_backend.path.rstrip('/') or '/'
    if parsed_endpoint.path.startswith(backend_path):
        relative_path = parsed_endpoint.path[len(backend_path):]
        return urlunparse(
            parsed_backend._replace(
                path=_join_issuer_path(parsed_backend.path, relative_path),
                params=parsed_endpoint.params,
                query=parsed_endpoint.query,
                fragment=parsed_endpoint.fragment,
            )
        )

    return endpoint


def _get_oidc_client_secret() -> str | None:
    secret = str(os.getenv("SSO_CLIENT_SECRET") or os.getenv("KEYCLOAK_CLIENT_SECRET") or "").strip()
    return secret or None


async def _exchange_oidc_code(
    backend_issuer: str,
    client_id: str,
    code: str,
    redirect_uri: str,
) -> dict[str, Any]:
    metadata = await _fetch_oidc_metadata(backend_issuer)
    token_endpoint = _require_oidc_endpoint(
        metadata,
        "token_endpoint",
    )
    token_endpoint = _rewrite_oidc_endpoint_to_backend(token_endpoint, backend_issuer)
    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
    }
    client_secret = _get_oidc_client_secret()
    if client_secret:
        payload["client_secret"] = client_secret

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            token_endpoint,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            content=urlencode(payload),
        )
    if response.status_code >= 400:
        raise HTTPException(status_code=500, detail="Token exchange failed")
    return response.json()


async def _refresh_oidc_token(
    backend_issuer: str,
    client_id: str,
    refresh_token: str,
) -> dict[str, Any]:
    metadata = await _fetch_oidc_metadata(backend_issuer)
    token_endpoint = _require_oidc_endpoint(
        metadata,
        "token_endpoint",
    )
    token_endpoint = _rewrite_oidc_endpoint_to_backend(token_endpoint, backend_issuer)
    payload = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
    }
    client_secret = _get_oidc_client_secret()
    if client_secret:
        payload["client_secret"] = client_secret

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            token_endpoint,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            content=urlencode(payload),
        )
    if response.status_code >= 400:
        raise HTTPException(status_code=401, detail="Refresh token exchange failed")
    return response.json()


async def _load_oidc_profile(backend_issuer: str, access_token: str, id_token: str | None) -> dict[str, Any] | None:
    metadata = await _fetch_oidc_metadata(backend_issuer)
    userinfo_url = _require_oidc_endpoint(
        metadata,
        "userinfo_endpoint",
    )
    userinfo_url = _rewrite_oidc_endpoint_to_backend(userinfo_url, backend_issuer)
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(
            userinfo_url,
            headers={"Authorization": f"Bearer {access_token}"},
        )
    if response.status_code < 400:
        payload = response.json()
        return payload if isinstance(payload, dict) else None
    return _decode_jwt_claims(id_token) or _decode_jwt_claims(access_token)


@router.post("/login", response_model=LoginResponseView)
async def login(
    payload: dict[str, Any],
    request: Request,
    response: Response,
    repository: AdminRepository = Depends(get_admin_repository),
    config_repository: AppConfigRepository = Depends(get_app_config_repository),
    session_repository: SessionRepository = Depends(get_session_repository),
) -> LoginResponseView:
    log_event(_log, "auth.login.start", component="auth-api", sso=bool(payload.get("sso")))
    config = config_repository.get_app_config()
    sso = bool(payload.get("sso"))
    if sso and not config.ssoEnabled:
        log_event(_log, "auth.login.sso_disabled", level="warning", component="auth-api")
        raise HTTPException(status_code=400, detail="SSO not enabled")

    user = repository.resolve_login_user(payload, sso=sso)
    if user is None:
        log_event(_log, "auth.login.user_not_found", level="warning", component="auth-api", sso=sso)
        if sso and payload.get("email"):
            raise HTTPException(status_code=404, detail="SSO user not found")
        if sso:
            raise HTTPException(status_code=404, detail="No users available for SSO")
        raise HTTPException(status_code=404, detail="User not found")

    # Create a server session and set an HttpOnly cookie so the UI can
    # use a classic web-app flow (token stored server-side).
    session_repo = session_repository
    sid = str(uuid.uuid4())
    token = _build_local_token(user, config, sid)
    token_expires_at = _token_expiry_datetime(token)
    try:
        session_repo.create_session(
            sid,
            str(user.id),
            access_token=token,
            token_expires_at=token_expires_at,
        )
    except Exception as exc:
        correlation_id = str(uuid.uuid4())
        log_event(
            _log,
            "auth.login.session_persist_failed",
            level="error",
            component="auth-api",
            correlationId=correlation_id,
        )
        raise HTTPException(
            status_code=503,
            detail={
                "error": "downstream_unavailable",
                "service": "postgres",
                "message": "Failed to create server session",
                "correlation_id": correlation_id,
            },
        ) from exc

    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=sid,
        httponly=True,
        secure=_request_is_secure(request),
        samesite="lax",
        path="/",
    )
    record_login_event(_extract_login_role_sources(user))
    log_event(_log, "auth.login.complete", component="auth-api", userId=str(user.id), sso=sso)
    return resolve_login_response_view(_serialize_login_user(user, token))


@router.post("/logout", response_model=LogoutResponseView)
async def logout(
    request: Request,
    response: Response,
    config_repository: AppConfigRepository = Depends(get_app_config_repository),
    session_repository: SessionRepository = Depends(get_session_repository),
) -> LogoutResponseView:
    config_repository.get_app_config()
    sid = str(request.cookies.get(SESSION_COOKIE_NAME) or "").strip()
    if sid:
        session_repo = session_repository
        try:
            session_repo.delete_session(sid)
        except Exception:
            pass
    response.delete_cookie(key=SESSION_COOKIE_NAME, path="/")
    log_event(_log, "auth.logout.complete", component="auth-api")
    return LogoutResponseView(ok=True)


@router.post("/refresh")
async def auth_refresh(
    payload: dict[str, Any],
    config_repository: AppConfigRepository = Depends(get_app_config_repository),
) -> dict[str, str]:
    config_repository.get_app_config()
    request_tokens = build_oidc_token_response_entity(payload)
    refresh_token = request_tokens.refresh_token if request_tokens is not None else None
    if not refresh_token:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "refresh_token_required",
                "message": "refresh_token is required",
            },
        )

    config = config_repository.get_app_config()
    if not config.ssoEnabled or not config.ssoIssuer or not config.ssoClientId:
        raise HTTPException(
            status_code=501,
            detail={
                "error": "refresh_not_supported",
                "message": "Token refresh is only supported when SSO is enabled and configured",
            },
        )

    correlation_id = str(uuid.uuid4())
    issuer = _normalize_issuer_url(config.ssoIssuer)
    backend_issuer = _build_backend_issuer(issuer)
    client_id = str(config.ssoClientId)

    try:
        token_payload = await _refresh_oidc_token(backend_issuer, client_id, refresh_token)
    except HTTPException:
        raise
    except Exception as exc:
        log_event(_log, "auth.refresh.failed", level="error", component="auth-api", correlationId=correlation_id)
        raise HTTPException(
            status_code=503,
            detail={
                "error": "downstream_unavailable",
                "service": "keycloak",
                "message": "Failed to refresh token",
                "correlation_id": correlation_id,
            },
        ) from exc

    token_entity = build_oidc_token_response_entity(token_payload)
    access_token = token_entity.access_token if token_entity is not None else None
    if not access_token:
        raise HTTPException(
            status_code=502,
            detail={
                "error": "invalid_refresh_response",
                "message": "Provider refresh response did not include access_token",
                "correlation_id": correlation_id,
            },
        )

    next_refresh = (token_entity.refresh_token if token_entity is not None else None) or refresh_token
    return {
        "token": access_token,
        "refresh_token": next_refresh,
    }


@router.get("/logout")
async def auth_logout_redirect(
    request: Request,
    id_token: str | None = Query(default=None),
    frontend: str | None = Query(default=None),
    config_repository: AppConfigRepository = Depends(get_app_config_repository),
    session_repository: SessionRepository = Depends(get_session_repository),
) -> RedirectResponse:
    """Redirect the browser to Keycloak's end-session endpoint.

    The frontend navigates here instead of constructing the Keycloak logout URL
    client-side. This avoids relying on React settings state and is always
    reliable because the backend reads the issuer/client from the database.
    """
    log_event(_log, "auth.logout.redirect.start", component="auth-api")
    config = config_repository.get_app_config()

    target_frontend = _normalize_frontend_origin(frontend) or "/"

    # Always terminate the server-side session cookie (if present).
    sid = str(request.cookies.get(SESSION_COOKIE_NAME) or "").strip()
    if sid:
        session_repo = session_repository
        try:
            session_repo.delete_session(sid)
        except Exception:
            pass

    if not config.ssoEnabled or not config.ssoIssuer or not config.ssoClientId:
        response = RedirectResponse(url=target_frontend, status_code=302)
        response.delete_cookie(key=SESSION_COOKIE_NAME, path="/")
        return response

    issuer = _normalize_issuer_url(config.ssoIssuer)
    backend_issuer = _build_backend_issuer(issuer)
    client_id = str(config.ssoClientId)
    post_logout = target_frontend

    params: dict[str, str] = {
        "client_id": client_id,
        "post_logout_redirect_uri": post_logout,
    }
    normalized_id_token = str(id_token or "").strip()
    if normalized_id_token:
        params["id_token_hint"] = normalized_id_token

    try:
        metadata = await _fetch_oidc_metadata(issuer)
        end_session_url = _require_oidc_endpoint(
            metadata,
            "end_session_endpoint",
        )
    except HTTPException:
        try:
            metadata = await _fetch_oidc_metadata(backend_issuer)
            end_session_url = _require_oidc_endpoint(
                metadata,
                "end_session_endpoint",
            )
            end_session_url = _rewrite_oidc_endpoint_to_public(
                end_session_url,
                backend_issuer,
                issuer,
            )
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=503, detail="OIDC discovery failed") from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="OIDC discovery failed") from exc

    end_session_url = f"{end_session_url}?{urlencode(params)}"
    log_event(_log, "auth.logout.redirect.end_session", component="auth-api", url=end_session_url)
    response = RedirectResponse(url=end_session_url, status_code=302)
    response.delete_cookie(key=SESSION_COOKIE_NAME, path="/")
    return response


@router.get("/redirect")
async def auth_redirect(
    frontend: str | None = Query(default=None),
    config_repository: AppConfigRepository = Depends(get_app_config_repository),
) -> RedirectResponse:
    log_event(_log, "auth.redirect.start", component="auth-api")
    config = config_repository.get_app_config()
    if not config.ssoEnabled or not config.ssoIssuer or not config.ssoClientId:
        log_event(_log, "auth.redirect.not_configured", level="warning", component="auth-api")
        raise HTTPException(status_code=400, detail="SSO not configured")

    issuer = _normalize_issuer_url(config.ssoIssuer)
    backend_issuer = _build_backend_issuer(issuer)
    try:
        metadata = await _fetch_oidc_metadata(issuer)
        authorization_endpoint = _require_oidc_endpoint(
            metadata,
            "authorization_endpoint",
        )
    except HTTPException:
        try:
            metadata = await _fetch_oidc_metadata(backend_issuer)
            authorization_endpoint = _require_oidc_endpoint(
                metadata,
                "authorization_endpoint",
            )
            authorization_endpoint = _rewrite_oidc_endpoint_to_public(
                authorization_endpoint,
                backend_issuer,
                issuer,
            )
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=503, detail="OIDC discovery failed") from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="OIDC discovery failed") from exc

    try:
        server_base = _get_public_api_base()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    redirect_uri = f"{server_base}/auth/v1/callback"
    issued_at = int(time.time() * 1000)
    state = _to_base64_url(
        json.dumps(
            {
                "nonce": f"{issued_at}-{random.random()}",
                "issuedAt": issued_at,
                "frontendOrigin": _normalize_frontend_origin(frontend),
            }
        )
    )
    query = urlencode(
        {
            "client_id": str(config.ssoClientId),
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid profile email",
            "state": state,
        }
    )
    return RedirectResponse(
        url=f"{authorization_endpoint}?{query}",
        status_code=302,
    )


@router.get("/callback")
async def auth_callback(
    request: Request,
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    repository: AdminRepository = Depends(get_admin_repository),
    config_repository: AppConfigRepository = Depends(get_app_config_repository),
    session_repository: SessionRepository = Depends(get_session_repository),
) -> RedirectResponse:
    with traced_span("auth.callback", endpoint_group="auth", operation="callback", auth_provider="oidc") as span:
        log_event(_log, "auth.callback.start", component="auth-api")
        if not code:
            set_span_attributes(span, auth_callback_state="missing_code")
            log_event(_log, "auth.callback.missing_code", level="warning", component="auth-api")
            raise HTTPException(status_code=400, detail="Missing code")
        if not state:
            set_span_attributes(span, auth_callback_state="missing_state")
            log_event(_log, "auth.callback.invalid_state", level="warning", component="auth-api")
            raise HTTPException(status_code=400, detail="Invalid state")
        state_payload = _decode_oidc_state(state)
        issued_at = state_payload.get("issuedAt")
        if not isinstance(issued_at, int):
            set_span_attributes(span, auth_callback_state="invalid_state")
            log_event(_log, "auth.callback.invalid_state", level="warning", component="auth-api")
            raise HTTPException(status_code=400, detail="Invalid state")
        now_ms = int(time.time() * 1000)
        if issued_at > now_ms or now_ms - issued_at > 10 * 60 * 1000:
            set_span_attributes(span, auth_callback_state="expired_state")
            log_event(_log, "auth.callback.expired_state", level="warning", component="auth-api")
            raise HTTPException(status_code=400, detail="Invalid state")

        config = config_repository.get_app_config()
        if not config.ssoIssuer or not config.ssoClientId:
            set_span_attributes(span, auth_callback_state="not_configured")
            log_event(_log, "auth.callback.not_configured", level="warning", component="auth-api")
            raise HTTPException(status_code=400, detail="SSO not configured")

        issuer = _normalize_issuer_url(config.ssoIssuer)
        backend_issuer = _build_backend_issuer(issuer)
        try:
            server_base = _get_public_api_base()
        except RuntimeError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        redirect_uri = f"{server_base}/auth/v1/callback"
        set_span_attributes(
            span,
            auth_signup_allowed=bool(config.allowSignup),
            frontend_origin_supplied=bool(state_payload.get("frontendOrigin")),
        )
        with traced_span("auth.callback.exchange_code", endpoint_group="auth", operation="exchange_code"):
            token_payload = await _exchange_oidc_code(
                backend_issuer,
                str(config.ssoClientId),
                code,
                redirect_uri,
            )
        token_entity = build_oidc_token_response_entity(token_payload)
        access_token = token_entity.access_token if token_entity is not None else None
        if not access_token:
            set_span_attributes(span, auth_callback_state="token_missing")
            log_event(_log, "auth.callback.token_missing", level="error", component="auth-api")
            raise HTTPException(status_code=500, detail="No access token from provider")

        with traced_span("auth.callback.load_profile", endpoint_group="auth", operation="load_profile"):
            profile = await _load_oidc_profile(
                backend_issuer,
                access_token,
                token_entity.id_token if token_entity is not None else None,
            )
        if not isinstance(profile, dict) or not profile:
            set_span_attributes(span, auth_callback_state="userinfo_failed")
            log_event(_log, "auth.callback.userinfo_failed", level="error", component="auth-api")
            raise HTTPException(status_code=500, detail="Failed to fetch user info")

        with traced_span("auth.callback.resolve_user", endpoint_group="auth", operation="resolve_user"):
            try:
                resolved_user = repository.find_or_create_user_from_oidc(
                    profile,
                    allow_signup=bool(config.allowSignup),
                    default_role=str(config.defaultUserRole or "viewer"),
                )
            except PermissionError as error:
                set_span_attributes(span, auth_callback_state="signup_forbidden")
                log_event(_log, "auth.callback.signup_forbidden", level="warning", component="auth-api")
                raise HTTPException(status_code=403, detail=str(error)) from error
            except ValueError as error:
                set_span_attributes(span, auth_callback_state="validation_error")
                log_event(_log, "auth.callback.validation_error", level="warning", component="auth-api")
                raise HTTPException(status_code=400, detail=str(error)) from error

            frontend_origin = state_payload.get("frontendOrigin") or _normalize_frontend_origin(
                str(
                    os.getenv("UI_VITE_LOCAL_URL")
                    or os.getenv("UI_NGINX_LOCAL_URL")
                    or os.getenv("KONG_PUBLIC_URL")
                    or ""
                )
            )
            if not frontend_origin:
                set_span_attributes(span, auth_callback_state="missing_frontend_origin")
                log_event(_log, "auth.callback.missing_frontend_origin", level="warning", component="auth-api")
                raise HTTPException(status_code=500, detail="Frontend redirect origin is not configured")

            id_token = token_entity.id_token if token_entity is not None else None
            refresh_token = token_entity.refresh_token if token_entity is not None else None

            # Create a server-side session and redirect back to the SPA with
            # the browser tokens the frontend expects to persist locally.
            session_repo = session_repository
            sid = str(uuid.uuid4())
            local_token = _build_local_token(resolved_user, config, sid)
            token_expires_at = _token_expiry_datetime(local_token)
            try:
                session_repo.create_session(
                    sid,
                    str(resolved_user.id),
                    access_token=local_token,
                    id_token=id_token,
                    refresh_token=refresh_token,
                    token_expires_at=token_expires_at,
                )
            except Exception as exc:
                correlation_id = str(uuid.uuid4())
                log_event(
                    _log,
                    "auth.callback.session_persist_failed",
                    level="error",
                    component="auth-api",
                    correlationId=correlation_id,
                )
                raise HTTPException(
                    status_code=503,
                    detail={
                        "error": "downstream_unavailable",
                        "service": "postgres",
                        "message": "Failed to create server session",
                        "correlation_id": correlation_id,
                    },
                ) from exc

            html_body = _build_auth_callback_html(
                frontend_origin,
                access_token,
                id_token or None,
                refresh_token or None,
            )
            response = HTMLResponse(content=html_body, status_code=200)
            response.set_cookie(
                key=SESSION_COOKIE_NAME,
                value=sid,
                httponly=True,
                secure=_request_is_secure(request),
                samesite="lax",
                path="/",
            )

            set_span_attributes(span, auth_callback_state="complete")
            log_event(_log, "auth.callback.complete", component="auth-api")
            return response