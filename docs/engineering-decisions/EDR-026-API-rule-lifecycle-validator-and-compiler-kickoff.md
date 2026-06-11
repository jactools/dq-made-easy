# EDR-026 [API]: Rule-Lifecycle Validator and Compiler Kickoff Patterns

**Status**: Accepted
**Date**: 2026-04-20
**Tag**: API

## Context
The repository now has a real compiler kickoff path and a live GX-supported validator that exercises create-through-activate-through-execution flows. These patterns need to remain stable so compiler artifacts and validator coverage do not drift apart.

## Decision
- Keep compiler output deterministic and reusable across rule-version and execution flows.
- Use the live GX-supported validator as the repository’s end-to-end contract check for supported rule lifecycle paths.
- Stage and rewire real materialized inputs for join-pair and delivery-backed validation scenarios rather than simulating them in-process.
- Treat unsupported or not-yet-covered join-pair scenarios as explicit gaps rather than silently broad coverage.

## Rationale
- Deterministic compiler output enables stable downstream reuse and verification.
- A live validator is the strongest check that compiler, API, worker, and storage assumptions still line up.
- Real staged inputs are required for meaningful join-pair and delivery-backed execution tests.

## Scope Boundaries
This decision covers compiler kickoff and validator coverage patterns.

It does not by itself define:
- full execution-contract shape, which is covered by EDR-018
- every future GX check type
- generic test-data generation conventions, which are covered by EDR-017

## Consequences
**Positive**
- Compiler and validator behavior stay tied to real runtime flows.
- Supported check-type coverage remains explicit.

**Negative**
- End-to-end validator maintenance is heavier because it stages real data and storage wiring.

## Implementation Guidance
- Keep compiler artifacts deterministic.
- Extend the validator by adding explicit live cases, not hidden shortcuts.
- Reuse staged AIStor/parquet paths for join-pair and delivery-backed live validations where appropriate.

## Related Artifacts
- `/memories/repo/dq-rulebuilder-fastapi-dq73-compiler-kickoff-note.md`
- `/memories/repo/dq-rulebuilder-fastapi-gx-supported-rule-lifecycle-validator-note.md`
