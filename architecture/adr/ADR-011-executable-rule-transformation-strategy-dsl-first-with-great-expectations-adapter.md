# ADR-011: Executable Rule Transformation Strategy (DSL-First with Great Expectations Adapter)

**Status**: Accepted
**Date**: 2026-03-11

### Context
Rule scheduling (`WF-1`) requires rules to be transformed from stored expressions into executable checks. Today, rules are validated and composed, but there is no deterministic compile-and-run layer that guarantees runtime execution semantics across environments.

Two implementation paths were under consideration:
1. Build an internal DSL execution model end-to-end.
2. Adopt Great Expectations (GE) as the primary runtime.

Each path has tradeoffs:
- Internal DSL gives tight control and alignment with existing SQL-like rule expressions.
- GE provides mature expectation execution and reporting patterns, but requires mapping and may not cover all custom semantics directly.

### Decision
Adopt a **DSL-first architecture with an optional Great Expectations adapter** (hybrid).

Execution flow:
1. Parse and normalize rule expressions into a canonical intermediate model (AST/IR).
2. Compile canonical model into executable artifacts for the default engine runtime.
3. Optionally translate canonical model into GE expectations through an adapter for compatible rule types.

### Rationale
- Preserves full compatibility with current expression syntax and join/filter composition rules.
- Avoids hard lock-in to one execution framework.
- Creates a single normalization layer that can feed multiple runtimes.
- Enables incremental adoption of GE where it adds value (reporting, expectation semantics) without blocking unsupported constructs.

### Scope Boundaries
- The canonical model is the source of truth for compile diagnostics and execution traceability.
- GE adapter is best-effort by rule type and operator support matrix.
- Unsupported GE mappings fall back to default DSL runtime execution path.

### Consequences
**Positive**:
- Clear prerequisite path for `WF-1` scheduling.
- Deterministic compile step before activation/execution.
- Stronger observability through compile/runtime diagnostics tied to rule versions.
- Future portability to additional runtimes without rewriting parsing logic.

**Negative**:
- Requires upfront work to define and maintain canonical grammar/IR.
- Dual runtime support introduces adapter maintenance overhead.
- GE parity testing is required to prevent semantic drift.

### Implementation Guidance
- Start with `DQ-7.2` to define supported grammar and normalization rules.
- Gate activation on compile success for selected rule statuses/environments.
- Add per-rule execution provenance: source expression hash, compiler version, runtime backend.
- Maintain a compatibility matrix documenting which rule patterns can execute via GE adapter.

### Status Mapping to Plan
- This ADR fulfills `DQ-7.1` in `docs/features/DQ_FEATURES.md`.

---

