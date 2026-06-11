# Spark Expectations Engine Integration Plan

Status: Draft
Target: add Nike Spark Expectations as a first-class execution engine under the existing Spark-based runtime stack.

## Goal

Use Nike Spark Expectations as a supported validation engine in dq-made-easy, while preserving the current GX path as the default and keeping the integration fail-fast, observable, and reversible.

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

[ ] [SE-PLAN-001] Add `spark-expectations` to the dq-engine dependency set.
[ ] [SE-PLAN-002] Create a small POC using one row-level rule and one aggregate rule against sample Spark data.
[ ] [SE-PLAN-003] Validate the happy path and the quarantine/error-table path.
[ ] [SE-PLAN-004] Capture the baseline runtime and packaging requirements for local and container runs.

Acceptance criteria:

[ ] [SE-AC-001] the package loads inside the dq-engine image
[ ] [SE-AC-002] one sample rule executes successfully
[ ] [SE-AC-003] failed rows are written to an error table or equivalent quarantine path
[ ] [SE-AC-004] the POC produces stats output for reporting

### Phase 2 — Adapter and compiler mapping

Objective: map canonical rule intent into Spark Expectations rules without changing the stored rule model.

Deliverables:

[ ] [SE-PLAN-005] Add a dedicated adapter module under dq-engine for Spark Expectations rule lowering.
[ ] [SE-PLAN-006] Define a fail-fast mapping table for supported constructs:
    [ ] row-level checks
    [ ] aggregate checks
    [ ] query-based checks
[ ] [SE-PLAN-007] Keep unsupported constructs explicit and reject them before execution.
[ ] [SE-PLAN-008] Add a neutral artifact projection path that can persist `engine_type = spark_expectations`.

Acceptance criteria:

[ ] [SE-AC-005] canonical rule payloads lower into Spark Expectations-friendly rule definitions
[ ] [SE-AC-006] unsupported semantics fail fast with actionable diagnostics
[ ] [SE-AC-007] the neutral artifact envelope can carry the new engine type without breaking GX flows

### Phase 3 — Runtime dispatch and execution path

Objective: route supported validations through a Spark Expectations execution path rather than the GX worker path.

Deliverables:

[ ] [SE-PLAN-009] Add a Spark Expectations execution worker or adapter seam inside dq-engine.
[ ] [SE-PLAN-010] Reuse the existing grouped execution and source-binding concepts where possible.
[ ] [SE-PLAN-011] Persist results through the current execution-monitoring and exception-store seams.
[ ] [SE-PLAN-012] Keep a clear separation between aggregate outcomes and failed-row evidence.

Acceptance criteria:

[ ] [SE-AC-008] a supported validation plan can execute through the Spark Expectations path
[ ] [SE-AC-009] failed rows and aggregate metrics are persisted through the existing runtime contract
[ ] [SE-AC-010] the current GX worker path remains unchanged for GX-based runs

### Phase 4 — Observability, notifications, and hardening

Objective: make the new engine production-ready rather than just technically runnable.

Deliverables:

[ ] [SE-PLAN-013] Connect Spark Expectations stats and observability output into the existing monitoring surface.
[ ] [SE-PLAN-014] Add notification hooks for email, Slack, or PagerDuty where appropriate.
[ ] [SE-PLAN-015] Add performance and memory guardrails for Spark jobs.
[ ] [SE-PLAN-016] Add integration tests for supported and unsupported rule families.

Acceptance criteria:

[ ] [SE-AC-011] metrics and audit outputs are visible in the existing observability flow
[ ] [SE-AC-012] failures are actionable and traceable
[ ] [SE-AC-013] the engine can run in the same operational model as the current Spark-based stack

## Recommended rollout order

[ ] Build the POC and prove that Spark Expectations can execute inside dq-engine.
[ ] Add the adapter and fail-fast rule mapping.
[ ] Wire the execution seam behind the existing neutral artifact contract.
[ ] Expand support only for the rule families that are proven and stable.
[ ] Keep GX as the default runtime until Spark Expectations support is verified in real runs.

## Non-goals

- replacing GX as the default engine immediately
- adding silent fallback from Spark Expectations to GX
- broadening the scope to every notification or reporting mode before the core execution path works

## Success criteria

- Spark Expectations can run inside the current dq-engine environment.
- Supported rules can be compiled and executed through the neutral artifact/execution seam.
- Unsupported rules fail fast with explicit diagnostics.
- The current GX runtime path remains backward compatible.
