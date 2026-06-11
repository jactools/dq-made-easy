# EDR-020 [UI]: Frontend Async Request Tracking and Profiling History Patterns

**Status**: Accepted
**Date**: 2026-04-20
**Tag**: UI

## Context
Queued test-data generation and profiling flows outlive a single page view. The UI needs a stable way to track in-flight requests, reconnect after navigation, and surface profiling history without inventing its own lifecycle semantics.

## Decision
- Track async request lifecycle in the frontend through a shared request-tracking provider instead of per-component polling logic.
- Keep profiling request history backed by backend request records and current-user scoping rather than local-only UI state.
- Convert backend snake_case request/history payloads into frontend camelCase explicitly in the UI layer.
- Require auth-sensitive async views to resubscribe after token/bootstrap changes instead of freezing on the first unauthenticated mount result.

## Rationale
- Shared request tracking prevents each screen from reimplementing async lifecycle management.
- Backend-owned profiling history is more durable and auditable than local client state.
- Explicit case conversion keeps the API contract canonical while preserving UI conventions.
- Auth/bootstrap timing issues are common in async screens and need a standard resync model.

## Scope Boundaries
This decision covers frontend async request visibility and profiling-history presentation.

It does not by itself define:
- backend queue semantics
- retry/cancel behavior
- auth bootstrap ordering, which is covered by EDR-013

## Consequences
**Positive**
- Async request state survives navigation more reliably.
- Profiling history stays tied to backend truth.
- UI payload handling remains aligned with the snake_case API contract.

**Negative**
- UI request-tracking infrastructure is more centralized and less ad hoc.
- Components must cooperate with the provider lifecycle instead of polling independently.

## Implementation Guidance
- Use the shared async request tracker/provider.
- Back profiling-history views with backend request endpoints.
- Normalize response shapes explicitly in the UI.
- Re-trigger auth-sensitive data loads after token/storage sync events.

## Related Artifacts
- `/memories/repo/dq-rulebuilder-ui-async-request-tracker-note.md`
- `/memories/repo/dq-rulebuilder-ui-profiling-request-history-note.md`
