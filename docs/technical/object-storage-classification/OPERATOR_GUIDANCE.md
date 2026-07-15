# Operator Guidance: Synthetic/Test Bucket and Evidence Boundaries

**Document ID**: DQ-OBJ-OPS-001  
**Version**: 1.0  
**Date**: 2026-07-15  
**Owner**: Data Governance + Engineering  
**Related**: [SEC-3 Implementation Plan](../../implementation-details/SEC_3_SYNTHETIC_TEST_BUCKET_AND_EVIDENCE_BOUNDARIES_IMPLEMENTATION_PLAN.md)  
**Fulfills**: SEC3-F-P2-03, SEC3-I-W4-01, SEC3-I-W4-02, SEC3-I-W4-04

## 1. Classifying a New Storage Target

When creating a new AIStor or S3-compatible storage target, determine its classification first:

### Decision Tree

1. **Will the output be presented as evidence in audits, reports, or compliance narratives?**
   - Yes → `real_evidence`
   - No → Go to step 2

2. **Is the data generated, mocked, previewed, or staged from local files?**
   - Yes → `synthetic_test`
   - No → Go to step 3

3. **Is the data produced by execution against real source data?**
   - Yes → `real_evidence`
   - No → `synthetic_test` (default)

### Naming the Bucket

Follow the patterns in [Bucket and Prefix Naming Conventions](./BUCKET_PREFIX_NAMING_CONVENTIONS.md):

- **Synthetic/test**: `dq-test-data`, `dq-landing-zone-*`, `dq-preview-*`, `dq-demo-*`
- **Real/evidence**: `dq-evidence-*`, `dq-reporting-*`, `dq-source-*`, `dq-delivery-*`

### Populating the Delivery Note

When the flow creates a delivery note, set:

| Field | Synthetic/Test | Real/Evidence |
|-------|----------------|---------------|
| `object_storage_classification` | `synthetic_test` | `real_evidence` |
| `evidence_classification` | `synthetic_result` | `real_evidence` |

These fields are already part of the `DataDeliveryNoteEntity` and are populated automatically for test-data materialization flows. For other flows, ensure the service that creates the delivery note sets these fields explicitly.

## 2. Resolving Ambiguous Flows

When a flow can produce both synthetic and real outputs (e.g., DQ exception persistence):

1. **Check the execution run type.** If the run executed against test data, classify as `synthetic_test`. If against real source data, classify as `real_evidence`.
2. **Use separate storage targets.** The preferred approach is to write synthetic outputs to a synthetic/test bucket and real outputs to a real/evidence bucket.
3. **Label the delivery note.** If separate buckets are not possible, the delivery note must carry the correct classification label.
4. **Record a deviation.** If the flow cannot be split or labeled at this time, record the ambiguity in the architecture deviation register.

## 3. Handling Classification Drift

If a bucket or prefix changes its intended classification:

1. **Update the naming.** Rename or recreate the bucket to match the new classification pattern.
2. **Update the delivery-note labels.** Ensure new outputs carry the correct labels.
3. **Migrate existing data.** Move or relabel existing artifacts where the old label would mislead interpretation.
4. **Retire the deviation.** If the drift was tracked as a deviation, close the deviation entry.

## 4. Developer Guidance for New Storage Usage

When adding new AIStor or S3-compatible storage usage:

1. **Classify before you code.** Decide `synthetic_test` or `real_evidence` and name the bucket/prefix accordingly.
2. **Use the naming convention.** Follow [Bucket and Prefix Naming Conventions](./BUCKET_PREFIX_NAMING_CONVENTIONS.md).
3. **Set delivery-note labels.** Ensure `object_storage_classification` and `evidence_classification` are populated.
4. **Add validation.** If the flow produces synthetic data, add a fail-fast check that rejects evidence-style URI terms.
5. **Document the flow.** Update the [Flow Inventory](./FLOW_INVENTORY.md) with the new entry.

## 5. Evidence Narrative Guidance

When writing evidence narratives, audit responses, or compliance documentation:

- **Synthetic results MUST be described as synthetic results.** Use terms like "generated test data", "synthetic materialization", or "preview output".
- **Synthetic results MUST NOT be described as production evidence, real-data validation, or regulated reporting evidence.**
- **Real/evidence results SHOULD reference the bucket and prefix** to make the classification traceable.
- **Mixed-classification artifacts SHOULD state the classification explicitly** and note any limitations on interpretation.
