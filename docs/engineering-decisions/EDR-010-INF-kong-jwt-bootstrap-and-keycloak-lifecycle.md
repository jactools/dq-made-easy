# EDR-010 [INF]: Kong JWT Bootstrap and Keycloak Lifecycle

**Status**: Accepted
**Date**: 2026-04-20
**Tag**: INF

## Context
The local and prototype authentication stack depends on Keycloak issuing tokens and Kong validating them through configured issuer and public-key material. In practice, several recurring failure modes showed that this integration is lifecycle-sensitive rather than static:

- recreating or reseeding Keycloak rotates signing keys, which leaves Kong with stale JWT credentials unless it is refreshed deliberately
- Keycloak realm import behavior can preserve old realm state, so changes to redirect URIs or role definitions may not apply to an existing data volume
- issuer URLs used by browsers or local hosts are not the same as the internal service host Kong must use to fetch JWKS material
- service-account token lifetime and browser token lifetime need different defaults

These are not one-off incidents; they define how auth bootstrap and reseed workflows must behave in this repository.

## Decision
Adopt the following Kong and Keycloak lifecycle rules:

- Kong JWT bootstrap must be rerunnable and must refresh issuer credentials after Keycloak reseed or key rotation rather than assuming existing credentials remain valid.
- When Kong fetches JWKS from an issuer configured with a browser-facing host such as `localhost` or `keycloak.local`, the fetch host may be rewritten to the internal `keycloak` service host, but accepted issuer aliases must still preserve the externally visible issuer identities.
- Kong bootstrap must register the supported issuer aliases explicitly instead of assuming one host name covers all local access paths.
- When stale JWT credentials exist in Kong, bootstrap must replace them rather than PATCHing or skipping existing credentials.
- Keycloak realm import changes that affect redirect URIs, role definitions, or other imported realm state must be applied through image rebuild plus fresh realm import state when the existing data volume would otherwise retain older configuration.
- Composite roles required by imported realm configuration must exist in the generated realm definition so import-time role resolution succeeds.
- Browser/user token lifetime and service-account token lifetime are separate concerns and must be configured separately.

## Rationale
- JWT validation failures after Keycloak reseed are usually a lifecycle/configuration issue, not an application logic defect.
- Internal network topology and external browser-facing issuer URLs are different concerns; bootstrap needs to respect both.
- Recreate-not-patch behavior for issuer credentials is more reliable when key material changes.
- Keycloak import strategy can hide configuration changes if persistent realm state is reused blindly.
- Composite roles and token lifetime settings are part of the repository's auth bootstrap contract and need to be explicit.

## Scope Boundaries
This decision applies to local and prototype Kong/Keycloak bootstrap behavior, reseed workflows, and imported realm lifecycle.

It does not by itself define:
- production identity-provider architecture
- application-level authorization semantics after a token is accepted
- UI login flow state management
- every Keycloak realm attribute outside bootstrap-critical auth behavior

## Consequences
**Positive**
- Kong and Keycloak can be reseeded or rebuilt without leaving silent JWT validation drift behind.
- Redirect URI and realm-role changes have a defined application path instead of relying on incidental container reuse.
- Local auth setup is more reproducible across fresh and reused environments.
- Token lifetime behavior is clearer for browser users versus service-account clients.

**Negative**
- Auth reseed workflows remain operationally explicit and sometimes require rebuild plus volume reset.
- Bootstrap scripts need to handle more alias and credential-replacement logic than a naive one-shot setup.
- Operators need to understand the difference between external issuer identity and internal JWKS fetch host.

## Implementation Guidance
- Re-run Kong bootstrap after Keycloak reseed or signing-key rotation.
- Rewrite only the JWKS fetch host when moving from browser-facing issuer hosts to the internal service host; do not mutate the logical issuer aliases incorrectly.
- Replace stale Kong JWT issuer credentials instead of skipping existing entries.
- Rebuild and re-import Keycloak when imported realm changes must override persisted realm state.
- Ensure generated realm definitions include required base roles for composite role expansion.
- Configure browser token lifespan at the realm level and service-account token lifespan at the client level.

## Related Artifacts
- `/memories/repo/dq-rulebuilder-kong-jwt-bootstrap-note.md`
- `/memories/repo/dq-rulebuilder-keycloak-composite-role-import-and-rebuild-note.md`
- `/memories/repo/dq-rulebuilder-keycloak-redirect-uri-import-order-note.md`
- `/memories/repo/dq-rulebuilder-keycloak-token-lifespan-note.md`
- `dq-kong/scripts/bootstrap_kong.sh`
- `dq-keycloak/jaccloud-realm.json`
- `dq-api/scripts/generate_keycloak_realm.py`