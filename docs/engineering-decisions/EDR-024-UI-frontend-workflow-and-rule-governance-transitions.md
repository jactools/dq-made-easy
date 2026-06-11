# EDR-024 [UI]: Frontend Workflow and Rule-Governance Transition Patterns

**Status**: Accepted
**Date**: 2026-04-20
**Tag**: UI

## Context
The UI renders and drives approval, activation, deactivation, and test-history flows on top of backend governance state. These screens need stable rules for what actions are available, how deactivation is modeled, and how rule lifecycle state is presented without inventing a separate client-side workflow model.

## Decision
- Drive frontend governance actions from backend-allowed transitions rather than pure role heuristics.
- Model rule deactivation as a typed approval workflow rather than an immediate local status flip.
- Preserve workspace-aware approval behavior and lifecycle visibility in the UI so governance requests stay discoverable after reload.
- Keep lifecycle/history visualization aligned with the backend contract, even when the UI intentionally compresses presentation stages.

## Rationale
- Backend-governed transitions are the authoritative workflow model.
- Deactivation is an approval process, not a local toggle.
- Workspace scoping and reload behavior must not hide active governance work.

## Scope Boundaries
This decision covers UI governance and approval workflow behavior.

It does not by itself define:
- server-side authorization
- audit persistence format
- every lifecycle visualization detail in all screens

## Consequences
**Positive**
- UI workflow behavior stays aligned with backend governance rules.
- Deactivation and approval flows remain visible and workspace-correct.

**Negative**
- UI state logic is more dependent on backend transition metadata.

## Implementation Guidance
- Derive available actions from allowed transitions.
- Use explicit deactivation request APIs instead of local-only state changes.
- Preserve workspace identifiers and pending-deactivation visibility in UI state.

## Related Artifacts
- `/memories/repo/dq-rulebuilder-ui-governance-transitions-note.md`
- `/memories/repo/dq-rulebuilder-ui-rule-deactivation-workflow-note.md`
- `/memories/repo/dq-rulebuilder-ui-rule-test-history-lifecycle-note.md`
