# EDR-023 [API]: Auth Scope Enforcement and Role-Based Access Rules

**Status**: Accepted
**Date**: 2026-04-20
**Tag**: API

## Context
Authorization drift is dangerous in this repository because API access, local login tokens, seeded roles, and UI capability checks can all diverge if roles or scopes are inferred implicitly. Repository policy already rejects silent fallbacks, and auth enforcement needs to reflect that.

## Decision
- Enforce API access from explicit scopes and permissions rather than implicit role-name defaults.
- Treat role-permission metadata in seed/runtime auth artifacts as the canonical authorization source.
- Keep governance and rule-lifecycle transitions guarded by server-side scope checks and explicit state-transition validation.
- Allow legacy role-based fallback only where older flows still require it, but keep scope-first enforcement as the canonical path.

## Rationale
- No-fallback auth behavior keeps authorization auditable and predictable.
- Scope-first enforcement aligns seeded roles, tokens, and API checks.
- State-transition rules belong on the server, not only in UI gating.

## Scope Boundaries
This decision covers API-side scope enforcement and role-permission modeling.

It does not by itself define:
- identity-provider bootstrap
- frontend auth event ordering
- row-level ownership filtering

## Consequences
**Positive**
- Authorization rules remain explicit and testable.
- Server-side lifecycle enforcement does not depend on UI behavior.

**Negative**
- Missing scope/permission seed data fails harder and earlier.

## Implementation Guidance
- Build auth principal permissions from explicit token or seeded role metadata.
- Reject invalid lifecycle writes with structured server-side errors.
- Keep scope naming and seeded role permissions synchronized.

## Related Artifacts
- `/memories/repo/dq-rulebuilder-role-permissions-no-fallback-note.md`
- `/memories/repo/dq-rulebuilder-fastapi-status-governance-server-enforcement-note.md`
- `/memories/repo/dq-rulebuilder-ui-backend-scope-gating-note.md`
