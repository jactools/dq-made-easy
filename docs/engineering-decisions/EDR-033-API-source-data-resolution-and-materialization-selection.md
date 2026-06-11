# EDR-033 [API]: Source Data Resolution and Materialization-Selection Rules

**Status**: Accepted
**Date**: 2026-04-20
**Tag**: API

## Context
Before execution can be planned, assignment scope must resolve into real, active data-object versions. This resolver path is a durable contract because stale mappings, inactive objects, or missing version metadata cannot be papered over safely.

## Decision
- Source-data resolution must fail fast on missing dataset or product mappings, object mismatches, missing latest-version links, or missing version rows.
- Resolution must return only active and queryable target versions; stale or inactive targets are errors, not filterable noise.
- Assignment-scope filtering must stay server-backed and data-model aware; the resolver must not invent client-side assumptions about what the scope intended.
- Resolved target payloads must include the metadata required by downstream planning and execution; partial target payloads are invalid.

## Rationale
- Resolution is the point where data-model truth is converted into executable target scope.
- Silent filtering hides broken metadata relationships and produces misleading no-op execution plans.
- Downstream planning depends on complete target metadata, not just IDs.

## Scope Boundaries
This decision covers source-target resolution prior to grouped execution planning.

It does not by itself define:
- execution grouping rules
- Spark runtime or worker behavior
- delivery selector resolution rules already covered elsewhere

## Consequences
**Positive**
- Broken scope and metadata relationships fail before work is scheduled.
- Execution planning receives complete, target-ready payloads.

**Negative**
- Callers cannot rely on silent narrowing when data relationships are stale.
- Resolver tests must stay aligned with active-version semantics.

## Implementation Guidance
- Validate dataset, product, object, and version relationships explicitly.
- Reject inactive or incomplete targets.
- Pass fully populated target metadata downstream.

## Related Artifacts
- `/memories/repo/dq-rulebuilder-fastapi-source-data-resolver-note.md`
