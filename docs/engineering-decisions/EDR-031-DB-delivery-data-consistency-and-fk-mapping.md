# EDR-031 [DB]: Delivery Data Consistency and Foreign-Key Mapping Rules

**Status**: Accepted
**Date**: 2026-04-20
**Tag**: DB

## Context
Delivery seed data links delivery rows, catalog objects, and downstream materialization paths. Earlier fixes showed that silent mismatches between CSV references and catalog IDs create misleading generated SQL and foreign-key failures.

## Decision
- Delivery-related seed data must be generated through the canonical seed generator rather than by hand-editing generated SQL artifacts.
- Foreign-key reference validation must happen before SQL generation; if delivery CSV rows reference missing catalog objects, generation must fail with a clear mismatch report.
- Generated SQL must be treated as a build artifact, not the source of truth; fixes belong in CSV inputs or generator logic.
- Seed generation must not silently drop invalid delivery rows or synthesize fallback IDs to satisfy constraints.

## Rationale
- The generator is the only place with enough context to validate cross-file delivery references consistently.
- Hand-editing SQL hides root-cause data problems and makes reseeding non-reproducible.
- Fail-fast foreign-key validation keeps delivery state aligned with catalog truth.

## Scope Boundaries
This decision covers delivery seed consistency and foreign-key validation.

It does not by itself define:
- delivery runtime selector resolution
- delivery materialization behavior
- broader schema migration policy

## Consequences
**Positive**
- Delivery seed failures point directly to broken source references.
- Reseeding stays reproducible because generated artifacts are not treated as editable source.

**Negative**
- Bad CSV changes now fail earlier and more visibly.
- Seed generator maintenance must preserve clear mismatch diagnostics.

## Implementation Guidance
- Keep delivery/catalog mapping validation in the generator path.
- Report unmatched delivery references explicitly.
- Fix source CSV or mapping logic instead of patching generated SQL.

## Related Artifacts
- `/memories/repo/dq-rulebuilder-data-deliveries-catalog-fk-map-note.md`
