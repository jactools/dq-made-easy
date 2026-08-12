# Shared Platform SSO and JWKS Inventory

**Status**: Complete  
**Date**: 2026-08-03  
**Work item**: SHARED-I-W1-02

## Purpose

Inventory the DQ SSO/OIDC/JWKS surfaces and distinguish reusable protocol/security primitives from product authorization and deployment policy.

## Inventory

| Capability | Primary paths | Classification | Boundary decision |
|---|---|---|---|
| Service-to-service token acquisition | `platform_foundation` auth package; DQ engine/API consumers | Shared; extracted | Canonical shared ownership is `platform-foundation`. App-specific env names remain consumer wiring until SHARED-I-W3-05. |
| OIDC discovery and endpoint selection | `dq-api/fastapi/app/api/v1/endpoints/auth.py` | Shared candidate | Extract issuer normalization, discovery retrieval, required endpoint validation, and internal/public endpoint mapping only after defining a typed provider config. Keep HTTP route behavior in DQ. |
| Browser authorization-code flow | `auth.py`; `dq-ui/src/auth/browserAuthClient.ts`; `AuthContext.tsx` | Split | Generic redirect URL and callback token parsing may be shared. DQ session persistence, frontend redirect contract, user bootstrap, and UI state stay DQ-owned. |
| JWT payload parsing and temporal/issuer/audience checks | `dq-api/fastapi/app/core/auth.py` | Split with security gap | Generic claim validation is a shared candidate, but current API code decodes payloads without signature verification and relies on the gateway trust boundary. Do not promote this implementation as a shared verifier. |
| JWKS signature verification | `docker/airflow/webserver_config.py` | Shared candidate | Extract configurable JWKS retrieval, signing-key selection, algorithm allowlist, issuer, and audience verification. Keep the Airflow FAB adapter in DQ. |
| Realm-role and scope claim extraction | `app/core/auth.py`; `docker/airflow/webserver_config.py` | Split | Generic extraction from `scope`, `scp`, `roles`, `realm_access`, and `resource_access` can be shared. DQ scope expansion and Airflow role mapping stay consumer-owned. |
| Route authorization policy | `app/core/auth.py`; auth middleware/decorators; endpoint guards | DQ-owned | DQ public routes, required scopes, workspace roles, exception permissions, and route policy must not move. |
| Auth endpoints and session lifecycle | `app/api/v1/endpoints/auth.py`; presenters; session/admin repositories | DQ-owned | Login callback, refresh/logout, local development token behavior, database sessions, and user resolution remain DQ-owned. |
| UI permission model | `AuthContext.tsx`; `useKeycloak.ts`; `ProtectedRoute.tsx`; DQ role/types/components | DQ-owned with small generic seams | Keep DQ roles, scopes, menus, and protected routes in DQ. Only protocol-level browser helpers are candidates. |
| Direct Keycloak JS client | `dq-ui/src/auth/keycloakClient.ts` | Consumer adapter | Keep client configuration in DQ; use a future shared browser adapter only if MaaS adopts the same flow. |
| Keycloak realm/client generation | `dq-api/scripts/generate_keycloak_realm.py`; `dq-keycloak/scripts/generate_seed_artifacts.sh` | Split | Realm generation mechanics, password validation, and artifact handling may be shared. DQ clients, redirects, roles, scopes, users, and workspace claims remain DQ-owned. |
| Keycloak runtime and readiness | `dq-keycloak/Dockerfile.keycloak`; entrypoint/trust scripts; `scripts/supporting/keycloak_readiness.sh` | Shared image/runtime candidate | Move reusable Keycloak TLS/trust/readiness image mechanics only after image contract definition. Keep realm artifacts in each consumer. |
| Kong JWKS/bootstrap | `scripts/configure_kong.sh`; `scripts/init_kong_config.sh`; `dq-kong/scripts/bootstrap_kong.sh` | Split | Generic JWKS-to-gateway credential bootstrap may be shared; DQ routes, services, consumers, ACLs, and gateway topology remain DQ-owned. |
| JWKS diagnostics/recovery | `scripts/reset_keycloak.sh`; Keycloak connectivity/debug scripts | Split | Generic JWKS readiness checks may be shared. Destructive reset/import behavior and DQ realm assumptions remain DQ-owned. |
| Airflow OAuth/FAB integration | `docker/airflow/webserver_config.py` | Split | Shared verifier and claim extraction; DQ-to-FAB role mapping and Airflow security-manager class remain DQ-owned. |
| OpenMetadata OIDC integration | `docker-compose/metadata.yml`; configure/seeding scripts | Consumer integration | OpenMetadata-specific environment mapping, callback, users, and admin client remain DQ deployment wiring. |
| Grafana and Zammad OIDC integration | Keycloak realm generator; Grafana/Zammad setup and validation scripts | Consumer integration | Product/client configuration and role mapping remain DQ-owned. Reuse only shared discovery/JWKS primitives. |
| Auth environment contracts | root env files; compose auth/gateway/metadata/airflow; API settings | Not yet standardized | Define one shared protocol-level contract in SHARED-I-W3-05; retain app-specific aliases only in adapters. |

## Shared Primitive Set

Already shared:

- static token provider
- OIDC client-credentials provider
- OIDC password provider where explicitly permitted
- token caching/retry behavior
- issuer-to-token-endpoint resolution
- env-driven token provider factories

Next shared candidates:

- typed OIDC provider configuration
- discovery document client
- JWKS cache and signing-key resolver
- JWT signature/issuer/audience/time validator
- generic scope and realm/resource-role extraction

## Consumer-Owned Policy

The following must remain outside the shared auth package:

- DQ or MaaS permission names and role mappings
- route/public-path policy
- workspace and tenant authorization
- session persistence and user provisioning
- Keycloak realm/client definitions
- Kong route/service topology
- Airflow, Grafana, OpenMetadata, and Zammad role mappings

## Security Finding

`dq-api/fastapi/app/core/auth.py` performs payload, expiry, issuer, and audience checks but does not verify the JWT signature itself. DQ relies on its trusted gateway model for signature enforcement. The shared package must be fail-closed and perform cryptographic JWKS verification; it must not copy the current unverified decoder as a reusable validator.

## Next Auth Work

SHARED-I-W3-02 should extract the Airflow-proven JWKS verification mechanics into a provider-neutral validator, add issuer/audience/algorithm tests, and then let DQ and MaaS wrap it with their own authorization policies.
