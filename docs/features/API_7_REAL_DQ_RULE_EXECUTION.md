# API-7 Real DQ Rule Execution

Status: Done

Goal: Execute compiled DQ rules against real source data, not just generated mock data, by introducing a source-execution contract, a grouped PySpark executor, separate violation persistence, and explicit scheduling/dispatch.

Milestone doc: [API-7 Real DQ Rule Execution Milestone](../implementation-details/API_7_REAL_DQ_RULE_EXECUTION_MILESTONE.md)

Progress tracking lives in the milestone doc. This file is the stable contract and architecture narrative.

For a concise checklist of known gaps and newly proposed requirements, see the milestone doc sections “Open Items / Missing Steps (Tracking)” and “Proposed Requirements (New)”.

Note: The lists below use stable IDs (e.g. `API7-F-P1-01`) so items can be referenced unambiguously. Checkboxes reflect current implementation status and should stay aligned with the milestone doc.

## Phase 1: Execution Contract

- [x] (API7-F-P1-01) Define the canonical runtime chain: rule version -> compiled artifact -> GX suite envelope -> source target.
- [x] (API7-F-P1-02) Lock the primary execution identifiers: `ruleId`, `ruleVersionId`, `gxSuiteId`, `gxSuiteVersion`, `dataObjectVersionId`.
- [x] (API7-F-P1-03) Keep generated-data testing as a separate flow and do not merge it into the real executor path.
- [x] (API7-F-P1-04) Confirm the compiler emits everything the executor needs without reparsing UI rule state.

### Draft Contract Shape

- [x] (API7-F-P1-05) `executionContract` is the runtime handoff from the GX suite envelope to the executor.
- [x] (API7-F-P1-06) `executionContract.engineTarget` stays `pyspark` for API-7.
- [x] (API7-F-P1-07) `executionContract.executionShape` is `single_object` for direct object runs or `join_pair` for ETL-materialized joins.
- [x] (API7-F-P1-08) `executionContract.traceability` carries the immutable execution identifiers and must remain fail-fast when any required identifier is missing.
- [x] (API7-F-P1-09) For `single_object`, the executor consumes one resolved `dataObjectVersionId` directly.
- [x] (API7-F-P1-10) For `join_pair`, the executor consumes a landing-zone artifact produced by a separate ETL step; it must not perform the join itself.
- [x] (API7-F-P1-11) The landing-zone materialization contract must identify both source inputs, the join shape, and the produced output location before the executor can start.
- [x] (API7-F-P1-12) If any required source input, landing-zone artifact, or traceability field is missing, the runtime must fail fast.

## Phase 2: Source Resolution and Planning

- [x] (API7-F-P2-01) Add a source-data resolver that maps assignment scope to active `dataObjectVersionId` targets.
- [x] (API7-F-P2-02) Resolve logical source versions to physical locations, datasets, or tables.
- [x] (API7-F-P2-03) Fail fast when a required source mapping is missing or inactive.
- [x] (API7-F-P2-04) Add a grouped planner that batches compatible suites by `dataObjectVersionId` for shared Spark execution.

## Phase 3: Real Source Execution

- [x] (API7-F-P3-01) Implement the first PySpark executor for compiled rules or GX suite envelopes.
- [x] (API7-F-P3-02) Run grouped batches in one Spark session where possible.
- [x] (API7-F-P3-03) Return explicit run status, timestamps, diagnostics, and correlation ids for each batch.
- [x] (API7-F-P3-04) Add an explicit backend trigger for on-demand source-data runs.

## Phase 4: Persistence and Lifecycle

- [x] (API7-F-P4-01) Store run metadata, status transitions, and diagnostics in the rule/result store.
- [x] (API7-F-P4-02) Write row-level violations to a separate exception store or schema, scoped strictly to a single `dataObjectVersionId`.
- [x] (API7-F-P4-03) Never store violation rows for different data objects in the same logical partition or access path.
- [x] (API7-F-P4-04) Keep the violation schema minimal: primary key, `ruleId`, execution ids, source target, `dataObjectVersionId`, and failure reason.
- [x] (API7-F-P4-05) Record pending, running, succeeded, failed, and cancelled states explicitly.

## Phase 5: Scheduling and Dispatch

- [x] (API7-F-P5-01) Add scheduling only after manual execution is stable.
- [x] (API7-F-P5-02) Reuse the same planner and executor contract for scheduled runs.
- [x] (API7-F-P5-03) Queue scheduled runs through the shared dispatch mechanism; the current Redis-backed `gx-execution:dispatch` queue is the first implementation and should broaden behind the same contract rather than creating runtime-specific scheduling paths.
- [x] (API7-F-P5-04) Keep the schedule handoff explicit with `scheduledAt`, `queueMessageId`, and `executorTarget`.
- [x] (API7-F-P5-05) Never silently fall back to synchronous execution when a worker is required.

Scheduling-time convention:
- Canonical scheduled timestamps are UTC instants.
- The UI may accept and display local time for operator convenience, but it converts to and from UTC at the API boundary.
- Timezone-native scheduling is out of scope. The product does not model schedules like “09:00 Europe/Amsterdam” or persist timezone identifiers as part of schedule semantics.

Current boundary:
- The implemented UX covers direct scheduled-run submission for active GX suites.
- The run-plan lifecycle now includes explicit draft, review, activation, and audit-history records for scheduled runs.
- Submitting a run-plan version for validation now invokes the GX plan validator and updates the version to `pending_review` or `validation_failed` based on the outcome.
- The Governance UI now also surfaces the GX run plan lifecycle matrix with explicit activation-requested and deactivation-requested states so the pending approval facts stay visible.

## Phase 6: Observability and UX

- [x] (API7-F-P6-01) Expose run state in the monitoring UI.
- [x] (API7-F-P6-02) Expose queue position in the monitoring UI.
- [x] (API7-F-P6-03) Expose executor progress (beyond lifecycle state transitions) in the monitoring UI.
- [x] (API7-F-P6-04) Add structured logs/metrics/tracing for execution surfaces, with GX as the first concrete emitter.
- [x] (API7-F-P6-05) Alert on missing source mappings.
- [x] (API7-F-P6-06) Alert on repeated execution failures.
- [x] (API7-F-P6-07) Alert on unavailable executor dependencies.

Monitoring convention:
- The top-level Execution Monitoring dashboard is runtime-agnostic and aggregates shared queue/run/status/transition/latency/results/failures/compile/throughput/heartbeat categories across executors.
- Shared Prometheus metric families and labels for that dashboard are defined in [EXECUTION_MONITORING_METRIC_TAXONOMY.md](../technical/EXECUTION_MONITORING_METRIC_TAXONOMY.md).
- Runtime-specific dashboards such as GX detail views can be added later without replacing the aggregated operational dashboard.

## Acceptance Criteria

- [x] (API7-F-AC-01) A compiled rule can execute against one real source target and persist a completed run record.
- [x] (API7-F-AC-02) Multiple rules sharing one `dataObjectVersionId` execute in a grouped batch.
- [x] (API7-F-AC-03) Missing source mappings or unavailable executor dependencies fail fast with explicit errors.
- [x] (API7-F-AC-04) Violations are written outside the rule/result database and remain isolated per `dataObjectVersionId`.
- [x] (API7-F-AC-05) Scheduled runs are enqueued explicitly for worker dispatch instead of falling back to ad hoc synchronous execution.
- [x] (API7-F-AC-06) The monitoring UI can display the run lifecycle for real source execution.
- [x] (API7-F-AC-07) Scheduling plans can be created as to-be drafts, validated or reviewed, and activated separately from executable scheduled runs.

