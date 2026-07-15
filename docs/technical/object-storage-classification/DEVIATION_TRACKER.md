# Deviation Tracker: Synthetic/Test Object Storage Boundaries

**Document ID**: DQ-OBJ-DEV-001  
**Version**: 1.0  
**Date**: 2026-07-15  
**Owner**: Data Governance + Engineering  
**Related**: [SEC-3 Implementation Plan](../../implementation-details/SEC_3_SYNTHETIC_TEST_BUCKET_AND_EVIDENCE_BOUNDARIES_IMPLEMENTATION_PLAN.md), [ARCH-EXC-0008](../../architecture/deviations/ARCH-EXC-0008-synthetic-test-object-storage-boundaries-are-not-yet-enforced.md)  
**Fulfills**: SEC3-F-P3-03, SEC3-I-W1-05, SEC3-I-W5-01, SEC3-I-W5-02, SEC3-I-W5-03, SEC3-I-W5-04

## 1. Active Deviations

| ID | Flow | Classification Issue | Risk | Owner | Target Closure | Status |
|----|------|---------------------|------|-------|----------------|--------|
| DEV-001 | DQ exception persistence | Same bucket (`dq-gx-exceptions`) used for synthetic and real-data runs | High — synthetic exceptions could be presented as real evidence | Engineering | 2026-10-31 | Open |
| DEV-002 | Local CSV staging | No delivery-note labels; classification inferred from bucket name only | Low — script is manual and outputs are not consumed as evidence | Engineering | 2026-09-30 | Open |
| DEV-003 | Delivery output bucket | Unconfigured; intended classification (`real_evidence`) not yet wired | Low — flow is inactive | Engineering | TBD | Open |

## 2. Deviation Details

### DEV-001: DQ Exception Persistence Classification Ambiguity

**Flow**: `dq-api/fastapi/app/application/services/exception_storage.py` + `dq-engine/gx_dispatch_runtime.py`  
**Current behavior**: All DQ exception outputs write to `dq-gx-exceptions/gx-exceptions` regardless of whether the execution run used test data or real source data.  
**Impact**: Downstream consumers (Kafka consumer, evidence packs) cannot distinguish synthetic exceptions from real exceptions by storage location alone.  
**Compensating control**: The `dq-gx-exceptions` bucket name does not match the `real_evidence` naming pattern (`dq-evidence-*`), so the classification is technically ambiguous rather than explicitly `real_evidence`. This reduces the risk of accidental misinterpretation, but does not eliminate it.  
**Resolution options**:
1. Split into two buckets: `dq-evidence-default` (real) and `dq-test-data` or `dq-landing-zone-*` (synthetic).
2. Keep one bucket but add classification labels to exception persistence metadata.
3. Add a runtime classification check that rejects real-data runs writing to synthetic buckets and vice versa.  
**Preferred resolution**: Option 1 — split into two buckets aligned with naming conventions.

### DEV-002: Local CSV Staging Lacks Delivery-Note Labels

**Flow**: `scripts/stage_local_csv_to_s3_parquet.py`  
**Current behavior**: Script writes Parquet to S3 but does not create a delivery note. Classification is inferred from the bucket name (`dq-landing-zone-*`).  
**Impact**: If the staged data is later consumed by a reporting or evidence flow, the classification label is not available in a structured artifact.  
**Compensating control**: The bucket naming convention makes the classification reviewable from the URI. The script is manual and not part of automated evidence flows.  
**Resolution**: Add a delivery-note creation step to the script, or document that the script output must be classified explicitly before it enters any evidence flow.

### DEV-003: Delivery Output Bucket Unconfigured

**Flow**: `DQ_DELIVERY_OUTPUT_BUCKET` in `.env.dev.example`  
**Current behavior**: Variable is empty; no flow writes to this bucket yet.  
**Impact**: None — flow is inactive.  
**Resolution**: When the delivery output flow is activated, configure the bucket to match the `real_evidence` naming pattern (`dq-delivery-*`).

## 3. Retired Deviations

(None yet.)

## 4. Drift Check Procedure

To check for classification drift:

1. Review all AIStor bucket names against the naming convention in [Bucket and Prefix Naming Conventions](./BUCKET_PREFIX_NAMING_CONVENTIONS.md).
2. Review all delivery notes for `object_storage_classification` and `evidence_classification` values.
3. Flag any delivery note whose classification does not match the bucket/prefix naming pattern.
4. Record new deviations in this document.
5. Update the [Flow Inventory](./FLOW_INVENTORY.md) with any new flows.

## 5. Progress Against Acceptance Criteria

| Criterion | Status | Notes |
|-----------|--------|-------|
| SEC3-F-AC-01: flows classifiable as `synthetic_test` or `real_evidence` | ⚠️ Partial | Naming convention defined; most flows classified; DQ exceptions ambiguous (DEV-001) |
| SEC3-F-AC-02: synthetic results treated as synthetic in documentation | ✅ Complete | Operator guidance, test materialization labels, exception report exports carry classification |
| SEC3-F-AC-03: synthetic results not presented as production evidence | ⚠️ Partial | One fail-fast check active (SEC3-F-P3-02a); broader enforcement pending |
| SEC3-F-AC-04: ambiguous flows tracked explicitly | ✅ Complete | DEV-001, DEV-002, DEV-003 recorded |
