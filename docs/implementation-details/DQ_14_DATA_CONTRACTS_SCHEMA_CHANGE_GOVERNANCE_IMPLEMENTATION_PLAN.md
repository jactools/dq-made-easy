# DQ-14 Data Contracts, Schema-Change Governance, and Conformance Checks Implementation Plan

> **Status:** [x] Complete
> **Current phase:** complete
> **Next step:** none; keep the contract governance surface under routine maintenance.

Related feature note: [../features/DQ_FEATURES.md](../features/DQ_FEATURES.md)

## Goal

Introduce governed data contracts for Data Assets and source datasets so users can define expected structure and compatibility rules, detect breaking schema change before publication or activation, and review conformance failures with explicit diagnostics.

The implementation should keep contract governance in this app while leaving physical data movement, publishing, and downstream operational remediation to the existing platform workflows.

## Principles

- Canonical contract first, runtime checks second.
- Fail fast on missing, invalid, or unsupported contract data.
- No silent compatibility shims for obsolete contract shapes.
- Contract governance must be explicit and reviewable.
- Schema-change diagnostics must distinguish compatible, additive, and breaking changes.

## Scope

In scope:

- [x] `DQ14-I-S-01` Define canonical data contract entities for Data Assets and source datasets.
- [x] `DQ14-I-S-02` Add schema-diff and change-classification logic for governed assets.
- [x] `DQ14-I-S-03` Add contract conformance checks for required fields, types, nullability, and compatibility rules.
- [x] `DQ14-I-S-04` Add approval and notification flows for contract changes inside workspace governance.
- [x] `DQ14-I-S-05` Update APIs, persistence, tests, and documentation to expose contract governance end to end.

Out of scope:

- [x] `DQ14-I-OOS-01` Build a full external schema registry product.
- [x] `DQ14-I-OOS-02` Replace data-platform publishing or orchestration with app-local fallback behavior.
- [x] `DQ14-I-OOS-03` Turn this app into the system of record for remediation execution after a conformance failure.

## Product Decisions

- [x] `DQ14-I-D-01` Use a canonical contract model that can represent the expected schema, business expectations, and version metadata for governed assets.
- [x] `DQ14-I-D-02` Classify schema changes explicitly as additive, compatible, or breaking.
- [x] `DQ14-I-D-03` Treat conformance checks as a validation surface that blocks unsafe activation or publication.
- [x] `DQ14-I-D-04` Keep contract-change approval within workspace governance, with notifications as a side effect of the approval decision.
- [x] `DQ14-I-D-05` Keep the contract API snake_case on the backend and normalize at the UI boundary where needed.

## Implementation Phases

### Phase 1: Define the Canonical Contract Model

- [x] `DQ14-I-P1-01` Define contract entities for Data Assets and source datasets.
- [x] `DQ14-I-P1-02` Define contract version metadata, ownership, status, and effective dates.
- [x] `DQ14-I-P1-03` Define field-level expectations for type, nullability, presence, and compatible values.
- [x] `DQ14-I-P1-04` Define canonical API schemas and persistence shape for contracts.
- [x] `DQ14-I-P1-05` Add validation for incomplete or unsupported contract payloads.

### Phase 2: Add Schema Diff and Change Classification

- [x] `DQ14-I-P2-01` Compare new and existing schemas at field and collection level.
- [x] `DQ14-I-P2-02` Detect added, removed, renamed, type-changed, and nullability-changed fields.
- [x] `DQ14-I-P2-03` Classify diffs into additive, compatible, and breaking categories.
- [x] `DQ14-I-P2-04` Surface diagnostics that explain why a change was classified the way it was.
- [x] `DQ14-I-P2-05` Fail fast when a contract change cannot be analyzed reliably.

### Phase 3: Add Contract Conformance Checks

- [x] `DQ14-I-P3-01` Validate required fields and field presence.
- [x] `DQ14-I-P3-02` Validate field types, nullability, and allowed compatibility rules.
- [x] `DQ14-I-P3-03` Report explicit conformance failures with machine-readable reasons.
- [x] `DQ14-I-P3-04` Track conformance outcomes per contract version and governed asset.
- [x] `DQ14-I-P3-05` Ensure failed conformance never silently resolves to an accepted state.

### Phase 4: Add Governance Workflow and Notifications

- [x] `DQ14-I-P4-01` Add approval states for proposed contract changes.
- [x] `DQ14-I-P4-02` Route contract-change review through workspace governance roles.
- [x] `DQ14-I-P4-03` Emit notification hooks for contract approval, rejection, and blocking conformance failures.
- [x] `DQ14-I-P4-04` Present contract status and breaking-change summary in the UI.
- [x] `DQ14-I-P4-05` Keep approval and notification behavior fail-fast when dependencies are unavailable.

### Phase 5: Verify, Document, and Roll Out

- [x] `DQ14-I-P5-01` Add backend tests for contract creation, diffing, conformance, and approval flow.
- [x] `DQ14-I-P5-02` Add API tests for canonical payloads and explicit failure cases.
- [x] `DQ14-I-P5-03` Update user-facing documentation and feature tracker references.
- [x] `DQ14-I-P5-04` Validate that the new contract surface does not regress existing Data Asset or source-dataset workflows.
- [x] `DQ14-I-P5-05` Confirm the implementation remains aligned with the app's no-fallback policy.

## Acceptance Criteria

- [x] `DQ14-I-AC-01` Users can define and view contracts for governed assets.
- [x] `DQ14-I-AC-02` Schema changes are classified as compatible or breaking with explicit diagnostics.
- [x] `DQ14-I-AC-03` Contract conformance failures are visible before activation or publication.
- [x] `DQ14-I-AC-04` Contract changes can be approved or rejected through workspace governance.
- [x] `DQ14-I-AC-05` Missing or unsupported contract data fails fast instead of being silently accepted.

## Suggested Delivery Order

- [x] `DQ14-I-DO-01` Define the canonical contract model and validation boundaries.
- [x] `DQ14-I-DO-02` Implement schema diff and breaking-change classification.
- [x] `DQ14-I-DO-03` Add conformance checks and explicit diagnostics.
- [x] `DQ14-I-DO-04` Add governance approval and notification hooks.
- [x] `DQ14-I-DO-05` Close the loop with tests and documentation.
