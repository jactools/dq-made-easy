# ARCH-1 Frontend BFF — Implementation Plan

Architectural decision: [ARCH_1_FRONTEND_BFF.md](/docs/features/ARCH_1_FRONTEND_BFF/)

## Summary

Route all browser traffic through the frontend as a Backend-For-Frontend (BFF). The edge becomes a pure TLS pass-through (SNI stream proxy) that forwards all encrypted TCP to the frontend. The frontend terminates TLS and proxies every path to the correct backend service over internal HTTPS.

## Principles

- **Edge never terminates TLS** — it only reads SNI hostnames and forwards encrypted TCP.
- **Frontend is the single browser origin** — all paths (API, SSO, observability, support) are served from one hostname.
- **Internal TLS verification required** — every frontend-to-backend proxy block uses `proxy_ssl_verify on` with the shared trust bundle.
- **No hostname literals in implementation files** — hostnames come from env vars (`KONG_SERVICE_FQDN`, `KEYCLOAK_SERVICE_FQDN`, etc.) so the plan is portable across dev/test/prod.

## Workstreams

### WS-1: Frontend nginx expansion

Extend the existing frontend nginx config to proxy all paths currently handled by the edge.

**WS-1.1: Extract shared proxy SSL includes**

Create two shared include files under `dq-ui/nginx/` that deduplicate proxy SSL settings:

| File | Purpose |
|------|---------|
| `proxy_ssl_kong.conf` | Proxy SSL settings for Kong (uses `KONG_SERVICE_FQDN` for SNI) |
| `proxy_ssl_backend.conf` | Proxy SSL settings for all other backends (service FQDN from env) |

Each include defines:
- HTTP version, standard proxy headers (`Host`, `X-Real-IP`, `X-Forwarded-For`, `X-Forwarded-Proto`, `Connection`)
- `proxy_ssl_server_name on`
- `proxy_ssl_name` set from the appropriate env-var-derived service FQDN
- `proxy_ssl_verify on` with the shared trust bundle (`/etc/nginx/certs/trust/internal-ca-bundle.pem`)
- `proxy_ssl_verify_depth 2`

**WS-1.2: Add backend proxy blocks to frontend nginx**

Add `location` blocks to `dq-ui/nginx/default.conf.template` for every path the edge currently handles:

| Path | Upstream | Notes |
|------|----------|-------|
| `/api/` | Kong | Already exists — keep as-is |
| `/auth/v1/` | Kong | API auth routes |
| `/admin/v1/` | Kong | Admin API routes |
| `/system/v1/` | Kong | System API routes |
| `/data-catalog/v1/` | Kong | Data catalog routes |
| `/rulebuilder/v1/` | Kong | Rule builder routes |
| `/iam/` | Keycloak | SSO login/logout/registration |
| `/metadata/` | OpenMetadata server | Data catalog UI |
| `/observability/` | Grafana | Dashboards |
| `/observability/otlp/` | OTEL collector | Browser OTLP exports (already exists) |
| `/support/` | Zammad Rails server | Support ticket portal |
| `/health` | Kong | Health endpoint for compose healthcheck |

For paths that need prefix stripping (`/iam/` → Keycloak root, `/metadata/` → OpenMetadata root, `/observability/` → Grafana root), use `proxy_set_header X-Forwarded-Prefix` and the backend's own prefix handling. For Kong-proxied paths, use `rewrite` to strip the BFF prefix and forward to Kong's internal route.

**WS-1.3: Update Frontend Dockerfile**

- Copy the new shared include files into the image (`/etc/nginx/proxy_ssl_kong.conf`, `/etc/nginx/proxy_ssl_backend.conf`)
- Ensure the trust bundle mount is present (`../tmp/certs/trust/internal-ca-bundle.pem:/etc/nginx/certs/trust/internal-ca-bundle.pem:ro`)
- Keep existing cert/key mounts and template rendering pipeline

**WS-1.4: Add required env vars to .env files**

Add service FQDN env vars to all `.env.*.local` files so the frontend nginx template can resolve backend hostnames at render time:

| Env var | Purpose |
|---------|---------|
| `KONG_SERVICE_FQDN` | SNI name for Kong proxy SSL |
| `KEYCLOAK_SERVICE_FQDN` | SNI name for Keycloak proxy SSL |
| `OPENMETADATA_SERVICE_FQDN` | SNI name for OpenMetadata proxy SSL |
| `GRAFANA_SERVICE_FQDN` | SNI name for Grafana proxy SSL |
| `ZAMMAD_SERVICE_FQDN` | SNI name for Zammad proxy SSL |

These are already partially present (e.g., `KONG_SERVICE_FQDN` exists). Audit and add any missing ones.

**WS-1.5: Update frontend template render script**

The frontend entrypoint script that renders `default.conf.template` → `default.conf` must substitute the new env vars into the proxy blocks. Ensure the Jinja2/variable substitution handles all new `{&#123;SERVICE_FQDN&#125;}` tokens.

**WS-1.6: Verify frontend healthcheck**

Update the frontend healthcheck in the compose file to use `/health` (proxied to Kong) instead of the current static-file check, so it validates the BFF proxy chain end-to-end.

---

### WS-2: Edge simplification (TLS pass-through)

Replace the current dual-mode edge config (local fan-out + public HTTP reverse proxy) with a single SNI stream block.

**WS-2.1: Collapse render_local and render_public into a single stream config**

Modify `dq-edge/docker-entrypoint.d/40-render-edge-config.sh` to produce a single `stream` nginx config with an `ssl_preread` SNI map. The map routes:

| SNI pattern | Upstream |
|-------------|----------|
| Primary frontend hostname (env-derived) | `frontend:443` |
| Wildcard for all app subdomains | `frontend:443` |
| Operator hostname (env-derived) | `kong:8002` (Kong admin bypass, plaintext) |
| `default` | `127.0.0.1:1` (drop) |

Remove `render_local()` and `render_public()` functions. Replace with a single `render_stream()` function that reads hostnames from env vars.

**WS-2.2: Remove edge TLS certificate handling**

The edge no longer needs TLS certificates (it's pure pass-through). Remove:

- Edge cert/key volume mounts from `docker-compose/gateway.yml`
- `ensure_edge_cert_assets()` calls from `scripts/stack_start.sh`
- Edge cert generation logic from startup scripts
- Any edge-specific `mkcert` invocations that produce edge certs

**WS-2.3: Add env_file to edge service**

Add `env_file` to the edge service definition in `docker-compose/gateway.yml` to follow the same env-file pattern as all other containers. The edge needs env vars for:

| Env var | Purpose |
|---------|---------|
| `FRONTEND_SERVICE_FQDN` | SNI hostname for frontend routing |
| `OPERATOR_SERVICE_FQDN` | SNI hostname for Kong admin bypass |

**WS-2.4: Update edge healthcheck**

Replace the HTTP-based edge healthcheck with a TCP port check on 443. The edge is pure pass-through and cannot respond to HTTP requests.

---

### WS-3: Compose and startup wiring

Wire the changes through docker-compose and startup scripts.

**WS-3.1: Remove Kong port exposure**

Kong is now internal-only. Remove any `ports:` mapping for Kong (8443, 8002) from the compose files. The only externally-facing ports are:

| Port | Service |
|------|---------|
| 443 | Edge (TLS pass-through to frontend) |
| 5174 | Vite dev server (local dev only, behind edge in production) |

**WS-3.2: Update edge depends_on**

The edge no longer depends on Kong or Keycloak being healthy. It only needs to reach the frontend on port 443. Update `depends_on` to:

```yaml
depends_on:
  frontend:
    condition: service_healthy
```

**WS-3.3: Update frontend depends_on**

The frontend now proxies to many backends. Add `depends_on` for the services it proxies to at startup (at minimum Kong for `/health`):

```yaml
depends_on:
  kong:
    condition: service_healthy
  trust-bundle:
    condition: service_completed_successfully
```

Other backends (Keycloak, Grafana, OpenMetadata, Zammad) can be lazy-loaded via nginx deferred DNS resolution (resolver + variable), consistent with the existing OTEL collector pattern.

**WS-3.4: Update startup scripts**

- Remove `ensure_edge_cert_assets()` from `scripts/stack_start.sh`
- Remove edge cert generation from any other startup script
- Ensure the trust bundle is still generated (frontend needs it for proxy SSL verification)

---

### WS-4: Documentation

**WS-4.1: Update edge README**

Rewrite `dq-edge/README.md` to document the TLS pass-through model:

- Edge is a pure TCP forwarder with SNI routing
- No TLS certificates on the edge
- SNI-based routing to frontend and operator bypass
- No HTTP inspection or payload visibility

**WS-4.2: Update user guide / architecture docs**

Update any architecture diagrams to show the BFF topology. All browser traffic flows:

```
Browser → Edge (SNI pass-through) → Frontend (TLS terminate + path routing) → Backend services
```

**WS-4.3: Document SNI-based operator bypass**

Document the operator bypass pattern (`OPERATOR_SERVICE_FQDN` → Kong admin) and note that it is plaintext on port 8002 (internal network only).

## Execution order

Execute workstreams in dependency order:

| Phase | Workstream | Depends on |
|-------|-----------|------------|
| 1 | WS-1 (Frontend nginx expansion) | None |
| 2 | WS-2 (Edge simplification) | WS-1 (edge needs frontend to accept all traffic) |
| 3 | WS-3 (Compose and startup) | WS-1 + WS-2 |
| 4 | WS-4 (Documentation) | WS-1 + WS-2 + WS-3 |

## Rollback plan

If BFF mode causes issues:

1. Revert compose files to pre-BFF state (restores Kong port exposure and edge fan-out)
2. Revert `40-render-edge-config.sh` to dual-mode (`render_local` + `render_public`)
3. Restore edge cert mounts and `ensure_edge_cert_assets()`
4. Frontend nginx remains expanded (no harm; unused proxy blocks are inert)

The frontend nginx expansion is additive and reversible at zero cost. The breaking changes are in the edge config and compose files, which are separate commits.

## Acceptance criteria

Map to the acceptance criteria in [ARCH_1_FRONTEND_BFF.md](/docs/features/ARCH_1_FRONTEND_BFF/):

| # | Criteria | Verification |
|---|----------|-------------|
| 1 | Browser reaches SPA on primary hostname | `curl -k https://primary-hostname/` returns HTML |
| 2 | API calls work through BFF | `curl -k https://primary-hostname/api/system/v1/ui-registry` returns JSON |
| 3 | SSO login flow works through BFF | `/iam/realms/master/.well-known/openid-configuration` returns OIDC discovery doc |
| 4 | Grafana dashboard works through BFF | `/observability/` returns Grafana HTML |
| 5 | OpenMetadata catalog works through BFF | `/metadata/` returns OpenMetadata HTML |
| 6 | Support portal works through BFF | `/support/` returns Zammad HTML |
| 7 | OTLP exports work through BFF | `/observability/otlp/` accepts POST |
| 8 | Operator bypass reaches Kong admin | SNI `operator-hostname` → `curl http://operator-hostname:8002/` returns Kong admin |
| 9 | Edge performs zero TLS termination | Edge nginx config has no `server` blocks in `http` context; only `stream` with `ssl_preread` |
| 10 | Internal TLS verification passes | All proxy blocks use `proxy_ssl_verify on` with trust bundle |
| 11 | Frontend healthcheck passes | `docker compose ps` shows frontend as healthy |
| 12 | Edge healthcheck passes | TCP port 443 check succeeds |
| 13 | `docker compose up` starts without errors | Full startup completes |
| 14 | `render_local`/`render_public` collapsed | `40-render-edge-config.sh` has single `render_stream()` function |

## Risks and mitigations

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Frontend nginx OOM under high API traffic | Medium | Monitor memory; tune `worker_connections` and buffer sizes |
| All API traffic passes through frontend | Medium | Frontend nginx already proxies `/api`; scale horizontally if needed |
| Breaking existing direct Kong connections | High | No backward-compat; document in changelog |
| Edge loses visibility into HTTP errors | Low | Edge is pure TCP pass-through by design; frontend and backend logs provide visibility |
| Kong admin bypass is plaintext (port 8002) | Low | Internal network only; can add TLS later if needed |

## Files to modify (no code)

| File | Change |
|------|--------|
| `dq-ui/nginx/default.conf.template` | Add proxy blocks for auth, admin, iam, metadata, observability, support, health |
| `dq-ui/nginx/proxy_ssl_kong.conf` | **New** — shared Kong proxy SSL settings |
| `dq-ui/nginx/proxy_ssl_backend.conf` | **New** — shared backend proxy SSL settings |
| `dq-ui/Dockerfile.frontend` | Copy shared proxy SSL includes |
| `dq-ui/scripts/render-frontend-config.sh` | Substitute new env vars in template |
| `dq-edge/docker-entrypoint.d/40-render-edge-config.sh` | Replace `render_local`/`render_public` with `render_stream` |
| `docker-compose/gateway.yml` | Add `env_file` to edge; remove edge cert mounts; update edge healthcheck; remove Kong port exposure |
| `docker-compose/core.yml` | Update frontend healthcheck and `depends_on` |
| `scripts/stack_start.sh` | Remove `ensure_edge_cert_assets()` |
| `.env.dev.local`, `.env.test.local`, `.env.prod.local` | Add missing service FQDN env vars |
| `dq-edge/README.md` | Document TLS pass-through model |

## Out of scope

- Rate limiting (handled by API backends)
- Kong authentication plugin changes
- Keycloak SSO flow changes
- Frontend build pipeline or Vite configuration changes
- Removing Kong admin bypass
