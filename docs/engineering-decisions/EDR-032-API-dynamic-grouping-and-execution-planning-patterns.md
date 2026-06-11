# EDR-032 [API]: Dynamic Grouping and Execution-Planning Patterns

**Status**: Accepted
**Date**: 2026-04-20
**Tag**: API

## Context
Execution planning now includes a dedicated grouped planner that converts resolved execution scope into target-centric batches for shared Spark execution. That planning step needs stable semantics distinct from source resolution and runtime dispatch.

## Decision
- The grouped execution planner must fail fast on malformed planner input or empty target scope.
- Grouping is performed per target data object version; suites for different target versions must not be merged into one batch.
- Planner output must preserve input order and suite cardinality; planning may group but must not deduplicate, collapse, or silently skip suites.
- Planner responsibilities stop at grouping and batch shaping; upstream schema validation and downstream execution remain separate contracts.

## Rationale
- Planning errors should surface where they occur, not later as Spark-side ambiguity.
- Shared execution only works safely when batches remain target-scoped.
- Order and cardinality preservation keeps planning observable and testable.

## Scope Boundaries
This decision covers grouping and batch-planning semantics.

It does not by itself define:
- source data resolution
- Spark dispatch/runtime behavior
- result aggregation or status persistence

## Consequences
**Positive**
- Execution planning becomes deterministic and test-friendly.
- Batch boundaries remain aligned with shared-runtime assumptions.

**Negative**
- Planner callers must provide valid, pre-validated envelopes.
- Invalid scope now fails immediately instead of degrading into empty output.

## Implementation Guidance
- Validate planner prerequisites before grouping.
- Emit one target version per batch.
- Preserve input ordering through planner output.

## Related Artifacts
- `/memories/repo/dq-rulebuilder-fastapi-grouped-execution-planner-note.md`
