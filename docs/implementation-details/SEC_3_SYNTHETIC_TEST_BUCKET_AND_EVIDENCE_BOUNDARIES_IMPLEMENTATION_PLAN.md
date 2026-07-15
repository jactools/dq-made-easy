# SEC-3 Synthetic/Test Bucket and Evidence Boundaries Implementation Plan

**Status**: In Progress  
**Target**: repository-managed separation between synthetic/test object-storage locations and real/evidence object-storage locations, with explicit classification labels on all delivery notes and evidence artifacts, and fail-fast enforcement when synthetic results are misclassified as real evidence  
**Date**: 2026-07-15

Related feature: [SEC-3 Synthetic/Test Bucket and Evidence Boundaries](../features/SEC_3_SYNTHETIC_TEST_BUCKET_AND_EVIDENCE_BOUNDARIES.md)  
Related requirement: [DQ-OBJ-SYN-001 Object Storage Synthetic/Test Bucket and Synthetic Evidence Requirements](../technical/OBJECT_STORAGE_SYNTHETIC_BUCKET_AND_SYNTHETIC_EVIDENCE_REQUIREMENTS.md)  
Related ADR: [ADR-031 Synthetic/Test Object Storage Buckets and Synthetic Evidence Boundaries](../../architecture/adr/ADR-031-synthetic-test-object-storage-buckets-and-synthetic-evidence-boundaries.md)

---

## Overview

SEC-3 introduces a mandatory interpretation boundary for all repository-managed AIStor or S3-compatible storage flows.

The target state is that every storage location and every artifact derived from it is explicitly classifiable as either `synthetic_test` or `real_evidence`, and that the platform fails fast when a flow attempts to represent synthetic test results as production-grade or reporting-grade evidence.

This matters because regulated frameworks (BCBS 239, MiFID II, EMIR, DORA) treat material misrepresentation of evidence as a compliance failure. A synthetic test result presented as real evidence is not an ambiguity — it is a violation.

The current repository already uses AIStor for multiple overlapping purposes (generated test data, delivery-object seeding, source-data execution paths, exception evidence). The boundary exists conceptually (ADR-031) but has not been implemented in naming, labeling, validation, or enforcement.

This plan implements that boundary in five workstreams: classification inventory, artifact labeling, runtime validation, documentation, and deviation tracking.

Derived documentation:
- [Bucket and Prefix Naming Conventions](../technical/object-storage-classification/BUCKET_PREFIX_NAMING_CONVENTIONS.md) — canonical bucket/prefix patterns for `synthetic_test` and `real_evidence` (W1)
- [Flow Inventory and Classification](../technical/object-storage-classification/FLOW_INVENTORY.md) — inventory of all current AIStor/S3 flows with classification (W1)
- [Operator Guidance](../technical/object-storage-classification/OPERATOR_GUIDANCE.md) — runbooks for classification, ambiguity resolution, drift handling (W4)
- [Deviation Tracker](../technical/object-storage-classification/DEVIATION_TRACKER.md) — active deviations, drift check procedure, progress against acceptance criteria (W5)

## Scope Definition

### In Scope

- All repository-managed AIStor or S3-compatible storage usage, including generated test-data materialization, delivery-object seeding, preview/validation staging, exception evidence persistence, and source-data-aligned execution paths.
- Delivery notes, execution summaries, evidence packs, and any reporting-oriented artifact that references object-storage outputs.
- API endpoints, database models, and frontend surfaces where classification labels must be visible and editable.
- Validation scripts and linting that enforce bucket/prefix naming conventions and classification consistency.
- Fail-fast checks that reject flows attempting to represent synthetic outputs as real evidence without explicit handling.

### Out of Scope for the First Cut

- Non-repository storage environments that already provide their own classification controls.
- Third-party storage integrations outside repository-managed compose definitions.
- Migration of existing data already stored in AIStor before this boundary is defined.
- Automated re-classification of legacy artifacts without manual review.

## Workstream 1: Classification Inventory and Naming Convention

- [x] (SEC3-I-W1-01) Define the repository naming or prefix convention for `synthetic_test` versus `real_evidence` object-storage locations. ([BUCKET_PREFIX_NAMING_CONVENTIONS.md](../technical/object-storage-classification/BUCKET_PREFIX_NAMING_CONVENTIONS.md))
- [x] (SEC3-I-W1-02) Document the canonical bucket or prefix patterns that operators and automation must follow when creating new storage targets. ([BUCKET_PREFIX_NAMING_CONVENTIONS.md](../technical/object-storage-classification/BUCKET_PREFIX_NAMING_CONVENTIONS.md))
- [x] (SEC3-I-W1-03) Inventory all current AIStor or S3-compatible flows and classify each one as `synthetic_test` or `real_evidence`. ([FLOW_INVENTORY.md](../technical/object-storage-classification/FLOW_INVENTORY.md))
- [x] (SEC3-I-W1-04) Document which existing flows produce synthetic results even when the execution path, schema, or surrounding workflow resembles a production scenario. ([FLOW_INVENTORY.md §3](../technical/object-storage-classification/FLOW_INVENTORY.md#3-flows-that-produce-synthetic-results-mimicking-production-paths-sec3-f-p1-03))
- [x] (SEC3-I-W1-05) Record any flows that currently mix synthetic and real evidence in the architecture deviation register so the ambiguity is explicit rather than implicit. ([DEVIATION_TRACKER.md](../technical/object-storage-classification/DEVIATION_TRACKER.md), [ARCH-EXC-0008](../../architecture/deviations/ARCH-EXC-0008-synthetic-test-object-storage-boundaries-are-not-yet-enforced.md))

## Workstream 2: Artifact Labeling and Delivery-Note Model

- [x] (SEC3-I-W2-01) Add explicit `object_storage_classification` and `evidence_classification` fields to the repository-managed delivery-note model where that model exists. ([DataDeliveryNoteEntity](../../dq-api/fastapi/app/domain/entities/data_catalog.py), [DataDeliveryNoteView](../../dq-api/fastapi/app/api/v1/schemas/data_catalog_view.py))
- [x] (SEC3-I-W2-02) Ensure API retrieval endpoints expose the classification labels so downstream consumers can distinguish synthetic from real results without guessing. ([DeliveryExceptionSummaryView](../../dq-api/fastapi/app/api/v1/schemas/exception_fact_view.py), [data_assets classification signals](../../dq-api/fastapi/app/api/v1/endpoints/data_assets.py))
- [x] (SEC3-I-W2-03) Update materialization request and completion flows to populate classification labels deterministically based on the `output_uri` bucket/prefix. ([test_data_materialization_support.py](../../dq-api/fastapi/app/api/v1/test_data_materialization_support.py))
- [x] (SEC3-I-W2-04) Ensure evidence packs and reporting-oriented artifacts carry the classification label through to their exported output so the label survives format conversion. ([exception_reports exports](../../dq-api/fastapi/app/api/v1/endpoints/exception_reports.py), [exception_reports presenter](../../dq-api/fastapi/app/api/presenters/exception_reports.py))
- [x] (SEC3-I-W2-05) Add frontend surfaces where operators can view and filter artifacts by classification label without requiring API-level access. ([DeliveryInventory.tsx](../../dq-ui/src/components/DeliveryInventory.tsx), [data_catalog.py](../../dq-api/fastapi/app/api/v1/endpoints/data_catalog.py))

## Workstream 3: Runtime Validation and Fail-Fast Enforcement

- [x] (SEC3-I-W3-01) Add validation or linting that checks documented bucket or prefix usage against the classification rule so new flows are rejected before they reach storage. ([classification_validation.py](../../dq-api/fastapi/app/domain/services/classification_validation.py))
- [x] (SEC3-I-W3-02) Add fail-fast checks to materialization request flows that reject any `output_uri` using evidence/reporting-style namespace terms for synthetic/test outputs. ([test_data_materialization_service.py](../../dq-api/fastapi/app/application/services/test_data_materialization_service.py), pre-existing SEC3-F-P3-02a)
- [x] (SEC3-I-W3-03) Add fail-fast checks to materialization completion flows that reject any attempt to label a synthetic/test output as `real_evidence` without explicit justification and audit logging. ([test_data_materialization_service.py](../../dq-api/fastapi/app/application/services/test_data_materialization_service.py), pre-existing SEC3-F-P3-02a)
- [x] (SEC3-I-W3-04) Add validation to evidence-pack export flows that fail closed when the pack contains mixed-classification artifacts and the consumer scope is limited to real evidence. ([classification_validation.py](../../dq-api/fastapi/app/domain/services/classification_validation.py))
- [x] (SEC3-I-W3-05) Add validation to execution-result persistence flows that flag and reject attempts to store synthetic test results in real/evidence storage targets. ([classification_validation.py](../../dq-api/fastapi/app/domain/services/classification_validation.py))

## Workstream 4: Documentation and Operator Guidance

- [x] (SEC3-I-W4-01) Add documentation guidance that synthetic/test bucket outputs must be described as synthetic results in repository documentation and evidence narratives. ([OPERATOR_GUIDANCE.md §5](../technical/object-storage-classification/OPERATOR_GUIDANCE.md#5-evidence-narrative-guidance))
- [x] (SEC3-I-W4-02) Add operator runbooks for classifying new storage targets, resolving ambiguous flows, and handling classification drift when legacy artifacts lack labels. ([OPERATOR_GUIDANCE.md §1-3](../technical/object-storage-classification/OPERATOR_GUIDANCE.md#1-classifying-a-new-storage-target))
- [x] (SEC3-I-W4-03) Update the platform's regulatory compliance narratives so the evidence classification boundary is explicit in BCBS 239, MiFID II, EMIR, DORA, and GDPR interpretations. ([REGULATORY_COMPLIANCE_NARRATIVES.md](../technical/object-storage-classification/REGULATORY_COMPLIANCE_NARRATIVES.md))
- [x] (SEC3-I-W4-04) Add developer guidance for new AIStor or S3-compatible storage usage so contributors follow the classification convention from the start. ([OPERATOR_GUIDANCE.md §4](../technical/object-storage-classification/OPERATOR_GUIDANCE.md#4-developer-guidance-for-new-storage-usage))

## Workstream 5: Deviation Tracking and Migration Path

- [x] (SEC3-I-W5-01) Record every remaining mixed or ambiguous storage flow as an explicit deviation in the architecture deviation register with owner, scope, and retirement target. ([DEVIATION_TRACKER.md §1-2](../technical/object-storage-classification/DEVIATION_TRACKER.md#1-active-deviations))
- [x] (SEC3-I-W5-02) Define the migration path for existing artifacts that lack classification labels, including manual review steps and automated relabeling where the bucket/prefix makes classification unambiguous. ([OPERATOR_GUIDANCE.md §3](../technical/object-storage-classification/OPERATOR_GUIDANCE.md#3-handling-classification-drift), [DEVIATION_TRACKER.md §2](../technical/object-storage-classification/DEVIATION_TRACKER.md#2-deviation-details))
- [x] (SEC3-I-W5-03) Add periodic drift checks that flag artifacts or flows whose classification label does not match the bucket/prefix they reference. ([DEVIATION_TRACKER.md §4](../technical/object-storage-classification/DEVIATION_TRACKER.md#4-drift-check-procedure))
- [x] (SEC3-I-W5-04) Track progress against the acceptance criteria and retire deviations as enforcement completes. ([DEVIATION_TRACKER.md §5](../technical/object-storage-classification/DEVIATION_TRACKER.md#5-progress-against-acceptance-criteria))

## Acceptance Criteria Mapping

| Acceptance Criterion | Satisfied By |
|---|---|
| SEC3-F-AC-01: storage flows classifiable as `synthetic_test` or `real_evidence` | W1 (naming), W2 (labeling) |
| SEC3-F-AC-02: synthetic results treated as synthetic in documentation and narratives | W4 (documentation) |
| SEC3-F-AC-03: synthetic results not presented as production or regulated evidence | W3 (fail-fast), W2 (labeling) |
| SEC3-F-AC-04: ambiguous flows tracked explicitly until enforcement is complete | W5 (deviation tracking) |

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Legacy artifacts lack classification labels | Audit evidence may be uninterpretable | W5 migration path with manual review; automated relabeling where unambiguous |
| Contributors create unclassified storage targets | New flows bypass the boundary | W3 fail-fast checks reject unclassified URIs |
| Mixed-classification evidence packs exported accidentally | Synthetic results presented as real evidence | W3 fail-fast on export; W4 documentation guidance |
| Storage flows change bucket/prefix without updating labels | Classification drift | W5 periodic drift checks |

## Progress Summary

| Workstream | Items | Status |
|------------|-------|--------|
| W1: Classification Inventory and Naming Convention | 5/5 | ✅ Complete |
| W2: Artifact Labeling and Delivery-Note Model | 5/5 | ✅ Complete |
| W3: Runtime Validation and Fail-Fast Enforcement | 5/5 (W3-02, W3-03 pre-existing: SEC3-F-P3-02a) | ✅ Complete |
| W4: Documentation and Operator Guidance | 4/4 | ✅ Complete |
| W5: Deviation Tracking and Migration Path | 4/4 | ✅ Complete |

**Total: 23/23 items complete (W3-02, W3-03 pre-existing SEC3-F-P3-02a)**

## Effort Estimate

| Workstream | Complexity | Effort | Remaining |
|------------|------------|--------|-----------|
| W1: Classification Inventory and Naming Convention | Medium | 2-3 days | 0 |
| W2: Artifact Labeling and Delivery-Note Model | Medium | 2-3 days | 0 |
| W3: Runtime Validation and Fail-Fast Enforcement | Medium | 3-5 days | 0 |
| W4: Documentation and Operator Guidance | Low | 1-2 days | 0 |
| W5: Deviation Tracking and Migration Path | Medium | 2-3 days | 0 |
| **Total** | | **10-16 days** | **0** |
