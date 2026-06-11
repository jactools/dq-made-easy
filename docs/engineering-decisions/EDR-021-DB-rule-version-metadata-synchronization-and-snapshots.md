# EDR-021 [DB]: Rule-Version Metadata Synchronization and Snapshot Rules

**Status**: Accepted
**Date**: 2026-04-20
**Tag**: DB

## Context
Rule-version data needs to preserve the execution-relevant state that was true at version time, while still staying synchronized with CSV-backed seed metadata and current rule/version tables.

## Decision
- Treat CSV-backed version metadata as the source of truth for seeded versioning state.
- Persist snapshot fields such as check-type metadata on rule versions so later execution can use version-time truth instead of only current rule state.
- Prefer version snapshot fields first and fall back to current rule data only for backward compatibility with older seeded or legacy rows.

## Rationale
- Version snapshots preserve historical execution semantics.
- CSV-backed synchronization keeps seeded version metadata reproducible.
- Explicit fallback allows older rows to keep working while snapshot coverage expands.

## Scope Boundaries
This decision covers rule-version metadata sync and snapshot usage.

It does not by itself define:
- all future snapshot fields
- approval/version lineage behavior
- general seeding policy beyond version metadata alignment

## Consequences
**Positive**
- Versioned execution logic can rely on snapshot data.
- Seeded version metadata stays synchronized across reseed paths.

**Negative**
- Snapshot fields need ongoing migration and CSV/header maintenance.

## Implementation Guidance
- Keep version metadata CSV-backed.
- Add snapshot fields through explicit migrations and seed/header updates.
- Resolve execution metadata from snapshots first, then current rule data only as fallback.

## Related Artifacts
- `/memories/repo/dq-rulebuilder-rule-version-metadata-csv-sync-note.md`
- `/memories/repo/dq-rulebuilder-ruleversion-checktype-snapshot-note.md`
