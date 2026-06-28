# ADR-034: Engine-Neutral Exception Fact Contract Family, Storage Authority, Identifier Handling, and Reason Taxonomy

**Status**: Accepted
**Date**: 2026-05-06
**Related**: [ADR-014](./ADR-014-gx-suite-registry-pyspark-execution-and-exception-store-separation.md), [ADR-017](./ADR-017-canonical-snake_case-api-fields.md), [ADR-019](./ADR-019-platform-business-keys-and-stable-identity-surfaces.md)

## Context

DQ-7.4 introduced a neutral exception-fact contract and neutral `/exceptions` APIs, but several design choices were still open:

- the public family name still competed with legacy GX-oriented internal names
- the long-term source of truth for millions of raw exception facts was not explicitly locked
- the platform needed a clear stance on whether record identifiers remain plaintext or move behind hashing or encryption semantics
- `reason_code` needed a controlled cross-engine meaning instead of remaining an engine-local string

Those decisions affect retention, reporting, privacy boundaries, future engine integrations, and the repository-wide no-fallback policy.

## Decision

Adopt the following canonical exception-fact decisions.

### 1. Canonical contract and API family name

Use **Exception Fact** as the canonical row-level failed-record contract family name.

- Public contract family: `exception-fact`
- Public API family: `/rulebuilder/v1/exceptions/...`
- Public report family: exception summaries and exception analytics
- Public archive term: exception archive

Legacy GX-specific names such as `gx_execution_violation` remain internal implementation details only until internal refactors retire them. They must not shape new public routes, contract names, docs, or governance language.

### 2. Storage authority and operating model

Use a **hybrid storage model**.

- Immutable raw source of truth: object-storage exception archive batches
- Query and report surface: dedicated relational exception projection store
- Rule/result database: excluded from raw exception facts

Consequences:

- object storage is the durable raw-fact archive for scale and replay
- the relational exception projection store is the authorized low-latency read model for raw-fact APIs, summaries, and backfill observability
- replay and backfill must be deterministic and fail fast on unresolved lineage gaps rather than silently approximating missing fields

The current repository-only backend remains acceptable for local development, tests, and maintenance flows, but it is not the long-term production source-of-truth choice.

### 3. Identifier handling policy

Store `record_reference.identifier_value` in plaintext inside the raw exception-fact stores and authorized raw-fact APIs, and pair it with a deterministic hash.

- `identifier_value` remains available for authorized drill-down, remediation, and deterministic replay
- `identifier_hash` is required for new writers whenever the identifier can be deterministically hashed
- `identifier_hash` uses the canonical format `sha256:<64 lowercase hex>`
- observability payloads, aggregate analytics, and exported exception-summary artifacts must not expose plaintext record identifiers
- encryption at rest is delegated to the underlying storage layer and platform controls; application-layer substitution of plaintext with encrypted blobs is not the canonical contract

### 4. Controlled `reason_code` taxonomy

`failure.reason_code` is the canonical cross-engine analytics code and must use a controlled business taxonomy rather than an engine-native artifact name.

Canonical reason families:

- `completeness_*`: missing required data, nullability, blank values
- `uniqueness_*`: duplicate keys or duplicate combinations
- `validity_*`: invalid format, invalid domain, invalid type coercion
- `consistency_*`: mismatched values across related columns or datasets
- `referential_integrity_*`: missing parent or broken reference
- `range_*`: numeric, temporal, or threshold boundary violations
- `freshness_*`: stale or overdue data assertions
- `volume_*`: row-count or cardinality threshold violations
- `custom_*`: approved domain-specific assertions that do not fit a shared family

Engine-native diagnostics such as GX expectation types remain valuable, but they belong in `engine_metadata` or `ops_metadata`, not as the canonical analytics key.

## Consequences

### Positive

- Public contracts now have a single neutral vocabulary that can outlive GX-specific internals.
- The storage model matches the scale requirement for millions of raw exception facts while preserving a fast read model.
- Raw-fact APIs retain operational usefulness without leaking identifiers into summary exports or observability.
- Future engines can normalize into a stable analytics taxonomy without forcing downstream consumers to understand engine-native codes.

### Negative

- Internal GX-oriented class and repository names are now explicitly transitional debt.
- The current GX adapter still needs follow-up work to normalize reason codes from expectation-native values into the controlled taxonomy.
- A relational projection pipeline must remain synchronized with the object-storage archive in production deployments.

## Implementation Guidance

- Keep using the existing `docs/contracts/exception-fact` contract family as the public source of truth.
- Prefer `exception_fact`, `exception_archive`, and `exception_analytics` naming for all new public-facing assets.
- Preserve engine-native failure details in `engine_metadata.expectation_type`, engine-native artifact references, and optional `ops_metadata` fields.
- Backfill jobs should add `identifier_hash` when absent using the canonical hash format.
- Cross-engine analytics and new engine adapters must emit controlled taxonomy values for `reason_code`; engine-native names should not be exposed as the long-term analytics key.

## Related Artifacts

- [docs/contracts/exception-fact/README.md](../../docs/contracts/exception-fact/README.md)
- [docs/implementation-details/DQ_7_4_GX_SUITE_ORCHESTRATION_IMPLEMENTATION_DETAILS.md](../../docs/implementation-details/DQ_7_4_GX_SUITE_ORCHESTRATION_IMPLEMENTATION_DETAILS.md)