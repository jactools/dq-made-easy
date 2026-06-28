# ABS-1 Execution Abstraction (GX + PySpark)

Goal: introduce a stable abstraction layer between rule definitions and execution runtimes so rules can compile into portable GX suites, integrate with self-built PySpark execution solutions, run efficiently in grouped batches, and remain retrievable by scope for external systems.

## Why this exists

The platform needs a consistent boundary between rule intent and runtime execution. ABS-1 makes that boundary explicit so the execution layer can evolve without changing the rule model.

- portable GX suite artifacts that can be reused by external executors
- retrieval by data object, data object version, dataset, and data product
- PySpark-first grouped execution by data object version to avoid repeated spin-up
- an integration seam for self-built PySpark solutions that want to reuse rule compilation, scope resolution, and grouped planning without adopting GX end to end
- separate persistence for aggregate outcomes and exception records
- structured observability across compile, retrieval, execution, and persistence

## Scope

### In scope

- Canonical abstraction contracts between rule model and execution runtimes
- Neutral validation plan as the canonical run-plan contract, with GX/Soda/SQL plans projected from it
- GX suite registry as a first-class retrievable artifact
- Retrieval APIs by data object, data object version, dataset, and data product
- PySpark-first grouped execution by data object version
- Integration contract for self-built PySpark solutions that reuse shared scope resolution, source adapters, and grouped execution seams where compatible
- Pluggable data source adapter contract for Spark, JDBC, and files
- Separate stores for aggregate outcomes and exception records
- Minimal exception record schema
- Structured logging, metrics, tracing, and alerting

### Out of scope

- Materializing data deliveries
- Delivery-linked execution and note enrichment
- Silent fallback to a different runtime when the requested runtime is unavailable
- Persisting exception rows in the same store as aggregate results
- Hiding compile or execution failures behind success responses

## User-facing outcome

A user or external system can request a canonical validation plan for a given scope, resolve that plan into a GX suite or another engine-specific run plan, execute it in the appropriate runtime, and inspect aggregate outcomes without losing the exception-level detail needed for troubleshooting and downstream workflows. The same abstraction boundary is intended to support teams that want to wire the compiled rule output into a self-built PySpark execution solution rather than relying only on the platform-owned GX runtime path.

## Success criteria

- [x] Rules can be transformed into portable GX suites
- [x] GX suites are retrievable by object, object version, dataset, and product scope
- [x] Assignment scope is separated from resolved execution-version scope
- [x] Grouped execution reduces repeated runtime spin-up and spin-down overhead
- [x] Exception records are not persisted in the rule/result database
- [x] Observability coverage is validated across compile, retrieval, execution, and persistence stages

## Runtime positioning

ABS-1 is not only a canonical abstraction exercise. The first concrete runtime path is GX backed by grouped PySpark execution, but the abstraction is also meant to support self-built PySpark integrations as a preview path where a team wants to keep its own executor, Spark job packaging, or operational model while still reusing the rule compiler, scope resolution, shared runtime metadata, and the neutral validation-plan contract.

Soda remains a separate follow-on expansion path, but it is not the only intended next step. The execution seam should be able to support both custom PySpark integrations and later non-PySpark engines without changing rule authoring semantics.

## Related implementation note

- [ABS-1 implementation details](/docs/implementation-details/ABS_1_EXECUTION_ABSTRACTION_IMPLEMENTATION_DETAILS/)
- [ABS-3 definition](/docs/status/current/ABS_3_DELIVERY_LINKED_RULE_EXECUTION/)
- [DQ_7_4 GX suite orchestration](/docs/implementation-details/DQ_7_4_GX_SUITE_ORCHESTRATION_IMPLEMENTATION_DETAILS/)

## Preview Track: Multi-Runtime Expansion (Self-Built PySpark + Soda)

Goal: extend the execution abstraction so the canonical DSL compiler can support self-built PySpark solutions beside the platform GX runtime as a preview capability, and later target Soda as an additional engine, without changing rule authoring semantics or introducing silent runtime fallback.

This is a preview track to ABS-1, not a change to the completed ABS-1 acceptance scope. ABS-1 established the stable compiler-to-runtime seam and the first runtime implementation. This track broadens that seam so multiple runtime implementations can coexist behind the same compiler contract, including teams' own PySpark executors.

### In scope

- Introduce the minimum runtime-neutral artifact and run-planning contract needed for a second engine
- Add `engine_type` through artifact persistence, run planning, and dispatch
- Add a preview self-built PySpark integration path that can consume canonical compiler output or the neutral artifact envelope without forcing the current GX worker path
- Add a Soda adapter path parallel to the current GX adapter path
- Reuse shared source resolution, grouped planning, queueing, provenance, and result normalization where engine-neutral
- Keep the top-level queueing and execution-monitoring semantics generic so multiple executors can aggregate into one operational dashboard, with runtime-specific drilldowns added separately
- Fail fast for unsupported self-built PySpark mappings when the requested contract or adapter capability is missing
- Fail fast for unsupported Soda mappings such as joins or row/filter-condition cases that do not yet have proven equivalence

### Out of scope

- Replacing GX as the default runtime in the first pass
- Repo-wide renaming of every `gx_*` table, API, or implementation symbol before multi-runtime support exists
- Silent fallback from a self-built PySpark integration to GX when the custom runtime cannot execute a requested rule
- Silent fallback from Soda to GX when Soda cannot execute a requested rule

### Tracked Work Items

- [x] `ABS-1.MR-01` Define a runtime-neutral validation artifact contract above the current GX suite envelope
- [x] `ABS-1.MR-02` Generalize the GX-specific repository contracts so a second engine can persist artifacts and run plans without GX-backed Postgres bridges
- [x] `ABS-1.MR-03` Add `engine_type` to runtime persistence and dispatch contracts
- [x] `ABS-1.MR-04` Define a self-built PySpark executor integration contract above the neutral artifact and grouped-planning seams
- [ ] `ABS-1.MR-05` Implement a self-built PySpark adapter path that can consume canonical compiler output or neutral artifacts while reusing shared source resolution and runtime metadata where practical
- [ ] `ABS-1.MR-06` Add integration tests for the self-built PySpark path, including fail-fast handling for unsupported contract gaps
- [ ] `ABS-1.MR-07` Implement a Soda translator and adapter path from canonical compiler output to Soda scan/check definitions
- [ ] `ABS-1.MR-08` Add worker/runtime dispatch for Soda while keeping source resolution and result normalization shared where practical
- [ ] `ABS-1.MR-09` Add mixed-engine tests covering supported mappings, persistence metadata, and at least one end-to-end Soda execution path

### Acceptance Criteria

- [ ] Canonical compiler output remains the single source of truth for GX, self-built PySpark, and Soda targets
- [ ] A supported rule can be executed through a preview self-built PySpark integration without changing the stored rule model
- [ ] A supported rule can be compiled and executed through Soda without changing the stored rule model
- [x] Runtime selection is explicit in persistence and dispatch contracts
- [ ] Unsupported self-built PySpark and Soda mappings fail fast with actionable diagnostics
- [ ] Existing GX execution paths remain backward compatible during the multi-runtime rollout

### MR-01 Initial Output

- The runtime-neutral contract now lives in [docs/contracts/validation-artifact-envelope/v1/schema.json](https://github.com/jactools/dq-rulebuilder/blob/main/docs/contracts/validation-artifact-envelope/v1/schema.json) with matching [JSON example](https://github.com/jactools/dq-rulebuilder/blob/main/docs/contracts/validation-artifact-envelope/v1/example.json) and [YAML example](https://github.com/jactools/dq-rulebuilder/blob/main/docs/contracts/validation-artifact-envelope/v1/example.yaml).
- The neutral envelope wraps an engine-native payload through `engine_artifact`, so the current GX suite envelope can remain intact while the outer contract becomes runtime-neutral.
- The first domain seam for that contract now lives beside the GX entities, so later MR work can generalize persistence and dispatch without first redesigning the payload shape.

### MR-02 Current Output

- A neutral artifact repository contract exists for both in-memory and Postgres-backed implementations, with GX wrappers still servicing the current API surface.
- A neutral run-plan repository contract now exists beside the GX run-plan repository, with bridge entities that project `suite` semantics to `artifact` semantics without changing the current GX endpoints yet.
- FastAPI dependency wiring now exposes neutral validation-artifact and validation-run-plan repositories for new application code, while the existing GX dependency getters remain in place for backward compatibility.
- The rule-activation flow now autopublishes through the neutral validation-artifact repository while still generating the current GX-backed artifact payload under that seam.
- The delivery-linked execution path in the data-catalog API now resolves candidate artifacts and run plans through the neutral repositories, while still projecting back to GX at the grouped-planning and dispatch boundary.
- The approvals endpoint now uses the neutral validation-artifact and validation-run-plan repositories for GX suite repair, run-plan governance transitions, and rule deactivation side effects, projecting artifacts back to GX only where the legacy payload mutation logic still requires it.
- The GX suite CRUD, retrieval, rule-link, and status-history endpoints now read and write through the neutral validation-artifact repository while preserving the current GX HTTP payload contract.
- GX run-plan draft creation and draft-version creation now resolve their single-suite and grouped-scope seeds from the neutral validation-artifact repository, then project those artifacts back into the existing GX run-plan snapshot contract.
- The GX run-plan query and lifecycle surface now reads and mutates through the neutral validation-run-plan repository as well, with the GX adapter layer projecting neutral run-plan rows back into the existing GX HTTP contract only at the use-case and HTTP boundary.
- Grouped execution planning now accepts neutral validation-artifact rows directly, so the grouped planner input seam no longer requires caller-side GX projection in run-plan seed resolution or delivery-linked execution resolution even though the emitted batch payload stays GX-shaped for the current worker path.
- Internal grouped execution now also tolerates neutral artifact envelopes inside planner batch `suites`, so the planner and PySpark executor can keep neutral artifact payloads across their in-process handoff while the external GX worker/runtime contracts remain unchanged.
- Grouped dispatch command building now also accepts snake_case and neutral artifact-style suite refs at the runtime boundary, so delivery-linked grouped dispatch no longer has to remap internal suite candidate payloads into GX camelCase keys before enqueueing.
- GX execution-run entity parsing now also accepts snake_case and neutral artifact-style aliases for suite metadata and nested run payloads, so internal run/status/query flows no longer need GX camelCase reshaping before they normalize persisted or queued run records.
- GX execution-run list-query normalization now also accepts neutral artifact-style suite aliases, and execution summary search now considers normalized engine-type metadata, which reduces another GX-only selector assumption in the internal query path without changing the outward GX API.
- GX execution-run repositories now normalize raw list-run query mappings at their own boundary, including neutral suite-selector aliases, so internal callers no longer need to prebuild GX query entities before filtering execution runs.
- The execution query use cases now pass raw neutral-friendly list-run filter mappings straight into the repository boundary instead of constructing GX query entities themselves, which keeps GX query-shaping localized to a single normalization seam.
- The data-catalog delivery-note endpoint now also passes a raw mapping directly into `GxExecutionRunRepository.list_runs(...)`, so direct GX list-query builder usage is reduced to the repository/domain normalization boundary itself.
- The neutral Postgres validation-artifact repository now persists directly to `validation_artifact_registry` and `validation_artifact_status_history`, so non-GX artifacts no longer have to round-trip through GX suite storage adapters.
- The neutral Postgres validation-run-plan repository now persists directly to `validation_run_plans` and `validation_run_plan_versions`, with lifecycle audit events in `validation_run_plan_transitions`, so neutral run plans no longer have to project artifact semantics back through GX run-plan tables.
- The current implementation remains additive at the API boundary only: GX callers stay stable while compatibility adapters translate neutral storage rows back into the existing GX HTTP contracts.

### MR-02 Completion Note

- Both remaining Postgres bridge removals are now complete: neutral artifact storage and neutral run-plan storage each have their own SQLAlchemy models, Alembic migrations, and seed data.
- GX HTTP and use-case adapters still project neutral storage rows back into GX response and validation shapes where required, but those projections now live at the compatibility boundary instead of inside the Postgres repositories.
- Follow-on multi-runtime work can treat MR-02 as closed and build on the neutral persistence seam rather than the earlier GX-backed bridge layer.

### MR-03 Completion Note

- Delivery-linked execution receipts now surface `resolved_engine_type`, and candidate suite/run-plan payloads now carry `engine_type` in snake_case.
- Grouped execution dispatch payloads, suite references, delivery snapshots, and persisted execution-run contracts now carry `engine_type`, so the current worker-facing GX path no longer relies on delivery metadata alone to preserve runtime identity.
- GX run-plan seed resolution now stamps `engine_type` onto generated suite references during single-suite and grouped-scope planning, keeping newly created run-plan payloads aligned with the dispatch/runtime contract.
- GX-to-neutral run-plan persistence adapters now preserve `engine_type` on suite or artifact references, and the GX run-plan API now exposes that metadata back on `suite_refs`, so draft creation, version creation, and later activation all round-trip the selected runtime explicitly.
- Single-suite GX run-plan activation now rehydrates missing `execution_contract.engine_type` from persisted run-plan metadata before scheduled enqueue, so older GX-shaped suite snapshots are normalized once at activation before the strict write path persists a new dispatch or execution run.
- Grouped GX dispatch now fails closed when suite references or delivery metadata resolve to a non-GX or mixed `engine_type`, so the current GX-only grouped activation path cannot silently enqueue an unsupported runtime selection.
- Delivery-linked applicability now drops grouped run plans whose active version does not resolve to `engine_type = gx`, and the direct GX suite start handoff now emits top-level `engine_type`, so these remaining runtime entry paths no longer rely on implicit inference to preserve engine identity.
- New dispatch payloads and execution-run create payloads now require explicit top-level `engine_type`, and matching nested `execution_contract.engine_type` when present, so write-side persistence fails fast instead of repairing runtime identity from nested payloads.
- Execution-run reads now require persisted top-level `engine_type` and no longer infer it from nested execution-contract or handoff payloads; legacy records must be migrated or rejected rather than silently normalized.
- The GX suite execution-contract HTTP view now exposes `engine_type`, and `gx_execution_runs` now persists a dedicated top-level runtime column with an Alembic revision that fails if legacy rows are present, so strict runtime identity survives API serialization and repository round-trips without fallback behavior.
- The current dispatch/runtime path remains GX-only and fails closed if a non-GX or mixed-engine grouped selection reaches delivery-linked execution, or if a non-GX artifact reaches the GX-only approvals flow.
- Grouped execution planning is still GX-envelope-based, so the neutral-to-GX projection currently happens immediately before grouped planning even though the downstream queue contract now records `engine_type` explicitly.

### MR-04 Draft Output

- The draft self-built PySpark executor request contract now lives in [docs/contracts/self-built-pyspark-executor-request/v1/schema.json](https://github.com/jactools/dq-rulebuilder/blob/main/docs/contracts/self-built-pyspark-executor-request/v1/schema.json) with matching [JSON example](https://github.com/jactools/dq-rulebuilder/blob/main/docs/contracts/self-built-pyspark-executor-request/v1/example.json) and [YAML example](https://github.com/jactools/dq-rulebuilder/blob/main/docs/contracts/self-built-pyspark-executor-request/v1/example.yaml).
- The request is intentionally defined above the current GX worker payload and carries one grouped execution batch, resolved source binding, explicit runtime traceability, and embedded runtime-neutral validation artifacts.
- The draft keeps `executor_kind = self_built_pyspark` separate from per-item `engine_type`, because the custom PySpark path is an execution implementation, not automatically a new validation engine. In the current draft, a self-built PySpark executor is expected to run `engine_type = gx` artifacts.
- The v1 draft intentionally scopes artifact input to the runtime-neutral validation artifact envelope. Direct canonical compiler-output handoff is deferred until the compiler artifact has its own versioned contract package.
- Unsupported engine types, missing source bindings, or missing required capabilities are expected to fail fast; the contract does not permit fallback to the platform-owned GX executor.

### PySpark-Native Artifact Draft

- A PySpark-native engine contract now lives in [docs/contracts/pyspark-native-artifact-envelope/v1/schema.json](https://github.com/jactools/dq-rulebuilder/blob/main/docs/contracts/pyspark-native-artifact-envelope/v1/schema.json) with matching [JSON example](https://github.com/jactools/dq-rulebuilder/blob/main/docs/contracts/pyspark-native-artifact-envelope/v1/example.json) and [YAML example](https://github.com/jactools/dq-rulebuilder/blob/main/docs/contracts/pyspark-native-artifact-envelope/v1/example.yaml).
- This introduces `engine_type = pyspark_native` as a real engine-native artifact family rather than using custom PySpark only as an alternate executor for `gx` artifacts.
- The neutral validation artifact envelope and the self-built PySpark executor request contract now both allow `pyspark_native` alongside `gx`.
- The self-built PySpark executor request contract now also includes a second example request carrying a `pyspark_native` item at [docs/contracts/self-built-pyspark-executor-request/v1/example_pyspark_native.json](https://github.com/jactools/dq-rulebuilder/blob/main/docs/contracts/self-built-pyspark-executor-request/v1/example_pyspark_native.json) and [YAML rendering](https://github.com/jactools/dq-rulebuilder/blob/main/docs/contracts/self-built-pyspark-executor-request/v1/example_pyspark_native.yaml).
- Compiler-to-artifact mapping rules for the new engine now live in [ABS-1 PySpark-native compiler mapping](/docs/implementation-details/ABS_1_PYSPARK_NATIVE_COMPILER_MAPPING/).
- The top-level Execution Monitoring dashboard now uses runtime-agnostic naming because queueing and lifecycle monitoring are intended to aggregate all executors through shared run, status, transition, latency, results/failures, compile, throughput, and heartbeat semantics.
- Runtime-specific dashboards such as GX drilldowns can be added later without changing the aggregated operational view.

### Related References

- [ADR-011: Executable Rule Transformation Strategy](/docs/architecture/adr/ADR-011-executable-rule-transformation-strategy-dsl-first-with-great-expectations-adapter/)
- [API-7 Real DQ Rule Execution](/docs/status/current/API_7_REAL_DQ_RULE_EXECUTION/)