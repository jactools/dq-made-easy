#!/usr/bin/env python3
"""
Generate a Keycloak realm JSON from the seed users CSV.

Usage:
    python generate_keycloak_realm.py --input ../mock-data/users.csv --output ../keycloak/realm.json --domain example.org

The script reads the CSV with headers including 'first_name', 'last_name', 'email', and 'password' and emits a realm JSON
compatible with Keycloak import (users + public clients named `dq-rules-ui` and `zammad`).
"""
import argparse
import csv
import json
import os
from pathlib import Path
from urllib.parse import urlparse


SCOPE_ROLES = [
    "dq:rules:read",
    "dq:rules:write",
    "dq:rules:create",
    "dq:rules:edit",
    "dq:rules:delete",
    "dq:rules:test",
    "dq:rules:approve",
    "dq:rules:activate",
    "dq:users:manage",
    "dq:workspace:manage",
    "dq:workspace:read",
    "dq:config:manage",
    "dq:admin:read",
    "dq:profiling:request",
    "dq:data_catalog:read",
    "dq:reports:read",
    "dq:audit:read",
    "dq:templates:read",
    "dq:templates:write",
    "dq:notifications:read",
    "dq:exceptions:read",
    "dq:exceptions:detail",
]

KEYCLOAK_USER_ACCESS_TOKEN_LIFESPAN_SECONDS = 24 * 60 * 60
KEYCLOAK_SERVICE_ACCOUNT_ACCESS_TOKEN_LIFESPAN_SECONDS = 60 * 60
PLACEHOLDER_PASSWORDS = {"password", "admin", "changeme", "secret"}
SAFE_PASSWORD_CHARACTERS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")


def validate_seed_password(password: str, *, label: str = "password") -> str:
    value = str(password or "")
    if not value:
        raise ValueError(f"{label} is required")
    if value.lower() in PLACEHOLDER_PASSWORDS:
        raise ValueError(f"{label} must not be a default or placeholder password")
    if not value.isprintable():
        raise ValueError(f"{label} must contain printable characters only")
    if any(character.isspace() for character in value):
        raise ValueError(f"{label} must not contain whitespace")
    return value


def split_workspaces(raw_workspaces):
    return [
        workspace
        for workspace in (part.strip() for part in str(raw_workspaces or "").split(";"))
        if workspace
    ]


def load_required_name_parts(row: dict[str, str], *, csv_path: str | Path) -> tuple[str, str]:
    first_name = (row.get("first_name") or "").strip()
    last_name = (row.get("last_name") or "").strip()
    if first_name and last_name:
        return first_name, last_name

    identifier = (row.get("email") or row.get("id") or "unknown row").strip() or "unknown row"
    raise ValueError(f"{csv_path} is missing required first_name/last_name for {identifier}")


def load_user_roles(user_roles_csv_path):
    role_map = {}
    p = Path(user_roles_csv_path)
    if not p.exists():
        return role_map

    with open(p, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            user_id = (row.get("user_id") or "").strip()
            role_id = (row.get("role_id") or "").strip()
            if not user_id or not role_id:
                continue
            role_map.setdefault(user_id, []).append(role_id)

    return role_map


def load_users(csv_path, user_role_map=None, email_domain=None):
    users = []
    by_username = {}
    user_role_map = user_role_map or {}
    with open(csv_path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        fieldnames = set(reader.fieldnames or [])
        missing_columns = sorted({"first_name", "last_name", "password"} - fieldnames)
        if missing_columns:
            raise ValueError(f"{csv_path} is missing required columns: {', '.join(missing_columns)}")
        for row in reader:
            user_id = (row.get("id") or "").strip()
            email = (row.get("email") or "").strip()
            if not email:
                continue
            if email_domain:
                local = email.split("@")[0]
                email = f"{local}@{email_domain}"

            # Prefer explicit role assignments from user_roles.csv keyed by user id.
            realm_roles = []
            if user_id and user_id in user_role_map:
                realm_roles = [r.strip() for r in user_role_map[user_id] if str(r).strip()]
            user_password = validate_seed_password(row.get("password"), label=f"password for {email}")
            workspaces = split_workspaces(row.get("workspaces"))
            first_name, last_name = load_required_name_parts(row, csv_path=csv_path)

            user_obj = {
                "username": email,
                "email": email,
                "firstName": first_name,
                "lastName": last_name,
                "emailVerified": True,
                "enabled": True,
                "credentials": [
                    {"type": "password", "value": user_password, "temporary": False}
                ],
                "realmRoles": sorted(set(realm_roles)),
            }
            if workspaces:
                user_obj["attributes"] = {"workspaces": workspaces}

            existing = by_username.get(email)
            if existing:
                merged_roles = sorted(set(existing.get("realmRoles", []) + user_obj["realmRoles"]))
                existing["realmRoles"] = merged_roles
                if workspaces:
                    merged_workspaces = sorted(
                        set((existing.get("attributes", {}) or {}).get("workspaces", []) + workspaces)
                    )
                    existing.setdefault("attributes", {})["workspaces"] = merged_workspaces
            else:
                by_username[email] = user_obj

    users.extend(by_username.values())
    return users


def load_roles_file(roles_csv_path):
    roles = []
    p = Path(roles_csv_path)
    if not p.exists():
        return roles
    with open(p, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            rid = (row.get("id") or "").strip()
            if rid:
                raw_permissions = (row.get("permissions") or "").strip()
                permissions = []
                if raw_permissions:
                    try:
                        parsed = json.loads(raw_permissions)
                    except json.JSONDecodeError:
                        parsed = []
                    if isinstance(parsed, list):
                        permissions = [str(permission).strip() for permission in parsed if str(permission).strip()]
                roles.append({"id": rid, "permissions": sorted(set(permissions))})
    return roles


def build_realm_roles(roles_list):
    unique_roles = []
    seen = set()

    for role in roles_list:
        if isinstance(role, str):
            role_name = role.strip()
            role_permissions = []
        else:
            role_name = str((role or {}).get("id") or "").strip()
            role_permissions = [
                str(permission).strip()
                for permission in (role or {}).get("permissions", [])
                if str(permission).strip()
            ]
        if not role_name or role_name in seen:
            continue
        seen.add(role_name)
        unique_roles.append({
            "id": role_name,
            "permissions": role_permissions,
        })

    for scope_role in SCOPE_ROLES:
        if scope_role not in seen:
            seen.add(scope_role)
            unique_roles.append({"id": scope_role, "permissions": []})

    role_objects = []
    for role in unique_roles:
        role_name = role["id"]
        composites = sorted(set(role.get("permissions", [])))
        role_obj = {"name": role_name}
        if composites:
            role_obj["composites"] = {"realm": composites}
        role_objects.append(role_obj)

    return role_objects


def _load_dotenv_from_repo(max_levels=6):
    """Load a .env file from the repository root (or nearest ancestor).

    This will set environment variables that are not already present in
    os.environ. It searches up to `max_levels` parent directories from this
    file's location.
    """
    p = Path(__file__).resolve()
    levels = 0
    for parent in p.parents:
        env_path = parent / ".env"
        if env_path.exists():
            try:
                with open(env_path, encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        if "=" not in line:
                            continue
                        key, val = line.split("=", 1)
                        key = key.strip()
                        val = val.strip()
                        if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                            val = val[1:-1]
                        # Do not override already-set environment variables.
                        if key and key not in os.environ:
                            os.environ[key] = val
            except Exception:
                # Don't fail hard on parsing errors - caller will validate required vars.
                pass
            return env_path
        levels += 1
        if levels >= max_levels:
            break
    return None

def generate_realm(
    users,
    realm_roles,
    client_redirect=None,
    realm_name=None,
    realm_display_name=None,
    openmetadata_callback=None,
    frontend_origins=None,
    grafana_public_url=None,
    grafana_oidc_secret=None,
    zammad_public_url=None,
    engine_service_client_id: str | None = None,
    engine_service_client_secret: str | None = None,
    openmetadata_client_id: str | None = None,
    openmetadata_client_secret: str | None = None,
):
    # Resolve runtime defaults from environment (after .env has been loaded).
    realm_name = realm_name or os.getenv("KEYCLOAK_REALM")
    if not realm_name:
        raise SystemExit("KEYCLOAK_REALM is required")

    realm_display_name = realm_display_name or os.getenv("KEYCLOAK_REALM_DISPLAY_NAME", "Keycloak Realm")

    openmetadata_callback = openmetadata_callback or os.getenv("OPENMETADATA_CALLBACK")
    if not openmetadata_callback:
        raise SystemExit("OPENMETADATA_CALLBACK is required")

    grafana_public_url = grafana_public_url or os.getenv("GRAFANA_PUBLIC_URL")
    if not grafana_public_url:
        raise SystemExit("GRAFANA_PUBLIC_URL is required")

    grafana_oidc_secret = grafana_oidc_secret or os.getenv("GRAFANA_OIDC_SECRET")
    if not grafana_oidc_secret:
        raise SystemExit("GRAFANA_OIDC_SECRET is required")

    zammad_public_url = zammad_public_url or os.getenv("ZAMMAD_PUBLIC_URL")
    if not zammad_public_url:
        raise SystemExit("ZAMMAD_PUBLIC_URL is required")

    frontend_origins = frontend_origins or [os.getenv("UI_VITE_LOCAL_URL"), os.getenv("UI_NGINX_LOCAL_URL")]

    def _require_valid_http_url(raw: str, *, label: str, allow_wildcard_path: bool) -> str:
        value = str(raw or "").strip()
        if not value:
            raise SystemExit(f"{label} is empty")
        if "${" in value:
            raise SystemExit(
                f"{label} contains an unresolved ${{VAR}} placeholder ('{value}'); "
                "Keycloak realm import does not expand env vars. Use a concrete URL."
            )
        check = value
        if allow_wildcard_path and check.endswith("/*"):
            check = check[:-2]
        parsed = urlparse(check)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise SystemExit(f"{label} is not a valid http(s) URL: '{value}'")
        return value

    zammad_public_url = _require_valid_http_url(
        zammad_public_url,
        label="--zammad-public-url",
        allow_wildcard_path=False,
    ).rstrip("/")
    zammad_callback_url = f"{zammad_public_url}/auth/openid_connect/callback"

    # Validate that any provided frontend origins are concrete and importable.
    validated_frontend_origins: list[str] = []
    for origin in frontend_origins:
        if not origin:
            continue
        validated_frontend_origins.append(_require_valid_http_url(str(origin), label="--frontend-origin", allow_wildcard_path=False).rstrip("/"))
    frontend_origins = validated_frontend_origins

    # Determine the set of redirect base URLs to allow for the dq-rules-ui client.
    # Strict behavior: require an explicit `--redirect` or `OIDC_REDIRECT_BASE_URL`.
    # DO NOT fall back to other env vars (e.g. `KONG_PUBLIC_URL`) or hard-coded defaults.

    redirect_bases = []
    if client_redirect:
        # If a full callback path is provided, keep it as the sole redirect URI
        if "/auth/v1/callback" in client_redirect:
            redirect_uris = [client_redirect]
            base = client_redirect.split("/auth/v1/callback", 1)[0].rstrip("/")
            redirect_bases = [base]
        elif "/v1/auth/callback" in client_redirect:
            # Legacy (version-first) callback path: allow only when explicitly provided.
            redirect_uris = [client_redirect]
            base = client_redirect.split("/v1/auth/callback", 1)[0].rstrip("/")
            redirect_bases = [base]
        else:
            redirect_uris = [client_redirect.rstrip("/") + "/auth/v1/callback"]
            redirect_bases = [client_redirect.rstrip("/")]
    else:
        _ = _load_dotenv_from_repo()
        oidc_base = os.getenv("OIDC_REDIRECT_BASE_URL")
        if not oidc_base:
            raise SystemExit("OIDC_REDIRECT_BASE_URL must be set when --redirect is not provided; refusing to use fallbacks.")
        redirect_bases = [oidc_base.rstrip("/")]
        redirect_uris = [f"{redirect_bases[0]}/auth/v1/callback"]

    # Build webOrigins: include frontend origins and the redirect base hosts
    web_origins = []
    for o in frontend_origins:
        if o and o not in web_origins:
            web_origins.append(o)
    for b in redirect_bases:
        if b and b not in web_origins:
            web_origins.append(b)

    for idx, origin in enumerate(web_origins):
        _require_valid_http_url(str(origin), label=f"webOrigins[{idx}]", allow_wildcard_path=False)

    post_logout_redirects = "##".join(web_origins)

    openmetadata_origin = openmetadata_callback.rsplit("/callback", 1)[0].rstrip("/")

    realm = {
        "realm": realm_name,
        "sslRequired": "external",
        "displayName": realm_display_name,
        "rememberMe": False,
        "accessTokenLifespan": KEYCLOAK_USER_ACCESS_TOKEN_LIFESPAN_SECONDS,
        "users": users,
        "enabled": True,
        "clients": [
            {
                "clientId": "dq-rules-ui",
                "enabled": True,
                "publicClient": True,
                "protocol": "openid-connect",
                "redirectUris": redirect_uris + [f"{o}/*" for o in frontend_origins if o] + [o for o in frontend_origins if o],
                "webOrigins": web_origins,
                "attributes": {
                    "post.logout.redirect.uris": post_logout_redirects,
                },
                "directAccessGrantsEnabled": True,
                "defaultClientScopes": ["profile", "email", "roles"],
                "protocolMappers": [
                    {
                        "name": "realm roles",
                        "protocol": "openid-connect",
                        "protocolMapper": "oidc-usermodel-realm-role-mapper",
                        "consentRequired": False,
                        "config": {
                            "multivalued": "true",
                            "userinfo.token.claim": "true",
                            "id.token.claim": "true",
                            "access.token.claim": "true",
                            "claim.name": "roles",
                            "jsonType.label": "String",
                        },
                    },
                    {
                        "name": "browser auth audience",
                        "protocol": "openid-connect",
                        "protocolMapper": "oidc-audience-mapper",
                        "consentRequired": False,
                        "config": {
                            "included.client.audience": "dq-rules-ui",
                            "id.token.claim": "true",
                            "access.token.claim": "true",
                        },
                    }
                ],
            },
            {
                "clientId": "openmetadata",
                "enabled": True,
                "publicClient": True,
                "protocol": "openid-connect",
                "redirectUris": [openmetadata_callback],
                "webOrigins": [openmetadata_origin],
                "directAccessGrantsEnabled": True,
                "standardFlowEnabled": True,
                "implicitFlowEnabled": True,
                "defaultClientScopes": ["profile", "email", "roles"],
            },
            {
                "clientId": "openmetadata-admin",
                "name": "OpenMetadata Admin",
                "description": "Confidential client for OpenMetadata admin/seed operations",
                "enabled": True,
                "publicClient": False,
                "clientAuthenticatorType": "client-secret",
                "secret": openmetadata_client_secret,
                "protocol": "openid-connect",
                "serviceAccountsEnabled": True,
                "standardFlowEnabled": False,
                "implicitFlowEnabled": False,
                "directAccessGrantsEnabled": False,
                "attributes": {
                    "access.token.lifespan": str(KEYCLOAK_SERVICE_ACCOUNT_ACCESS_TOKEN_LIFESPAN_SECONDS),
                },
                "defaultClientScopes": ["openid", "profile", "email", "roles"],
                "protocolMappers": [
                    {
                        "name": "email",
                        "protocol": "openid-connect",
                        "protocolMapper": "oidc-hardcoded-claim-mapper",
                        "consentRequired": False,
                        "config": {
                            "introspection.token.claim": "true",
                            "id.token.claim": "true",
                            "access.token.claim": "true",
                            "claim.name": "email",
                            "claim.value": "openmetadata-admin@jaccloud.nl",
                            "jsonType.label": "String",
                        },
                    },
                ],
            },
            {
                "clientId": "zammad",
                "name": "Zammad",
                "description": "Zammad support portal browser client",
                "enabled": True,
                "publicClient": True,
                "protocol": "openid-connect",
                "standardFlowEnabled": True,
                "implicitFlowEnabled": False,
                "directAccessGrantsEnabled": False,
                "redirectUris": [zammad_callback_url],
                "webOrigins": [zammad_public_url],
                "defaultClientScopes": ["profile", "email"],
                "attributes": {
                    "post.logout.redirect.uris": f"{zammad_public_url}/*",
                },
            },
            {
                "clientId": "grafana",
                "name": "Grafana",
                "description": "Grafana - Rule Builder Observability UI",
                "enabled": True,
                "publicClient": False,
                "serviceAccountsEnabled": True,
                "secret": grafana_oidc_secret,
                "protocol": "openid-connect",
                "standardFlowEnabled": True,
                "implicitFlowEnabled": False,
                "directAccessGrantsEnabled": False,
                "redirectUris": [
                    f"{grafana_public_url.rstrip('/')}/login/generic_oauth",
                ],
                "webOrigins": [grafana_public_url.rstrip('/')],
                "defaultClientScopes": ["profile", "email", "roles"],
                "protocolMappers": [
                    {
                        "name": "realm roles",
                        "protocol": "openid-connect",
                        "protocolMapper": "oidc-usermodel-realm-role-mapper",
                        "consentRequired": False,
                        "config": {
                            "multivalued": "true",
                            "userinfo.token.claim": "true",
                            "id.token.claim": "true",
                            "access.token.claim": "true",
                            "claim.name": "roles",
                            "jsonType.label": "String",
                        },
                    },
                    {
                        "name": "grafana-roles",
                        "protocol": "openid-connect",
                        "protocolMapper": "oidc-script-based-protocol-mapper",
                        "consentRequired": False,
                        "config": {
                            "userinfo.token.claim": "true",
                            "multivalued": "true",
                            "id.token.claim": "true",
                            "access.token.claim": "true",
                            "claim.name": "resource_access.grafana.roles",
                            "script": (
                                "var roles = []; "
                                "if (user.realmRoles) { "
                                "user.realmRoles.forEach(function(role) { "
                                "if (role === 'admin' || role === 'cross-admin') { roles.push('Admin'); } "
                                "else if (role === 'rule-approver' || role === 'user' || role === 'r01' || role === 'r02' || role === 'r11' || role === 'r12') { roles.push('Editor'); } "
                                "else if (role === 'viewer') { roles.push('Viewer'); } "
                                "}); } roles"
                            ),
                        },
                    },
                ],
            },
            {
                "clientId": engine_service_client_id or "dq-engine-gx-worker",
                "name": "dq-engine GX worker",
                "description": "Service client for dq-engine GX dispatch worker (client-credentials)",
                "enabled": True,
                "publicClient": False,
                "clientAuthenticatorType": "client-secret",
                "secret": engine_service_client_secret or "changeme",
                "protocol": "openid-connect",
                "serviceAccountsEnabled": True,
                "standardFlowEnabled": False,
                "implicitFlowEnabled": False,
                "directAccessGrantsEnabled": False,
                "attributes": {
                    "access.token.lifespan": str(KEYCLOAK_SERVICE_ACCOUNT_ACCESS_TOKEN_LIFESPAN_SECONDS),
                },
                "defaultClientScopes": ["profile", "email", "roles"],
            },
        ],
        "roles": {"realm": realm_roles},
    }

    # Validate generated redirect URIs are importable by Keycloak.
    client0 = (realm.get("clients") or [None])[0] or {}
    redirects = client0.get("redirectUris") if isinstance(client0, dict) else []
    if isinstance(redirects, list):
        for idx, uri in enumerate(redirects):
            _require_valid_http_url(str(uri), label=f"redirectUris[{idx}]", allow_wildcard_path=True)

    return realm


def _load_existing_client_secret(*, realm_json_path: Path, client_id: str) -> str | None:
    if not realm_json_path.exists():
        return None
    try:
        payload = json.loads(realm_json_path.read_text(encoding="utf-8"))
    except Exception:
        return None

    clients = payload.get("clients") if isinstance(payload, dict) else None
    if not isinstance(clients, list):
        return None

    for client in clients:
        if not isinstance(client, dict):
            continue
        if str(client.get("clientId") or "").strip() != client_id:
            continue
        secret_value = str(client.get("secret") or "").strip()
        return secret_value or None

    return None


def _write_env_snippet(*, output_path: Path, client_id: str, client_secret: str) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    contents = (
        "# Generated by dq-api/scripts/generate_keycloak_realm.py\n"
        "# Do not commit. Source this file before running docker compose, or let scripts/start_stack_pull.sh do it.\n"
        f"DQ_ENGINE_OIDC_CLIENT_ID={client_id}\n"
        f"DQ_ENGINE_OIDC_CLIENT_SECRET={client_secret}\n"
    )
    output_path.write_text(contents, encoding="utf-8")
    try:
        os.chmod(output_path, 0o600)
    except Exception:
        # Best-effort on platforms/filesystems that don't support chmod.
        pass


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", default="../mock-data/users.csv", help="Path to users CSV")
    p.add_argument("--output", default="../keycloak/jaccloud-realm.json", help="Output realm JSON path")
    p.add_argument("--domain", default=None, help="Optional email domain to replace existing domains, e.g. example.org")
    p.add_argument("--redirect", help="Client redirect URI")
    p.add_argument("--realm-name", default=None, help="Realm name (falls back to .env KEYCLOAK_REALM)")
    p.add_argument("--realm-display-name", default=None, help="Realm display name (falls back to .env KEYCLOAK_REALM_DISPLAY_NAME)")
    p.add_argument("--openmetadata-callback", default=None, help="OpenMetadata OIDC callback URI (falls back to .env OPENMETADATA_CALLBACK)")
    p.add_argument("--openmetadata-client-id", default=None, help="Client ID for the confidential OpenMetadata OIDC client in Keycloak (falls back to .env OPENMETADATA_CLIENT_ID)")
    p.add_argument(
        "--frontend-origin",
        action="append",
        dest="frontend_origins",
        help="Frontend web origin to allow for the dq-rules-ui client; repeat for multiple origins",
    )
    p.add_argument(
        "--grafana-public-url",
        default=None,
        help="Public base URL of Grafana (falls back to .env GRAFANA_PUBLIC_URL)",
    )
    p.add_argument(
        "--grafana-oidc-secret",
        default=None,
        help="Client secret for the confidential Grafana OIDC client in Keycloak (falls back to .env GRAFANA_OIDC_SECRET)",
    )
    p.add_argument(
        "--zammad-public-url",
        default=None,
        help="Public base URL of the Zammad support portal (falls back to .env ZAMMAD_PUBLIC_URL)",
    )
    p.add_argument(
        "--browser-auth-public-url",
        default=None,
        help="Public base URL of the browser auth entrypoint (falls back to .env BROWSER_AUTH_PUBLIC_URL)",
    )
    p.add_argument(
        "--browser-auth-client-id",
        default=None,
        help="Client ID for the browser auth client (falls back to .env BROWSER_AUTH_CLIENT_ID)",
    )
    p.add_argument(
        "--browser-auth-client-secret",
        default=None,
        help="Client secret for the browser auth client (falls back to .env BROWSER_AUTH_CLIENT_SECRET)",
    )
    p.add_argument(
        "--openmetadata-client-secret",
        default=None,
        help="Client secret for the confidential OpenMetadata OIDC client in Keycloak (falls back to .env OPENMETADATA_CLIENT_SECRET)",
    )
    p.add_argument(
        "--engine-service-client-id",
        default="dq-engine-gx-worker",
        help="Client ID to create for dq-engine GX worker client-credentials auth",
    )
    p.add_argument(
        "--engine-service-client-secret",
        default=None,
        help="Optional secret for the dq-engine service client (if omitted, one is generated or reused)",
    )
    p.add_argument(
        "--engine-service-client-env-output",
        default=None,
        help="Optional path to write an env snippet (DQ_ENGINE_OIDC_CLIENT_ID/SECRET) for docker-compose",
    )
    args = p.parse_args()

    # Load .env from the repository so runtime defaults come from project configuration.
    _load_dotenv_from_repo()

    csv_path = Path(args.input).resolve()
    out_path = Path(args.output).resolve()

    if not csv_path.exists():
        print(f"Input CSV not found: {csv_path}")
        raise SystemExit(1)

    roles_path = Path(args.input).parent / "roles.csv"
    user_roles_path = Path(args.input).parent / "user_roles.csv"

    user_role_map = load_user_roles(user_roles_path)
    users = load_users(
        csv_path,
        user_role_map=user_role_map,
        email_domain=args.domain,
    )

    # load role ids from roles.csv if present and include in realm
    roles_list = load_roles_file(roles_path)
    existing_role_ids = {
        str((role or {}).get("id") or "").strip()
        for role in roles_list
        if isinstance(role, dict)
    }
    for always_role in [
        "admin",
        "viewer",
        "user",
        "analyst",
        "data-steward",
        "rule-approver",
        "user-manager",
        "workspace-manager",
        "cross-admin",
    ]:
        if always_role not in existing_role_ids:
            roles_list.append({"id": always_role, "permissions": []})
            existing_role_ids.add(always_role)

    realm_roles = build_realm_roles(roles_list)

    engine_client_id = str(args.engine_service_client_id or "").strip() or "dq-engine-gx-worker"
    engine_client_secret = str(args.engine_service_client_secret or "").strip() or None
    if engine_client_secret is None:
        engine_client_secret = _load_existing_client_secret(realm_json_path=out_path, client_id=engine_client_id)
    if engine_client_secret is None:
        # Local/dev default: keep the realm JSON a usable example without embedding a
        # randomly generated secret in git.
        engine_client_secret = "changeme"

    openmetadata_client_id = str(args.openmetadata_client_id or "").strip() or "openmetadata-admin"
    openmetadata_client_secret = str(args.openmetadata_client_secret or "").strip() or None
    if openmetadata_client_secret is None:
        openmetadata_client_secret = _load_existing_client_secret(realm_json_path=out_path, client_id=openmetadata_client_id)
    if openmetadata_client_secret is None:
        # Local/dev default: keep the realm JSON a usable example without embedding a
        # randomly generated secret in git.
        openmetadata_client_secret = "changeme"

    realm = generate_realm(
        users,
        realm_roles,
        client_redirect=args.redirect,
        realm_name=args.realm_name,
        realm_display_name=args.realm_display_name,
        openmetadata_callback=args.openmetadata_callback,
        frontend_origins=args.frontend_origins,
        grafana_public_url=args.grafana_public_url,
        grafana_oidc_secret=args.grafana_oidc_secret,
        zammad_public_url=args.zammad_public_url,
        engine_service_client_id=engine_client_id,
        engine_service_client_secret=engine_client_secret,
        openmetadata_client_id=openmetadata_client_id,
        openmetadata_client_secret=openmetadata_client_secret
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(realm, fh, indent=2)

    print(f"Wrote realm JSON to: {out_path}")

    if args.engine_service_client_env_output:
        env_out = Path(args.engine_service_client_env_output).resolve()
        _write_env_snippet(output_path=env_out, client_id=engine_client_id, client_secret=engine_client_secret)
        print(f"Wrote engine client env snippet to: {env_out}")


if __name__ == "__main__":
    main()
