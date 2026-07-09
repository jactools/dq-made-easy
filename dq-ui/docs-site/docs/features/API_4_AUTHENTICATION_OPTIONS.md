# API-4 Advanced Authentication Options

Goal: Expand authentication capabilities to support enterprise integration scenarios while preserving current gateway/auth compatibility.

Related work: [API-7 Real DQ Rule Execution](/docs/features/current/API_7_REAL_DQ_RULE_EXECUTION/)

Related architecture note: [API-4 Entra ID + Keycloak Brokering Architecture](/docs/features/API_4_ENTRA_KEYCLOAK_BROKERING/)

Current overlap assessment as of 2026-05-25:

- The product already has a substantial auth foundation: centralized FastAPI auth middleware, per-route scope mapping, bearer-token extraction, trusted-proxy auth handling, local login/logout/refresh endpoints, and OIDC redirect/callback endpoints.
- Runtime auth configuration already exists through app-config and the Application Settings UI, including `ssoEnabled`, `ssoProvider`, `ssoIssuer`, `ssoClientId`, and the local-auth toggle that drives the SSO Login and Admin Login UX.
- JWT/OIDC hardening is already partly implemented through issuer normalization, public-to-internal issuer rewriting for backend discovery, allowed client-id checks, and structured auth error responses.
- Auth observability already exists in narrow form through successful-login metrics, request telemetry, and system summaries, but not yet as a full auth-event audit trail.
- The Keycloak browser migration is only partial: `keycloak-js` is installed and helper modules exist, but the frontend still parses `auth_token`, `auth_id_token`, and `refresh_token` from the browser callback URL, and the backend still supports that callback-token handoff.

What still remains is the enterprise platform layer: one explicit auth-mode matrix and policy model, validator seams for non-user tokens, first-class service-account/token-management surfaces, deeper diagnostics and audit controls, and one canonical Keycloak JS browser path with end-to-end integration coverage.

## Phase 1: Requirements and Auth Matrix

- Define supported auth modes (OIDC/OAuth2, service tokens, PAT, mTLS where applicable).
- Define per-endpoint auth requirements and scope mapping.
- Define token lifetime, rotation, and revocation behavior.
- Define backward-compatibility constraints for existing clients.

## Phase 2: Implementation Foundations

- Implement pluggable auth validators in FastAPI middleware/dependencies.
- Add JWT/OIDC validation hardening (issuer/audience/clock-skew checks).
- Add service-account and machine-to-machine token path.
- Add standard claims-to-role mapping and workspace scoping.

## Phase 3: API and UX Management Surface

- Add API token management endpoints (create/revoke/list with masked display).
- Add key rotation and JWK refresh controls.
- Add auth diagnostics endpoint for token introspection troubleshooting.
- Add admin UX for auth provider settings and policy controls.

### Keycloak JS Migration Status

- `keycloak-js` is already a bundled `dq-ui` dependency and lightweight auth helper modules exist under `dq-ui/src/auth`.
- The backend already exposes the current auth route family needed for browser auth orchestration: `/auth/v1/login`, `/auth/v1/logout`, `/auth/v1/refresh`, `/auth/v1/redirect`, and `/auth/v1/callback`.
- The login modal already reads runtime SSO settings and can present SSO Login versus Admin Login based on app-config.
- The migration is not complete: the app shell still boots from callback URL tokens, and the backend callback still participates in sending browser-visible tokens.
- Browser integration coverage for login, refresh, logout, and expired-session recovery on the Keycloak path is still missing.

Remaining Keycloak JS cutover:

- Wire the Keycloak JS client through the canonical app bootstrap path so `AuthContext` delegates login, initialization, refresh, and logout to one provider contract.
- Remove the custom `auth_token` callback parsing and backend token-handoff behavior once the canonical provider path is in place.
- Keep Kong as the JWT validation and route-enforcement layer while the browser handles PKCE login flow responsibilities.
- Update repo-controlled callers to the canonical browser path instead of maintaining long-lived dual browser flows.
- Add Playwright/browser integration coverage for login, token refresh, logout, and expired-session recovery.
- Preserve the current public-browser-issuer and internal-backend-issuer split for local and test environments.

## Phase 4: Security and Compliance

- Add audit trail for auth configuration and token lifecycle events.
- Add anomaly signals for suspicious auth patterns.
- Add secure defaults for strong algorithms and minimum key sizes.
- Add integration tests for each supported auth flow.

## Acceptance Criteria

- Multiple auth modes are supported with clear policy boundaries.
- Externally owned client integrations continue to function where required, and repo-controlled callers use the canonical auth contracts.
- Token lifecycle operations are observable and auditable.
- Auth failures return actionable diagnostics without leaking secrets.
- Security defaults align with enterprise requirements.

## Tracked Work Items (Current Status)

- [~] `API-4.1` Auth mode matrix and policy model
	- Existing overlap: centralized scope mapping, runtime SSO/provider settings, trusted-proxy auth support, local admin auth, and the Entra-to-Keycloak brokering model already define parts of the auth surface.
	- Remaining: publish one canonical matrix for browser OIDC, local admin auth, trusted-proxy auth, and external automation or service-account access, including token lifetime, rotation, revocation, and per-endpoint policy boundaries.
- [~] `API-4.2` Pluggable FastAPI auth validators
	- Existing overlap: `AuthMiddleware` already centralizes bearer extraction, proxy-auth handling, session validation, and scope enforcement, and the route protection model is already explicit.
	- Remaining: split the current user-centric path into explicit validator seams by auth mode and token type so non-browser and non-human callers do not depend on the same path as interactive users.
- [~] `API-4.3` OIDC/JWT hardening and config controls
	- Existing overlap: issuer normalization, allowed client-id checks, public/internal issuer rewriting, and runtime SSO issuer or client configuration already exist.
	- Remaining: add operator-facing controls and diagnostics for JWK refresh, key rotation, explicit skew or algorithm policy, and broader token-validation troubleshooting.
- [~] `API-4.4` Service account token flow
	- Existing overlap: repo-controlled CLI automation already acquires non-browser Keycloak tokens through a narrow password-grant path.
	- Remaining: add a first-class non-human service-account or client-credentials flow with scoped roles, rotation, revocation, and no dependency on a human password.
- [ ] `API-4.5` Token management endpoints
	- Remaining: no create, revoke, list, or masked-display API token management endpoints exist yet for PATs or service tokens.
- [~] `API-4.6` Auth diagnostics and troubleshooting support
	- Existing overlap: auth responses already return structured errors, successful-login metrics are exposed through system summaries, and auth provider settings are already visible through app-config-backed UI surfaces.
	- Remaining: add dedicated diagnostics for token introspection, issuer or JWK status, claim-mapping explanation, provider health, and operator troubleshooting workflows.
- [~] `API-4.7` Migrate SPA authentication to Keycloak JS with PKCE
	- Existing overlap: `keycloak-js` is installed, `dq-ui` already has auth helper modules, the login modal already presents SSO login, and the backend already exposes redirect, callback, refresh, and logout endpoints.
	- Remaining: make Keycloak JS the canonical browser path, remove callback URL token parsing and backend token handoff, and add browser integration coverage for login, refresh, logout, and expired-session recovery.
- [~] `WF-4.1` Auth event audit pipeline integration
	- Existing overlap: login success metrics and request-level telemetry already exist.
	- Remaining: persist auditable auth configuration changes, token lifecycle events, refresh or logout failures, and suspicious auth-pattern signals in a reviewable pipeline.
- [~] `DOC-4.1` Enterprise auth configuration guide
	- Existing overlap: the Entra brokering architecture note, dedicated environment auth contract, and scattered SSO and app-config docs already exist.
	- Remaining: consolidate operator guidance for issuer ownership, client registration, mode selection, service-account setup, token policy, and troubleshooting.

## Already Covered Elsewhere

- Centralized FastAPI auth enforcement, route-to-scope mapping, and trusted-proxy auth handling.
- Runtime auth provider settings and the existing SSO Login versus Admin Login UX wiring.
- The Entra ID to Keycloak brokering architecture and the public-browser-issuer versus internal-backend-issuer contract.
- Successful-login metrics, request telemetry, and structured auth failure responses.

## Remaining Platform Gap

The missing scope is not "authentication exists" in general. The missing scope is an enterprise auth platform that clearly models every supported auth mode, manages non-human credentials and token lifecycle explicitly, exposes operator diagnostics and audit surfaces, and completes the browser cutover to one canonical Keycloak JS PKCE path without the current custom callback-token handoff.

## Delivery Milestones

- Milestone A (Model/Compatibility): `API-4.1` to `API-4.2`
- Milestone B (Flows): `API-4.3` to `API-4.4`
- Milestone C (Management/Hardening): `API-4.5` to `API-4.7`, `WF-4.1`, `DOC-4.1`
