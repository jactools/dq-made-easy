from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse, urlunparse

from fastapi import Request

from app.core.config import Settings


PUBLIC_PREFIXES = (
    # Root health endpoint used by container health checks.
    "/health",

    # Auth endpoints are public (login flow and token refresh).
    "/auth/v1",
    "/auth/v1/login",
    "/auth/v1/logout",
    "/auth/v1/refresh",
    "/auth/v1/redirect",
    "/auth/v1/callback",

    # System endpoints that must remain callable without JWT (Kong allowlist).
    "/system/v1/health",
    "/system/v1/live",
    "/system/v1/readiness",
    "/system/v1/ready",
    "/system/v1/system-info",
    "/system/v1/version-catalog",

    # Profiling enqueue is used as an integration hook.
    "/rulebuilder/v1/profiling/enqueue",
)


@dataclass(slots=True)
class AuthenticatedPrincipal:
    user_id: str | None
    scopes: list[str]
    consumer_groups: list[str]
    claims: dict[str, Any]
    token_source: str


def normalize_auth_path(path: str) -> str:
    normalized = str(path or "").split("?", 1)[0].strip()
    if "//" in normalized:
        normalized = "/" + "/".join(segment for segment in normalized.split("/") if segment)
    if normalized == "/api":
        normalized = "/"
    elif normalized.startswith("/api/"):
        stripped = normalized[4:]
        normalized = stripped or "/"
    if normalized != "/" and normalized.endswith("/"):
        normalized = normalized.rstrip("/")
    return normalized or "/"


def _issuer_variants(issuer: str | None) -> set[str]:
    normalized = str(issuer or "").strip().rstrip("/")
    if not normalized:
        return set()

    variants = {normalized}
    parsed = urlparse(normalized)
    if parsed.scheme == "https" and parsed.hostname:
        internal_netloc = f"{parsed.hostname}:8080"
        internal_issuer = parsed._replace(scheme="http", netloc=internal_netloc)
        variants.add(urlunparse(internal_issuer).rstrip("/"))

    return variants


def is_public_route(path: str) -> bool:
    normalized = normalize_auth_path(path)
    if normalized == "/":
        return True

    # Integration hook: profiling worker reports lifecycle transitions.
    # Keep this narrowly scoped to only the report endpoint.
    # Expected normalized shape:
    #   /rulebuilder/v1/profiling/requests/<profiling_request_id>/report
    if normalized.startswith("/rulebuilder/v1/profiling/requests/") and normalized.endswith("/report"):
        parts = normalized.split("/")
        # ['', 'rulebuilder', 'v1', 'profiling', 'requests', '<id>', 'report']
        if len(parts) == 7 and parts[1:5] == ["rulebuilder", "v1", "profiling", "requests"] and parts[6] == "report":
            return True

    return any(
        normalized.startswith(prefix)
        for prefix in PUBLIC_PREFIXES
    )


def get_required_scopes(method: str, path: str) -> list[str]:
    normalized_method = str(method or "GET").upper()
    normalized_path = normalize_auth_path(path)

    if normalized_path.startswith("/system/v1/ui-registry/assets/") and normalized_method in {"GET", "HEAD", "OPTIONS"}:
        return []

    if is_public_route(normalized_path):
        return []

    # User self-service profile and preferences.
    # Keep this authenticated-only so SSO bootstrap can resolve the current user
    # without requiring a separate rules-read scope.
    if normalized_path in {"/admin/v1/me", "/user/v1/me"}:
        return []

    if normalized_path.startswith("/system/v1/support/requests"):
        return ["dq:rules:read"]

    if normalized_path.startswith("/system/v1/app-config"):
        if normalized_method in {"GET", "HEAD", "OPTIONS"}:
            return ["dq:admin:read"]
        return ["dq:config:manage"]

    if normalized_path.startswith("/system/v1/ui-registry"):
        if normalized_method in {"GET", "HEAD", "OPTIONS"}:
            return ["dq:admin:read", "dq:config:manage"]
        return ["dq:config:manage"]

    if normalized_path.startswith("/agent/v1/audit/events"):
        if normalized_method in {"GET", "HEAD", "OPTIONS"}:
            return ["dq:admin:read"]
        return ["dq:rules:write"]

    if normalized_path.startswith("/agent/v1"):
        if normalized_method in {"GET", "HEAD", "OPTIONS"}:
            return ["dq:rules:read"]
        return ["dq:rules:write"]

    if normalized_path.startswith("/admin/v1/users") or normalized_path.startswith("/admin/v1/roles"):
        if normalized_method in {"GET", "HEAD", "OPTIONS"}:
            return ["dq:admin:read", "dq:workspace:read"]
        return ["dq:users:manage"]

    if normalized_path.startswith("/admin/v1/exception-fact-access-requests"):
        if normalized_method in {"GET", "HEAD", "OPTIONS"}:
            return ["dq:admin:read", "dq:workspace:read"]
        if normalized_method == "POST":
            return ["dq:rules:read"]
        return ["dq:users:manage"]

    if normalized_path.startswith("/admin/v1/rules"):
        if normalized_method in {"GET", "HEAD", "OPTIONS"}:
            return ["dq:admin:read", "dq:workspace:read"]
        return ["dq:users:manage"]

    if normalized_path.startswith("/rulebuilder/v1/workspaces"):
        if normalized_method in {"GET", "HEAD", "OPTIONS"}:
            return ["dq:rules:read", "dq:workspace:manage"]
        return ["dq:workspace:manage"]

    if normalized_path.startswith("/rulebuilder/v1/approvals"):
        if normalized_method in {"GET", "HEAD", "OPTIONS"}:
            return ["dq:rules:read"]
        return ["dq:rules:approve"]

    if normalized_path.startswith("/rulebuilder/v1/exception-fact-access-requests"):
        if normalized_method in {"GET", "HEAD", "OPTIONS"}:
            return ["dq:rules:read"]
        if normalized_method == "POST":
            return ["dq:rules:read"]
        return ["dq:rules:approve"]

    if normalized_path.startswith("/rulebuilder/v1/exceptions"):
        if "/facts/" in normalized_path:
            if "/export" in normalized_path:
                return ["dq:rules:read"]
            return ["dq:rules:read", "dq:exceptions:detail"]
        if normalized_method in {"GET", "HEAD", "OPTIONS"}:
            return ["dq:rules:read", "dq:exceptions:read"]
        return ["dq:rules:edit", "dq:rules:write"]

    if normalized_path.startswith("/rulebuilder/v1/deliveries/") and "/exception-summary" in normalized_path:
        if "/export" in normalized_path:
            return ["dq:rules:read"]
        return ["dq:rules:read", "dq:exceptions:read"]

    if normalized_path.startswith("/rulebuilder/v1/execution-plans/") and "/exception-summary" in normalized_path:
        if "/export" in normalized_path:
            return ["dq:rules:read"]
        return ["dq:rules:read", "dq:exceptions:read"]

    if normalized_path.startswith("/rulebuilder/v1/notifications"):
        if normalized_method in {"GET", "HEAD", "OPTIONS"}:
            return ["dq:notifications:read"]
        return ["dq:notifications:read"]

    if normalized_path.startswith("/data-catalog/v1/suggestions/natural-language-rule-previews"):
        if normalized_method in {"GET", "HEAD", "OPTIONS"}:
            return ["dq:rules:read"]
        return ["dq:rules:create", "dq:rules:write"]

    if normalized_path.startswith("/data-catalog/v1/profiling"):
        if normalized_method in {"GET", "HEAD", "OPTIONS"}:
            return ["dq:rules:read"]
        return ["dq:profiling:request", "dq:rules:test"]

    if normalized_path.startswith("/data-catalog/v1/suggestions"):
        if normalized_method in {"GET", "HEAD", "OPTIONS"}:
            return ["dq:rules:read"]
        return ["dq:rules:edit", "dq:rules:write"]

    if normalized_path.startswith("/data-catalog/v1/metadata-registry/access-grants"):
        if normalized_method in {"GET", "HEAD", "OPTIONS"}:
            return ["dq:rules:read", "dq:data_catalog:read"]
        return ["dq:users:manage"]

    if normalized_path.startswith("/data-catalog/v1/metadata-registry/external-parties"):
        if normalized_path.endswith("/approve"):
            return ["dq:users:manage"]
        if normalized_path.endswith("/access-grants"):
            if normalized_method in {"GET", "HEAD", "OPTIONS"}:
                return ["dq:rules:read", "dq:data_catalog:read"]
            return ["dq:users:manage"]
        return ["dq:rules:read", "dq:data_catalog:read"]

    if normalized_path.startswith("/data-catalog/v1/metadata-registry"):
        return ["dq:rules:read", "dq:data_catalog:read"]

    if normalized_path.startswith("/data-catalog/v1/ontology"):
        return ["dq:data_catalog:read"]

    if normalized_path.startswith("/data-catalog/v1/materialization-requests"):
        return ["dq:rules:test", "dq:rules:write"]

    if any(
        part in normalized_path
        for part in (
            "/test",
            "/batch-test-requests",
            "/generate-test-data",
            "/test-data/requests",
            "/test-data/materializations",
        )
    ):
        return ["dq:rules:test", "dq:rules:write"]

    if normalized_path.startswith("/rulebuilder/v1/gx") and "/runs" in normalized_path:
        if normalized_method in {"GET", "HEAD", "OPTIONS"}:
            return ["dq:rules:read"]
        return ["dq:rules:test", "dq:rules:write"]

    if normalized_path == "/rulebuilder/v1/rules" and normalized_method == "POST":
        return ["dq:rules:create", "dq:rules:write"]

    if normalized_path.startswith("/rulebuilder/v1/rules") and normalized_method in {"PUT", "PATCH"}:
        return ["dq:rules:edit", "dq:rules:write"]

    if normalized_path.startswith("/rulebuilder/v1/rules") and normalized_method == "DELETE":
        return ["dq:rules:delete", "dq:rules:write"]

    if normalized_path.startswith("/data-catalog/v1/rule-attributes") and normalized_method != "GET":
        return ["dq:rules:edit", "dq:rules:write"]

    if normalized_method in {"GET", "HEAD", "OPTIONS"}:
        return ["dq:rules:read"]

    return ["dq:rules:edit", "dq:rules:write"]


def get_bearer_token(request: Request) -> tuple[str | None, str | None]:
    authorization = request.headers.get("authorization")
    if authorization and authorization.startswith("Bearer "):
        return authorization[7:].strip(), "authorization"

    for header_name in ("x-auth-request-access-token", "x-forwarded-access-token"):
        token = request.headers.get(header_name)
        if token:
            return token.strip(), header_name

    return None, None


def decode_jwt_payload(token: str) -> dict[str, Any] | None:
    try:
        parts = str(token).split(".")
        if len(parts) < 2:
            return None
        segment = parts[1].replace("-", "+").replace("_", "/")
        pad_len = (4 - (len(segment) % 4)) % 4
        payload = f"{segment}{'=' * pad_len}"
        raw = __import__("base64").b64decode(payload).decode("utf-8")
        parsed = __import__("json").loads(raw)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


def is_jwt_payload_valid(payload: dict[str, Any] | None, settings: Settings) -> bool:
    if not payload:
        return False

    now = __import__("time").time()
    if isinstance(payload.get("exp"), (int, float)) and payload["exp"] <= now:
        return False
    if isinstance(payload.get("nbf"), (int, float)) and payload["nbf"] > now:
        return False

    expected_issuer = (settings.sso_issuer or "").rstrip("/")
    token_issuer = str(payload.get("iss") or "").rstrip("/")
    if settings.sso_enabled and expected_issuer and token_issuer:
        if token_issuer not in _issuer_variants(expected_issuer):
            return False

    if settings.sso_enabled:
        allowed_clients = settings.sso_allowed_client_ids_list
        if allowed_clients:
            token_azp = str(payload.get("azp") or "").strip()
            if token_azp:
                if token_azp not in allowed_clients:
                    return False
            elif payload.get("aud"):
                audiences = payload["aud"] if isinstance(payload["aud"], list) else [payload["aud"]]
                audience_values = [str(value) for value in audiences]
                if not any(client_id in audience_values for client_id in allowed_clients):
                    return False

    return True


def _collect_scope_values(values: set[str], raw: Any) -> None:
    if raw is None:
        return
    if isinstance(raw, list):
        for item in raw:
            _collect_scope_values(values, item)
        return
    for token in str(raw).split():
        scoped = token.strip().strip(",")
        if scoped:
            values.add(scoped)


def get_scopes_from_payload(payload: dict[str, Any]) -> list[str]:
    values: set[str] = set()
    _collect_scope_values(values, payload.get("scope"))
    _collect_scope_values(values, payload.get("scp"))
    _collect_scope_values(values, payload.get("roles"))
    _collect_scope_values(values, payload.get("permissions"))
    _collect_scope_values(values, payload.get("realm_access", {}).get("roles"))
    _collect_scope_values(values, payload.get("resource_access", {}).get("account", {}).get("roles"))
    return sorted(values)


def get_consumer_groups_from_header(raw_groups: str | None) -> list[str]:
    if not raw_groups:
        return []

    groups: list[str] = []
    for group in str(raw_groups).split(","):
        cleaned = group.strip()
        if cleaned and cleaned not in groups:
            groups.append(cleaned)
    return groups


def expand_granted_scopes(granted: list[str]) -> set[str]:
    expanded = {str(scope).strip() for scope in granted if str(scope).strip()}

    if "dq:rules:write" in expanded:
        expanded.update(
            {
                "dq:rules:read",
                "dq:rules:create",
                "dq:rules:edit",
                "dq:rules:delete",
                "dq:rules:test",
                "dq:rules:approve",
                "dq:rules:activate",
            }
        )

    return expanded


def has_required_scope(granted: list[str], required: list[str]) -> bool:
    expanded = expand_granted_scopes(granted)

    if "dq:*" in expanded:
        return True

    for required_scope in required:
        if required_scope in expanded:
            return True

        required_parts = str(required_scope).split(":")
        for i in range(len(required_parts) - 1, 0, -1):
            parent_scope = f"{':'.join(required_parts[:i])}:*"
            if parent_scope in expanded:
                return True

    return False


def build_principal(
    token: str,
    token_source: str,
    settings: Settings,
    consumer_groups: list[str] | None = None,
) -> AuthenticatedPrincipal | None:
    payload = decode_jwt_payload(token)
    if not is_jwt_payload_valid(payload, settings):
        return None

    scopes = set(get_scopes_from_payload(payload))
    user_id = next(
        (
            value
            for value in (
                payload.get("sub"),
                payload.get("preferred_username"),
                payload.get("email"),
                payload.get("upn"),
            )
            if value
        ),
        None,
    )

    return AuthenticatedPrincipal(
        user_id=str(user_id) if user_id else None,
        scopes=sorted(scopes),
        consumer_groups=list(consumer_groups or []),
        claims=payload,
        token_source=token_source,
    )


# Header name that Kong sets on requests it has already authenticated.
KONG_AUTHENTICATED_HEADER = "x-consumer-custom-id"

# Cookie name for server-side sessions (session id stored client-side; tokens stored server-side).
SESSION_COOKIE_NAME = "dq_session"


def build_principal_trusted(
    token: str,
    token_source: str,
    consumer_groups: list[str] | None = None,
) -> AuthenticatedPrincipal | None:
    """Build a principal by decoding the JWT without re-validating the
    signature or checking issuer / audience.  Use only when a trusted
    upstream proxy (e.g. Kong with the JWT plugin enabled) has already
    performed authentication.  The backend is responsible solely for
    authorisation (scope checking against DB-derived roles)."""
    payload = decode_jwt_payload(token)
    if not payload:
        return None

    scopes = set(get_scopes_from_payload(payload))
    user_id = next(
        (
            value
            for value in (
                payload.get("sub"),
                payload.get("preferred_username"),
                payload.get("email"),
                payload.get("upn"),
            )
            if value
        ),
        None,
    )

    return AuthenticatedPrincipal(
        user_id=str(user_id) if user_id else None,
        scopes=sorted(scopes),
        consumer_groups=list(consumer_groups or []),
        claims=payload,
        token_source=token_source,
    )