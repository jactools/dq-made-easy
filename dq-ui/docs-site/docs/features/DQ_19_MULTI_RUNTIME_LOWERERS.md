# DQ-19 Multi-Runtime Lowerer Expansion for Trino, Polars, and Dask

Status: Proposed

## Goal

Extend the DQ Engine’s compiler and execution abstraction so canonical DQ rules can be lowered to additional execution engines beyond the current Spark-oriented path. The first target engines are:

- Trino for distributed SQL federation and warehouse-style execution
- Polars for lightweight dataframe-native validation in Python workloads
- Dask and Dask-SQL for cluster-backed Python and SQL execution

The work should preserve the current rule authoring model and reuse the existing neutral artifact and execution-seam concepts rather than introducing a parallel rule format.

## Why this feature matters

The current DQ Engine path is strongest for Spark-based and GX-style execution, but modern analytics environments often span multiple execution models:

- Trino is common in federated warehouse workflows and query-engine environments.
- Polars is increasingly used for fast local and batch dataframe validation.
- Dask and Dask-SQL are relevant for Python-native distributed workloads and notebook-driven pipelines.

Supporting these runtimes would make the DQ Engine more portable and allow teams to execute the same canonical DQ rules against the engine that best fits the data platform.

## Scope

### In scope

- A runtime-neutral lowering contract for engine-specific adapters
- A capability matrix so the compiler can declare which rule families each engine supports
- A Trino lowerer for distributed SQL-style predicate and aggregate validation
- A Polars lowerer for dataframe-native row-level and aggregate checks
- A Dask and Dask-SQL lowerer path for distributed Python and SQL execution
- Fail-fast diagnostics for unsupported semantics rather than silent fallback
- Regression tests and proof artifacts for each engine path

### Out of scope

- Replacing Spark as the default runtime in the first phase
- Automatic fallback from one engine to another
- Full support for every engine-specific construct in the initial rollout
- Rewriting the rule model or introducing engine-specific authoring syntax

## User-facing outcome

Users should be able to request a validation plan once and have it projected to the appropriate runtime without changing the stored rule definition. For engines that support the rule, execution should be observable, traceable, and comparable to other runtime paths. Unsupported semantics should fail fast with explicit guidance.

## Proposed engine identities

| Engine | Proposed engine_type | Proposed engine_target | Initial purpose |
| --- | --- | --- | --- |
| Trino | trino | trino_sql | Federated SQL / warehouse-style validation |
| Polars | polars | polars | Dataframe-native validation in Python pipelines |
| Dask / Dask-SQL | dask_sql or dask | dask | Distributed Python and SQL execution |

## Architecture direction

This feature should build on the existing execution abstraction rather than creating a separate engine stack.

- Keep canonical rule intent as the single source of truth.
- Introduce engine-specific lowerers behind a shared interface.
- Preserve the neutral validation-artifact envelope for runtime-agnostic persistence.
- Keep execution dispatch and result normalization generic so each engine can plug in without changing the main contract.

## Success criteria

- A supported rule can be compiled and executed through Trino without changing the stored rule definition.
- A supported rule can be compiled and executed through Polars without changing the stored rule definition.
- A supported rule can be compiled and executed through Dask or Dask-SQL without changing the stored rule definition.
- Unsupported constructs fail fast with actionable diagnostics.
- Each engine path is observable through the same execution and evidence model.

## Proposed workstreams

### 1. Foundation and capability contract

- Define a shared adapter interface and a capability registry.
- Add compiler-side metadata for engine support and required runtime features.
- Define the initial supported/unsupported construct matrix for each engine.

### 2. Trino lowerer

- Map row-level checks, aggregate checks, and simple SQL predicates to Trino SQL.
- Add execution adapter and local validation harness.
- Validate behavior against a Trino-compatible environment.

### 3. Polars lowerer

- Map canonical rule intent to Polars expressions and lazy dataframe operations.
- Add execution adapter and regression tests.
- Validate against local and container-based Polars runtimes.

### 4. Dask / Dask-SQL lowerer

- Support Dask dataframe semantics for Python-native execution.
- Add Dask-SQL-backed translation for SQL-shaped validations where appropriate.
- Validate distributed execution and failure handling.

### 5. Observability, rollout, and hardening

- Add engine-specific diagnostics and evidence capture.
- Add CI coverage for supported and unsupported rule families.
- Roll out each engine as opt-in and keep Spark/GX as the default path.

## Related references

- [ABS_1_EXECUTION_ABSTRACTION.md](/docs/features/ABS_1_EXECUTION_ABSTRACTION/)
- [SPARK_EXPECTATIONS_ENGINE_PLAN.md](/docs/implementation-details/SPARK_EXPECTATIONS_ENGINE_PLAN/)
