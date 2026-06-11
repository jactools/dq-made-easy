# DQ-7 Executable Rule Transformation

Status: Complete

Goal: transform stored rule expressions into executable artifacts and route activated GX runs through a traceable adapter/runtime boundary.

Current status: DQ-7 is complete. The compiler produces a normalized intermediate model and deterministic artifact mapping, activation validates that compiled snapshots are runnable before scheduling, and the GX adapter/runtime path supports retrieval, execution handoff, persistence separation, and traceable execution results.

## Why this exists

DQ-7 is the bridge between authored rules and runtime execution. The feature needed a compiler, a validation gate, and an execution adapter so activation does not schedule a rule that cannot be executed and runtime output can be traced back to the source rule and version.

## Scope

### In scope

- Compile stored rule expressions into an intermediate executable model
- Preserve deterministic artifact mapping for rule/version/expression combinations
- Validate runnable GX snapshots before activation
- Route activated runs through the GX adapter and grouped execution path
- Persist traceability fields for execution handoff and downstream monitoring

### Out of scope

- Adding unsupported expression constructs to the grammar
- Introducing silent fallback behavior when compilation or activation fails
- Broadening the runtime to non-GX multi-source adapters beyond the current documented contract

## User-facing outcome

Users can validate and activate rules with predictable runtime behavior, and execution results remain traceable back to the source rule version, compiled artifact, and activation handoff. Failed validation blocks activation early with actionable diagnostics rather than allowing an invalid rule to proceed.

## Tracked Work Items

- [x] `DQ-7.DC-01` Define execution target approach: internal DSL runtime, Great Expectations integration, or hybrid
- [x] `DQ-7.DC-02` Document supported expression subset and unsupported constructs
- [x] `DQ-7.DC-03` Define normalization rules so filter/join expressions compile consistently
- [x] `DQ-7.ARC-01` Build a rule compiler stage: rule expression -> normalized AST/intermediate model -> executable artifact
- [x] `DQ-7.ARC-02` Add adapter layer for Great Expectations expectations when GE mode is used
- [x] `DQ-7.ARC-03` Add deterministic mapping from rule IDs/versions to executable artifacts
- [x] `DQ-7.ARC-04` Add validation gate that fails activation when rule cannot be compiled
- [x] `DQ-7.OB-01` Add execution result schema with pass/fail, failure count, and sample failures
- [x] `DQ-7.OB-02` Add compile/runtime diagnostics for unsupported functions/operators
- [x] `DQ-7.OB-03` Add traceability fields linking execution output back to rule version and source expression
- [x] `DQ-7.OB-04` Add test harness for compilation and execution regression cases
- [x] `DQ-7.DT-01` DSL vs Great Expectations architecture decision record
- [x] `DQ-7.DT-02` Expression normalization and supported-grammar specification
- [x] `DQ-7.DT-03` Rule compiler to intermediate executable model
- [x] `DQ-7.DT-04` Great Expectations adapter
- [x] `DQ-7.DT-05` Compile-time diagnostics surfaced in API/UI
- [x] `DQ-7.DT-06` Execution result contract and traceability fields
- [x] `DQ-7.DT-07` Regression suite for compile and runtime behavior

## Acceptance Criteria

- [x] A rule can be compiled into executable checks before scheduling
- [x] Compilation failures produce actionable diagnostics in UI/API
- [x] Execution output is version-aware and traceable to source rule expression
- [x] Both simple predicates and regex-like validations are executable through the chosen runtime
- [x] Invalid runnable snapshots are rejected before activation

## Related References

- [DQ feature rollup](../features/DQ_FEATURES.md)
- [Rule DSL contract](../features/DQ-7_RULE_DSL_CONTRACT.md)
- [DQ-1 Rule Validation User Guide](../user-manuals/DQ-1_RULE_VALIDATION_USER_GUIDE.md)
- [DQ-2 Join Conditions User Guide](../user-manuals/DQ-2_JOIN_CONDITIONS_USER_GUIDE.md)
- [Compiler implementation progress](../implementation-details/DQ_7_3_RULE_COMPILER_IMPLEMENTATION_PROGRESS.md)
- [GX orchestration implementation details](../implementation-details/DQ_7_4_GX_SUITE_ORCHESTRATION_IMPLEMENTATION_DETAILS.md)
- [Activation use cases](../../dq-api/fastapi/app/application/use_cases/gx_run_plans.py)