# ARCH-1 Frontend as Backend-For-Frontend (BFF)

Status: Proposed

## Goal

Consolidate **all** browser-facing traffic through the **frontend** container as a Backend-For-Frontend (BFF), so the browser never connects directly to Kong, Keycloak, OpenMetadata, Grafana, or any other backend service.

The edge is a **TLS pass-through** (SNI preread stream proxy) — it never terminates TLS and never sees HTTP payloads. It forwards encrypted TCP connections to the appropriate backend based on the SNI hostname. The frontend terminates TLS and proxies every path to the correct backend service over internal HTTPS.

**All traffic — browser-to-edge and edge-to-backend — is encrypted end-to-end.** TLS terminates at the actual service, not at the edge.

## Current architecture

### Public mode (edge)

```
Browser ──TLS──► Edge ─────────────────────────────────────► Kong ──► API
                   │
                   ├──► Frontend (static files only)
                   │
                   ├──► Keycloak (/iam/)
                   │
                   ├──► OpenMetadata (/metadata/)
                   │
                   ├──► Grafana (/observability/)
                   │
                   └──► Zammad (/support/)
```

### Local mode (edge stream)

```
Browser ──TLS──► Edge (SNI preread)
                   │
                   ├──► frontend:443
                   ├──► kong:8443
                   ├──► keycloak:8443
                   ├──► openmetadata-server:8585
                   ├──► grafana:3000
                   └──► zammad-railsserver:3000
```

### Frontend nginx (today)

The frontend already proxies `/api` requests to Kong via internal HTTPS:

```nginx
# Frontend nginx/default.conf
location /api {
    proxy_pass https://kong:8443;
    proxy_ssl_verify on;
    proxy_ssl_trusted_certificate /etc/nginx/certs/trust/internal-ca-bundle.pem;
    ...
}
```

This is the half-built BFF. The gap is that **the edge still exposes Kong routes directly** to the browser.

## Constraints

1. **Edge is TLS pass-through only** — the edge never terminates TLS and never sees HTTP payloads. It uses nginx `stream` with `ssl_preread` to forward encrypted TCP to backends based on SNI hostname.
2. **All internal traffic is TLS/HTTPS** — every hop (edge→frontend, frontend→kong, frontend→keycloak, etc.) uses TLS with certificate verification per SEC-5.
3. **Rate limiting is in the API backend** — Kong handles authentication and routing only. Rate limiting is implemented by the API services themselves.

## Target architecture

### Both modes (BFF)

In BFF mode, both local and public collapse to the same topology. The edge is a TLS pass-through (SNI preread stream proxy) that forwards **all** encrypted TCP to the frontend. The frontend terminates TLS and does all path-based routing.

```
Browser ──TLS (encrypted)──► Edge (SNI preread, pass-through) ──TLS──► Frontend:443 (BFF)
                                                                                │
                                                                                ├──► /, /docs/, /assets/   → static files (self)
                                                                                ├──► /api/                  → kong:8443 (internal HTTPS)
                                                                                ├──► /auth/v1/              → kong:8443 (internal HTTPS)
                                                                                ├──► /admin/v1/             → kong:8443 (internal HTTPS)
                                                                                ├──► /system/v1/            → kong:8443 (internal HTTPS)
                                                                                ├──► /data-catalog/v1/      → kong:8443 (internal HTTPS)
                                                                                ├──► /rulebuilder/v1/       → kong:8443 (internal HTTPS)
                                                                                ├──► /iam/                  → keycloak:8443 (internal HTTPS)
                                                                                ├──► /metadata/             → openmetadata-server:8585 (internal HTTPS)
                                                                                ├──► /observability/        → grafana:3000 (internal HTTPS)
                                                                                ├──► /observability/otlp/   → otel-collector:4318 (internal HTTPS)
                                                                                ├──► /support/              → zammad-railsserver:3000 (internal HTTPS)
                                                                                └──► /health                → kong:8443 (internal HTTPS)
```

**Edge responsibilities (TLS pass-through only):**
- Accept encrypted TCP on port 443
- Read SNI hostname via `ssl_preread`
- Forward encrypted TCP to `frontend:443`
- Never decrypt, never inspect HTTP payloads, never terminate TLS

**Bypass paths** (edge routes directly, not via BFF):
- SNI `ops.jac.dot` → Kong admin (`kon
g:8002`) — operator access
- No edge-level health endpoint needed — edge health is TCP port check

**Kong responsibilities:**
- Authentication (OIDC, JWT validation)
- Request routing to API backends
- **Not** rate limiting (handled by API backends themselves)

## Why BFF matters

### 1. Single browser origin

All browser requests go to one hostname (`https://dq.jac.dot`), not multiple hosts (Kong, Keycloak, Grafana, etc.). This simplifies:

- **CORS**: No cross-origin preflight issues; everything is same-origin
- **CSP**: One `default-src` directive instead of allowlisting every backend host
- **SSO cookies**: No SameSite/cross-domain cookie gymnastics between Kong and Keycloak
- **Service Worker**: Can cache/intercept all API calls from one origin

### 2. Kong becomes internal-only

Kong is a service-mesh API gateway, not a public-facing component. Making it internal-only:

- Reduces Kong's attack surface (no direct browser exposure)
- Kong handles authentication (OIDC, JWT) and request routing only
- Rate limiting is in the API backends themselves (not Kong plugins)
- Aligns with the principle that Kong is an **internal** service mesh, not a public gateway

### 3. Consistent with SEC-5 TLS enforcement

The SEC-5 model requires internal services to communicate over TLS with certificate verification. The frontend already has the trust bundle (`internal-ca-bundle.pem`) and proxy SSL verification enabled for Kong. The BFF extends this to all proxied paths.

### 4. Frontend already has the plumbing

The frontend nginx config already proxies `/api` to Kong with full TLS verification. The BFF completes the pattern by moving all edge routing rules into the frontend.

## Proposed changes

### 1. Edge nginx — both modes (SNI pass-through)

Both local and public modes collapse to the same edge config: a simple SNI preread stream proxy that forwards encrypted TCP to the frontend. The edge **never terminates TLS**.

```nginx
# Edge: BFF mode (TLS pass-through, both local and public)
load_module /usr/lib/nginx/modules/ngx_stream_module.so;

events {
    worker_connections 1024;
}

stream {
    resolver 127.0.0.11 ipv6=off valid=10s;

    map $ssl_preread_server_name $upstream {
        # All normal traffic → Frontend BFF
        frontend.jac.dot    frontend:443;
        dq.jac.dot          frontend:443;
        *.jac.dot           frontend:443;

        # Operator bypass → Kong admin
        ops.jac.dot         kong:8002;

        # Default: drop
        default             127.0.0.1:1;
    }

    server {
        listen 443;
        ssl_preread on;
        proxy_connect_timeout 5s;
        proxy_timeout 300s;
        proxy_pass $upstream;
    }
}
```

**Key properties:**
- Edge sees only SNI hostname and encrypted TCP — **zero HTTP inspection**
- All traffic to `*.jac.dot` goes to `frontend:443` (frontend terminates TLS)
- Operator traffic to `ops.jac.dot` goes to `kong:8002` (Kong admin, plaintext)
- No certificates needed on the edge itself (it just passes through TLS)
- `render_local()` and `render_public()` collapse into one config

**Trade-off vs current local mode:**
- Current local mode fans out to 6 backends via SNI (frontend, kong, keycloak, openmetadata, grafana, zammad). BFF mode sends everything to frontend, which then does path-based routing. This is simpler at the edge, richer in the frontend.

### 2. Frontend nginx — expand proxy coverage

Extend the existing `/api` proxy to cover all backend paths currently handled by the edge:

```nginx
# Already exists:
location /api { ... proxy_pass https://kong:8443; ... }

# New proxy blocks (add to frontend nginx/default.conf):

location /auth/v1/ {
    proxy_pass https://kong:8443;
    include /etc/nginx/proxy_ssl_kong.conf;
}

location /admin/v1/ {
    proxy_pass https://kong:8443;
    include /etc/nginx/proxy_ssl_kong.conf;
}

location /system/v1/ {
    proxy_pass https://kong:8443;
    include /etc/nginx/proxy_ssl_kong.conf;
}

location /data-catalog/v1/ {
    proxy_pass https://kong:8443;
    include /etc/nginx/proxy_ssl_kong.conf;
}

location /rulebuilder/v1/ {
    proxy_pass https://kong:8443;
    include /etc/nginx/proxy_ssl_kong.conf;
}

location /iam/ {
    proxy_set_header X-Forwarded-Prefix /iam;
    proxy_pass https://keycloak:8443;
    include /etc/nginx/proxy_ssl_backend.conf;
}

location /metadata/ {
    proxy_set_header X-Forwarded-Prefix /metadata;
    proxy_pass https://openmetadata-server:8585;
    include /etc/nginx/proxy_ssl_backend.conf;
}

location /observability/otlp/ {
    proxy_pass https://dq-made-easy-otel-collector:4318/;
    include /etc/nginx/proxy_ssl_backend.conf;
}

location /observability/ {
    proxy_set_header X-Forwarded-Prefix /observability;
    proxy_pass https://grafana:3000;
    include /etc/nginx/proxy_ssl_backend.conf;
}

location /support/ {
    proxy_set_header X-Forwarded-Prefix /support;
    proxy_pass https://zammad-railsserver:3000;
    include /etc/nginx/proxy_ssl_backend.conf;
}

location /health {
    proxy_pass https://kong:8443;
    include /etc/nginx/proxy_ssl_kong.conf;
}
```

### 3. Extract shared SSL proxy config

Deduplicate proxy SSL settings into shared includes:

**`/etc/nginx/proxy_ssl_kong.conf`:**
```nginx
proxy_http_version 1.1;
proxy_set_header Host $host;
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
proxy_set_header X-Forwarded-Proto $scheme;
proxy_set_header Connection "";
proxy_ssl_server_name on;
proxy_ssl_name kong.jac.dot;
proxy_ssl_verify on;
proxy_ssl_trusted_certificate /etc/nginx/certs/trust/internal-ca-bundle.pem;
proxy_ssl_verify_depth 2;
```

**`/etc/nginx/proxy_ssl_backend.conf`:**
```nginx
proxy_http_version 1.1;
proxy_set_header Host $host;
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
proxy_set_header X-Forwarded-Proto $scheme;
proxy_set_header Connection "";
proxy_ssl_server_name on;
proxy_ssl_verify on;
proxy_ssl_trusted_certificate /etc/nginx/certs/trust/internal-ca-bundle.pem;
proxy_ssl_verify_depth 2;
```

### 4. Frontend Dockerfile — copy shared configs

```dockerfile
# Dockerfile.frontend additions
COPY nginx/proxy_ssl_kong.conf /etc/nginx/proxy_ssl_kong.conf
COPY nginx/proxy_ssl_backend.conf /etc/nginx/proxy_ssl_backend.conf
```

### 5. Edge env_file

Add `env_file: ../${ROOT_ENV_FILE?ROOT_ENV_FILE is required}` to the edge service definition in `docker-compose/gateway.yml` to follow the same env-file pattern as all other containers.

## Scope

### In scope

- Edge nginx: replace both `render_local()` and `render_public()` with a single SNI stream block
- Frontend nginx: add proxy blocks for all paths currently handled by the edge
- Shared SSL proxy config extraction
- Edge `env_file` directive
- Frontend Dockerfile updates
- Update `40-render-edge-config.sh` to render a single stream config (no `render_public`/`render_local` split)
- Update frontend `docker-compose/core.yml` healthcheck if needed
- Update `docker-compose.yml` and include files (no Kong port exposure to browser)
- Edge no longer needs its own TLS certificate (pure pass-through)

### Out of scope

- Implementing rate limiting (handled by API backends, not Kong)
- Changing Kong's authentication plugins or OIDC configuration
- Changing Keycloak's SSO flow
- Changing the frontend's build pipeline or Vite configuration
- Removing Kong's admin bypass (`ops.jac.dot` → `kong:8002`)

## Acceptance criteria

- [ ] Browser can reach `https://dq.jac.dot` and get the SPA
- [ ] Browser API calls (`/api/v1/...`) work through the BFF
- [ ] SSO login flow (`/iam/...`) works through the BFF
- [ ] Observability OTLP exports (`/observability/otlp/...`) work through the BFF
- [ ] Grafana dashboard (`/observability/...`) works through the BFF
- [ ] OpenMetadata catalog (`/metadata/...`) works through the BFF
- [ ] Support ticket portal (`/support/...`) works through the BFF
- [ ] SNI `ops.jac.dot` reaches Kong admin directly (bypasses BFF)
- [ ] Edge performs **zero** TLS termination (stream mode only, no SSL certificates on edge)
- [ ] All internal service-to-service TLS verification passes (proxy_ssl_verify on with trust bundle)
- [ ] Frontend healthcheck passes
- [ ] Edge healthcheck passes (TCP port 443, no HTTP)
- [ ] `docker compose up` starts without errors
- [ ] `render_local()` and `render_public()` are collapsed into a single stream config

## Security considerations

| Concern | Mitigation |
|---------|-----------|
| Frontend becomes single point of failure | Frontend has healthcheck + restart policy; edge is lightweight TCP pass-through |
| Frontend nginx buffer limits | `client_max_body_size 10M` already set; increase if needed for large payloads |
| CORS simplification | All requests are same-origin; no CORS headers needed (simpler, more secure) |
| Edge never terminates TLS | Edge has zero SSL certificates; it's a pure TCP forwarder with SNI routing |
| Kong admin bypass | SNI `ops.jac.dot` → `kong:8002` (plaintext); consider IP allowlist in production |
| Internal TLS verification | All frontend→backend proxy blocks use `proxy_ssl_verify on` with shared trust bundle |
| Rate limiting | Implemented by API backends themselves, not by Kong or edge |

## Risk assessment

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Frontend nginx OOM under high API traffic | Medium | Monitor memory; tune `worker_connections` and buffer sizes |
| All API traffic passes through frontend | Medium | Frontend nginx is proven to proxy `/api` already; scale horizontally if needed |
| Breaking existing direct Kong connections | High | No backward-compat; document clean break in changelog |
| Edge loses visibility into HTTP errors | Low | Edge is pure TCP pass-through by design; frontend and backend logs provide visibility |
| Kong admin bypass is plaintext (port 8002) | Low | Internal network only; acceptable for operator access; can add TLS later if needed |

## Proposed workstreams

### 1. Frontend nginx expansion
- [ ] `ARCH-1.1` Extract shared proxy SSL includes (`proxy_ssl_kong.conf`, `proxy_ssl_backend.conf`)
- [ ] `ARCH-1.2` Add proxy blocks for all backend paths (auth, admin, iam, metadata, observability, support)
- [ ] `ARCH-1.3` Update Dockerfile.frontend to copy shared configs
- [ ] `ARCH-1.4` Test frontend proxy coverage locally

### 2. Edge simplification (TLS pass-through)
- [ ] `ARCH-1.5` Collapse `render_local()` and `render_public()` into single SNI stream config
- [ ] `ARCH-1.6` Remove edge TLS certificate handling (edge is pure pass-through)
- [ ] `ARCH-1.7` Add SNI `ops.jac.dot` → Kong admin bypass
- [ ] `ARCH-1.8` Add `env_file` to edge service in `gateway.yml`

### 3. Compose and startup
- [ ] `ARCH-1.9` Remove Kong port exposure from `core.yml` (if any)
- [ ] `ARCH-1.10` Update frontend healthcheck for BFF mode
- [ ] `ARCH-1.11` Update edge healthcheck to TCP-only (no HTTP)
- [ ] `ARCH-1.12` Verify `docker compose up` works with BFF architecture
- [ ] `ARCH-1.13` Remove edge certificate generation from startup scripts (no longer needed)

### 4. Documentation
- [ ] `ARCH-1.14` Update edge README with TLS pass-through model
- [ ] `ARCH-1.15` Update user guide with BFF architecture diagram
- [ ] `ARCH-1.16` Document SNI-based operator bypass (`ops.jac.dot`)

## Related references

- [SEC_1_INTERNAL_SERVICE_TLS.md](./SEC_1_INTERNAL_SERVICE_TLS.md) — internal service TLS model
- [SEC_5_SENSITIVE_DATA_ENCRYPTION_AND_KEY_SEGREGATION.md](./SEC_5_SENSITIVE_DATA_ENCRYPTION_AND_KEY_SEGREGATION.md) — TLS enforcement
- [ARCH_1_FRONTEND_BFF.md](./ARCH_1_FRONTEND_BFF.md) — this document
