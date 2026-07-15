# ARCH-EXC-0008: Synthetic/Test Object Storage Boundaries Are Not Yet Enforced

**Status**: Approved
**Category**: data
**Owner**: Data Governance
**First recorded**: 2026-04-22
**Last reviewed**: 2026-04-22
**Next review date**: 2026-05-31
**Target closure date**: 2026-10-31
**Risk level**: high
**Impact level**: high
**Governing baseline**: [ADR-031 Synthetic/Test Object Storage Buckets and Synthetic Evidence Boundaries](../adr/ADR-031-synthetic-test-object-storage-buckets-and-synthetic-evidence-boundaries.md), [DQ-OBJ-SYN-001](../../docs/technical/OBJECT_STORAGE_SYNTHETIC_BUCKET_AND_SYNTHETIC_EVIDENCE_REQUIREMENTS.md), [SEC-3 Synthetic/Test Bucket and Evidence Boundaries](../../docs/features/SEC_3_SYNTHETIC_TEST_BUCKET_AND_EVIDENCE_BOUNDARIES.md)

## Affected Surface

Repository-managed AIStor or other S3-compatible storage usage across generated test-data materialization, local CSV staging, source-data-aligned execution paths, exception evidence persistence, and delivery-oriented artifacts.

## Summary

The repository now defines a synthetic/test bucket and synthetic-evidence boundary, but current AIStor or other S3-compatible flows do not yet enforce or expose that classification consistently.

## Rationale

Object-storage support evolved across test-data generation, delivery seeding, exception evidence, and source-data execution without one shared interpretation rule for synthetic versus real/evidence storage.

## Risk Details

Without explicit enforcement, synthetic/test outputs can be misread as production-like evidence, and mixed bucket usage can blur the distinction between engineering verification, operational evidence, and reporting support.

## Impact Details

This affects AIStor or S3-compatible storage bucket naming, delivery-note interpretation, evidence narratives, testing workflows, and future reporting-oriented claims that depend on clear evidence semantics.

## Compensating Controls

ADR-031, requirement `DQ-OBJ-SYN-001`, and SEC-3 now make the boundary explicit. Existing docs already distinguish some generated-data paths from real-data execution, which reduces ambiguity compared with having no stated control at all.

## Validation and Evidence

- [ABS_2_DATA_CATALOG_MATERIALIZATION.md](../../docs/features/ABS_2_DATA_CATALOG_MATERIALIZATION.md) and [ABS_2_DATA_CATALOG_MATERIALIZATION_IMPLEMENTATION_DETAILS.md](../../docs/implementation-details/ABS_2_DATA_CATALOG_MATERIALIZATION_IMPLEMENTATION_DETAILS.md) describe generated outputs written to AIStor or other S3-compatible storage.
- [API_7_REAL_DQ_RULE_EXECUTION_MILESTONE.md](../../docs/implementation-details/API_7_REAL_DQ_RULE_EXECUTION_MILESTONE.md) describes a real-data execution path that also reads from AIStor or other S3-compatible storage.
- [exception_storage.py](../../dq-api/fastapi/app/application/services/exception_storage.py) defaults DQ exception persistence to AIStor or other S3-compatible object storage.
- [stage_local_csv_to_s3_parquet.py](../../scripts/stage_local_csv_to_s3_parquet.py) allows arbitrary local CSV staging into AIStor or other S3-compatible storage.

## Implementation Progress

Phase 1 (Classification Baseline) is complete:
- [Bucket and Prefix Naming Conventions](../../docs/technical/object-storage-classification/BUCKET_PREFIX_NAMING_CONVENTIONS.md) defines canonical naming patterns
- [Flow Inventory](../../docs/technical/object-storage-classification/FLOW_INVENTORY.md) classifies all current AIStor/S3 flows
- [Operator Guidance](../../docs/technical/object-storage-classification/OPERATOR_GUIDANCE.md) provides runbooks for classification and drift handling
- [Deviation Tracker](../../docs/technical/object-storage-classification/DEVIATION_TRACKER.md) tracks remaining deviations (DEV-001, DEV-002, DEV-003)

Remaining work: Phase 2 (artifact labeling for non-materialization flows), Phase 3 (broader validation and enforcement beyond SEC3-F-P3-02a).

## Exit Criteria

Repository-managed object-storage flows expose or enforce `synthetic_test` versus `real_evidence` classification, synthetic bucket results are labeled as synthetic results where interpretation matters, and mixed or ambiguous storage semantics are reduced to explicit approved exceptions only.

This deviation will be retired when DEV-001 (DQ exception classification ambiguity) is resolved and all other deviations are closed.