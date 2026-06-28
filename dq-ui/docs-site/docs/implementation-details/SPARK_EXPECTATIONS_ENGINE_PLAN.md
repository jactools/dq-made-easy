# Spark Expectations Engine Integration Plan

Status: Preview (runtime dispatch, quarantine persistence, and metrics exposure validated)
Target: add Nike Spark Expectations as a preview execution engine under the existing Spark-based runtime stack.

## Goal

Use Nike Spark Expectations as a preview validation engine in dq-made-easy, while preserving the current GX path as the default and keeping the integration fail-fast, observable, and reversible.

## Why this engine

Spark Expectations is a PySpark-native DQ framework from Nike that fits the current architecture well:

- it runs in Spark and aligns with the existing dq-engine runtime
- it supports row-level, aggregate, and query-based rules
- it quarantines failed rows into error tables instead of silently dropping them
- it produces stats/observability output and supports notification integrations

This makes it a strong candidate for the next non-GX engine path behind the existing execution abstraction.

## Current state to build on

The repo already has the right seams for this work:

- dq-engine currently runs GX over Spark
- the ABS-1 abstraction already separates rule intent from runtime execution
- the neutral validation-artifact envelope already supports explicit engine identity
- the current runtime path is prepared for multi-engine expansion rather than a hard GX-only model

The integration should therefore reuse those seams instead of introducing a parallel execution model from scratch.

## Proposed engine identity

Use an explicit runtime identity for the new path:

- engine_type = spark_expectations
- engine_target = pyspark

This keeps the execution substrate (`pyspark`) separate from the validation engine implementation (`spark_expectations`).

## Implementation plan

### Phase 1 — Proof of concept and dependency baseline

Objective: prove that Spark Expectations can run in the current dq-engine container and execute one simple rule path.

Deliverables:

[x] [SE-PLAN-001] Add `spark-expectations` to the dq-engine dependency set.
[x] [SE-PLAN-002] Create a small POC using one row-level rule and one aggregate rule against the data_sources/teller_machine data that is seeded onto AIStor.
[x] [SE-PLAN-003] Validate the happy path and the quarantine/error-table path.
[x] [SE-PLAN-004] Capture the baseline runtime and packaging requirements for local and container runs.
[x] [SE-PLAN-017] Add a bounded chunked error-management path that can summarize millions of failed rows without materializing them all in memory.

Acceptance criteria:

[x] [SE-AC-001] the package loads inside the dq-engine image
[x] [SE-AC-002] one sample rule executes successfully
[x] [SE-AC-003] failed rows are written to an error table or equivalent quarantine path
[x] [SE-AC-004] the POC produces stats output for reporting
[x] [SE-AC-014] very large failure sets are handled with bounded memory usage and explicit chunking metadata

### Phase 2 — Adapter and compiler mapping

Objective: map canonical rule intent into Spark Expectations rules without changing the stored rule model.

Deliverables:

[x] [SE-PLAN-005] Add a dedicated adapter module under dq-engine for Spark Expectations rule lowering.
[x] [SE-PLAN-006] Define a fail-fast mapping table for supported constructs:
    [x] row-level checks (not_null, min, max, equals, not_equal, between, in)
    [x] aggregate checks (count, sum, avg, stddev, row_count, unique, missing_count, duplicate_count, distinct_count)
    [x] query-based checks (count-based query expectations)
[x] [SE-PLAN-007] Keep unsupported constructs explicit and reject them before execution.
    - Unsupported constructs for the initial rollout:
      - Arbitrary custom expressions and SQL predicates. Reason: they require expression translation and evaluation semantics that are not yet modeled in the neutral rule envelope.
      - Window and analytic operations such as rank, dense_rank, lag, lead, or other `OVER (...)` patterns. Reason: they depend on ordering and partition context that is not part of the current lowering contract.
      - Complex query expectations that return rows or multiple values instead of a scalar count. Reason: the adapter currently targets count-based scalar query expectations and cannot safely lower richer result-set semantics.
      - Cross-field or multi-column predicates. Reason: the initial mapping is intentionally single-column and fail-fast to avoid ambiguous lowering and hard-to-audit behavior.
[x] [SE-PLAN-008] Add a neutral artifact projection path that can persist `engine_type = spark_expectations`.

Acceptance criteria:

[x] [SE-AC-005] canonical rule payloads lower into Spark Expectations-friendly rule definitions
[x] [SE-AC-006] unsupported semantics fail fast with actionable diagnostics
[x] [SE-AC-007] the neutral artifact envelope can carry the new engine type without breaking GX flows

### Phase 3 — Runtime dispatch and execution path

Objective: route supported validations through a Spark Expectations execution path rather than the GX worker path.

Deliverables:

[x] [SE-PLAN-009] Add a Spark Expectations execution worker or adapter seam inside dq-engine.
[x] [SE-PLAN-010] Reuse the existing grouped execution and source-binding concepts where possible.
[x] [SE-PLAN-011] Persist results through the current execution-monitoring and exception-store seams.
[x] [SE-PLAN-012] Keep a clear separation between aggregate outcomes and failed-row evidence.

Acceptance criteria:

[x] [SE-AC-008] a supported validation plan can execute through the Spark Expectations path
[x] [SE-AC-009] failed rows and aggregate metrics are persisted through the existing runtime contract
[x] [SE-AC-010] the current GX worker path remains unchanged for GX-based runs

Validation evidence:

- Verified in a containerized Spark runtime with the focused regression suite: 13 tests passed in 9.50s.
- Verified the quarantine artifact path end to end against the real AIStor-backed S3-compatible service from inside the containerized test runtime.
- Validation uses `scripts/run_spark_expectations_container_tests.sh` and the dedicated dq-engine test container; it never relies on the host Java environment.
- Spark Expectations follows the shared engine seams already used by the generic runtime paths: `normalize_engine_type()` maps PySpark aliases to `spark_expectations`, `build_compiled_artifact_for_engine()` emits the same canonical envelope shape, and worker reporting persists `metrics` through the existing GX report transport.
- Custom PySpark already uses the same run-result contract shape for `performanceSummary` and execution metrics, so Spark Expectations can reuse the generic metrics/reporting seam rather than inventing a separate persistence model.

### Phase 4 — Observability, notifications, and hardening

Objective: make the new engine production-ready rather than just technically runnable.

Deliverables:

[x] [SE-PLAN-013] Connect Spark Expectations stats and observability output into the existing monitoring surface.
[x] [SE-PLAN-014] Expose Spark Expectations execution counters and duration totals through the engine metrics endpoint in Prometheus format.
[x] [SE-PLAN-015] Add performance and memory guardrails for Spark jobs.
[x] [SE-PLAN-016] Add integration tests for supported and unsupported rule families.

Acceptance criteria:

[x] [SE-AC-011] metrics and audit outputs are visible in the existing observability flow
[x] [SE-AC-012] failures are actionable and traceable
[x] [SE-AC-013] the engine can run in the same operational model as the current Spark-based stack

Validation evidence:

- Verified end to end with `./scripts/validation/validate_spark_expectations_real_aistor.sh`, including the full construct matrix and the large quarantine/error-table path.

## Recommended rollout order

[x] Build the POC and prove that Spark Expectations can execute inside dq-engine.
[x] Add the adapter and fail-fast rule mapping.
[x] Wire the execution seam behind the existing neutral artifact contract.
[x] Expand support only for the rule families that are proven and stable.
[x] Keep GX as the default runtime until Spark Expectations support is verified in real runs.

## Immediate next steps

1. Finish [SE-PLAN-016] with integration tests that prove the supported families execute successfully and the unsupported families fail fast in the containerized dq-engine test runtime.

## Non-goals

- replacing GX as the default engine immediately
- adding silent fallback from Spark Expectations to GX
- broadening the scope to every notification or reporting mode before the core execution path works

## Success criteria

- Spark Expectations can run inside the current dq-engine environment.
- Supported rules can be compiled and executed through the neutral artifact/execution seam.
- Unsupported rules fail fast with explicit diagnostics.
- The current GX runtime path remains backward compatible.
