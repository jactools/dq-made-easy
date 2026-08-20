#!/usr/bin/env python3
"""dq-job-oidc-gateway-init — seed Keycloak tenant setup + Kong gateway for DQ.

Phase 1 (Keycloak, tenant-admin client credentials, realm from KEYCLOAK_REALM):
  - Ensure realm roles (DQ role set)
  - Assign realm roles to users (mock-data user->role mapping)
  - Ensure the "dq-rules-ui" public OIDC client (redirect URI, web origins,
    realm-roles + audience protocol mappers, post-logout URIs)

Phase 2 (Kong Admin API, plaintext HTTP):
  - Service "dq-api" -> internal API URL
  - Routes (public allowlist + protected API routes)
  - CORS + rate-limiting (service level)
  - JWT + ACL plugins on protected routes
  - Consumers + JWT credentials + ACL groups, synced from realm users

Idempotent: safe to re-run. Consumes the platform-managed Keycloak realm
(docs/architecture/keycloak-seeding-split.md) and the platform-managed Kong
instance via its Admin API (tenant-side consumption).
"""

import base64
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

KEYCLOAK_URL = os.environ["KEYCLOAK_INTERNAL_URL"].rstrip("/")
KEYCLOAK_REALM = os.environ["KEYCLOAK_REALM"]
KONG_ADMIN_URL = os.environ["KONG_ADMIN_INTERNAL_URL"].rstrip("/")
DQ_API_INTERNAL_URL = os.environ["DQ_API_INTERNAL_URL"].rstrip("/")
CORS_ORIGINS = [o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]
OIDC_REDIRECT_BASE = os.environ["OIDC_REDIRECT_BASE_URL"].rstrip("/")
ENGINE_CLIENT_ID = os.environ.get("DQ_ENGINE_OIDC_CLIENT_ID", "")
CLIENT_ID = os.environ["CLIENT_ID"]
CLIENT_SECRET = os.environ["CLIENT_SECRET"]
CA_BUNDLE = os.environ.get("CA_BUNDLE", "")

UI_CLIENT_ID = "dq-rules-ui"

# ---------------------------------------------------------------------------
# Role -> Kong ACL group mapping (kept identical to scripts/bootstrap_kong.sh)
# ---------------------------------------------------------------------------
ROLE_GROUP = {
    "admin": "admin", "cross-admin": "admin", "user-manager": "admin",
    "workspace-manager": "admin",
    "r11": "admin", "r12": "admin", "r13": "admin",
    "r14": "admin", "r15": "admin", "r16": "admin",
    "data-steward": "data-steward", "rule-approver": "data-steward",
    "r02": "data-steward", "r04": "data-steward", "r06": "data-steward",
    "r08": "data-steward", "r10": "data-steward",
    "analyst": "analyst", "user": "analyst",
    "r01": "analyst", "r03": "analyst", "r05": "analyst",
    "r07": "analyst", "r09": "analyst",
    "viewer": "viewer",
}

ALL_AUTH_GROUPS = ["authenticated", "viewer", "analyst", "data-steward", "admin"]
STEWARD_GROUPS = ["data-steward", "admin"]
ADMIN_ONLY_GROUPS = ["admin"]

# Mock-data user->role assignments (dq-db/mock-data/user_roles.csv + users.csv).
USER_ROLES = {
    "alice@jaccloud.nl": ["admin"],
    "auditor@jaccloud.nl": ["auditor"],
    "bob@jaccloud.nl": ["r02", "user"],
    "bram@jaccloud.nl": ["viewer"],
    "charlie@jaccloud.nl": ["r01", "rule-approver", "user"],
    "charlotte@jaccloud.nl": ["viewer"],
    "corporate-admin@jaccloud.nl": ["cross-admin", "r12"],
    "daan@jaccloud.nl": ["viewer"],
    "demo-analyst@jaccloud.nl": ["r01", "user"],
    "demo-data-steward@jaccloud.nl": ["r02", "rule-approver", "user"],
    "demo-viewer@jaccloud.nl": ["viewer"],
    "dq-admin@jaccloud.nl": ["admin"],
    "emma@jaccloud.nl": ["viewer"],
    "fleur@jaccloud.nl": ["viewer"],
    "jacbeekers@jaccloud.nl": ["admin", "cross-admin"],
    "james@jaccloud.nl": ["viewer"],
    "jan@jaccloud.nl": ["viewer"],
    "maaike@jaccloud.nl": ["viewer"],
    "multi.workspace@jaccloud.nl": ["r01", "r04"],
    "oliver@jaccloud.nl": ["viewer"],
    "olivia@jaccloud.nl": ["viewer"],
    "openmetadata-admin@jaccloud.nl": ["admin"],
    "operator@jaccloud.nl": ["operator"],
    "regulator@jaccloud.nl": ["regulator"],
    "retail-admin@jaccloud.nl": ["r11"],
    "ruben@jaccloud.nl": ["viewer"],
    "sofie@jaccloud.nl": ["viewer"],
    "sophie@jaccloud.nl": ["r02", "user"],
    "thomas@jaccloud.nl": ["viewer"],
    "william@jaccloud.nl": ["viewer"],
}

# Kong routes: (name, path, methods-or-None-for-all, acl-groups-or-None-for-public)
ROUTES = [
    ("dq-api-auth-v1", "/api/auth/v1", None, ALL_AUTH_GROUPS),
    ("dq-api-admin-v1", "/api/admin/v1", None, ADMIN_ONLY_GROUPS),
    ("dq-api-admin-v1-users", "/api/admin/v1/users", None, ADMIN_ONLY_GROUPS),
    ("dq-api-admin-v1-roles", "/api/admin/v1/roles", None, ADMIN_ONLY_GROUPS),
    ("dq-api-admin-v1-rules", "/api/admin/v1/rules", None, ADMIN_ONLY_GROUPS),
    ("dq-api-system-v1", "/api/system/v1", None, ALL_AUTH_GROUPS),
    ("dq-api-system-v1-app-config-read", "/api/system/v1/app-config",
     ["GET", "HEAD", "OPTIONS"], ALL_AUTH_GROUPS),
    ("dq-api-system-v1-app-config-write", "/api/system/v1/app-config",
     ["POST", "PUT", "PATCH", "DELETE"], ADMIN_ONLY_GROUPS),
    ("dq-api-system-v1-ui-registry", "/api/system/v1/ui-registry", None, ALL_AUTH_GROUPS),
    ("dq-api-data-catalog-v1", "/api/data-catalog/v1", None, ALL_AUTH_GROUPS),
    ("dq-api-rulebuilder-v1", "/api/rulebuilder/v1", None, ALL_AUTH_GROUPS),
    ("dq-api-agent-v1", "/api/agent/v1", None, ALL_AUTH_GROUPS),
    ("dq-api-v1", "/api/v1", None, ALL_AUTH_GROUPS),
    ("dq-api-rulebuilder-v1-approvals-read", "/api/rulebuilder/v1/approvals",
     ["GET", "HEAD", "OPTIONS"], ALL_AUTH_GROUPS),
    ("dq-api-rulebuilder-v1-approvals-write", "/api/rulebuilder/v1/approvals",
     ["POST", "PUT", "PATCH", "DELETE"], STEWARD_GROUPS),
    # Public allowlist (no JWT at Kong)
    ("dq-api-health", "/api/health", None, None),
    ("dq-api-admin-v1-me", "/api/admin/v1/me", None, None),
    ("dq-api-auth-v1-redirect", "/api/auth/v1/redirect", None, None),
    ("dq-api-auth-v1-callback", "/api/auth/v1/callback", None, None),
    ("dq-api-auth-v1-logout", "/api/auth/v1/logout", None, None),
    ("dq-api-auth-v1-login", "/api/auth/v1/login", None, None),
    ("dq-api-system-v1-version-catalog", "/api/system/v1/version-catalog", None, None),
    ("dq-api-system-v1-system-info", "/api/system/v1/system-info", None, None),
    ("dq-api-system-v1-health", "/api/system/v1/health", None, None),
    ("dq-api-system-v1-readiness", "/api/system/v1/readiness", None, None),
    ("dq-api-system-v1-live", "/api/system/v1/live", None, None),
    ("dq-api-system-v1-ready", "/api/system/v1/ready", None, None),
    ("dq-api-docs", "/api-docs", None, None),
    ("dq-api-docs-json", "/api-docs-json", None, None),
]

SSL_CTX = None


def log(msg):
    print(f"[oidc-gateway-init] {msg}", flush=True)


def die(msg):
    log(f"ERROR: {msg}")
    sys.exit(1)


def http(method, url, token=None, data=None, form=None, timeout=30, retry_404=False):
    """HTTP request with retries on transient 5xx / connection errors.

    ``retry_404``: Keycloak's Admin API intermittently returns transient 404s
    in this cluster, so Keycloak callers opt in to retrying 404. Kong returns
    deterministic 404s (resource-not-found) used by create-if-missing logic,
    so Kong callers must NOT retry 404 or first runs stall for minutes.

    Returns (status, parsed_json_or_bytes).
    """
    global SSL_CTX
    if SSL_CTX is None:
        SSL_CTX = ssl.create_default_context(cafile=CA_BUNDLE) if CA_BUNDLE else \
            ssl.create_default_context()
    body = None
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if data is not None:
        body = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"
    if form is not None:
        body = urllib.parse.urlencode(form).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"

    retry_codes = {500, 502, 503}
    if retry_404:
        retry_codes.add(404)

    last_err = None
    for attempt in range(6):
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            resp = urllib.request.urlopen(req, context=SSL_CTX if url.startswith("https") else None,
                                          timeout=timeout)
            raw = resp.read()
            return resp.status, (json.loads(raw) if raw else None)
        except urllib.error.HTTPError as e:
            if e.code in retry_codes and attempt < 5:
                last_err = e
                time.sleep(attempt + 1)
                continue
            raw = e.read()
            try:
                return e.code, json.loads(raw) if raw else None
            except Exception:
                return e.code, raw
        except Exception as e:  # connection errors
            last_err = e
            time.sleep(attempt + 1)
    die(f"request failed after retries: {method} {url} ({last_err})")


def kc(path, token, method="GET", data=None):
    # retry_404=True: Keycloak Admin API transient-404 flakiness (observed in dev)
    return http(method, f"{KEYCLOAK_URL}/admin/realms/{KEYCLOAK_REALM}{path}",
                token=token, data=data, retry_404=True)


def kong(path, method="GET", data=None):
    # retry_404=False: Kong 404 is deterministic (create-if-missing lookups)
    return http(method, f"{KONG_ADMIN_URL}{path}", data=data)


def b64url_decode(value):
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def rsa_public_key_pem_from_jwk(jwk):
    """Build SPKI PEM from JWK n/e (ported from scripts/bootstrap_kong.sh)."""
    n = int.from_bytes(b64url_decode(jwk["n"]), "big")
    e = int.from_bytes(b64url_decode(jwk["e"]), "big")

    def der_len(length):
        if length < 128:
            return bytes([length])
        s = length.to_bytes((length.bit_length() + 7) // 8, "big")
        return bytes([0x80 | len(s)]) + s

    def der_integer(value):
        data = value.to_bytes((value.bit_length() + 7) // 8 or 1, "big")
        if data[0] & 0x80:
            data = b"\x00" + data
        return b"\x02" + der_len(len(data)) + data

    def der_sequence(data):
        return b"\x30" + der_len(len(data)) + data

    def der_oid(oid):
        parts = [int(x) for x in oid.split(".")]
        body = bytes([40 * parts[0] + parts[1]])
        for part in parts[2:]:
            encoded = []
            while True:
                encoded.insert(0, part & 0x7F)
                part >>= 7
                if part == 0:
                    break
            for i in range(len(encoded) - 1):
                encoded[i] |= 0x80
            body += bytes(encoded)
        return b"\x06" + der_len(len(body)) + body

    rsakey = der_sequence(der_integer(n) + der_integer(e))
    alg = der_sequence(der_oid("1.2.840.113549.1.1.1") + b"\x05\x00")
    spki = der_sequence(alg + b"\x03" + der_len(len(rsakey) + 1) + b"\x00" + rsakey)
    # b64encode (NOT encodebytes — the latter wraps at 76 chars and would
    # corrupt the 64-char line slicing below with embedded newlines)
    b64 = base64.b64encode(spki).decode()
    lines = [b64[i:i + 64] for i in range(0, len(b64), 64)]
    return "-----BEGIN PUBLIC KEY-----\n" + "\n".join(lines) + "\n-----END PUBLIC KEY-----\n"


# ---------------------------------------------------------------------------
# Phase 1: Keycloak tenant setup
# ---------------------------------------------------------------------------
def tenant_admin_token():
    url = f"{KEYCLOAK_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/token"
    status, body = http("POST", url, form={
        "grant_type": "client_credentials",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    })
    if status != 200 or not isinstance(body, dict) or "access_token" not in body:
        die(f"tenant-admin token failed (HTTP {status}): {str(body)[:200]}")
    log(f"tenant-admin token obtained (realm={KEYCLOAK_REALM})")
    return body["access_token"]


def ensure_realm_roles(tok):
    needed = sorted(set(r for roles in USER_ROLES.values() for r in roles) | set(ROLE_GROUP))
    _, roles = kc("/roles", tok)
    existing = {r["name"] for r in roles}
    created = 0
    for name in needed:
        if name in existing:
            continue
        # Keycloak 26: roles are created on the collection endpoint
        status, _ = kc("/roles", tok, method="POST", data={"name": name})
        if status not in (200, 201):
            die(f"create role {name} failed (HTTP {status})")
        created += 1
    log(f"realm roles ensured ({len(needed)} needed, {created} created)")
    _, roles = kc("/roles", tok)
    return {r["name"]: r["id"] for r in roles}


def assign_user_roles(tok, role_ids):
    assigned = 0
    for email, role_names in sorted(USER_ROLES.items()):
        status, users = kc(f"/users?email={urllib.parse.quote(email)}&exact=true", tok)
        if status != 200 or not users:
            log(f"  skip (user not found): {email}")
            continue
        user_id = users[0]["id"]
        for role_name in role_names:
            role_id = role_ids.get(role_name)
            if not role_id:
                log(f"  WARNING: role {role_name} missing for {email}")
                continue
            status, _ = kc(f"/users/{user_id}/role-mapping/realm", tok,
                           method="POST", data=[{"id": role_id}])
            if status in (200, 201, 204, 409):
                assigned += 1
            elif status != 400:
                die(f"assign {role_name} to {email} failed (HTTP {status})")
    log(f"role assignments upserted ({assigned})")


def frontend_origins():
    origins = [OIDC_REDIRECT_BASE]
    host = urllib.parse.urlparse(OIDC_REDIRECT_BASE)
    no_port = f"{host.scheme}://{host.hostname}"
    if no_port != OIDC_REDIRECT_BASE:
        origins.append(no_port)
    return origins


def ensure_ui_client(tok):
    origins = frontend_origins()
    redirect_uri = f"{OIDC_REDIRECT_BASE}/api/auth/v1/callback"
    redirect_uris = [redirect_uri] + [f"{o}/*" for o in origins] + origins
    payload = {
        "clientId": UI_CLIENT_ID,
        "enabled": True,
        "publicClient": True,
        "standardFlowEnabled": True,
        "directAccessGrantsEnabled": True,
        "protocol": "openid-connect",
        "redirectUris": redirect_uris,
        "webOrigins": origins,
        "attributes": {"post.logout.redirect.uris": "##".join(origins)},
        "defaultClientScopes": ["openid", "profile", "email", "roles"],
    }
    mappers = [
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
                "included.client.audience": UI_CLIENT_ID,
                "id.token.claim": "true",
                "access.token.claim": "true",
            },
        },
    ]
    status, clients = kc(f"/clients?clientId={UI_CLIENT_ID}", tok)
    if status != 200:
        die(f"client lookup failed (HTTP {status})")
    if clients:
        client_uuid = clients[0]["id"]
        status, _ = kc(f"/clients/{client_uuid}", tok, method="PATCH", data=payload)
        if status not in (200, 204):
            die(f"update client {UI_CLIENT_ID} failed (HTTP {status})")
        log(f"client {UI_CLIENT_ID} updated (uuid={client_uuid})")
    else:
        payload = dict(payload)
        payload["protocolMappers"] = mappers
        status, _ = kc("/clients", tok, method="POST", data=payload)
        if status not in (200, 201):
            die(f"create client {UI_CLIENT_ID} failed (HTTP {status})")
        log(f"client {UI_CLIENT_ID} created")
        return
    # Ensure protocol mappers (idempotent by name)
    status, existing = kc(f"/clients/{client_uuid}/protocol-mappers/models", tok)
    if status == 200:
        have = {m["name"] for m in existing}
        for m in mappers:
            if m["name"] not in have:
                status, _ = kc(f"/clients/{client_uuid}/protocol-mappers/models", tok,
                               method="POST", data=m)
                if status not in (200, 201):
                    die(f"add mapper {m['name']} failed (HTTP {status})")
                log(f"  mapper added: {m['name']}")


# ---------------------------------------------------------------------------
# Phase 2: Kong gateway
# ---------------------------------------------------------------------------
def wait_for_kong():
    for attempt in range(60):
        status, _ = kong("/")
        if status == 200:
            log(f"Kong admin ready at {KONG_ADMIN_URL}")
            return
        time.sleep(2)
    die("Kong admin not ready after 120s")


def fetch_rsa_public_key():
    jwks_url = f"{KEYCLOAK_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/certs"
    status, body = http("GET", jwks_url, retry_404=True)
    if status != 200 or not isinstance(body, dict):
        die(f"JWKS fetch failed (HTTP {status})")
    keys = body.get("keys", [])
    rsa = next((k for k in keys if k.get("kty") == "RSA" and k.get("use", "sig") == "sig"), None) \
        or next((k for k in keys if k.get("kty") == "RSA"), None)
    if not rsa:
        die("no RSA key in JWKS")
    pem = rsa_public_key_pem_from_jwk(rsa)
    log(f"RSA public key fetched from JWKS (kid={rsa.get('kid', 'n/a')})")
    return pem


def upsert_service():
    status, svc = kong("/services/dq-api")
    if status == 404:
        status, _ = kong("/services", method="POST", data={"name": "dq-api", "url": DQ_API_INTERNAL_URL})
        if status not in (200, 201):
            die(f"create service failed (HTTP {status})")
        log(f"service dq-api created -> {DQ_API_INTERNAL_URL}")
        return
    if status != 200:
        die(f"service lookup failed (HTTP {status})")
    if svc.get("url") != DQ_API_INTERNAL_URL:
        status, _ = kong("/services/dq-api", method="PATCH", data={"url": DQ_API_INTERNAL_URL})
        if status != 200:
            die(f"update service failed (HTTP {status})")
        log(f"service dq-api url updated -> {DQ_API_INTERNAL_URL}")
    else:
        log("service dq-api up to date")


def upsert_route(name, path, methods):
    status, route = kong(f"/routes/{urllib.parse.quote(name, safe='')}")
    if status == 404:
        data = {"name": name, "paths": [path], "strip_path": False}
        if methods:
            data["methods"] = methods
        status, _ = kong("/services/dq-api/routes", method="POST", data=data)
        if status not in (200, 201):
            die(f"create route {name} failed (HTTP {status})")
        return
    if status != 200:
        die(f"route lookup {name} failed (HTTP {status})")
    if route.get("paths") != [path]:
        status, _ = kong(f"/routes/{route['id']}", method="PATCH", data={"paths": [path]})
        if status != 200:
            die(f"update route {name} failed (HTTP {status})")


def upsert_route_plugin(route_name, plugin_name, payload):
    status, plugins = kong(f"/routes/{urllib.parse.quote(route_name, safe='')}/plugins")
    if status != 200:
        die(f"route plugins lookup {route_name} failed (HTTP {status})")
    for p in plugins.get("data", []):
        if p["name"] == plugin_name:
            status, _ = kong(f"/plugins/{p['id']}", method="DELETE")
            if status not in (200, 204):
                die(f"delete plugin {plugin_name} on {route_name} failed (HTTP {status})")
    status, _ = kong(f"/routes/{urllib.parse.quote(route_name, safe='')}/plugins",
                     method="POST", data=payload)
    if status not in (200, 201):
        die(f"create plugin {plugin_name} on {route_name} failed (HTTP {status})")


def upsert_service_plugin(service, plugin_name, payload, replace=True):
    status, plugins = kong(f"/services/{service}/plugins")
    if status != 200:
        die(f"service plugins lookup failed (HTTP {status})")
    existing = [p for p in plugins.get("data", []) if p["name"] == plugin_name]
    if existing:
        if not replace:
            return
        for p in existing:
            status, _ = kong(f"/plugins/{p['id']}", method="DELETE")
            if status not in (200, 204):
                die(f"delete plugin {plugin_name} failed (HTTP {status})")
    status, _ = kong(f"/services/{service}/plugins", method="POST", data=payload)
    if status not in (200, 201):
        die(f"create service plugin {plugin_name} failed (HTTP {status})")


def setup_service_plugins():
    upsert_service_plugin("dq-api", "cors", {
        "name": "cors",
        "config": {
            "origins": CORS_ORIGINS or [OIDC_REDIRECT_BASE],
            "methods": ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
            "headers": ["Accept", "Accept-Version", "Content-Length", "Content-MD5",
                        "Content-Type", "Date", "X-Auth-Token", "Authorization",
                        "X-Correlation-ID", "traceparent", "tracestate", "baggage"],
            "exposed_headers": ["X-Kong-Response-Latency", "X-Kong-Upstream-Latency",
                                "X-Correlation-ID", "X-Trace-ID"],
            "credentials": True,
            "max_age": 3600,
        },
    })
    upsert_service_plugin("dq-api", "rate-limiting", {
        "name": "rate-limiting",
        "config": {"minute": 1000, "hour": 50000, "policy": "local"},
    }, replace=False)
    log("service plugins (cors, rate-limiting) up to date")


def setup_routes_and_auth_plugins():
    for name, path, methods, acl_groups in ROUTES:
        upsert_route(name, path, methods)
    # regex priority so /api/admin/v1/me wins over /api/admin/v1 prefix routes
    status, route = kong("/routes/dq-api-admin-v1-me")
    if status == 200:
        kong(f"/routes/{route['id']}", method="PATCH", data={"regex_priority": 100})
    protected = [(n, g) for n, _, _, g in ROUTES if g]
    for name, acl_groups in protected:
        upsert_route_plugin(name, "jwt", {
            "name": "jwt",
            "config": {
                "key_claim_name": "preferred_username",
                "claims_to_verify": ["exp"],
                "run_on_preflight": False,
            },
        })
        upsert_route_plugin(name, "acl", {
            "name": "acl",
            "config": {"allow": acl_groups, "hide_groups_header": False},
        })
    log(f"routes created/updated ({len(ROUTES)}), jwt+acl on {len(protected)} protected routes")


def consumer_groups_for_roles(role_names):
    groups = ["authenticated"]
    for role in role_names:
        group = ROLE_GROUP.get(role)
        if group and group not in groups:
            groups.append(group)
    return groups


def realm_users(tok):
    users = []
    first = 0
    while True:
        status, page = kc(f"/users?first={first}&max=100", tok)
        if status != 200:
            die(f"user list failed (HTTP {status})")
        users.extend(page)
        if len(page) < 100:
            break
        first += 100
    return users


def sync_consumers(tok, rsa_pem):
    users = realm_users(tok)
    role_id_by_name = None

    def role_names_for(user_id):
        nonlocal role_id_by_name
        if role_id_by_name is None:
            _, roles = kc("/roles", tok)
            role_id_by_name = {r["id"]: r["name"] for r in roles}
        _, mappings = kc(f"/users/{user_id}/role-mappings/realm", tok)
        return [role_id_by_name[m["id"]] for m in mappings if m["id"] in role_id_by_name]

    synced = 0
    for user in users:
        username = user.get("username") or user.get("email")
        if not username or not user.get("enabled", True):
            continue
        enc = urllib.parse.quote(username, safe="")
        groups = consumer_groups_for_roles(role_names_for(user["id"]))
        # Consumer
        status, consumer = kong(f"/consumers/{enc}")
        if status == 404:
            status, _ = kong("/consumers", method="POST",
                             data={"username": username, "custom_id": username})
            if status not in (200, 201):
                die(f"create consumer {username} failed (HTTP {status})")
        elif status != 200:
            die(f"consumer lookup {username} failed (HTTP {status})")
        elif consumer.get("custom_id") != username:
            status, _ = kong(f"/consumers/{enc}", method="PATCH", data={"custom_id": username})
            if status != 200:
                die(f"update consumer {username} failed (HTTP {status})")
        # JWT credential (replace)
        status, creds = kong(f"/consumers/{enc}/jwt")
        if status == 200:
            for c in creds.get("data", []):
                if c.get("key") == username:
                    kong(f"/consumers/{enc}/jwt/{c['id']}", method="DELETE")
        status, _ = http("POST", f"{KONG_ADMIN_URL}/consumers/{enc}/jwt", data=None, form={
            "key": username,
            "algorithm": "RS256",
            "rsa_public_key": rsa_pem,
        })
        if status not in (200, 201):
            die(f"create jwt credential for {username} failed (HTTP {status})")
        # ACL groups (add missing only)
        status, acls = kong(f"/consumers/{enc}/acls")
        have = {a["group"] for a in acls.get("data", [])} if status == 200 else set()
        for group in groups:
            if group not in have:
                status, _ = kong(f"/consumers/{enc}/acls", method="POST", data={"group": group})
                if status not in (200, 201):
                    die(f"add acl group {group} for {username} failed (HTTP {status})")
        synced += 1
    log(f"consumers synced ({synced} users, groups from realm roles)")


def sync_engine_service_consumer(tok, rsa_pem):
    if not ENGINE_CLIENT_ID:
        return
    status, clients = kc(f"/clients?clientId={urllib.parse.quote(ENGINE_CLIENT_ID)}", tok)
    if status != 200 or not clients:
        log(f"engine client {ENGINE_CLIENT_ID} not in realm — skipping engine consumer (best effort)")
        return
    status, sa_user = kc(f"/clients/{clients[0]['id']}/service-account-user", tok)
    if status != 200 or not sa_user.get("id"):
        log(f"no service-account user for {ENGINE_CLIENT_ID} — skipping (best effort)")
        return
    username = sa_user.get("username") or sa_user.get("email")
    if not username:
        return
    enc = urllib.parse.quote(username, safe="")
    groups = consumer_groups_for_roles([
        r["name"] for r in (kc(f"/users/{sa_user['id']}/role-mappings/realm", tok)[1] or [])
    ])
    status, _ = kong(f"/consumers/{enc}")
    if status == 404:
        kong("/consumers", method="POST", data={"username": username, "custom_id": username})
    # Replace existing JWT credential (idempotent re-runs)
    status, creds = kong(f"/consumers/{enc}/jwt")
    if status == 200:
        for c in creds.get("data", []):
            if c.get("key") == username:
                kong(f"/consumers/{enc}/jwt/{c['id']}", method="DELETE")
    status, _ = http("POST", f"{KONG_ADMIN_URL}/consumers/{enc}/jwt", data=None, form={
        "key": username, "algorithm": "RS256", "rsa_public_key": rsa_pem,
    })
    if status not in (200, 201):
        log(f"WARNING: engine consumer jwt credential failed (HTTP {status})")
    status, acls = kong(f"/consumers/{enc}/acls")
    have = {a["group"] for a in acls.get("data", [])} if status == 200 else set()
    for group in groups:
        if group not in have:
            kong(f"/consumers/{enc}/acls", method="POST", data={"group": group})
    log(f"engine service consumer synced: {username}")


def main():
    log(f"realm={KEYCLOAK_REALM} keycloak={KEYCLOAK_URL} kong={KONG_ADMIN_URL}")

    # Phase 1: Keycloak
    tok = tenant_admin_token()
    role_ids = ensure_realm_roles(tok)
    assign_user_roles(tok, role_ids)
    ensure_ui_client(tok)

    # Phase 2: Kong
    wait_for_kong()
    rsa_pem = fetch_rsa_public_key()
    upsert_service()
    setup_service_plugins()
    setup_routes_and_auth_plugins()
    sync_consumers(tok, rsa_pem)
    sync_engine_service_consumer(tok, rsa_pem)

    log("configuration complete")


if __name__ == "__main__":
    main()
