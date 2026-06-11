# EDR-013 [UI]: Frontend Auth State and Token Ordering

**Status**: Accepted
**Date**: 2026-04-20
**Tag**: UI

## Context
The UI auth flow depends on several moving pieces becoming coherent at the same time: persisted auth state, token storage, cross-component token-change events, workspace memberships, and permission gating derived from backend-issued scopes. A recurring class of frontend bugs came from these pieces being initialized in the wrong order or from the UI inventing client-side assumptions that did not match the backend auth contract.

Observed failures included:

- fresh authenticated sessions being cleared because token-change events fired before authenticated auth state had been persisted
- components mounting early, issuing unauthenticated requests, and keeping stale failure state instead of reloading after token bootstrap
- login UX collapsing multi-workspace memberships into a synthetic default workspace instead of honoring backend memberships
- sidebar and entity visibility being derived from fragile frontend assumptions rather than normalized backend scopes and profile data

These are stable UI auth rules rather than isolated screen bugs.

## Decision
Adopt the following frontend auth and bootstrap rules:

- Persist authenticated auth state before broadcasting token-change events.
- Use the safe bootstrap order for authenticated sessions: set auth state, persist auth state, write auth and refresh tokens, then dispatch the auth-token-changed event.
- Components whose data depends on authenticated bootstrap must react to auth-token and storage synchronization events so they can recover from early unauthenticated mounts.
- UI code must use normalized API base handling consistently across authenticated versioning and rule-version flows rather than mixing hardcoded and normalized endpoints.
- Public version metadata needed before sign-in must remain fetchable without requiring an auth token; add Authorization only when a token exists.
- Preserve backend-provided `workspace_roles` and drive workspace selection from real backend memberships rather than a synthetic default workspace.
- Frontend permission and visibility checks should prefer backend scopes and permissions first, with legacy role-based fallback only where older/mock flows still need it.
- Normalize backend role/scope inputs regardless of whether they arrive as arrays or delimited strings.

## Rationale
- Token events are meaningful only after the UI has a persisted authenticated state to accompany them.
- Early component mounts are common in the frontend; auth-aware reload hooks are safer than assuming token bootstrap already finished.
- Multi-workspace behavior belongs to the backend auth contract, not frontend guesswork.
- Scope-driven gating keeps the UI aligned with the backend authorization model and reduces drift between API access and visible UI affordances.
- Public pre-login metadata should not be artificially blocked by client auth assumptions.

## Scope Boundaries
This decision applies to frontend auth bootstrap, token event ordering, workspace-selection state, and scope-based UI gating.

It does not by itself define:
- backend token issuance or session persistence implementation
- full UI routing architecture
- every ownership-filtering rule for personalized views
- Keycloak or Kong bootstrap behavior outside the frontend auth client

## Consequences
**Positive**
- Fresh logins and SSO callbacks initialize more reliably without clearing the session accidentally.
- Auth-sensitive components can recover from early bootstrap timing instead of sticking in stale unauthenticated state.
- Multi-workspace users see real backend memberships instead of collapsed client-side defaults.
- UI visibility stays closer to backend authorization semantics.

**Negative**
- Frontend auth/bootstrap code must remain deliberate about event ordering and cross-component synchronization.
- Components that previously assumed a ready token at mount time need explicit resync handling.
- Legacy role-based fallbacks need to coexist carefully with scope-first logic until older flows are fully retired.

## Implementation Guidance
- Dispatch `dq-auth-token-changed` only after authenticated auth state and tokens are both persisted.
- Skip auth-dependent bootstrap requests while an SSO callback token is still in the URL and retry after token persistence completes.
- Subscribe auth-sensitive versioning and similar components to token/storage synchronization so they can refetch after bootstrap.
- Use the normalized API base helper consistently in authenticated versioning flows.
- Preserve backend `workspace_roles` verbatim in frontend auth state and derive workspace selectors from those memberships.
- Normalize scope/role inputs from arrays or delimited strings before applying permission checks.

## Related Artifacts
- `/memories/repo/dq-rulebuilder-ui-auth-token-authstate-order-note.md`
- `/memories/repo/dq-rulebuilder-ui-versioning-auth-bootstrap-note.md`
- `/memories/repo/dq-rulebuilder-ui-multi-workspace-login-note.md`
- `/memories/repo/dq-rulebuilder-ui-backend-scope-gating-note.md`
- `/memories/repo/dq-rulebuilder-ui-owner-token-normalization-note.md`
- `dq-ui/src/`