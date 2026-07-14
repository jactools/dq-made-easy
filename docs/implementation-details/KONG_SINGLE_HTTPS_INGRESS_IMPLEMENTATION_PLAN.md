# Kong Single HTTPS Ingress - Implementation Plan

> Superseded note
> This implementation plan contains historical cutover references. Where it mentions `DQ_UI_API_URL`, treat that name as superseded by `KONG_PUBLIC_URL` for browser-facing runtime configuration and `KONG_LOCAL_URL` for host-local usage.

## Goal

Implement one public HTTPS edge on port `443` for the platform while supporting:

- local full-stack development on multiple `*.jac.dot` hostnames
- public internet access on `jacloud.nl` and `www.jacloud.nl` only, with no public subdomains

This plan is intentionally concrete for:

- `docker-compose.yml`
- edge route configuration
- Kong bootstrap assumptions
- local and public environment variables
- certificate handling
- validation script alignment

## Dual URL Model

### Local

| Surface | Local browser URL | Routed by | Upstream |
|---|---|---|---|
| dq-made-easy UI | `https://dq-made-easy.jac.dot` | edge ingress | `frontend` |
| dq-api | `https://dq-made-easy.jac.dot/...` | edge ingress -> Kong | `kong` -> `api` |
| Keycloak | `https://keycloak.jac.dot` | edge ingress | `keycloak` |
| OpenMetadata | `https://openmetadata.jac.dot` | edge ingress | `openmetadata-server` |
| Zammad | `https://itsm.jac.dot` | edge ingress | `zammad-nginx` |
| Grafana | `https://observability.jac.dot` | edge ingress | `grafana` |
| Kong Admin / Manager | `https://kong-admin.jac.dot` | edge ingress, restricted only | `kong:8001` and manager |

### Public

| Surface | Public browser URL | Routed by | Upstream |
|---|---|---|---|
| Canonical host | `https://www.jacloud.nl` | edge ingress | mixed by path |
| Alias host | `https://jacloud.nl` | edge redirect | redirect to canonical host |
| dq-api | `https://www.jacloud.nl/...` | edge ingress -> Kong | `kong` -> `api` |
| Keycloak | `https://www.jacloud.nl/iam` | edge ingress | `keycloak` |
| OpenMetadata | `https://www.jacloud.nl/metadata` | edge ingress | `openmetadata-server` |
| Zammad | `https://www.jacloud.nl/support` | edge ingress | `zammad-nginx` |
| Grafana | `https://www.jacloud.nl/observability` | edge ingress | `grafana` |
| Kong Admin / Manager | `https://www.jacloud.nl/ops/kong` | edge ingress, restricted only | `kong:8001` and manager |

## Workstream 1: Add The Edge Ingress Service

### Files

- `docker-compose.yml`
- new edge config files, for example under `dq-edge/`

### Plan

1. Add a dedicated edge ingress service that publishes `443:443`.
2. Support two route modes:
   - local host-based routing for `*.jac.dot`
   - public single-host path-based routing for `www.jacloud.nl`
3. Add apex redirect behavior from `jacloud.nl` to the canonical host.
4. Preserve `Host`, `X-Forwarded-Proto`, `X-Forwarded-For`, and `X-Forwarded-Host`.
5. Route dq-api traffic to Kong rather than directly to dq-api.

### Notes

- The edge ingress is a router and TLS terminator, not a replacement for Kong.
- Kong remains the enforcement point for dq-api auth and gateway policy.
- The edge configuration should likely be split into separate local and public templates to avoid hidden conditional behavior.

## Workstream 2: Keep Kong Focused On API Gateway Concerns

### Files

- `dq-kong/scripts/bootstrap_kong.sh`
- `scripts/init_kong_config.sh`
- `dq-kong/README.md`

### Plan

1. Keep existing dq-api path-based Kong routes.
2. Continue to let Kong own API protection, CORS, tracing, and explicit public allowlists.
3. Update Kong bootstrap assumptions so browser origins align with the active local or public topology.
4. Preserve fail-fast route protection for auth, health, and docs endpoints.

### Required behavior change

`KONG_PUBLIC_URL` should continue to mean the browser-facing API origin, but the value now differs by topology:

- local: `KONG_PUBLIC_URL=https://dq-made-easy.jac.dot`
- public: `KONG_PUBLIC_URL=https://www.jacloud.nl`

This preserves compatibility with existing scripts while changing the actual public origin model.

## Workstream 3: Separate Local And Public Environment Models

### Files

- `.env.dev.example`
- `.env.prod.example`
- local `.env.dev.local`
- `scripts/supporting/setup_env.sh`
- `dq-ui/scripts/docker-entrypoint-runtime-config.sh`
- `dq-ui/src/config/api.ts`

### Plan

1. Keep `.env.dev.example` local-focused, because the repo’s current default workflow is local development.
2. Use `.env.prod.example` as the public `jacloud.nl` template rather than overwriting local defaults.
3. Keep internal service-to-service URLs separate from browser-facing URLs.
4. Stop documenting raw public container ports for steady-state public access.

### Local target values

- `DQ_UI_API_URL=https://dq-made-easy.jac.dot`
- `OIDC_REDIRECT_BASE_URL=https://dq-made-easy.jac.dot`
- `KONG_PUBLIC_URL=https://dq-made-easy.jac.dot`
- `UI_VITE_LOCAL_URL=https://dq-made-easy.jac.dot`
- `UI_NGINX_LOCAL_URL=https://dq-made-easy.jac.dot`
- `KEYCLOAK_PUBLIC_URL=https://keycloak.jac.dot`
- `OPENMETADATA_CALLBACK=https://openmetadata.jac.dot/callback`

### Public target values

- `DQ_UI_API_URL=https://www.jacloud.nl`
- `OIDC_REDIRECT_BASE_URL=https://www.jacloud.nl`
- `KONG_PUBLIC_URL=https://www.jacloud.nl`
- `UI_VITE_LOCAL_URL=https://www.jacloud.nl`
- `UI_NGINX_LOCAL_URL=https://www.jacloud.nl`
- `KEYCLOAK_PUBLIC_URL=https://www.jacloud.nl/iam`
- `SSO_PUBLIC_ISSUER_URL=https://www.jacloud.nl/iam/realms/jaccloud`
- `VITE_KEYCLOAK_PUBLIC_URL=https://www.jacloud.nl/iam`
- `VITE_SSO_ISSUER_URL=https://www.jacloud.nl/iam/realms/jaccloud`
- `OPENMETADATA_CALLBACK=https://www.jacloud.nl/metadata/callback`
- `OM_AUTHENTICATION_AUTHORITY=https://www.jacloud.nl/iam/realms/jaccloud`
- `OM_AUTHENTICATION_CALLBACK_URL=https://www.jacloud.nl/metadata/callback`
- `OM_AUTHENTICATION_DISCOVERY_URI=https://www.jacloud.nl/iam/realms/jaccloud/.well-known/openid-configuration`
- `GRAFANA_PUBLIC_URL=https://www.jacloud.nl/observability` when public access is enabled

### Important note

Because local and public browser URLs differ materially, one static env file cannot be treated as both the local and deployment truth without becoming misleading. The repo should make that separation explicit.

## Workstream 4: Make Public Path Prefixes Real

### Files

- `docker-compose.yml`
- service-specific configuration and env wiring
- auth-related docs and scripts

### Plan

1. Make Keycloak work correctly behind `/iam`.
2. Make OpenMetadata work correctly behind `/metadata`.
3. Make Grafana work correctly behind `/observability` when public access is enabled.
4. Make Zammad work correctly behind `/support` when public access is enabled.
5. Verify service-generated redirects, cookies, issuer metadata, discovery URLs, and callback URLs remain correct.

### Current risk

The repo does not currently show obvious path-prefix support settings for Keycloak or OpenMetadata. This is a mandatory implementation gap, not an optional improvement.

## Workstream 5: Local `*.jac.dot` Resolution And Certificates

### Files

- `scripts/create_certs.sh`
- `scripts/stack_start.sh`
- `scripts/stack.sh dev start`
- docs that explain local setup

### Plan

1. Require local hostname resolution for the local public hosts to `127.0.0.1`.
2. Add a local preflight check that fails if required hostnames are missing from `/etc/hosts` or equivalent local resolver.
3. Update certificate generation to support the local `*.jac.dot` host inventory.
4. Fail fast when `443` is already in use.

### Required local hostnames

- `dq-made-easy.jac.dot`
- `keycloak.jac.dot`
- `openmetadata.jac.dot`
- `kong-admin.jac.dot` when operator edge access is enabled
- `itsm.jac.dot` when support is public
- `observability.jac.dot` when Grafana is public

### Certificate plan

The edge ingress should terminate local TLS with either:

1. one wildcard certificate for `*.jac.dot`, or
2. one explicit SAN certificate covering the required local hostnames

## Workstream 6: Public DNS, TLS, And Canonical Redirects

### Files

- deployment docs
- edge configuration

### Plan

1. Publish `jacloud.nl` and `www.jacloud.nl`.
2. Redirect the apex host to the canonical host.
3. Terminate public TLS with a certificate covering both hosts.
4. Keep all public application surfaces under the canonical host with explicit path prefixes.

## Workstream 7: Remove Direct Public Port Exposure

### Files

- `docker-compose.yml`
- service-specific deployment docs

### Plan

1. Keep existing direct host ports only during migration.
2. After validation, remove public host port mappings for:
   - `api`
   - `frontend`
   - `keycloak`
   - `openmetadata-server`
   - `zammad-nginx` when public through the edge
   - `grafana` when public through the edge
3. Keep Kong Admin and Manager either private, localhost-only, or heavily restricted behind `/ops/kong`.

## Workstream 8: Align Validation And Smoke Scripts

### Files

- `scripts/validate.sh`
- `scripts/validate_user_login_end_to_end.sh`
- `scripts/smoke_test_auth_kong.sh`
- `scripts/validate_openmetadata_otel_smoke.sh`
- any script that still hardcodes `:9443`, `:9444`, `:8585`, or `:3000`

### Plan

1. Update validation scripts so they can run against the local `*.jac.dot` model.
2. Add deployment validation expectations for the public `www.jacloud.nl` model.
3. Use `KONG_PUBLIC_URL=https://dq-made-easy.jac.dot` locally and `KONG_PUBLIC_URL=https://www.jacloud.nl` publicly.
4. Fail fast if validation is pointed at deprecated port-based public URLs once cutover is complete.

## Recommended Execution Order

### Phase 1: Edge Skeleton

1. add the edge ingress service
2. implement local host-based routes for `*.jac.dot`
3. implement public single-host routes for `www.jacloud.nl`
4. keep existing direct ports temporarily for rollback validation

### Phase 2: Environment Separation

1. keep `.env.example` local-focused
2. add a deployment env model for `jacloud.nl`
3. update runtime config handling for both topologies

### Phase 3: Path-Prefix Readiness

1. make Keycloak work under `/iam`
2. make OpenMetadata work under `/metadata`
3. validate service-generated links, discovery, cookies, and callbacks

### Phase 4: Local Prerequisites

1. update `scripts/create_certs.sh`
2. add hostname and port-443 preflight checks
3. document the required `/etc/hosts` entries

### Phase 5: Validation Conversion

1. update smoke and validation scripts to use the new local and public URLs
2. validate login, logout, cookies, redirects, OpenMetadata callback flow, and operator access restrictions

### Phase 6: Exposure Lockdown

1. remove direct public host ports
2. restrict Kong Admin and Manager
3. verify no browser flow depends on legacy public ports or public subdomains

## Definition Of Done

- one public edge publishes `443`
- local full-stack execution works on the required `*.jac.dot` hostnames
- public browser-facing execution works on `jacloud.nl` and `www.jacloud.nl` with no public subdomains
- dq-api browser traffic still goes through Kong
- Keycloak and OpenMetadata work behind their required public path prefixes
- direct public service ports are removed after cutover
- validation scripts no longer assume legacy public ports

## Related Documents

- [KONG_SINGLE_HTTPS_INGRESS_TARGET_ARCHITECTURE.md](./KONG_SINGLE_HTTPS_INGRESS_TARGET_ARCHITECTURE.md)
- [KONG_SINGLE_HTTPS_INGRESS_FILE_CHECKLIST.md](./KONG_SINGLE_HTTPS_INGRESS_FILE_CHECKLIST.md)
- [KONG_SINGLE_HTTPS_INGRESS_APP_CUTOVER_MATRIX.md](./KONG_SINGLE_HTTPS_INGRESS_APP_CUTOVER_MATRIX.md)