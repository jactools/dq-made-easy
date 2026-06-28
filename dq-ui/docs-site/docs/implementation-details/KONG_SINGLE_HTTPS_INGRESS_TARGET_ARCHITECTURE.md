# Kong Single HTTPS Ingress - Target Architecture

## Goal

Provide one public internet-facing HTTPS entrypoint on port `443` while supporting two different routing models:

- local full-stack development on multiple `*.jac.dot` hostnames
- public internet access on `jacloud.nl` and `www.jacloud.nl` only, with no public subdomains

Kong remains the API gateway for dq-api traffic. Infrastructure and operator-only surfaces stay non-public by default.

## Decision Summary

The target model is:

1. One edge ingress publishes `:443`.
2. Local development uses host-based routing on multiple `*.jac.dot` hostnames.
3. Public internet access uses a single canonical host, preferably `https://www.jacloud.nl`, with `https://jacloud.nl` redirecting to that canonical host.
4. Public browser apps other than the main UI move behind path prefixes on that one public host.
5. Kong remains behind the edge and continues to own dq-api policy enforcement.
6. Kong Admin and Kong Manager do not become openly internet-visible, even if they are reachable through the same public hostname.

This is a dual-topology design: local host-based routing, public single-host path-based routing.

## Why This Model

The requirement is now explicit:

- locally, multiple hostnames under `*.jac.dot` are acceptable and desirable
- publicly, there must be no subdomains for application surfaces

That rules out the earlier public multi-host recommendation. It also means the repo must support path-prefix deployment for services that currently assume their own public hostname.

Important gap: a repo search did not find obvious current path-prefix settings for Keycloak or OpenMetadata. The single-public-host model is therefore the required target, but it is not yet a low-risk configuration-only change. Path-prefix support must be implemented and validated explicitly.

## Target Edge Topology

### Local topology

```text
Browser
  -> edge ingress :443
     -> dq-made-easy.jac.dot /                     -> frontend nginx
     -> dq-made-easy.jac.dot /api...              -> Kong proxy
     -> dq-made-easy.jac.dot /auth...             -> Kong proxy
     -> dq-made-easy.jac.dot /rulebuilder...      -> Kong proxy
     -> dq-made-easy.jac.dot /system...           -> Kong proxy
     -> dq-made-easy.jac.dot /admin...            -> Kong proxy
     -> dq-made-easy.jac.dot /data-catalog...     -> Kong proxy
     -> keycloak.jac.dot /*                       -> Keycloak
     -> openmetadata.jac.dot /*                   -> OpenMetadata
     -> itsm.jac.dot /*                           -> Zammad (optional)
     -> observability.jac.dot /*                  -> Grafana (optional)
     -> kong-admin.jac.dot /*                     -> Kong Admin / Manager (restricted only)
```

### Public topology

```text
Internet
  -> edge ingress :443
     -> jacloud.nl/*                              -> 301/308 redirect to https://www.jacloud.nl
     -> www.jacloud.nl /                          -> frontend nginx
     -> www.jacloud.nl /api...                    -> Kong proxy
     -> www.jacloud.nl /auth...                   -> Kong proxy
     -> www.jacloud.nl /rulebuilder...            -> Kong proxy
     -> www.jacloud.nl /system...                 -> Kong proxy
     -> www.jacloud.nl /admin...                  -> Kong proxy
     -> www.jacloud.nl /data-catalog...           -> Kong proxy
     -> www.jacloud.nl /iam...                    -> Keycloak
     -> www.jacloud.nl /metadata...               -> OpenMetadata
     -> www.jacloud.nl /support...                -> Zammad (optional)
     -> www.jacloud.nl /observability...          -> Grafana (optional)
     -> www.jacloud.nl /ops/kong...               -> Kong Admin / Manager (restricted only)
```

## Route Model

### Local route model

| Local host | Paths | Upstream service | Notes |
|---|---|---|---|
| `dq-made-easy.jac.dot` | `/` | `frontend` | Main UI shell |
| `dq-made-easy.jac.dot` | `/api`, `/auth`, `/rulebuilder`, `/system`, `/admin`, `/data-catalog`, `/v1` | `kong` | Kong keeps API policy responsibility |
| `keycloak.jac.dot` | `/*` | `keycloak` | Local browser OIDC issuer |
| `openmetadata.jac.dot` | `/*` | `openmetadata-server` | Local metadata UI |
| `itsm.jac.dot` | `/*` | `zammad-nginx` | Optional |
| `observability.jac.dot` | `/*` | `grafana` | Optional |
| `kong-admin.jac.dot` | `/*` | `kong:8001` and optionally manager | Restricted only |

### Public route model

| Public host | Public paths | Upstream service | Notes |
|---|---|---|---|
| `jacloud.nl` | `/*` | edge redirect | Redirect to canonical `https://www.jacloud.nl` |
| `www.jacloud.nl` | `/` | `frontend` | Main product entrypoint |
| `www.jacloud.nl` | `/api`, `/auth`, `/rulebuilder`, `/system`, `/admin`, `/data-catalog`, `/v1` | `kong` | Kong remains responsible for API auth, ACLs, rate limiting, and route policy |
| `www.jacloud.nl` | `/iam` | `keycloak` | Public Keycloak base path; requires explicit relative-path support |
| `www.jacloud.nl` | `/metadata` | `openmetadata-server` | Public OpenMetadata base path; requires explicit base-path support validation |
| `www.jacloud.nl` | `/support` | `zammad-nginx` | Optional |
| `www.jacloud.nl` | `/observability` | `grafana` | Optional and preferably operator-only |
| `www.jacloud.nl` | `/ops/kong` | `kong:8001` and optionally manager | Restricted only; avoid if private access is possible |

## Public Exposure Policy

### Public by default

- dq-made-easy UI
- dq-api through Kong
- Keycloak under `/iam`
- OpenMetadata under `/metadata`

### Public only when explicitly intended

- Zammad under `/support`
- Grafana under `/observability`

### Never open to the internet without operator controls

- Kong Admin API
- Kong Manager
- Postgres
- Redis
- AIStor
- OpenTelemetry Collector
- Pushgateway
- dq-engine
- worker containers
- OpenMetadata ingestion and helper containers

## Edge Proxy Responsibilities

The edge ingress is an L7 router and TLS terminator. It does not replace Kong.

It should:

- terminate public TLS on `:443`
- support local host-based routing and public single-host path-based routing
- preserve `Host`, `X-Forwarded-Proto`, `X-Forwarded-For`, and `X-Forwarded-Host`
- forward dq-api traffic to Kong rather than directly to dq-api
- perform path stripping or prefix preservation intentionally for `/iam`, `/metadata`, `/support`, `/observability`, and `/ops/kong`
- enforce operator-only controls for Kong Admin and Kong Manager

It should not:

- duplicate Kong JWT or ACL policy
- bypass Kong for dq-api browser traffic
- silently fall back to legacy direct public ports once cutover is complete

## Kong Responsibilities In The Target State

Kong remains the policy gateway for dq-api and any other API surfaces intentionally routed through it.

Kong keeps responsibility for:

- JWT validation where enabled
- ACL enforcement
- rate limiting
- CORS for API traffic
- request tracing and gateway headers
- dq-api route segmentation and explicit public allowlist behavior

Kong does not become the general-purpose reverse proxy for all browser apps. The edge ingress owns the public single-host path map, and Kong owns the API gateway concerns behind it.

## Service-Specific Target Settings

### dq-made-easy UI

- Local URL: `https://dq-made-easy.jac.dot`
- Public canonical URL: `https://www.jacloud.nl`
- Public alias: `https://jacloud.nl` redirecting to the canonical host
- Preferred browser API base remains same-origin path routing through the edge ingress

### dq-api

- Local browser base: `https://dq-made-easy.jac.dot`
- Public browser base: `https://www.jacloud.nl`
- No direct public host port after cutover
- Browser traffic must arrive through the edge ingress and Kong

### Keycloak

- Local URL: `https://keycloak.jac.dot`
- Public URL: `https://www.jacloud.nl/iam`
- Public deployment requires explicit Keycloak relative-path and forwarded-host support
- Internal issuer/admin URLs stay on the Docker network where server-to-server flows already depend on them

### OpenMetadata

- Local URL: `https://openmetadata.jac.dot`
- Public URL: `https://www.jacloud.nl/metadata`
- Public deployment requires explicit base-path support validation
- Callback, authority, and discovery URLs must align with the public `/iam` and `/metadata` paths

### Zammad

- Local URL when used: `https://itsm.jac.dot`
- Public URL when used: `https://www.jacloud.nl/support`
- Proxy trust and HTTPS scheme settings must stay explicit

### Grafana

- Local URL when used: `https://observability.jac.dot`
- Public URL when used: `https://www.jacloud.nl/observability`
- `GF_SERVER_ROOT_URL` and login callback behavior must align with the path prefix

### Kong Admin and Kong Manager

- Local operator URL when exposed through the edge: `https://kong-admin.jac.dot`
- Public preference: private access only, not internet exposure
- If the same-host requirement is absolute even for operator surfaces, use `https://www.jacloud.nl/ops/kong` with VPN, IP allowlist, and extra authentication at the edge

## DNS And TLS Model

### Local

- hostnames under `*.jac.dot` resolve to `127.0.0.1`
- TLS can use either a wildcard certificate for `*.jac.dot` or a SAN certificate covering the local hosts

### Public

- public DNS exposes `jacloud.nl` and `www.jacloud.nl`
- `jacloud.nl` redirects to the canonical host
- TLS covers `jacloud.nl` and `www.jacloud.nl`

## Local `*.jac.dot` Runtime Model

Local full-stack mode should use:

- `https://dq-made-easy.jac.dot`
- `https://keycloak.jac.dot`
- `https://openmetadata.jac.dot`
- `https://observability.jac.dot` when Grafana is public in local testing
- `https://itsm.jac.dot` when Zammad is public in local testing
- `https://kong-admin.jac.dot` only for restricted operator access

Required local behavior:

1. each hostname resolves to `127.0.0.1`
2. the edge ingress binds public `443`
3. startup fails fast if `443` is unavailable
4. startup fails fast if required local hostnames are not configured

Existing local `:5174` Vite development can remain for frontend-only work, but it is a separate developer workflow rather than the target full-stack ingress model.

## Public Single-Host Runtime Model

Public browser-facing traffic should use:

- `https://www.jacloud.nl/`
- `https://www.jacloud.nl/iam`
- `https://www.jacloud.nl/metadata`
- `https://www.jacloud.nl/support` when enabled
- `https://www.jacloud.nl/observability` when enabled

Required public behavior:

1. `https://jacloud.nl` redirects to `https://www.jacloud.nl`
2. no public app requires a public subdomain
3. service-generated redirects and callbacks stay within the canonical host and the assigned path prefixes
4. operator surfaces remain restricted even if they live under the same public hostname

## Direct Port Removal Target

After cutover, these should not remain publicly published on host ports:

- `api`
- `frontend`
- `keycloak`
- `openmetadata-server`
- `zammad-nginx` when publicly routed
- `grafana` when publicly routed

Only the edge ingress should publish public `:443`.

Kong Admin and Manager should either:

- not publish host ports at all, or
- publish only to localhost, or
- be exposed only behind restricted operator access

## Recommended Implementation Sequence

### Phase 1: Edge Foundation

1. Introduce one edge ingress service publishing only `443`.
2. Implement local host-based routes for `*.jac.dot`.
3. Implement public single-host routes for `www.jacloud.nl` plus apex redirect.
4. Keep all existing direct ports during initial validation.

### Phase 2: Public Path-Prefix Readiness

1. Make Keycloak work correctly under `/iam`.
2. Make OpenMetadata work correctly under `/metadata`.
3. Validate redirect, issuer, callback, and generated-link behavior.

### Phase 3: Core App Cutover

1. Move the UI browser origin to the final canonical public host.
2. Keep dq-api behind Kong only.
3. Move public auth and metadata traffic behind the single-host edge routes.

### Phase 4: Optional Browser Apps

1. Move Zammad to `/support` if it should be public.
2. Move Grafana to `/observability` only if public browser access is intentional.

### Phase 5: Exposure Lockdown

1. remove direct public host ports for moved apps
2. keep Kong Admin and Manager restricted
3. verify no browser workflow depends on raw container ports or public subdomains

## Definition Of Done

- exactly one internet-facing `:443` entrypoint exists
- local full-stack execution works on the required `*.jac.dot` hostnames
- public browser-facing execution works on `jacloud.nl` and `www.jacloud.nl` with no public subdomains
- dq-api browser traffic reaches the API only through the edge and Kong
- Keycloak and OpenMetadata use correct public path prefixes with correct callbacks and discovery URLs
- direct public host ports are removed for migrated apps
- Kong Admin and Kong Manager remain reachable only through restricted operator access

## Related Documents

- [KONG_SINGLE_HTTPS_INGRESS_IMPLEMENTATION_PLAN.md](/docs/implementation-details/KONG_SINGLE_HTTPS_INGRESS_IMPLEMENTATION_PLAN/)
- [KONG_SINGLE_HTTPS_INGRESS_FILE_CHECKLIST.md](/docs/implementation-details/KONG_SINGLE_HTTPS_INGRESS_FILE_CHECKLIST/)
- [KONG_SINGLE_HTTPS_INGRESS_APP_CUTOVER_MATRIX.md](/docs/implementation-details/KONG_SINGLE_HTTPS_INGRESS_APP_CUTOVER_MATRIX/)