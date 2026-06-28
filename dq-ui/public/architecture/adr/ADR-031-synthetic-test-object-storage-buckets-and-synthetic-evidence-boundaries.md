# ADR-031: Synthetic/Test Object Storage Buckets and Synthetic Evidence Boundaries

**Status**: Accepted  
**Date**: 2026-04-22  
**Related**: [ADR-014](./ADR-014-gx-suite-registry-pyspark-execution-and-exception-store-separation.md), [ADR-018](./ADR-018-iso-11179-based-data-definition-framework-for-bcbs-239-and-mifid-ii.md), [ADR-030](./ADR-030-eu-financial-regulatory-baseline-and-control-mapping.md), [Synthetic/Test Object Storage and Synthetic Evidence Requirements](../../docs/technical/OBJECT_STORAGE_SYNTHETIC_BUCKET_AND_SYNTHETIC_EVIDENCE_REQUIREMENTS.md)

## Context

The repository uses AIStor or other S3-compatible storage for multiple different purposes, including generated test data, delivery-object seeding, source-data execution paths, and exception evidence persistence.

That flexibility is useful for development and integration, but it creates an evidence-classification problem: if synthetic/test data, real source-aligned data, and evidence artifacts can all land in the same object-storage domain without explicit boundary rules, downstream users can over-interpret what the stored results mean.

For regulated or security-sensitive use cases, the repository needs an explicit rule that separates synthetic/test object-storage paths from real/evidence object-storage paths and prevents evidence derived from synthetic/test storage from being represented as production-grade or reporting-grade evidence.

## Decision

Adopt a repository rule that synthetic/test object-storage buckets or prefixes are logically segregated from real/evidence buckets or prefixes, and that evidence derived from synthetic/test object-storage locations is classified as synthetic results.

For this ADR:

1. Repository-managed object-storage locations MUST be classifiable as either:
   - synthetic/test storage, or
   - real/evidence storage.
2. Synthetic/test object-storage locations MUST be used for generated data, test fixtures, preview materializations, and other non-production synthetic artifacts.
3. Real/evidence object-storage locations MUST be used for operational evidence, exception evidence, or source-data-aligned artifacts when those artifacts are intended to support production, compliance, or reporting narratives.
4. Evidence produced from synthetic/test buckets or prefixes MUST be treated as synthetic results, even when the execution path, schema, or surrounding workflow resembles a production scenario.
5. Repository artifacts MUST NOT present synthetic/test bucket results as production-grade evidence, regulated reporting evidence, or proof of real-data correctness.
6. Delivery notes, execution notes, evidence packs, validation scripts, and future reporting artifacts SHOULD identify whether the underlying storage location was synthetic/test or real/evidence when that distinction materially affects interpretation.
7. Missing segregation, missing classification, or ambiguous evidence semantics MUST be treated as a tracked gap rather than left implicit.

## Consequences

### Positive

- The repository gains a clear interpretation boundary for AIStor or S3-compatible storage results.
- Synthetic results can still be useful for tests, previews, and demonstrations without being confused with production evidence.
- Future compliance, reporting, and data-protection narratives can distinguish synthetic outputs from real/evidence outputs more credibly.

### Negative

- Existing object-storage usage patterns may need refactoring, naming conventions, or validation rules.
- Some current AIStor flows are broader than the new boundary and will need explicit migration or deviation handling.

## Implementation Notes

- Use a requirement or implementation artifact to define naming, prefix, bucket-classification, and evidence-labeling expectations.
- Keep synthetic/test evidence useful for engineering and demonstration workflows, but label it explicitly as synthetic.
- Record current non-conforming usage in the architecture deviation register until the boundary is enforced.