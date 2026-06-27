# DQ-19 Implementation Plan: Trino, Polars, and Dask/Dask-SQL Lowerers

Status: Proposed

## Objective

Introduce a future-ready multi-runtime lowerer architecture for the DQ Engine so canonical rule payloads can be projected to Trino, Polars, and Dask/Dask-SQL without changing the stored rule model.

## Guiding principles

- Keep the canonical rule model unchanged.
- Make runtime support explicit and capability-driven.
- Prefer fail-fast behavior for unsupported semantics.
- Reuse the neutral artifact and execution abstraction seams already established by the engine work.
- Keep Spark/GX as the default path until the new lowerers are validated.

## Phase 0 — Architecture baseline

### Goal

Prepare the compiler and adapter boundary for additional runtimes.

### Deliverables

- Define a shared lowerer interface in the DQ Engine package.
- Add a capability registry that reports supported rule families per engine.
- Introduce an engine-specific adapter registry keyed by `engine_type`.
- Add a neutral artifact contract mapping from canonical rules to runtime-specific native payloads.

### Acceptance criteria

- The compiler can resolve which adapter handles a requested engine.
- Unsupported engines fail fast with actionable errors.
- The neutral artifact envelope can represent native engine payloads for multiple runtimes.

## Phase 1 — Trino lowerer

### Goal

Enable lowering of canonical DQ rules to Trino SQL for distributed SQL execution.

### Scope

- Row-level checks such as not_null, equals, not_equal, between, in, not_in.
- Aggregate checks such as count, sum, avg, min, max.
- Simple SQL predicates and filter conditions.
- Basic query-based validation patterns where a scalar result is expected.

### Deliverables

- Add a `trino` adapter module under `dq-engine`.
- Implement a lowerer that emits Trino-native SQL or a structured SQL plan.
- Add execution wrapper for Trino-backed validation.
- Add regression tests for supported constructs and unsupported constructs.

### Risks and mitigations

- Risk: dialect differences in SQL semantics.
- Mitigation: start with a narrow, well-tested subset and document unsupported constructs explicitly.

## Phase 2 — Polars lowerer

### Goal

Enable lowering of canonical DQ rules to Polars expressions for dataframe-native execution.

### Scope

- Row-level checks over columns and expressions.
- Aggregate checks such as count, sum, avg, min, max.
- Lightweight validation flows suitable for local or notebook-based use.

### Deliverables

- Add a `polars` adapter module under `dq-engine`.
- Implement lowering to Polars expressions, lazy dataframe operations, and validation plans.
- Add support for simple failure reporting and error summary output.
- Add regression tests for supported constructs.

### Risks and mitigations

- Risk: Polars semantics differ from Spark for some expressions.
- Mitigation: keep the initial supported set conservative and ensure parity tests for the shared rule families.

## Phase 3 — Dask and Dask-SQL lowerer

### Goal

Support distributed Python and SQL execution paths using Dask and Dask-SQL.

### Scope

- Dask dataframe execution for row-level and aggregate validators.
- Dask-SQL execution for SQL-shaped validations where a SQL front-end is natural.
- Distributed execution and basic failure aggregation.

### Deliverables

- Add a `dask` adapter module and a `dask_sql` adapter path if needed.
- Implement lowering into Dask dataframe operations or Dask-SQL query plans.
- Add execution and diagnostics support for distributed validation runs.
- Add regression tests for supported and unsupported constructs.

### Risks and mitigations

- Risk: Dask execution environments vary and may not be available in all deployments.
- Mitigation: keep the implementation as an optional runtime with clear dependency management and explicit capability checks.

## Phase 4 — Runtime dispatch and evidence

### Goal

Make each runtime first-class in the execution pipeline.

### Deliverables

- Wire each adapter into the runtime dispatch layer.
- Persist engine-specific artifacts and diagnostics using the existing neutral artifact and run-plan contracts.
- Add engine evidence folders and proof artifacts for each runtime.
- Add logging and tracing for compile, execution, and result persistence.

### Acceptance criteria

- A supported rule can be dispatched to the selected runtime without changing the stored rule definition.
- Runtime-specific evidence is captured and linked to the execution run.
- Unsupported semantics fail fast with explicit diagnostics.

## Phase 5 — Validation and rollout

### Goal

Validate the lowerers in a repeatable way before broad rollout.

### Deliverables

- Add focused regression suites for Trino, Polars, and Dask paths.
- Add integration tests with local or containerized environments where possible.
- Capture proof artifacts under the repo’s test evidence structure.
- Keep the new engines opt-in until stability is demonstrated.

### Acceptance criteria

- At least one supported validation path is proven for each new engine.
- The default Spark/GX path remains unchanged and passes existing regression coverage.

## Recommended implementation order

1. Shared lowerer interface and capability registry.
2. Trino lowerer.
3. Polars lowerer.
4. Dask / Dask-SQL lowerer.
5. Runtime dispatch and evidence integration.
6. Rollout and hardening.

## Non-goals for the first iteration

- Full semantic parity with every Spark construct.
- Automatic runtime fallback.
- Engine-specific authoring syntax.
- Production rollout of all engines at once.

## Open questions

- Should Trino and Dask-SQL use a common SQL-plan abstraction or separate engine-native adapters?
- Should Polars use a lazy-expression path or eager execution first?
- Which rule families should be prioritized for the initial release of each engine?
