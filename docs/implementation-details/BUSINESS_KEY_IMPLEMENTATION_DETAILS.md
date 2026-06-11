# Business Key Implementation Details

This note turns the business-key feature into a phased implementation backlog.

For the feature plan, see [Business Keys and Stable Identity Surfaces](../features/BUSINESS_KEYS.md).

Goal: add a stable business-key layer across the platform while preserving technical primary keys and existing joins.

## Problem Statement

Core entities currently expose a mix of technical IDs and semantic names. That is enough for persistence, but it makes public lookup, grouping, and cross-entity reporting inconsistent.

What is needed is a business-key layer that:
- is stable and immutable once minted
- can be used for lookup and filtering
- survives renames and version churn
- applies consistently to rules and adjacent entity families
- remains additive until the backfill and uniqueness story is ready
- keeps UUID7 identifiers internal to persistence and non-UI runtime joins

## Proposed Model Split

- Technical IDs remain the primary persistence keys.
- Business keys become the stable public identity layer.
- Semantic metadata stays alongside technical IDs instead of replacing them.
- The first slice should be additive and low-risk: schema fields, read models, and round-trip tests.

## Canonical Naming Rules

Use the most stable canonical source value available for each entity family.

- Prefer an immutable domain identifier over a display name when the entity already has one.
- Prefer a normalized semantic name when the entity family is represented by business terminology rather than a generated identifier.
- Prefer a canonical storage/location string when the location itself is the stable business identity.
- Keep the chosen business key immutable once minted.
- Keep technical IDs authoritative for joins, foreign keys, and lifecycle operations.

Current entity-family mapping:

- Rules and rule versions: use the normalized rule name as the public business key; rule versions compose the rule business key with the version number.
- Data products, data sets, data objects, and data object catalog entries: use the canonical business name, normalized to a stable lowercase hyphenated form.
- Data deliveries and delivery notes: use the canonical delivery location.
- GX suites and GX artifact envelopes: keep the suite identity contract separate from the execution hints metadata.
- GX run plans: use the run-plan identifier as the public business key.
- Approvals: use the approval identifier as the public business key.
- Execution and violation records: use the parent execution identity and row identity as the public grouping keys, not display text.

## Current Foundation

The first implementation slice can build on existing contract and repository patterns:

- `SnakeModel` already drives canonical API serialization.
- GX suite envelopes already carry a versioned JSON contract.
- The data catalog already exposes attribute metadata with primary-key flags.
- Rule publishing already serializes execution hints and GX metadata.

## Delivery Phases

### Phase 1 - Canonical Metadata and Read/Write Contract

Add additive business-key metadata to the contract surfaces that already exist.

#### Phase 1 Deliverables

- business-key fields in rule and GX suite metadata
- business-key flag in the attribute catalog
- repository round-trip support for the additive metadata
- focused tests proving backward compatibility

### Phase 2 - Entity Expansion and Uniqueness Rules

Extend business keys to the remaining core entity families and define per-entity uniqueness.

#### Phase 2 Deliverables

- business-key support for data objects, deliveries, run plans, approvals, and related records
- uniqueness constraints by entity family
- migration/backfill strategy

Status update: the additive business-key surfaces for run plans and approvals are now implemented in the API, repository, migration, and list-filter layers. Uniqueness constraints and backfill remain deferred to the later hardening phase.

### Phase 3 - Lookup and Filter Surfaces

Expose business-key lookup/filter capabilities in the APIs that need them.

#### Phase 3 Deliverables

- public query filters by business key
- read-model enrichment for business-key fields
- response contract tests

### Phase 4 - Backfill and Governance Hardening

Backfill existing rows, resolve collisions, and finalize governance rules.

#### Phase 4 Deliverables

- backfill migrations
- duplicate resolution scripts
- governance documentation

## Numbered Backlog

### Phase 1 Backlog

1. [x] (BUSKEY-01) Define canonical business-key naming rules.
   - Decide the canonical source values for each entity family.
   - Keep business keys immutable once minted.
   - Preserve technical IDs as the authoritative joins.

2. [x] (BUSKEY-02) Add additive business-key metadata to rule and GX suite contracts.
   - Extend rule publish metadata with `businessKeyFields`.
   - Extend GX artifact execution hints with `businessKeyFields`.
   - Keep `primaryKeyFields` unchanged for compatibility.

3. [x] (BUSKEY-03) Add business-key flag support to the attribute catalog.
   - Extend attribute models with `isBusinessKey`.
   - Persist the flag in the data-catalog repository layer.
   - Preserve the existing `isPrimaryKey` behavior.

4. [x] (BUSKEY-04) Add focused tests for the additive metadata path.
   - Prove the new fields serialize with snake_case.
   - Prove repositories round-trip the metadata.
   - Prove existing consumers still work without business keys present.

### Phase 2 Backlog

5. [ ] (BUSKEY-05) Extend business-key metadata to the remaining entity families.
   - Add explicit business keys for data objects, deliveries, run plans, approvals, and core identity tables.
   - Decide entity-specific uniqueness scopes.
   - Keep the implementation additive until backfill is ready.

### Phase 3 Backlog

6. [x] (BUSKEY-06) Add business-key lookup and filter support.
   - Allow read endpoints to filter by business key where it helps discovery.
   - Expose business keys in read models.
   - Keep technical-ID lookup paths intact.

### Phase 4 Backlog

7. [ ] (BUSKEY-07) Backfill existing rows and enforce uniqueness.
   - Assign business keys to existing records.
   - Resolve duplicates deterministically.
   - Add uniqueness constraints after cleanup.

## Acceptance Criteria

- The platform can carry business-key metadata without breaking existing technical-ID flows.
- Rule and GX suite metadata can express business-key fields.
- Attributes can mark whether they participate in a business key.
- The contract remains snake_case on the wire.
- The implementation can be expanded to other entity families without redesigning the core approach.

## Related references

- [ADR-019](../../architecture/adr/ADR-019-platform-business-keys-and-stable-identity-surfaces.md)
- [ADR-018](../../architecture/adr/ADR-018-iso-11179-based-data-definition-framework-for-bcbs-239-and-mifid-ii.md)
- [Business Keys and Stable Identity Surfaces](../features/BUSINESS_KEYS.md)