# ABS-1 Execution Abstraction - Implementation Details

This note turns ABS-1 into an actionable backlog.

Goal: build the layer that compiles rule definitions into GX suites, registers them as retrievable artifacts, executes them in a grouped PySpark-first runtime, and preserves a seam for self-built PySpark integrations or later non-GX engines while keeping a separate exception store.

ABS1-GX-01 is satisfied by the canonical GX artifact envelope and registry baseline already defined in the GX orchestration contract and contract files.

## Multi-Runtime Bootstrap - MR-01

ABS-1.MR-01 is the first additive step for multi-runtime support: define a runtime-neutral validation artifact contract above the GX-native envelope without breaking the existing GX path.

### MR-01 Deliverables

1. A versioned runtime-neutral contract package at [docs/contracts/validation-artifact-envelope/v1/schema.json](../contracts/validation-artifact-envelope/v1/schema.json).
2. Example payloads showing how a GX-native suite envelope is wrapped as an engine-native artifact instead of being rewritten in place.
3. A domain builder seam that can project the current `GxArtifactEnvelopeEntity` into the neutral envelope while persistence and dispatch remain GX-specific for now.

### MR-01 Contract Intent

- Keep the current GX suite envelope valid and usable.
- Introduce neutral outer fields for artifact identity, scope, compiler provenance, execution hints, and run-planning semantics.
- Carry the engine-native payload under `engine_artifact` so future self-built PySpark or Soda artifacts can sit beside GX without inventing a second outer envelope.
- Avoid persistence changes in this step; repository, run-plan, and dispatch contracts remain GX-shaped until MR-02 and MR-03.

### MR-01 Output

- Contract package: [docs/contracts/validation-artifact-envelope/README.md](../contracts/validation-artifact-envelope/README.md)
- JSON Schema: [docs/contracts/validation-artifact-envelope/v1/schema.json](../contracts/validation-artifact-envelope/v1/schema.json)
- Examples: [docs/contracts/validation-artifact-envelope/v1/example.json](../contracts/validation-artifact-envelope/v1/example.json) and [docs/contracts/validation-artifact-envelope/v1/example.yaml](../contracts/validation-artifact-envelope/v1/example.yaml)
- Domain seam: `app/domain/entities/validation_artifact.py` with a `build_validation_artifact_envelope_from_gx_artifact(...)` bridge for the current GX path

## Multi-Runtime Repository Generalization - MR-02 First Slice

MR-02 is broader than a single file change. The first slice generalizes the artifact repository seam without renaming the existing GX-facing API surface or changing Postgres storage yet.

### MR-02 First Slice Output

1. A neutral repository contract at `app/domain/interfaces/v1/validation_artifact_repository.py` using `ValidationArtifactEnvelopeEntity` and neutral status-history rows.
2. An in-memory repository implementation at `app/infrastructure/repositories/in_memory_validation_artifact_repository.py` with the same overwrite-protection and status-history semantics as the GX repository.
3. The GX in-memory repository now delegates through the neutral repository seam and projects back to `GxArtifactEnvelopeEntity`, which keeps the current GX API paths stable while proving the generalized storage contract.

### MR-02 Storage Completion

- `PostgresValidationArtifactRepository` now persists directly to `validation_artifact_registry` and `validation_artifact_status_history`, so engine-neutral artifacts no longer route through `PostgresGxSuiteRepository`.
- `PostgresValidationRunPlanRepository` now persists directly to `validation_run_plans`, `validation_run_plan_versions`, and `validation_run_plan_transitions`, so neutral run-plan state no longer routes through `PostgresGxRunPlanRepository`.
- Compatibility adapters and GX-facing HTTP contracts remain in place, but they now sit above neutral storage instead of being embedded in the Postgres repository implementations.

This keeps the slice additive: the neutral repository exists and is exercised in memory first, while the rest of MR-02 can migrate storage and callers incrementally.

## MR-02 Expanded Slice

The next MR-02 slice broadens the same approach in two directions without changing the current GX API contracts:

1. A Postgres-backed neutral artifact repository now wraps the current GX suite repository so non-GX callers can target a neutral artifact seam while persistence remains on the current GX tables.
2. A neutral run-plan repository contract and bridge entities now sit beside the GX run-plan repository, projecting `suite` references and snapshots to `artifact` references and snapshots.

### Current Boundaries

- The neutral Postgres artifact repository is still GX-backed today and fails fast if asked to project a non-GX artifact into the current GX storage shape.
- The neutral run-plan repository currently wraps the GX run-plan repositories rather than replacing their storage internals.
- FastAPI dependency wiring now exposes neutral validation-artifact and validation-run-plan repository getters for new application code, while existing GX dependency getters remain available for compatibility.
- The rules activation use case is the first application slice moved onto that neutral artifact seam: autopublish persists through `ValidationArtifactRepository` even though the generated artifact remains GX-backed today.
- The delivery-linked execution resolver and orchestrator now consume the neutral artifact and run-plan repositories from the data-catalog endpoint, but they still project selected artifacts back to GX before grouped planning and dispatch because the grouped planner and runtime queue contracts remain GX-shaped.
- The approvals endpoint now consumes the neutral artifact and run-plan repositories as well. It still projects neutral artifacts back into GX envelopes for the existing suite-repair and suite-deactivation payload rewrites, and it fails closed if a non-GX artifact reaches that GX-only path.
- The GX suite API helper and the GX suite save/list/fetch/status-history endpoints now consume `ValidationArtifactRepository`, translating neutral artifact rows back into GX response views at the HTTP boundary so callers keep the existing suite contract unchanged.
- The GX run-plan seed resolver now consumes `ValidationArtifactRepository` too. The run-plan create and create-version adapters resolve single-suite and grouped-scope seeds from neutral artifact rows, project them back into GX suite entities for planner/runnable validation, and fail closed if a non-GX artifact reaches that path.
- The GX run-plan use cases and HTTP adapter now consume `ValidationRunPlanRepository` across create, create-version, get, list, governance transition, validation, and activation. They project neutral run-plan rows back into GX entities through `build_gx_run_plan_entity_from_validation_run_plan` before the existing GX validation and response presenters run.
- GX run-plan validation responses now clear an intentionally invalid pending suite snapshot before serializing the plan view, so `validation_failed` responses can surface diagnostics for malformed snapshots without breaking the strict GX response schema.
- `GroupedExecutionPlanner` now accepts `ValidationArtifactEnvelopeEntity` inputs directly and performs the neutral-to-GX projection internally only when it builds the current worker-facing batch payload. That lets the GX run-plan seed resolver and the delivery-linked execution request resolver hand neutral artifact rows into grouped planning without duplicating caller-side projection logic.
- `GroupedExecutionPlanner` now preserves neutral artifact envelopes in batch `suites` when its inputs are neutral, and `PysparkExecutionExecutor` now accepts those neutral batch payloads directly by projecting them to GX only at suite-coercion time. The in-process planner-to-executor seam is therefore neutral-capable even though downstream GX dispatch/runtime payloads still keep the current GX shape.
- The grouped planner also honors optional incremental-selection hints on the execution-hints contract, so a plan can narrow the resolved execution scope to selected partitions or changed slices instead of always running the full resolved target set.
- `build_gx_run_plan_suite_ref_entity` now accepts `suite_id` / `suite_version` plus neutral artifact aliases such as `artifact_id` / `artifact_version` and `validation_artifact_id` / `validation_artifact_version`. That lets grouped dispatch callers hand internal artifact-ref payloads to the runtime boundary directly, where they are normalized once into the existing GX suite-ref entity shape.
- `build_gx_execution_run_entity`, `build_gx_execution_run_summary_entity`, and the supporting execution-status/history parsers now accept snake_case run metadata plus neutral artifact aliases for suite identifiers and versions. They also derive `engineType` from nested execution-contract or handoff payload metadata when it is not present as a top-level field, so execution-run normalization no longer depends on callers pre-shaping GX camelCase dicts.
- `build_gx_execution_run_list_query_entity` now accepts neutral artifact aliases such as `artifact_id` and `validation_artifact_id` for the suite selector, and `filter_gx_execution_run_summaries` now includes normalized `engineType` in its search haystack. Internal execution-run query flows can therefore use neutral selector terminology and still land on the existing GX repository/query contract at a single normalization boundary.
- `GxExecutionRunRepository.list_runs` and both concrete adapters now accept either a typed `GxExecutionRunListQueryEntity` or a raw mapping. The repository boundary itself calls `build_gx_execution_run_list_query_entity(...)`, which lets internal callers pass neutral suite-selector aliases directly into in-memory and Postgres execution-run filtering without duplicating GX query-entity construction beforehand.
- `list_gx_execution_run_summaries(...)` and `get_gx_execution_exception_analytics(...)` now rely on that repository-boundary normalization directly. They pass raw mappings like `{ "submitted_after": ..., "status": ... }` into `repository.list_runs(...)`, so the execution use-case layer no longer imports or constructs GX list-query entities just to satisfy the repository contract.
- `get_data_delivery_note(...)` in the data-catalog endpoint now follows the same pattern and calls `execution_run_repository.list_runs({})` directly. After that cleanup, `build_gx_execution_run_list_query_entity(...)` remains an internal normalization tool for the repository/domain boundary rather than an endpoint/use-case helper.

That keeps MR-02 incremental but useful: neutral contracts now exist for artifacts and run plans across both in-memory and Postgres-backed repository surfaces, while legacy GX-only mutation points are isolated to narrow projection boundaries.

### MR-02 Closure Result

- MR-02 is now closed: both neutral Postgres bridges have been replaced with direct neutral storage paths.
- Seeded GX-shaped payloads can still be normalized at the repository read boundary where required, which keeps seeded compatibility intact while the stored table ownership is now neutral.
- The remaining follow-on work belongs to MR-03 and later slices, not to repository generalization.

## MR-03 Early Slice

The first MR-03 slice starts threading `engine_type` through a real application path without attempting a repo-wide runtime-contract rewrite.

### MR-03 Early Output

1. Delivery-linked execution candidate payloads now include `engine_type` for both artifact and run-plan selections.
2. Delivery-linked execution receipts now expose `resolved_engine_type` so the API contract records the runtime chosen for execution.
3. The delivery-linked orchestrator now records `engineType` in the runtime delivery snapshot, grouped suite references, and enqueue payload so the grouped-dispatch handoff preserves runtime identity end to end.
4. The grouped-dispatch runtime builders now persist `engine_type` into the typed execution contract and execution-run records, so worker-side GX contracts can inspect runtime identity without inferring it from delivery metadata.
5. The GX run-plan seed resolver now writes `engineType="gx"` into generated suite references for new single-suite and grouped-scope run-plan snapshots, aligning newly created plans with the deeper dispatch metadata seam.

### MR-03 Still Pending

- Grouped execution planning still requires `GxArtifactEnvelopeEntity`, so neutral artifacts are projected back to GX just before planning.
- Queue payload entities and downstream worker contracts are still GX-specific even though they now carry `engine_type` explicitly.
- A full second-engine dispatch path does not exist yet; unsupported `engine_type` values must still fail closed.

## MR-04 Draft Contract - Self-Built PySpark Executor Request

MR-04 defines the handoff contract for teams that want to run grouped batches in their own PySpark executor without coupling that executor to the current GX worker queue payload.

### MR-04 Deliverables

1. A versioned request contract package at [docs/contracts/self-built-pyspark-executor-request/v1/schema.json](../contracts/self-built-pyspark-executor-request/v1/schema.json).
2. Example payloads showing one grouped batch, resolved source binding, explicit run traceability, and embedded neutral validation artifacts.
3. Clear fail-fast semantics for unsupported engine types, unresolved source bindings, and missing executor capabilities.

### MR-04 Contract Intent

- Keep the integration boundary above the runtime-neutral validation artifact and grouped-planning seams.
- Carry grouped batch context, source binding, and run traceability in snake_case so a self-built executor can run without reconstructing internal API state.
- Keep `executor_kind` separate from `engine_type`, so the contract can describe a custom PySpark execution path while preserving the underlying validation-engine identity. In MR-04 this means `executor_kind = self_built_pyspark` can legitimately execute `engine_type = gx` artifacts.
- Avoid direct coupling to GX-only queue payloads or internal worker heartbeat semantics.
- Defer direct canonical compiler-output handoff until the compiler artifact itself is published as a versioned contract package.

### MR-04 Current Output

- The draft request contract now exists as a contract package with JSON Schema plus JSON and YAML examples.
- The request embeds the neutral validation artifact envelope as the artifact input today, which lets the external executor consume explicit artifact identity and run-planning metadata without implicit repository lookups.
- The grouped batch contract now externalizes resolved source binding for Spark, JDBC, file, and materialized-join inputs, which keeps source resolution on the platform side and lets unsupported bindings fail closed before or during executor handoff.

## PySpark-Native Artifact Contract Draft

The PySpark-native artifact draft defines a third engine-native artifact family for cases where the compiled output is no longer a GX suite and should instead be executed as a PySpark-native validation plan.

### PySpark-Native Draft Output

1. A versioned contract package now exists at [docs/contracts/pyspark-native-artifact-envelope/v1/schema.json](../contracts/pyspark-native-artifact-envelope/v1/schema.json).
2. The contract carries PySpark-native check definitions, row predicates, traceability, and failure-output intent in snake_case.
3. The neutral validation artifact envelope now allows `engine_type = pyspark_native`, and the self-built PySpark executor request contract now accepts that engine type as a valid item payload.
4. The self-built executor request package now includes a second example payload for `engine_type = pyspark_native`.
5. Compiler-to-artifact mapping rules now live in [ABS_1_PYSPARK_NATIVE_COMPILER_MAPPING.md](./ABS_1_PYSPARK_NATIVE_COMPILER_MAPPING.md).
6. The grouped PySpark executor seam now accepts `pyspark_native` validation artifacts through the neutral validation-artifact projection path for supported single-object plans, so native plans can flow through the existing runtime boundary without falling back to GX.

### PySpark-Native Draft Intent

- Distinguish a true PySpark-native validation artifact from the separate concern of using custom PySpark as an alternate executor for `gx` artifacts.
- Keep `engine_target = pyspark` while making `engine_type = pyspark_native` explicit, so runtime substrate and validation semantics remain separate concepts.
- Allow later compiler work to target PySpark-native plans directly without having to overload GX-only envelope semantics.
- Keep current Grafana dashboards, alert names, and panel titles GX-scoped until a non-GX runtime actually emits production telemetry; renaming the observability surface ahead of runtime support would make the dashboards less accurate, not more general.

## Increment 1 - Contract and Registry Baseline

The first increment should land the shared contract and registry baseline that the later execution work can build on. Existing GX suite orchestration work already covers part of this shape, so this increment should extend the current foundation rather than reintroduce it.

### Increment 1 Scope

- Canonical GX suite artifact envelope and identifier semantics
- GX suite registry logical schema and storage contract
- Retrieval API shape for object, object version, dataset, and product scopes
- Clear separation between assignment scope and resolved execution scope
- Minimal validation around malformed or ambiguous scope requests

### Increment 1 Deliverables

1. Canonical suite artifact envelope for v1 payloads.
2. Registry model that stores suite identity, version, scope, and provenance.
3. Retrieval API contract with explicit scope filtering rules.
4. Validation rules that fail fast on ambiguous or unsupported scope input.
5. Documentation alignment with the existing GX orchestration contract.

### Increment 1 Exit Criteria

- A suite artifact can be described consistently across the feature and implementation docs.
- The registry schema is stable enough for later execution and persistence work.
- Retrieval semantics are explicit before any execution batching is added.
- Existing GX suite orchestration notes can be treated as the implementation reference for this baseline.

### Increment 1 Backlog

1. [x] (ABS1-GX-01) Define canonical abstraction contract.
   - Separate rule intent, assignment scope, and resolved execution scope.
   - Preserve stable identifiers across compile and execution phases.
   - Fail fast when scope resolution is ambiguous or incomplete.

   Implemented by the canonical GX artifact envelope in [docs/contracts/gx-artifact-envelope/v1/schema.json](../contracts/gx-artifact-envelope/v1/schema.json), [docs/contracts/gx-artifact-envelope/v1/example.json](../contracts/gx-artifact-envelope/v1/example.json), and [docs/contracts/gx-artifact-envelope/v1/example.yaml](../contracts/gx-artifact-envelope/v1/example.yaml), plus the phase-A contract and registry baseline in [DQ_7_4_GX_SUITE_ORCHESTRATION_IMPLEMENTATION_DETAILS.md](./DQ_7_4_GX_SUITE_ORCHESTRATION_IMPLEMENTATION_DETAILS.md).

2. [x] (ABS1-GX-02) Implement GX suite registry.
   - Store suite artifacts as first-class retrievable objects.
   - Persist suite versioning and provenance metadata.
   - Expose registry lookup by suite id and scope.

   Implemented by the `gx_suite_registry`, `gx_suite_execution_target_map`, `gx_suite_rule_map`, and `gx_suite_status_history` tables, together with the Phase A write, status, and retrieval APIs in [DQ_7_4_GX_SUITE_ORCHESTRATION_IMPLEMENTATION_DETAILS.md](./DQ_7_4_GX_SUITE_ORCHESTRATION_IMPLEMENTATION_DETAILS.md).

3. [x] (ABS1-GX-03) Add suite retrieval APIs.
   - Support retrieval by data object, data object version, dataset, and data product.
   - Return a not-found error when no suite exists for the requested scope.
   - Reject unsupported or malformed scope filters explicitly.

   Implemented by the Phase A retrieval API contract in [DQ_7_4_GX_SUITE_ORCHESTRATION_IMPLEMENTATION_DETAILS.md](./DQ_7_4_GX_SUITE_ORCHESTRATION_IMPLEMENTATION_DETAILS.md), including `GET /rulebuilder/v1/gx/suites`, `GET /rulebuilder/v1/gx/suites/{suiteId}`, and the scope validation rules for `dataObjectId`, `dataObjectVersionId`, `datasetId`, and `dataProductId`.

## Increment 2 - Grouped Execution and Adapter Support

The second increment should take the registered artifacts and make them executable at scale by adding grouped runtime behavior and adapter coverage.

### Increment 2 Scope

- Grouped execution by data object version
- One PySpark session per execution batch where possible
- Pluggable data source adapters for Spark, JDBC, and files
- Fail-fast handling for unsupported adapters

### Increment 2 Deliverables

1. Grouped execution path keyed by data object version.
2. PySpark session reuse per execution batch where practical.
3. Data source adapter contract covering Spark, JDBC, and file-based readers.
4. Explicit rejection of unsupported runtime adapters.

### Increment 2 Exit Criteria

- Suites can be executed in grouped batches without changing the registry baseline.
- Data loading is isolated from suite compilation.
- Unsupported runtime paths fail fast instead of silently falling back.

### Increment 2 Backlog

4. [x] (ABS1-GX-04) Implement grouped execution.
   - Group suites by data object version.
   - Use one PySpark session per execution batch where possible.
   - Avoid repeated runtime spin-up and spin-down overhead.

   Implemented by the grouped planner and PySpark executor in [API7 Real DQ Rule Execution Milestone](./API_7_REAL_DQ_RULE_EXECUTION_MILESTONE.md) and [API-7 Real DQ Rule Execution](../features/API_7_REAL_DQ_RULE_EXECUTION.md), which both batch compatible suites by `dataObjectVersionId` and run grouped batches in one Spark session where possible.

5. [x] (ABS1-GX-05) Add pluggable data source adapters.
   - Support Spark DataFrames, JDBC-backed sources, and file-based readers.
   - Keep source loading isolated from suite compilation.
   - Reject unsupported adapters explicitly.

   Implemented by the data source strategy and adapter contract in [DQ_7_4_GX_SUITE_ORCHESTRATION_IMPLEMENTATION_DETAILS.md](./DQ_7_4_GX_SUITE_ORCHESTRATION_IMPLEMENTATION_DETAILS.md), which defines Spark DataFrames, JDBC-backed sources, file-based readers, and the adapter methods `resolve_asset(scope)`, `load_dataframe(asset_ref)`, `materialize_primary_key(df, primary_key_config)`, and `emit_validation_target(df, gx_context)`.

## Increment 3 - Persistence Separation and Observability

The third increment should harden the runtime contract by separating persisted outcomes from exception detail and adding the observability needed to operate the system.

### Increment 3 Scope

- Separate persistence for aggregate outcomes and exception records
- Minimal exception record schema
- Structured logging, metrics, tracing, and validation tests

### Increment 3 Deliverables

1. Result persistence split between rule/result storage and exception storage.
2. Minimal exception record schema with primary key, ruleId, and violation reason.
3. Observability and validation coverage for compile, retrieval, execution, and persistence paths.

### Increment 3 Exit Criteria

- Aggregate outcomes and exception records are stored separately.
- The exception store contains only the minimum violation facts required for downstream use.
- The implementation emits enough telemetry to validate compile and execution failures.

Current status: the persistence split is in place, and the exception-storage path now enforces a minimal base violation fact (`dataPrimaryKey`, `ruleId`, `violationReason`) with optional operational metadata separated into `ops` / `ops_metadata`. The repository-backed schema has now been migrated and validated against the live local Postgres integration slice. Increment 3 is complete: observability primitives are implemented and the end-to-end validation passes now cover compile, retrieval, execution, and persistence.

### Increment 3 Backlog

6. [x] (ABS1-GX-06) Separate result persistence.
   - Store aggregate outcomes in the rule/result database.
   - Store exception records in a dedicated exception store.
   - Preserve the ABS-1.6 separation model.

   Implemented by API-7 Phase 4 persistence in [API_7_REAL_DQ_RULE_EXECUTION_MILESTONE.md](./API_7_REAL_DQ_RULE_EXECUTION_MILESTONE.md) and [API_7_REAL_DQ_RULE_EXECUTION.md](../features/API_7_REAL_DQ_RULE_EXECUTION.md), which store run metadata in the rule/result store and row-level violations in a separate exception store scoped to `dataObjectVersionId`.

7. [x] (ABS1-GX-07) Enforce minimal exception record schema.
   - Persist only primary key, ruleId, and violation reason in the base exception record.
   - Keep any optional operational metadata separate from the violation fact.
   - Avoid raw payload storage in the initial scope.

   Implemented: the exception-store boundary in [DQ_7_4_GX_SUITE_ORCHESTRATION_IMPLEMENTATION_DETAILS.md](./DQ_7_4_GX_SUITE_ORCHESTRATION_IMPLEMENTATION_DETAILS.md) is now enforced in both object storage and the repository-backed DB path. The Alembic head `20260418_0024` has been applied to the live local Postgres database, and the ORM schema plus GX retrieval integration slice now validate that contract successfully.

   Repository-backed DB migration target: keep `data_object_version_id`, `id`, `execution_run_id`, `rule_id`, `detected_at`, `created_at`, and `updated_at` as relational columns because they support scope isolation, run scoping, rule filtering, and time ordering. Use `data_primary_key` and `violation_reason` as the base fact columns, move optional metadata such as `suite_id`, `suite_version`, `rule_version_id`, `correlation_id`, and `failure_class` into `ops_metadata_json`, and remove `details_json` from the base exception row. In the current prototype path, callers are expected to write the canonical contract directly and the Alembic migration recreates `gx_execution_violations` accordingly rather than translating legacy rows.

8. [x] (ABS1-GX-08) Add observability and validation tests.
   - Emit structured logs, metrics, and traces for compile, retrieval, execution, and persistence.
   - Track suite compile duration, batch duration, and failure counts.
   - Verify grouped execution, scope retrieval, and failure handling.

   Split status:
   - [x] (ABS1-GX-08a) Add structured logs and tracing on major GX API and worker surfaces.
   - [x] (ABS1-GX-08b) Add metrics, dashboards, and alert baselines for major GX surfaces.
   - [x] (ABS1-GX-08c) Validate compile and retrieval observability end to end in one pass.
   - [x] (ABS1-GX-08d) Validate execution and persistence observability end to end.

   Completed: the API-7 observability phase in [API_7_REAL_DQ_RULE_EXECUTION_MILESTONE.md](./API_7_REAL_DQ_RULE_EXECUTION_MILESTONE.md), the GX logging and monitoring checklist in [docs/technical/LOGGING_AND_MONITORING_POLICY_IMPLEMENTATION_CHECKLIST.md](../technical/LOGGING_AND_MONITORING_POLICY_IMPLEMENTATION_CHECKLIST.md), and the GX worker / API monitoring panels and alerts now have validation coverage across compile, retrieval, execution, and persistence.

   ABS1-GX-08c completion evidence:
   - Structured log-field contract passes via [scripts/validate_logging_required_fields_contract.sh](../../scripts/validate_logging_required_fields_contract.sh).
   - Correlation propagation contract passes via [scripts/validate_correlation_propagation.sh](../../scripts/validate_correlation_propagation.sh).
   - Compile-path test slice passes via [dq-api/fastapi/tests/application/services/test_rule_compiler.py](../../dq-api/fastapi/tests/application/services/test_rule_compiler.py) and [dq-api/fastapi/tests/unit/test_rules_helpers_more.py](../../dq-api/fastapi/tests/unit/test_rules_helpers_more.py).
   - Retrieval-path integration slice passes via [dq-api/fastapi/tests/infrastructure/integration/test_gx_retrieval_integration.py](../../dq-api/fastapi/tests/infrastructure/integration/test_gx_retrieval_integration.py).
   - Monitoring baseline passes via [scripts/validate_monitoring_baseline.sh](../../scripts/validate_monitoring_baseline.sh), with dashboard and alert assets anchored in [observability/grafana/provisioning/dashboards/dq-api-observability.json](../../observability/grafana/provisioning/dashboards/dq-api-observability.json) and [observability/prometheus/alerts.yml](../../observability/prometheus/alerts.yml).

   ABS1-GX-08d completion evidence:
   - Execution API slice passes via [dq-api/fastapi/tests/api/test_execution_monitoring.py](../../dq-api/fastapi/tests/api/test_execution_monitoring.py), covering run retrieval, status history, failure reporting, and fail-fast worker availability.
   - Delivery-linked failure persistence slice passes via [dq-api/fastapi/tests/api/test_delivery_linked_execution_endpoints.py](../../dq-api/fastapi/tests/api/test_delivery_linked_execution_endpoints.py), confirming run summaries and row-level violations remain separated.
   - Exception storage slice passes via [dq-api/fastapi/tests/application/services/test_exception_storage.py](../../dq-api/fastapi/tests/application/services/test_exception_storage.py).
   - Worker execution and correlation slice passes via [dq-engine/tests/test_gx_dispatch_worker.py](../../dq-engine/tests/test_gx_dispatch_worker.py) and [dq-engine/tests/test_correlation_runtime_chain.py](../../dq-engine/tests/test_correlation_runtime_chain.py).
   - Monitoring baseline passes via [scripts/validate_monitoring_baseline.sh](../../scripts/validate_monitoring_baseline.sh), with runtime dashboard and alert assets anchored in [observability/grafana/provisioning/dashboards/dq-execution-monitoring.json](../../observability/grafana/provisioning/dashboards/dq-execution-monitoring.json) and [observability/prometheus/alerts.yml](../../observability/prometheus/alerts.yml).

   Local validation snapshot on 2026-04-18:
   - `python -m pytest tests/application/services/test_rule_compiler.py tests/unit/test_rules_helpers_more.py -q --no-cov` -> `33 passed`
   - `python -m pytest -m integration tests/infrastructure/integration/test_gx_retrieval_integration.py -q --no-cov` -> `10 passed`
   - `./scripts/validate_logging_required_fields_contract.sh` -> passed
   - `./scripts/validate_correlation_propagation.sh` -> passed
   - `./scripts/validate_monitoring_baseline.sh` -> passed
   - `python -m pytest tests/api/test_execution_monitoring.py -k 'report_gx_execution_run or get_gx_execution_run or get_gx_execution_run_status_history or schedule_gx_suite_run_rejects_missing_worker_heartbeat' -q --no-cov` -> `6 passed, 44 deselected`
   - `python -m pytest tests/application/services/test_exception_storage.py tests/api/test_delivery_linked_execution_endpoints.py -k 'exception_storage or delivery_linked_execution_failure_reports_run_and_violations_separately' -q --no-cov` -> `4 passed, 12 deselected`
   - `python -m pytest tests/test_gx_dispatch_worker.py tests/test_correlation_runtime_chain.py -q` -> `7 passed`

## Problem Statement

The platform needs a stable execution abstraction so rule definitions are not coupled to a specific runtime or storage shape.

What is needed is a service that:

- compiles rules into portable GX suites
- registers suites with both assignment scope and resolved execution scope
- retrieves suites by data object, data object version, dataset, or data product
- executes suites in grouped batches by data object version
- persists aggregate outcomes separately from exception records
- exposes structured diagnostics for compile and execution failures

## Proposed Model Split

- The rule model remains the source of truth for rule intent.
- The GX suite becomes the portable execution artifact.
- The suite registry stores the compiled artifact, assignment scope, and resolved execution-version references.
- The execution runtime consumes resolved suite artifacts and writes results to separate outcome and exception stores.

## Suggested API Shape

- POST /rulebuilder/v1/gx/suites
- GET /rulebuilder/v1/gx/suites/{suite_id}
- GET /rulebuilder/v1/gx/suites?data_object_id={id}
- GET /rulebuilder/v1/gx/suites?data_object_version_id={id}
- GET /rulebuilder/v1/gx/suites?dataset_id={id}
- GET /rulebuilder/v1/gx/suites?data_product_id={id}

## Acceptance Criteria

- Rules can be transformed into portable GX suites.
- GX suites are retrievable by object, object version, dataset, and product scope.
- Grouped execution reduces repeated runtime overhead.
- Aggregate outcomes and exception records remain stored separately.
- Exception records stay out of the rule/result database.
- Failure handling remains explicit and machine-readable.

## Related references

- [ABS-1 definition](../features/ABS_1_EXECUTION_ABSTRACTION.md)
- [DQ_7_4 GX suite orchestration](./DQ_7_4_GX_SUITE_ORCHESTRATION_IMPLEMENTATION_DETAILS.md)
- [ABS-3 implementation details](./ABS_3_DELIVERY_LINKED_RULE_EXECUTION_IMPLEMENTATION_DETAILS.md)