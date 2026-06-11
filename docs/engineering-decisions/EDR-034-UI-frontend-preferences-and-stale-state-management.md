# EDR-034 [UI]: Frontend Preferences and Stale-State Management Rules

**Status**: Accepted
**Date**: 2026-04-20
**Tag**: UI

## Context
Frontend settings and event-driven session flags can survive navigation and logout if case conversion and cleanup are inconsistent. Those stale-state failures lead to toggles resetting unexpectedly or screens reopening themselves after reauthentication.

## Decision
- Frontend user preferences must be normalized between backend snake_case and UI camelCase consistently on both load and save.
- Session-storage flags used for event-driven navigation must be cleared when consumed and again during persisted auth-session cleanup on logout.
- Shared events with multiple listeners must have a clear state owner so duplicate writes or missed cleanup do not leave stale flags behind.
- Preference and stale-session fixes must carry regression coverage across logout/login boundaries.

## Rationale
- Preference drift is usually caused by asymmetric case conversion or stale cached state.
- Logout is the only reliable boundary for clearing navigation state that may outlive a page view.
- Event listeners without one cleanup owner make stale state difficult to reason about.

## Scope Boundaries
This decision covers frontend preference serialization and stale-session cleanup behavior.

It does not by itself define:
- backend preference API behavior
- multi-tab synchronization strategy
- feature-flag or experimentation storage

## Consequences
**Positive**
- Preference state survives reloads and reauthentication more predictably.
- Event-driven navigation becomes less prone to stale replay bugs.

**Negative**
- UI code must maintain explicit normalization and cleanup paths.
- Session cleanup changes require end-to-end regression testing.

## Implementation Guidance
- Normalize preference payloads in both directions.
- Clear session flags on consume and on logout cleanup.
- Centralize ownership for shared navigation-state events.

## Related Artifacts
- `/memories/repo/dq-rulebuilder-ui-preview-preferences-snake-case-note.md`
- `/memories/repo/dq-rulebuilder-ui-stale-new-rule-session-flag-note.md`
