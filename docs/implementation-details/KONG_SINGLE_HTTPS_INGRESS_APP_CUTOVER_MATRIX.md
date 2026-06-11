# Kong Single HTTPS Ingress - App Cutover Matrix

> Superseded note
> This cutover matrix contains historical migration steps. Where it mentions `DQ_UI_API_URL`, treat that name as superseded by `KONG_PUBLIC_URL` for browser-facing runtime configuration and `KONG_LOCAL_URL` for host-local usage.

This document breaks the Kong cutover down by application so each app can be migrated and verified independently.

Goal: provide an app-by-app task list that identifies local URL, public URL, required configuration changes, break risks, and verification steps.

Architecture note: the target model uses one edge ingress on public `:443`, with local host-based routing on `*.jac.dot` and public single-host path-based routing on `www.jacloud.nl`. Kong remains behind that edge for dq-api traffic.

## Local And Public Route Map

| Application | Local URL | Public URL | Should be public | Notes |
|---|---|---|---|---|
| dq-made-easy UI | `https://dq-made-easy.jac.dot` | `https://www.jacloud.nl` | yes | Main product entrypoint |
| dq-api | routed under `https://dq-made-easy.jac.dot` | routed under `https://www.jacloud.nl` | yes | API remains path-based through Kong |
| Keycloak | `https://keycloak.jac.dot` | `https://www.jacloud.nl/iam` | yes | Public OIDC issuer and browser login |
| OpenMetadata | `https://openmetadata.jac.dot` | `https://www.jacloud.nl/metadata` | yes | Public path-prefix support must be validated |
| Zammad | `https://itsm.jac.dot` | `https://www.jacloud.nl/support` | optional | Only when support is intended to be browser-accessible |
| Grafana | `https://observability.jac.dot` | `https://www.jacloud.nl/observability` | optional | Prefer operator-only unless public dashboard access is required |
| Kong Admin API | `https://kong-admin.jac.dot` | `https://www.jacloud.nl/ops/kong` | restricted only | Prefer private or localhost-only over public operator routing |
| Kong Manager | `https://kong-admin.jac.dot` | `https://www.jacloud.nl/ops/kong` | restricted only | Prefer private or localhost-only over public operator routing |

## App Cutover Task Lists

### dq-made-easy UI

#### Current state

- Public URL examples still reference direct ports and Kong hostnames.
- Runtime API base is injected via `DQ_UI_API_URL`.
- Browser SSO uses public issuer settings from Vite/runtime config.

#### Tasks

1. [ ] Keep the local browser-facing URL on `https://dq-made-easy.jac.dot`.
2. [ ] Set the final public browser-facing product URL to `https://www.jacloud.nl`.
3. [ ] Redirect `https://jacloud.nl` to the canonical public host.
4. [ ] Change `DQ_UI_API_URL` so local uses `https://dq-made-easy.jac.dot` and public uses `https://www.jacloud.nl`.
3. [ ] Verify the UI does not require direct access to container port `5173` or `5174`.
5. [ ] Keep the UI on same-origin browser paths while the edge forwards API traffic to Kong.
6. [ ] Update any local/deployment guides that still instruct users to hit the direct frontend port.

#### Break risks

1. [ ] Runtime API base still points at `https://kong.jac.dot:9443` or localhost examples.
2. [ ] Browser SSO still points to stale Keycloak hostnames instead of local `keycloak.jac.dot` or public `/iam`.
3. [ ] UI startup fails fast if `DQ_UI_API_URL` is not updated.

#### Verification

1. [ ] Load the application shell at `https://dq-made-easy.jac.dot`.
2. [ ] Load the application shell at `https://www.jacloud.nl`.
3. [ ] Verify authenticated API traffic succeeds through Kong.
4. [ ] Verify logout returns the browser to the correct frontend host.

### dq-api

#### Current state

- Kong already routes dq-api by path.
- The API still publishes a direct host port.
- Auth redirect/callback logic already depends on explicit public URLs and forwarded scheme handling.

#### Tasks

1. [ ] Keep dq-api behind Kong path routes on the main product host.
2. [ ] Remove direct host port exposure for the `api` service after Kong routes are validated.
3. [ ] Update `OIDC_REDIRECT_BASE_URL` and `DQ_UI_API_URL` to support both the local and public URL models.
4. [ ] Keep `TRUST_PROXY_AUTH` aligned with the policy that API traffic must arrive through the edge and Kong.

#### Break risks

1. [ ] Missing or stale public redirect base breaks auth redirects.
2. [ ] Direct host exposure undermines `RequireKongGatewayMiddleware` assumptions.
3. [ ] Incorrect forwarded-proto handling could create non-secure cookies.

#### Verification

1. [ ] Verify `/auth/v1/redirect`, `/auth/v1/callback`, and `/auth/v1/logout` through Kong locally and publicly.
2. [ ] Verify API calls fail when attempted directly without Kong.
3. [ ] Verify session cookies are marked secure behind Kong HTTPS.

### Keycloak

#### Current state

- Keycloak already has a public hostname concept and internal issuer separation.
- It is still directly exposed on container ports.

#### Tasks

1. [ ] Keep `KEYCLOAK_PUBLIC_HOSTNAME` and `KEYCLOAK_PUBLIC_URL` as the canonical public browser URL.
2. [ ] Keep local browser access on `https://keycloak.jac.dot`.
3. [ ] Make public browser access work on `https://www.jacloud.nl/iam`.
3. [ ] Remove direct host exposure for Keycloak once Kong routing is working.
4. [ ] Keep internal issuer and admin URLs on the Docker network for server-to-server calls.

#### Break risks

1. [ ] OIDC clients still point at `:9444` instead of the final local or public URL.
2. [ ] Keycloak redirects and issuer metadata may be inconsistent if `/iam` relative-path handling is incomplete.

#### Verification

1. [ ] Open the OIDC discovery endpoint on `https://keycloak.jac.dot`.
2. [ ] Open the OIDC discovery endpoint on `https://www.jacloud.nl/iam`.
3. [ ] Complete a full login flow from the UI.
4. [ ] Verify token refresh and logout still work.

### OpenMetadata

#### Current state

- OpenMetadata is directly exposed.
- Its callback and authority settings explicitly use the old direct public URLs.

#### Tasks

1. [ ] Keep local OpenMetadata access on `https://openmetadata.jac.dot`.
2. [ ] Make public OpenMetadata access work on `https://www.jacloud.nl/metadata`.
3. [ ] Update `OM_AUTHENTICATION_AUTHORITY` to the final public Keycloak `/iam` URL.
4. [ ] Update `OM_AUTHENTICATION_CALLBACK_URL` to the final public OpenMetadata `/metadata` callback URL.
5. [ ] Update `OM_AUTHENTICATION_DISCOVERY_URI` to the final public Keycloak discovery URL.
5. [ ] Remove the direct host port after OIDC flow validation.

#### Break risks

1. [ ] High risk of broken login callback if callback URL remains on `:8585`.
2. [ ] High risk of broken public path-prefix behavior if OpenMetadata still assumes root-path hosting.
3. [ ] High risk of mixed internal/public URL confusion during cutover.

#### Verification

1. [ ] Load OpenMetadata on `https://openmetadata.jac.dot`.
2. [ ] Load OpenMetadata on `https://www.jacloud.nl/metadata`.
3. [ ] Complete the Keycloak-backed login flow.
4. [ ] Verify generated callback and login links use the correct host and path prefix.

### Zammad

#### Current state

- Zammad is exposed through `zammad-nginx` directly.
- Proxy and public-scheme related settings are present but not yet aligned for a Kong-terminated HTTPS edge.

#### Tasks

1. [ ] Keep local Zammad access on `https://itsm.jac.dot` if support is enabled locally.
2. [ ] Route Zammad through `https://www.jacloud.nl/support` if support should be public.
3. [ ] Update `ZAMMAD_PUBLIC_URL` to the final public support URL model.
3. [ ] Update `NGINX_SERVER_SCHEME` and `ZAMMAD_HTTP_TYPE` for the HTTPS edge model.
4. [ ] Configure `RAILS_TRUSTED_PROXIES` so proxy forwarding is explicit and trusted.
5. [ ] Remove the direct host port only after redirect and cookie behavior is validated.

#### Break risks

1. [ ] Redirects may continue to use HTTP if scheme settings remain stale.
2. [ ] Cookies or proxy trust may break if the trusted proxy list is left empty.
3. [ ] Application-generated links may still point to the old host or scheme.

#### Verification

1. [ ] Load the support portal on the local host when enabled.
2. [ ] Load the support portal on the public `/support` path when enabled.
3. [ ] Verify redirects and generated URLs stay on HTTPS.
4. [ ] Verify authentication and session behavior through the edge.

### Grafana

#### Current state

- Grafana is directly exposed.
- OIDC browser auth and root URL settings explicitly reference the current public URL.

#### Tasks

1. [ ] Decide whether Grafana should be public at all.
2. [ ] Keep local Grafana access on `https://observability.jac.dot` when enabled locally.
3. [ ] If public, route it through `https://www.jacloud.nl/observability`.
4. [ ] Update `GRAFANA_PUBLIC_URL` to the final public HTTPS URL.
4. [ ] Keep browser auth URL on the public Keycloak host and token/userinfo URLs on the internal issuer where intended.
5. [ ] Remove the direct host port after login and deep-link validation.

#### Break risks

1. [ ] Grafana-generated links will be wrong if `GF_SERVER_ROOT_URL` remains `http://...:3000`.
2. [ ] OIDC callback/login can break if Keycloak public and internal URLs are mixed incorrectly.

#### Verification

1. [ ] Load Grafana on the local host when enabled.
2. [ ] Load Grafana on the public `/observability` path when enabled.
3. [ ] Complete the OIDC login flow.
4. [ ] Verify dashboard links and redirects remain on the correct public HTTPS URL and path prefix.

## Shared Cutover Tasks

1. [ ] Add local host-based routing to the edge ingress configuration.
2. [ ] Add public single-host path-based routing to the edge ingress configuration.
3. [ ] Keep Kong Admin API and Kong Manager non-public unless explicit restricted `/ops/kong` access is required.
4. [ ] Remove external HTTP ingress for app traffic.
5. [ ] Keep `.env.example` local-focused and add deployment-specific env guidance for the public `jacloud.nl` model.
6. [ ] Update deployment and gateway documentation.
7. [ ] Add explicit validation steps for every public app moved behind the single-host route model.

## Cutover Strategy

### Phase 1

1. [ ] Add local host-based routing support to the edge ingress.
2. [ ] Add public single-host path-based routing support to the edge ingress.
3. [ ] Move dq-made-easy UI and dq-api.
4. [ ] Validate login, refresh, logout, and Kong-only API enforcement.

### Phase 2

1. [ ] Make Keycloak work behind public `/iam`.
2. [ ] Move OpenMetadata behind public `/metadata`.
3. [ ] Validate OIDC callback and public links.

### Phase 3

1. [ ] Move Zammad if support needs public browser access.
2. [ ] Move Grafana only if public access is required.

### Phase 4

1. [ ] Remove remaining direct public app ports.
2. [ ] Restrict Kong admin surfaces.
3. [ ] Document the new steady-state dual-topology ingress model.

## Definition of Done

- Local full-stack execution works on the required `*.jac.dot` hostnames.
- Each intended public app has a stable edge-routed HTTPS path on `www.jacloud.nl`.
- No intended public app relies on a direct host port.
- Each app's local URL, public URL, callback URL, issuer URL, and root URL settings are aligned.
- Kong Admin and infrastructure services remain non-public unless explicitly restricted for operator access.
- Verification is complete for login, redirects, cookies, and generated links.