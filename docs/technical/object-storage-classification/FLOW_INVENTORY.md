# Object-Storage Flow Inventory and Classification

**Document ID**: DQ-OBJ-INV-001  
**Version**: 1.0  
**Date**: 2026-07-15  
**Owner**: Data Governance + Engineering  
**Related**: [SEC-3 Implementation Plan](../../implementation-details/SEC_3_SYNTHETIC_TEST_BUCKET_AND_EVIDENCE_BOUNDARIES_IMPLEMENTATION_PLAN.md)  
**Fulfills**: SEC3-F-P1-02, SEC3-F-P1-03, SEC3-I-W1-03, SEC3-I-W1-04, SEC3-I-W1-05

## 1. Inventory Methodology

Each flow is classified by answering: does this flow produce synthetic/test data or real/evidence data? The classification is based on the source of the data and the intended interpretation of the output, not on the execution path or schema.

| Flow | Classification | Rationale |
|------|----------------|-----------|
| Test data materialization | `synthetic_test` | Generates mock data from schema attributes |
| Local CSV staging | `synthetic_test` | Local CSV data staged into S3; no real-data provenance |
| DQ exception persistence (source-data runs) | `real_evidence` | Exception evidence from production-aligned execution |
| DQ exception persistence (test-data runs) | `synthetic_test` | Exception evidence from synthetic data runs |
| Delivery output bucket | `real_evidence` (pending) | Intended for production delivery; currently unpopulated |
| Preview/validation staging | `synthetic_test` | Preview outputs not intended as production evidence |
| Demo data generation | `synthetic_test` | Demonstration and onboarding data |

## 2. Flow Details

### 2.1 Test Data Materialization (SEC3-I-W1-03a)

| Attribute | Value |
|-----------|-------|
| Classification | `synthetic_test` |
| Bucket pattern | `dq-test-data` |
| Key prefix pattern | `data_object_version_id=.../attr_hash=.../sample_count=.../format=...` |
| Env var | `DQ_TEST_DATA_OUTPUT_PREFIX` (default: `s3a://dq-test-data`) |
| Config location | `.env.dev.example` (line 356), `dq-engine/test_data_materialization_worker.py` |
| Delivery-note labels | `object_storage_classification: synthetic_test`, `evidence_classification: synthetic_result` |
| Enforcement | `ensure_synthetic_test_output_uri()` rejects evidence-style URI terms |
| Status | ✅ Classified, labels populated, one fail-fast check active |

### 2.2 Local CSV Staging (SEC3-I-W1-03b)

| Attribute | Value |
|-----------|-------|
| Classification | `synthetic_test` |
| Bucket pattern | `dq-landing-zone-*` (prefix: `dq-landing-zone-`) |
| Key prefix pattern | `gx/join-pairs/local-csv-staging/case_id=.../role=.../version_id=.../format=parquet` |
| Script | `scripts/stage_local_csv_to_s3_parquet.py` |
| Delivery-note labels | Not populated (no delivery note created by this script) |
| Enforcement | None |
| Status | ⚠️ Classified by bucket pattern; no delivery-note labels, no enforcement |

### 2.3 DQ Exception Persistence (SEC3-I-W1-03c)

| Attribute | Value |
|-----------|-------|
| Classification | **Mixed** — depends on the execution run |
| Bucket pattern | `dq-gx-exceptions` (configurable via `GX_EXCEPTION_STORAGE_BUCKET`) |
| Key prefix pattern | `gx-exceptions/...` |
| Env vars | `GX_EXCEPTION_STORAGE_BUCKET`, `GX_EXCEPTION_STORAGE_ENDPOINT`, `GX_EXCEPTION_STORAGE_PREFIX` |
| Config location | `.env.dev.example` (lines 369-374) |
| Service | `dq-api/fastapi/app/application/services/exception_storage.py` |
| Delivery-note labels | Not populated (exception storage does not create delivery notes) |
| Enforcement | None |
| Status | ⚠️ **Ambiguous** — same bucket used for synthetic and real-data runs |

This flow is the primary source of classification ambiguity. When DQ rules run against test data, the exception output is synthetic. When they run against real source data, the exception output is evidence. The current bucket and prefix (`dq-gx-exceptions/gx-exceptions`) do not distinguish these cases.

**Deviation recorded**: [ARCH-EXC-0008](../../architecture/deviations/ARCH-EXC-0008-synthetic-test-object-storage-boundaries-are-not-yet-enforced.md)

### 2.4 Delivery Output Bucket (SEC3-I-W1-03d)

| Attribute | Value |
|-----------|-------|
| Classification | `real_evidence` (intended) |
| Bucket pattern | Unconfigured (empty in `.env.dev.example`) |
| Env var | `DQ_DELIVERY_OUTPUT_BUCKET` |
| Config location | `.env.dev.example` (line 363) |
| Service | Not yet wired into a production flow |
| Delivery-note labels | N/A (flow not active) |
| Enforcement | N/A (flow not active) |
| Status | 🔲 Unconfigured — classification intended as `real_evidence` when activated |

### 2.5 AIStor as the Storage Backend (SEC3-I-W1-03e)

| Attribute | Value |
|-----------|-------|
| Storage system | AIStor (S3-compatible) |
| Endpoint | `https://aistor:9000` (configurable) |
| Auth | `AISTOR_ROOT_USER` / `AISTOR_ROOT_PASSWORD` |
| Bucket creation | Auto-created by `test_data_materialization_worker` via `_ensure_bucket_exists()` |
| Classification awareness | None — AIStor treats all buckets equally |

AIStor itself does not enforce classification boundaries. Classification is enforced by repository conventions, validation, and fail-fast checks on the producer side.

## 3. Flows That Produce Synthetic Results Mimicking Production Paths (SEC3-F-P1-03)

The following flows produce `synthetic_test` results but use execution paths, schemas, or surrounding workflows that resemble production scenarios:

| Flow | Why it mimics production | Classification |
|------|--------------------------|----------------|
| Test data materialization | Uses Spark, writes Parquet/Delta, creates delivery notes, reports completion via API | `synthetic_test` |
| DQ exception persistence (test-data runs) | Uses the same DQ rules, same exception schema, same Kafka consumer pipeline | `synthetic_test` |
| Local CSV staging | Writes Parquet to S3 with the same Spark session and S3 credentials | `synthetic_test` |

These flows are explicitly classified as `synthetic_test` despite their production-like execution paths. The classification is based on data provenance (generated or locally staged), not execution resemblance.

## 4. Mixed or Ambiguous Flows (SEC3-F-P1-03, SEC3-I-W1-05)

| Flow | Ambiguity | Resolution Path | Deviation |
|------|-----------|-----------------|-----------|
| DQ exception persistence | Same bucket for synthetic and real runs | Split into `dq-evidence-default` (real) and `dq-test-data` or new prefix (synthetic) | ARCH-EXC-0008 |

## 5. Open Questions

1. Should DQ exception persistence for test-data runs write to a separate bucket, or use a synthetic prefix within the same bucket?
2. Should the delivery output bucket be activated now or deferred until a real-data execution path exists?
3. Should classification labels be required on all delivery notes, or only where interpretation depends on it?
