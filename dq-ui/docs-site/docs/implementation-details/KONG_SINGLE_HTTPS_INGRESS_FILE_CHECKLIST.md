# Kong Single HTTPS Ingress - File Checklist

> Superseded note
> This checklist contains historical migration references. Where it mentions `DQ_UI_API_URL`, treat that name as superseded by `KONG_PUBLIC_URL` for browser-facing runtime configuration and `KONG_LOCAL_URL` for host-local usage.

This document turns the Kong edge-cutover into a file-by-file implementation backlog.

Goal: make one edge ingress the single public HTTPS entrypoint while supporting local `*.jac.dot` host-based routing and public `jacloud.nl` / `www.jacloud.nl` single-host path-based routing.

Architecture note: Kong remains behind the edge as the dq-api gateway. Publicly, Keycloak, OpenMetadata, and optional browser apps must live behind path prefixes on the canonical public host rather than on their own public subdomains.

## Scope

- Browser-facing surfaces that must move behind the edge:
  - dq-made-easy UI
  - dq-api
  - Keycloak
  - OpenMetadata
  - Zammad, when the support profile is intended to be public
  - Grafana, only if observability should be browser-accessible outside operator-only access
- Internal-only services that should not be openly exposed through the public internet route map:
  - Kong Admin API and Kong Manager
  - Postgres, Redis, AIStor, OpenTelemetry Collector, Pushgateway
  - dq-engine and worker containers
  - OpenMetadata ingestion and internal support containers

## Implementation Order

1. Add the edge ingress service and publish only `443` for public traffic.
2. Implement local host-based routing for `*.jac.dot`.
3. Implement public single-host path-based routing for `www.jacloud.nl` with apex redirect from `jacloud.nl`.
4. Move dq-made-easy UI and dq-api behind the edge, with dq-api still routed through Kong.
5. Make Keycloak and OpenMetadata path-prefix capable under `/iam` and `/metadata`.
6. Move optional browser apps behind `/support` and `/observability` when needed.
7. Remove direct host-port exposure and keep the edge as the only public HTTPS entrypoint.

## File Task List

### `docker-compose.yml`

1. [ ] Add a dedicated edge ingress service that publishes `443:443`.
   - Support local host-based routes for `dq-made-easy.jac.dot`, `keycloak.jac.dot`, `openmetadata.jac.dot`, and optional local hostnames.
   - Support public path-based routes on `www.jacloud.nl` for `/`, `/iam`, `/metadata`, `/support`, `/observability`, and restricted `/ops/kong`.
   - Redirect `jacloud.nl` to `https://www.jacloud.nl`.

2. [ ] Reduce direct public Kong exposure after the edge is working.
   - Remove or disable the external `9111:8000` mapping.
   - Remove `9443:8443` after the edge is the public HTTPS entrypoint.
   - Keep Kong Admin and Manager non-public or localhost-only unless explicitly routed through restricted `/ops/kong` access.

3. [ ] Remove direct host `ports:` mappings for public apps after edge routes exist.
   - `api`
   - `frontend`
   - `keycloak`
   - `openmetadata-server`
   - `zammad-nginx`, if routed through the edge
   - `grafana`, if routed through the edge

4. [ ] Keep infrastructure and worker services internal-only.
   - Verify no new host `ports:` are added for Postgres, Redis, engines, workers, or observability backends.
   - If operator-only access is needed, prefer localhost-only publication instead of public host exposure.

5. [ ] Update service environment for the new public URLs.
   - `frontend`: `DQ_UI_API_URL`
   - `api`: `OIDC_REDIRECT_BASE_URL`, `DQ_UI_API_URL`
   - `keycloak`: local hostname settings and public `/iam` path settings
   - `openmetadata-server`: local host settings and public `/metadata` callback / authority settings
   - `grafana`: root URL and OIDC browser auth URL
   - `zammad-*`: scheme, fqdn, and trusted proxies

6. [ ] Preserve internal service-to-service URLs where required.
   - Keep `SSO_INTERNAL_ISSUER` for backend and Grafana server-to-server calls.
   - Keep OpenMetadata internal token and userinfo traffic on the Docker network where already expected.
   - Do not replace internal dependency calls with public URLs unless the application requires that.

7. [ ] Add explicit mode handling for local and public edge config.
   - Prefer separate config templates or mounted config files rather than hidden runtime conditionals.

### `dq-kong/scripts/bootstrap_kong.sh`

1. [ ] Keep Kong focused on dq-api route configuration and policy.
   - Keep existing path-based dq-api routes working during migration.
   - Do not add non-API browser app routing here unless there is a separate requirement.

2. [ ] Update public-origin assumptions to the final edge-routed URLs.
   - `KONG_PUBLIC_URL` should represent the browser-facing API base through the edge.
   - local CORS and redirect handling should align with `https://dq-made-easy.jac.dot`.
   - public CORS and redirect handling should align with `https://www.jacloud.nl`.

3. [ ] Keep dq-api route protections fail-fast and explicit.
   - Preserve JWT and ACL setup for protected API routes.
   - Keep public allowlist behavior explicit for health, auth redirect/callback, and docs endpoints.

4. [ ] Preserve forwarded headers and host expectations for dq-api traffic arriving from the edge.
   - Verify `X-Forwarded-Proto` and `Host` handling still produce correct redirects and secure cookies.

### `.env.dev.example`

1. [ ] Keep `.env.dev.example` local-focused.
   - Use `https://dq-made-easy.jac.dot` as the local UI and API base.
   - Use local `*.jac.dot` hostnames for Keycloak and OpenMetadata.
   - Remove stale direct-port public examples.

2. [ ] Add or update deployment-specific env guidance for the public `jacloud.nl` model.
   - Use `.env.prod.example` as the public deployment template.
   - Public canonical UI URL
   - Public Keycloak issuer path under `/iam`
   - Public OpenMetadata path under `/metadata`
   - Optional public Grafana path under `/observability`
   - Optional public Zammad path under `/support`

3. [ ] Keep internal issuer and internal upstream values separate from browser-facing values.

### `.env`

1. [ ] Normalize the repo-local public URLs to the target edge model.
   - Keep local defaults on `https://dq-made-easy.jac.dot`.
   - Keep local Keycloak and OpenMetadata values on local `*.jac.dot` hostnames.
   - Remove direct-port public URLs for Keycloak, OpenMetadata, and Grafana.

2. [ ] Keep server-side internal URLs intact where required.

3. [ ] Verify all OIDC-related values align across UI, API, Keycloak, OpenMetadata, and Grafana.

4. [ ] Do not treat the local `.env` as the deployment truth for the public single-host model.

### `dq-ui/nginx/default.conf`

1. [ ] Decide whether the UI container still needs to proxy `/api` internally.
   - Preferred end state: browser calls the edge on the same public origin, and the edge forwards API paths to Kong.
   - If the internal `/api` proxy is retained for compatibility, verify it still points to the correct upstream and does not bypass Kong policy unexpectedly.

2. [ ] Keep forwarded-proto and host behavior explicit if the frontend remains behind Kong.

3. [ ] Preserve SPA and runtime-config behavior after the edge cutover.

### `dq-ui/scripts/docker-entrypoint-runtime-config.sh`

1. [ ] Update runtime API base expectations to the final public origin.
   - Keep fail-fast behavior when `DQ_UI_API_URL` is missing.
   - Ensure the configured value is the browser-facing URL, not an internal service alias.

2. [ ] Verify generated `runtime-config.js` matches the final edge-routed URL model.

### `dq-ui/src/config/api.ts`

1. [ ] Verify same-origin or host-routed API base behavior is correct after cutover.

2. [ ] Remove legacy assumptions that normalize old internal hostnames or stale ports if they become misleading after migration.

3. [ ] Keep the no-fallback contract intact: the UI must still fail fast if no API base URL is configured.

### `dq-ui/src/auth/browserAuthClient.ts`

1. [ ] Verify browser SSO redirect construction still targets the final public auth endpoints on the edge-routed host model.

2. [ ] Verify issuer URL selection handles both local `https://keycloak.jac.dot` and public `https://www.jacloud.nl/iam` correctly.

3. [ ] Keep HTTPS-only browser SSO behavior explicit.

### `dq-ui/src/auth/keycloakClient.ts`

1. [ ] Update `VITE_KEYCLOAK_PUBLIC_URL` consumers to support local hostnames and the public `/iam` path.

2. [ ] Verify login-required startup still works when Keycloak is path-prefixed publicly.

### `dq-api/fastapi/app/api/v1/endpoints/auth.py`

1. [ ] Verify public redirect base construction uses the final browser-facing URL.

2. [ ] Verify `X-Forwarded-Proto` handling remains correct behind Kong-only HTTPS.

3. [ ] Verify callback HTML still returns the browser to the correct frontend origin after moving off direct container ports.

4. [ ] Keep fail-fast behavior for missing public API base URLs.

### `dq-api/fastapi/app/middleware/require_kong_gateway.py`

1. [ ] Keep Kong-only enforcement for API traffic.

2. [ ] Verify the middleware still recognizes edge -> Kong requests correctly after the new host-based edge routing is added.

3. [ ] Ensure no new direct bypass path is introduced when app ports are removed.

### `dq-api/scripts/generate_keycloak_realm.py`

1. [ ] Update generated redirect and web-origin defaults for both the local `*.jac.dot` model and the public `jacloud.nl` model.

2. [ ] Remove stale direct-port examples, especially for Grafana and the main UI.

3. [ ] Keep explicit input requirements and fail-fast behavior intact.

### `dq-ui/DEPLOYMENT_GUIDE.md`

1. [ ] Update the deployment guide to describe the edge ingress as the only public ingress and Kong as the API gateway behind it.

2. [ ] Remove direct API and direct Keycloak browser access examples.

3. [ ] Document the public single-host path map for `/iam`, `/metadata`, `/support`, and `/observability`.

### `dq-kong/README.md`

1. [ ] Document the new public ingress model.
   - edge ingress on `443`
   - Kong as the dq-api gateway behind the edge
   - non-public admin surfaces

2. [ ] Document the supported hostname inventory.
   - local `*.jac.dot` hosts
   - public `jacloud.nl` and `www.jacloud.nl`

3. [ ] Document the rule that infrastructure services remain private.

### Edge config files

1. [ ] Add separate local and public edge route definitions.
   - local host-based routes
   - public single-host path-based routes
   - apex redirect from `jacloud.nl` to `www.jacloud.nl`

2. [ ] Keep route stripping / prefix preservation explicit for `/iam`, `/metadata`, `/support`, `/observability`, and `/ops/kong`.

3. [ ] Keep fail-fast startup when required certificates or route templates are missing.

## Verification Task List

1. [ ] Verify the edge ingress starts with the new route model and no bootstrap errors.
2. [ ] Verify the UI loads successfully from the local `*.jac.dot` hostnames and from the final public hostname.
3. [ ] Verify API requests succeed through the edge and Kong, and fail when bypassing Kong.
4. [ ] Verify Keycloak login, token refresh, and logout locally and through public `/iam`.
5. [ ] Verify OpenMetadata login and callback flow locally and through public `/metadata`.
6. [ ] Verify Zammad login and application redirects use HTTPS and the public `/support` path when enabled.
7. [ ] Verify Grafana OIDC login and generated links use the public `/observability` path when enabled.
8. [ ] Verify no browser-facing app remains reachable on its old direct host port.
9. [ ] Verify Kong Admin API and Manager are not publicly exposed without operator restrictions.

## Definition of Done

- The edge ingress is the only public HTTPS ingress for supported public web apps.
- Local full-stack execution works on the required `*.jac.dot` hostnames.
- Public browser-facing execution works on `jacloud.nl` and `www.jacloud.nl` without public subdomains.
- The browser no longer depends on direct container host ports for UI, API, auth, or metadata access.
- Internal service ports remain private unless explicitly justified.
- All updated applications use correct public URLs for redirects, callbacks, cookies, and generated links.
- Validation confirms no silent fallback to direct service exposure remains.