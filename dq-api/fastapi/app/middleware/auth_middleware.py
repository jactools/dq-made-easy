from datetime import datetime, timezone

from fastapi import Request
from fastapi.responses import JSONResponse
from opentelemetry import trace
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.auth import (
    KONG_AUTHENTICATED_HEADER,
    SESSION_COOKIE_NAME,
    build_principal,
    build_principal_trusted,
    get_consumer_groups_from_header,
    get_bearer_token,
    get_required_scopes,
    has_required_scope,
    normalize_auth_path,
)
from app.core.config import get_settings
from app.core.dependencies import get_app_config_repository, get_session_repository
from app.core.dependencies import get_admin_repository
from app.core.otel_metrics import increment_auth_failure
from app.core.request_context import clear_auth_context, set_consumer_groups, set_scopes, set_user_id


def _session_value(session: object, field_name: str):
    if session is None:
        return None
    getter = getattr(session, "get", None)
    if callable(getter):
        return getter(field_name)
    return getattr(session, field_name, None)


def _allows_bearer_without_session(request: Request) -> bool:
    if str(request.method or "").upper() != "POST":
        return False

    normalized_path = normalize_auth_path(str(request.url.path or ""))
    return normalized_path.startswith("/rulebuilder/v1/validation-run-plans/") and normalized_path.endswith("/replay")


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        settings = get_settings()
        required_scopes = get_required_scopes(request.method, request.url.path)
        token, token_source = get_bearer_token(request)
        consumer_groups = get_consumer_groups_from_header(request.headers.get("x-consumer-groups"))

        def _resolve_override(dep_fn):
            overrides = getattr(request.app, "dependency_overrides", None)
            if isinstance(overrides, dict) and dep_fn in overrides:
                return overrides[dep_fn]()
            return dep_fn()

        session_repo = None
        if not token:
            cookie_sid = str(request.cookies.get(SESSION_COOKIE_NAME) or "").strip()
            if cookie_sid:
                try:
                    session_repo = _resolve_override(get_session_repository)
                except Exception:
                    return self._problem_response(
                        request,
                        503,
                        "Service Unavailable",
                        "Session store is unavailable",
                    )

                try:
                    session = session_repo.get_session(cookie_sid)
                except Exception:
                    return self._problem_response(
                        request,
                        503,
                        "Service Unavailable",
                        "Session store is unavailable",
                    )
                session_token = _session_value(session, "access_token")

                if session_token:
                    token = str(session_token)
                    token_source = "cookie"
                elif required_scopes:
                    increment_auth_failure(
                        method=request.method,
                        path=request.url.path,
                        reason="missing_session",
                    )
                    return self._problem_response(request, 401, "Unauthorized", "Session not found")

        try:
            if token:
                kong_authenticated = (
                    settings.trust_proxy_auth
                    and request.headers.get(KONG_AUTHENTICATED_HEADER) is not None
                )

                if kong_authenticated:
                    principal = build_principal_trusted(
                        token,
                        token_source or "authorization",
                        consumer_groups=consumer_groups,
                    )
                else:
                    principal = build_principal(
                        token,
                        token_source or "authorization",
                        settings,
                        consumer_groups=consumer_groups,
                    )

                if principal is None:
                    if required_scopes:
                        increment_auth_failure(
                            method=request.method,
                            path=request.url.path,
                            reason="invalid_token",
                        )
                        return self._problem_response(request, 401, "Unauthorized", "Token validation failed")
                else:
                    try:
                        session_repo = session_repo or _resolve_override(get_session_repository)
                        app_config_repo = _resolve_override(get_app_config_repository)
                        admin_repo = _resolve_override(get_admin_repository)
                    except Exception:
                        session_repo = None
                        app_config_repo = None
                        admin_repo = None

                    sid = principal.claims.get("sid") if isinstance(principal.claims, dict) else None
                    allow_bearer_without_session = _allows_bearer_without_session(request)
                    if sid and not session_repo and not allow_bearer_without_session:
                        if not kong_authenticated:
                            return self._problem_response(
                                request,
                                503,
                                "Service Unavailable",
                                "Session store is unavailable",
                            )

                    if sid and session_repo and not kong_authenticated and not allow_bearer_without_session:
                        try:
                            session = session_repo.get_session(str(sid))
                        except Exception:
                            return self._problem_response(
                                request,
                                503,
                                "Service Unavailable",
                                "Session store is unavailable",
                            )
                        config = None
                        try:
                            config = app_config_repo.get_app_config() if app_config_repo else None
                        except Exception:
                            config = None

                        timeout_minutes = getattr(config, "sessionTimeoutMinutes", None) if config is not None else None
                        if timeout_minutes:
                            if not session or (_session_value(session, "last_activity") is None):
                                return self._problem_response(request, 401, "Unauthorized", "Session not found")
                            last = _session_value(session, "last_activity")
                            if isinstance(last, datetime):
                                current_time = datetime.now(timezone.utc).replace(tzinfo=None)
                                elapsed = (current_time - last).total_seconds()
                                if elapsed > int(timeout_minutes) * 60:
                                    try:
                                        session_repo.delete_session(str(sid))
                                    except Exception:
                                        return self._problem_response(
                                            request,
                                            503,
                                            "Service Unavailable",
                                            "Session store is unavailable",
                                        )
                                    return self._problem_response(request, 401, "Unauthorized", "Session expired")
                        try:
                            session_repo.touch_session(str(sid))
                        except Exception:
                            return self._problem_response(
                                request,
                                503,
                                "Service Unavailable",
                                "Session store is unavailable",
                            )

                    effective_scopes = list(principal.scopes)
                    current_user = None
                    if admin_repo is not None and principal.user_id:
                        try:
                            current_user = admin_repo.get_current_user(principal.user_id, principal.claims)
                        except Exception:
                            current_user = None
                        if current_user is not None:
                            effective_scopes = sorted({str(scope).strip() for scope in [*effective_scopes, *list(current_user.granted_scopes or [])] if str(scope).strip()})

                    request.state.user_id = principal.user_id
                    request.state.scopes = effective_scopes
                    request.state.consumer_groups = principal.consumer_groups
                    request.state.auth_claims = principal.claims
                    set_user_id(principal.user_id)
                    set_scopes(effective_scopes)
                    set_consumer_groups(principal.consumer_groups)

                    span = trace.get_current_span()
                    if span.is_recording():
                        span.set_attribute("user_id", principal.user_id)

                    if required_scopes and not has_required_scope(effective_scopes, required_scopes):
                        detail = f"Missing required scope. Need one of: {', '.join(required_scopes)}"
                        increment_auth_failure(
                            method=request.method,
                            path=request.url.path,
                            reason="missing_scope",
                        )
                        return self._problem_response(request, 403, "Forbidden", detail)
            elif required_scopes:
                increment_auth_failure(
                    method=request.method,
                    path=request.url.path,
                    reason="missing_token",
                )
                return self._problem_response(request, 401, "Unauthorized", "Bearer token is required for this endpoint")

            return await call_next(request)
        finally:
            clear_auth_context()

    @staticmethod
    def _problem_response(request: Request, status: int, title: str, detail: str) -> JSONResponse:
        return JSONResponse(
            status_code=status,
            content={
                "type": "about:blank",
                "title": title,
                "status": status,
                "detail": detail,
                "instance": request.url.path,
            },
        )