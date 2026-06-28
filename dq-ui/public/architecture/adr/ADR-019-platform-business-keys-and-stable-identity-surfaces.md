# ADR-019: Platform Business Keys and Stable Identity Surfaces

**Status**: Proposed
**Date**: 2026-04-17
**Related**: [ADR-018](./ADR-018-iso-11179-based-data-definition-framework-for-bcbs-239-and-mifid-ii.md), [ADR-017](./ADR-017-canonical-snake_case-api-fields.md), [ADR-014](./ADR-014-gx-suite-registry-pyspark-execution-and-exception-store-separation.md)

## Context

dq-rulebuilder already uses a mix of technical IDs, versioned identifiers, and semantic names across rules, data catalog objects, deliveries, GX suites, run plans, approvals, and execution records. That mixture works for persistence, but it makes public lookup, reporting, and cross-entity grouping inconsistent.

The platform needs a stable identity layer that:
- distinguishes business meaning from storage identity
- stays immutable once minted
- can be used for lookup and filtering across API surfaces
- survives renames and version churn without rewriting historical records
- applies consistently to multiple entity families, not only rules

Business keys are the right abstraction for that layer. They are not database primary keys and they are not display labels. They are stable, canonical, human-meaningful identifiers that can be exposed to API consumers while technical IDs remain the authoritative join keys.

## Decision

Adopt platform business keys as the canonical stable identity surface for core entities.

The platform must:
- keep technical IDs as the primary database and foreign-key identity
- generate business keys from canonical, immutable source values where possible
- expose business keys in read models and public filters when they improve traceability
- preserve historical references when names or labels change
- treat the same logical entity consistently across rule definitions, catalog entities, deliveries, GX artifacts, run plans, and approvals

The initial implementation should be additive:
- keep all existing technical IDs and relationships intact
- add business-key metadata fields and read paths first
- backfill and constrain uniqueness after the additive contract is proven

## Canonical Naming Rules

Use the most stable canonical source value available for each entity family.

- Prefer an immutable domain identifier over a display name when the entity already has one.
- Prefer a normalized semantic name when the entity family is represented by business terminology rather than a generated identifier.
- Prefer a canonical storage/location string when the location itself is the stable business identity.
- Keep the chosen business key immutable once minted.
- Keep technical IDs authoritative for joins, foreign keys, and lifecycle operations.

Current entity-family mapping:

- Rules and rule versions: keep the technical rule identifier as the business key until a dedicated domain key exists.
- Data products, data sets, data objects, and data object catalog entries: use the canonical business name, normalized to a stable lowercase hyphenated form.
- Data deliveries and delivery notes: use the canonical delivery location.
- GX suites and GX artifact envelopes: keep the suite identity contract separate from the execution hints metadata.
- GX run plans: use the run-plan identifier as the public business key.
- Approvals: use the approval identifier as the public business key.
- Execution and violation records: use the parent execution identity and row identity as the public grouping keys, not display text.

## Consequences

### Positive

- Public consumers get stable, human-readable lookup keys.
- Reporting and audit trails can group logically related records across versions.
- Renames stop breaking historical references.
- The platform gains a shared identity model that applies across catalog, execution, and governance flows.

### Negative

- Identity modeling becomes more explicit and therefore more opinionated.
- Existing records need backfill and duplicate resolution before strict uniqueness can be enforced.
- Some entity families will need both business keys and technical IDs to avoid breaking joins.
- Public APIs will grow additional read/filter fields.

## Implementation Guidance

- Keep business keys immutable once created.
- Prefer canonical, normalized source values over display text when a stable source code exists.
- Use entity-family-specific uniqueness scopes rather than one global naming rule.
- Preserve snake_case in API payloads and filters.
- Add business keys first as optional additive metadata; enforce uniqueness only after backfill and collision review.
- Apply the same pattern to related entities where semantic identity matters, including rules, data objects, data deliveries, GX suites, run plans, approvals, and violation records.

## Related Artifacts

- [ABSTRACTION_FEATURES.md](../../docs/features/ABSTRACTION_FEATURES.md)
- [ABS_3_DELIVERY_LINKED_RULE_EXECUTION_IMPLEMENTATION_DETAILS.md](../../docs/implementation-details/ABS_3_DELIVERY_LINKED_RULE_EXECUTION_IMPLEMENTATION_DETAILS.md)
- [BUSINESS_KEYS.md](../../docs/features/BUSINESS_KEYS.md)
- [BUSINESS_KEY_IMPLEMENTATION_DETAILS.md](../../docs/implementation-details/BUSINESS_KEY_IMPLEMENTATION_DETAILS.md)