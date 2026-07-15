# Object-Storage Bucket and Prefix Naming Conventions

**Document ID**: DQ-OBJ-NAME-001  
**Version**: 1.0  
**Date**: 2026-07-15  
**Owner**: Data Governance + Engineering  
**Related**: [ADR-031](../../architecture/adr/ADR-031-synthetic-test-object-storage-buckets-and-synthetic-evidence-boundaries.md), [DQ-OBJ-SYN-001](../OBJECT_STORAGE_SYNTHETIC_BUCKET_AND_SYNTHETIC_EVIDENCE_REQUIREMENTS.md), [SEC-3 Feature](../../features/SEC_3_SYNTHETIC_TEST_BUCKET_AND_EVIDENCE_BOUNDARIES.md), [SEC-3 Implementation Plan](../../implementation-details/SEC_3_SYNTHETIC_TEST_BUCKET_AND_EVIDENCE_BOUNDARIES_IMPLEMENTATION_PLAN.md)  
**Fulfills**: SEC3-F-P1-01, SEC3-I-W1-01, SEC3-I-W1-02

## 1. Purpose

Define the canonical bucket and prefix patterns that operators, automation, and contributors must follow when creating new object-storage targets. These patterns make the `synthetic_test` versus `real_evidence` classification reviewable from the URI alone.

## 2. Classification Values

Every repository-managed object-storage location is classified as one of two values:

| Value | Meaning |
|-------|---------|
| `synthetic_test` | Generated data, mock data, preview materializations, fixture-derived data, test-run outputs. Never the source of production-grade evidence. |
| `real_evidence` | Operational evidence, exception evidence, source-data-aligned artifacts, regulated-reporting support. Produced by execution paths against real data. |

## 3. Bucket Naming Rules

### 3.1 Synthetic/Test Buckets

Synthetic/test buckets MUST use one of the following prefix patterns:

| Pattern | Use Case | Example |
|---------|----------|---------|
| `dq-test-data` | General test data materialization outputs | `dq-test-data` |
| `dq-landing-zone-*` | CSV staging, join-pair staging, local-to-S3 staging | `dq-landing-zone-workspace123` |
| `dq-preview-*` | Preview materializations and validation staging | `dq-preview-finance-q4` |
| `dq-demo-*` | Demonstration data and engineering verification | `dq-demo-onboarding` |

Rules:
- Bucket names MUST begin with `dq-test-data`, `dq-landing-zone`, `dq-preview`, or `dq-demo`.
- Bucket names MUST be lowercase, hyphen-separated, and S3-compatible.
- Bucket names MUST NOT contain the terms `evidence`, `reporting`, `regulatory`, `compliance`, `production`, or `operational`.
- Bucket names SHOULD include a workspace, environment, or project suffix where the bucket supports multiple tenants.

### 3.2 Real/Evidence Buckets

Real/evidence buckets MUST use one of the following prefix patterns:

| Pattern | Use Case | Example |
|---------|----------|---------|
| `dq-evidence-*` | Exception evidence, operational evidence | `dq-evidence-default` |
| `dq-reporting-*` | Regulated reporting support | `dq-reporting-bcbs239` |
| `dq-source-*` | Source-data-aligned execution artifacts | `dq-source-teller-machine` |
| `dq-delivery-*` | Production delivery outputs | `dq-delivery-finance` |

Rules:
- Bucket names MUST begin with `dq-evidence`, `dq-reporting`, `dq-source`, or `dq-delivery`.
- Bucket names MUST be lowercase, hyphen-separated, and S3-compatible.
- Bucket names MUST NOT contain the terms `test`, `synthetic`, `preview`, `demo`, `mock`, or `fixture`.
- Bucket names SHOULD include a domain, workspace, or environment suffix.

## 4. Key Prefix (Path) Rules

Key prefixes within buckets MUST follow these conventions:

### 4.1 Synthetic/Test Key Prefixes

| Pattern | Use Case |
|---------|----------|
| `test-materialization/` | Test data materialization outputs |
| `staging/` or `landing-zone/` | CSV or local-to-S3 staging |
| `preview/` | Preview materializations |
| `demo/` | Demonstration data |
| `gx/join-pairs/local-csv-staging/` | GX join-pair local CSV staging |

### 4.2 Real/Evidence Key Prefixes

| Pattern | Use Case |
|---------|----------|
| `gx-exceptions/` | DQ exception evidence (source-data-aligned runs only) |
| `evidence/` | Operational evidence artifacts |
| `reporting/` | Regulated reporting artifacts |
| `delivery/` | Production delivery outputs |

### 4.3 Prohibited Key Prefixes

Key prefixes in `synthetic_test` buckets MUST NOT use the following terms, as they conflict with real/evidence semantics:
- `evidence`, `reporting`, `regulatory`, `compliance`, `production`, `operational`

Key prefixes in `real_evidence` buckets MUST NOT use:
- `test`, `synthetic`, `preview`, `demo`, `mock`, `fixture`

## 5. URI Examples

### Synthetic/Test URIs

```
s3a://dq-test-data/data_object_version_id=abc123/format=parquet
s3a://dq-landing-zone-workspace123/gx/join-pairs/local-csv-staging/case_id=xyz/role=customer/version_id=abc/format=parquet
s3a://dq-preview-finance/preview/data_object_version_id=def456/format=parquet
s3a://dq-demo-onboarding/demo/sample_data/format=parquet
```

### Real/Evidence URIs

```
s3a://dq-evidence-default/gx-exceptions/execution_run_id=run123/format=parquet
s3a://dq-reporting-bcbs239/reporting/quarterly/bcbs239-report-2026-q1.parquet
s3a://dq-source-teller-machine/source/execution/artifacts/format=parquet
s3a://dq-delivery-finance/delivery/data_object_version_id=ghi789/format=parquet
```

## 6. Determining Classification from a URI

To classify an existing URI:

1. Parse the bucket name from the URI.
2. If the bucket matches a `synthetic_test` pattern (section 3.1), the classification is `synthetic_test`.
3. If the bucket matches a `real_evidence` pattern (section 3.2), the classification is `real_evidence`.
4. If the bucket does not match any pattern, treat the URI as **unclassified** and record a deviation.
5. Key prefixes provide secondary confirmation but are not the primary classification signal.

## 7. Environment Handling

These naming conventions apply across all environments (dev, test, prod). Environment-specific suffixes are encouraged:

```
dq-test-data-dev
dq-evidence-default-test
dq-reporting-bcbs239-prod
```

## 8. Migration Notes

Existing buckets that do not follow these conventions must be tracked as deviations until migrated. The bucket naming convention is enforced for all new storage targets created after this document's effective date.
