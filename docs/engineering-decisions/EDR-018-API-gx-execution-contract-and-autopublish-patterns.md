# EDR-018 [API]: GX Execution Contract and Autopublish Patterns

**Status**: Accepted
**Date**: 2026-04-20
**Tag**: API

## Context
GX-backed rule activation and live validation depend on a consistent contract between rule definitions, execution plans, suite snapshots, run-plan snapshots, and worker execution behavior. Several problems surfaced when parts of that contract were incomplete, legacy-shaped, or inferred indirectly:

- autopublish and approval repair paths could drift if expectations were rebuilt through intermediate translations instead of the structured rule model
- run-plan validation could appear valid until execution time if required execution-contract snapshots were missing
- activation could leak raw validation errors when suite snapshots were malformed
- cross-object and join-pair checks need explicit source-shape handling and pre-materialized inputs rather than implicit worker-side joins
- view contracts needed to expose stable check-type metadata so UI and orchestration flows could reason about execution consistently

These are stable GX execution-contract rules, not point fixes.

## Decision
Adopt the following GX execution-contract and autopublish rules:

- GX autopublish and approval-repair paths should build expectations from structured `check_type` and `check_type_params` first, falling back to intermediate-model translation only when necessary.
- The repository execution contract must distinguish explicit source shapes such as `single_object`, `single_object_grouped`, and `join_pair`.
- Join-pair execution is a pre-materialization contract: workers execute against landed/materialized inputs and must not perform ad hoc source joins themselves.
- Run-plan validation for single-suite GX execution requires a valid `executionContractSnapshot`; missing snapshots must fail fast with a clear contract error.
- Activation requires a valid full `suiteSnapshot`; malformed or legacy/incomplete snapshots must fail with structured validation errors rather than leaking raw framework exceptions.
- Rule view and list contracts must expose stable check-type metadata so downstream UI, validator, and orchestration flows can reason from the canonical rule contract.
- Unsupported or not-yet-materialized cross-object cases should fail fast instead of pretending activation/execution can succeed without the required preconditions.

## Rationale
- Structured rule metadata is the most direct and maintainable source for expectation building.
- Explicit execution-contract shapes reduce ambiguity across compiler, API, validator, and worker layers.
- Join-pair execution correctness depends on landed inputs and traceability metadata, not on hidden worker-side source resolution.
- Fail-fast snapshot validation is safer than allowing partial legacy shapes to fail deep in execution.
- Stable check-type exposure keeps API consumers aligned with the same contract the execution layer uses.

## Scope Boundaries
This decision applies to GX expectation/autopublish construction, execution-contract shape semantics, snapshot validation for activation/run plans, and canonical check-type exposure in rule-facing API contracts.

It does not by itself define:
- every supported GX check type forever
- worker queueing and runtime fail-closed behavior
- data-delivery materialization contract details outside the execution-contract preconditions they satisfy
- frontend UX for presenting rule activation failures

## Consequences
**Positive**
- GX execution flows share a more explicit and stable contract across API, validator, and worker layers.
- Snapshot and run-plan defects surface earlier with clearer failure semantics.
- Autopublish and repair behavior stay closer to canonical rule definitions.
- Cross-object limitations remain visible instead of being hidden by partial or misleading activation behavior.

**Negative**
- Legacy or incomplete snapshots are rejected more aggressively.
- Supporting new GX check types requires deliberate extension of the structured check-type path.
- Join-pair and cross-object flows still need explicit pre-materialization support before they can be treated as generally supported.

## Implementation Guidance
- Build GX expectations from `check_type` and `check_type_params` whenever the structured rule model contains enough information.
- Keep execution-contract source shapes explicit and validated before dispatch.
- Require `executionContractSnapshot` for single-suite run-plan validation and fail fast if it is missing.
- Validate `suiteSnapshot` against the canonical suite envelope and return structured API errors for invalid snapshots.
- Preserve canonical rule-view exposure of check-type metadata in API responses and normalization layers.
- Treat unsupported cross-object execution without pre-materialized inputs as an error, not as a degraded success path.

## Related Artifacts
- `/memories/repo/dq-rulebuilder-fastapi-gx-autopublish-direct-checktype-builder-note.md`
- `/memories/repo/dq-rulebuilder-fastapi-gx-supported-rule-lifecycle-validator-note.md`
- `/memories/repo/dq-rulebuilder-gx-run-plan-validation-execution-contract-note.md`
- `/memories/repo/dq-rulebuilder-fastapi-gx-run-plan-activation-invalid-snapshot-note.md`
- `/memories/repo/dq-rulebuilder-fastapi-api7-execution-contract-shapes-note.md`
- `/memories/repo/dq-rulebuilder-dq4-join-consistency-phase3-view-contract-note.md`
- `dq-api/fastapi/app/api/`
- `dq-engine/`