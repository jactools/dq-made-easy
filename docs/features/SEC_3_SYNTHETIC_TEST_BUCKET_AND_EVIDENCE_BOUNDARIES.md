# SEC-3 Synthetic/Test Bucket and Evidence Boundaries

Goal: enforce a repository-managed separation between synthetic/test object-storage locations and real/evidence object-storage locations, and ensure that evidence derived from synthetic/test storage is interpreted as synthetic results.

Related architecture: [ADR-031 Synthetic/Test Object Storage Buckets and Synthetic Evidence Boundaries](../../architecture/adr/ADR-031-synthetic-test-object-storage-buckets-and-synthetic-evidence-boundaries.md)

Related requirement: [Object Storage Synthetic/Test Bucket and Synthetic Evidence Requirements](../technical/OBJECT_STORAGE_SYNTHETIC_BUCKET_AND_SYNTHETIC_EVIDENCE_REQUIREMENTS.md)

## Phase 1: Classification Baseline

- [x] (SEC3-F-P1-01) Define the repository naming or prefix convention for `synthetic_test` versus `real_evidence` object-storage locations. ([Bucket and Prefix Naming Conventions](../technical/object-storage-classification/BUCKET_PREFIX_NAMING_CONVENTIONS.md))
- [x] (SEC3-F-P1-02) Identify current AIStor or other S3-compatible flows that must be classified under the new boundary. ([Flow Inventory](../technical/object-storage-classification/FLOW_INVENTORY.md))
- [x] (SEC3-F-P1-03) Document which existing flows produce synthetic results even when they mimic production-like execution paths. ([Flow Inventory §3](../technical/object-storage-classification/FLOW_INVENTORY.md#3-flows-that-produce-synthetic-results-mimicking-production-paths-sec3-f-p1-03))

## Phase 2: Artifact Semantics

- [x] (SEC3-F-P2-01) Ensure delivery notes or related result artifacts can indicate synthetic/test versus real/evidence interpretation where relevant. ([DataDeliveryNoteEntity](../../dq-api/fastapi/app/domain/entities/data_catalog.py))
- [x] (SEC3-F-P2-01a) Expose explicit delivery-note labels such as `object_storage_classification` and `evidence_classification` where repository-managed note models exist. ([DataDeliveryNoteView](../../dq-api/fastapi/app/api/v1/schemas/data_catalog_view.py), [DeliveryExceptionSummaryView](../../dq-api/fastapi/app/api/v1/schemas/exception_fact_view.py))
- [x] (SEC3-F-P2-02) Ensure evidence packs and reporting-oriented artifacts carry the classification label through to their exported output so the label survives format conversion. ([exception_reports exports](../../dq-api/fastapi/app/api/v1/endpoints/exception_reports.py))
- [x] (SEC3-F-P2-03) Add documentation guidance that synthetic/test bucket outputs must be described as synthetic results. ([OPERATOR_GUIDANCE.md](../technical/object-storage-classification/OPERATOR_GUIDANCE.md))

## Phase 3: Validation and Enforcement

- [ ] (SEC3-F-P3-01) Add validation or linting that checks documented bucket or prefix usage against the classification rule where practical.
- [ ] (SEC3-F-P3-02) Add fail-fast checks for flows that attempt to represent synthetic/test storage outputs as real/evidence outputs without explicit handling.
- [x] (SEC3-F-P3-02a) Reject test-data materialization request and completion flows when `output_uri` uses explicit evidence/reporting-style namespace terms for synthetic/test outputs.
- [ ] (SEC3-F-P3-03) Record any remaining mixed or ambiguous storage flows as explicit deviations.

## Acceptance Criteria

- [ ] (SEC3-F-AC-01) Repository-managed object-storage flows are classifiable as `synthetic_test` or `real_evidence`. (⚠️ Partial — naming convention defined, most flows classified, DQ exceptions ambiguous)
- [x] (SEC3-F-AC-02) Results from synthetic/test buckets are explicitly treated as synthetic results in repository documentation and evidence narratives. (operator guidance, test materialization labels, exception report exports)
- [ ] (SEC3-F-AC-03) Synthetic/test bucket results are not presented as production-grade or regulated reporting evidence. (⚠️ Partial — one fail-fast check active)
- [x] (SEC3-F-AC-04) Remaining ambiguous flows are tracked explicitly until enforcement is complete. ([Deviation Tracker](../technical/object-storage-classification/DEVIATION_TRACKER.md))