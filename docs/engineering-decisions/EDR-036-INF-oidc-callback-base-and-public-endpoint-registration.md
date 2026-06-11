# EDR-036 [INF]: OIDC Callback Base and Public-Endpoint Registration Rules

**Status**: Accepted
**Date**: 2026-04-20
**Tag**: INF

## Context
OIDC login relies on redirect URIs that must match the public gateway and Keycloak registration exactly. This broke when redirect bases were derived from internal hostnames or when test runs leaked repository-root environment into auth endpoint settings.

## Decision
- Redirect URI construction must follow an explicit priority order from dedicated public override to public API base to server base, with only an environment-specific last-resort fallback.
- Public-facing callback URLs must use the externally reachable API or gateway hostname, never container-internal aliases.
- Redirect URI matching is exact; path, host, case, and trailing slash must remain aligned with Keycloak client configuration.
- Auth endpoint tests must run from the service-local directory so repository-root environment does not leak into callback-base resolution.

## Rationale
- OIDC login fails completely when redirect URI construction and Keycloak registration diverge.
- Public and internal hostnames serve different audiences and cannot be substituted safely.
- Test isolation matters because auth settings are environment-derived.

## Scope Boundaries
This decision covers OIDC callback base resolution and public endpoint registration.

It does not by itself define:
- frontend auth-state behavior
- token validation semantics
- Keycloak client provisioning workflow

## Consequences
**Positive**
- Redirect URI failures become easier to diagnose and less environment-dependent.
- Auth endpoint tests run against the intended service-local settings.

**Negative**
- Auth configuration becomes stricter about public base consistency.
- Misregistered callback URLs fail immediately instead of degrading unpredictably.

## Implementation Guidance
- Keep callback-base precedence explicit in settings.
- Use only public hostnames in redirect URIs.
- Validate exact callback registration in tests.
- Run auth endpoint tests from the service directory.

## Related Artifacts
- `/memories/repo/dq-rulebuilder-fastapi-oidc-public-callback-base-note.md`
