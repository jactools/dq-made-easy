# Object Storage Synthetic/Test Bucket and Synthetic Evidence Requirements

**Requirement ID**: DQ-OBJ-SYN-001  
**Version**: 1.0  
**Effective Date**: 2026-04-22  
**Owner**: Data Governance + Engineering + Security  
**Related ADR**: [ADR-031](/docs/architecture/adr/ADR-031-synthetic-test-object-storage-buckets-and-synthetic-evidence-boundaries/)

## 1. Purpose

Define the repository rule that separates synthetic/test object-storage locations from real/evidence object-storage locations, and require that results derived from synthetic/test storage are treated as synthetic results.

## 2. Scope

This requirement applies to repository-managed AIStor or S3-compatible storage usage, including:

- generated test-data materialization,
- delivery-object seeding,
- preview or validation staging,
- exception evidence persistence,
- source-data-aligned execution paths,
- evidence packs, delivery notes, and reporting-oriented artifacts that reference object-storage outputs.

## 3. Requirement Statements

### 3.1 Bucket and Prefix Classification

- Repository-managed object-storage locations MUST be classifiable as either `synthetic_test` or `real_evidence`.
- Synthetic/test buckets or prefixes SHOULD use an explicit naming or prefix convention that makes the classification reviewable.
- Real/evidence buckets or prefixes SHOULD be distinct from synthetic/test buckets or prefixes.

### 3.2 Allowed Uses for Synthetic/Test Storage

- Synthetic/test object-storage locations MAY contain generated data, mock data, preview materializations, fixture-derived data, and test-run outputs.
- Synthetic/test locations MUST NOT be treated as the source of production-grade evidence solely because the workflow path is otherwise realistic.

### 3.3 Evidence Semantics

- Evidence produced from synthetic/test buckets or prefixes MUST be classified as synthetic results.
- Synthetic results MAY support testing, demonstrations, preview workflows, or engineering verification.
- Synthetic results MUST NOT be described as production evidence, real-data validation evidence, or regulated reporting evidence unless the artifact explicitly states the limitation and purpose.

### 3.4 Real/Evidence Storage

- Object-storage artifacts intended to support operational evidence, exception evidence, production narratives, or regulated-reporting support SHOULD use real/evidence storage classification.
- Where a repository flow can operate against both synthetic/test and real/evidence storage, the distinction SHOULD be visible in notes, evidence packs, or result metadata.

### 3.5 Delivery and Evidence Artifacts

- Delivery notes, execution summaries, evidence packs, and similar artifacts SHOULD identify whether the underlying storage location was `synthetic_test` or `real_evidence` when interpretation depends on it.
- Test outputs from synthetic/test object storage SHOULD be labeled so downstream readers do not confuse them with real-data outcomes.
- Where repository-managed delivery-note models are used, they SHOULD expose explicit fields such as `object_storage_classification` and `evidence_classification` so the label is visible in API output and derived evidence artifacts.

### 3.6 Gaps and Exceptions

- Current repository flows that do not enforce or expose this classification MUST be tracked as deviations or implementation gaps.
- Validation or automation that later enforces bucket/prefix rules SHOULD fail fast when a flow attempts to represent synthetic/test storage as real/evidence storage without explicit handling.

## 4. Repository Interpretation Rules

Use the following interpretation rules unless a stricter requirement is defined for a specific feature:

1. Generated test-data materializations default to `synthetic_test` interpretation.
2. Local CSV staging into AIStor or other S3-compatible storage defaults to `synthetic_test` interpretation unless the workflow explicitly states otherwise and is governed accordingly.
3. Evidence from test, preview, or generated-data workflows is synthetic evidence.
4. Exception evidence, source-data-aligned execution inputs, and reporting-evidence flows require explicit classification and must not inherit synthetic semantics accidentally.

## 5. Verification Expectations

Compliance evidence for this requirement SHOULD include:

- documented bucket or prefix naming conventions,
- feature or implementation docs that state storage classification,
- delivery/evidence artifacts that label synthetic results where applicable,
- deviations for flows that currently mix or blur the boundary.

## 6. Current Repository Position

The repository already contains synthetic/test object-storage flows and also uses AIStor or other S3-compatible storage for non-synthetic operational evidence paths.

This requirement establishes the missing interpretation boundary. It does not mean the current repository fully enforces that boundary yet.