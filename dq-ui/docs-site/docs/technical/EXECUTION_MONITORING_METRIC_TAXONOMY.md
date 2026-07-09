# Execution Monitoring Metric Taxonomy

Purpose: define the shared Prometheus metric families and label rules that back the top-level Execution Monitoring dashboard across all executors.

Related policy: [LOGGING_AND_MONITORING_POLICY_ISO27001.md](/docs/technical/LOGGING_AND_MONITORING_POLICY_ISO27001/)
Related dashboard semantics: [EDR-005-OBS execution monitoring dashboard status and activity semantics](/docs/engineering-decisions/EDR-005-OBS-execution-monitoring-dashboard-status-and-activity-semantics/)
Related execution feature: [API_7_REAL_DQ_RULE_EXECUTION.md](/docs/features/current/API_7_REAL_DQ_RULE_EXECUTION/)

## Scope

This taxonomy applies to any runtime or service that contributes to the shared Execution Monitoring dashboard, including:
- platform-owned executors such as GX-backed workers
- future runtime implementations such as `pyspark_native` or Soda-backed executors
- API- or scheduler-side services that emit compile, dispatch, or run-lifecycle telemetry for those runtimes

This taxonomy does not replace runtime-specific metrics for deep drilldown. Runtime-specific metrics may still exist, but the top-level Execution Monitoring dashboard must be supportable from the shared metric families below.

## Design Rules

- The top-level dashboard is runtime-agnostic and aggregates shared execution categories across executors.
- Shared metric names use the `dq_` prefix and avoid runtime-specific names such as `gx` in the canonical series name.
- Labels must stay low-cardinality and enumerable.
- High-cardinality identifiers such as `run_id`, `rule_id`, `suite_id`, `correlation_id`, `data_object_version_id`, and free-form error text MUST NOT be emitted as Prometheus labels.
- If a runtime cannot emit the shared metric categories required for the top-level dashboard, that gap must be treated as an explicit implementation gap or approved exception, not hidden behind dashboard naming.

## Required Shared Labels

The following labels are the shared execution-monitoring vocabulary.

| Label | Required on | Allowed values / semantics |
| --- | --- | --- |
| `executor` | executor-emitted metrics and dispatch/heartbeat metrics | Stable executor implementation identifier such as `gx`, `pyspark_native`, `soda` |
| `engine_type` | artifact/run/compile metrics | Validation-engine identity such as `gx`, `pyspark_native`, `soda` |
| `service` | all shared metrics where service ownership matters | Stable emitting service identifier such as `dq-api`, `dq-engine`, `dq-db` |
| `status` | current-run gauge family | Canonical lifecycle state such as `pending`, `running`, `succeeded`, `failed`, `cancelled` |
| `from_status` | transition counter family when available | Prior canonical lifecycle state |
| `to_status` | transition counter family | Destination canonical lifecycle state |
| `execution_shape` | throughput/dispatch metrics where relevant | Stable planning shape such as `single_object`, `join_pair`, `grouped_object` |
| `result` | compile/result/failure families | Controlled enum such as `passed`, `failed`, `accepted`, `succeeded` |
| `operation` | compile/dispatch families | Controlled operation name such as `compile_artifact`, `publish_artifact`, `start_run`, `schedule_run`, `dispatch_batch` |
| `phase` | latency histogram family | Controlled phase such as `dispatch`, `execution`, `source_read` |
| `queue_key` | heartbeat metrics only | Stable queue identifier such as `dq-gx:execution-dispatch` |
| `queue_type` | queue telemetry | Stable queue purpose such as `natural_language_draft`, `profiling`, `gx_execution`, `test_data_materialization` |

Label rules:
- `executor` identifies the implementation that executes or owns the runtime path.
- `engine_type` identifies the artifact semantics. It may differ from `executor` when one executor can run multiple artifact families.
- `result`, `status`, `operation`, `phase`, and `execution_shape` must stay controlled enums documented in code or contract docs.
- `queue_key` is allowed only for low-cardinality queue identity and must not contain generated IDs.
- `queue_type` must be a controlled enum owned by the emitting service, not a free-form queue display name.

## Canonical Metric Families

### 1. Current Runs by Status

| Canonical metric | Type | Required labels | Meaning |
| --- | --- | --- | --- |
| `dq_execution_runs` | gauge | `executor`, `engine_type`, `service`, `status` | Current number of active or persisted runs in each lifecycle state |

This metric powers panels such as pending runs, running runs, and current runs by status.

### 2. Run Transitions

| Canonical metric | Type | Required labels | Meaning |
| --- | --- | --- | --- |
| `dq_execution_run_transitions_total` | counter | `executor`, `engine_type`, `service`, `to_status` | Total count of run transitions into a lifecycle state |

Recommended label:
- `from_status` when available from the emitting service without inflating cardinality.

### 3. Execution Latency

| Canonical metric | Type | Required labels | Meaning |
| --- | --- | --- | --- |
| `dq_execution_latency_ms` | histogram | `executor`, `engine_type`, `service`, `phase` | Latency distribution for execution phases such as dispatch, execution, or source read |

The shared dashboard should read p95 or similar quantiles from this family.

### 4. Execution Results

| Canonical metric | Type | Required labels | Meaning |
| --- | --- | --- | --- |
| `dq_execution_results_total` | counter | `executor`, `engine_type`, `service`, `result` | Validation result counts, typically `passed` and `failed` |

### 5. Execution Failures

| Canonical metric | Type | Required labels | Meaning |
| --- | --- | --- | --- |
| `dq_execution_failures_total` | counter | `executor`, `engine_type`, `service` | Count of execution failures that prevented or interrupted successful completion |

Optional low-cardinality label:
- `failure_kind` with a controlled enum such as `dependency_unavailable`, `timeout`, `contract_invalid`, `runtime_error`

### 6. Compile Activity

| Canonical metric | Type | Required labels | Meaning |
| --- | --- | --- | --- |
| `dq_execution_compile_events_total` | counter | `engine_type`, `service`, `operation`, `result` | Compile or publish outcomes for execution artifacts |

Recommended operations:
- `compile_artifact`
- `publish_artifact`

### 7. Dispatch and Throughput

| Canonical metric | Type | Required labels | Meaning |
| --- | --- | --- | --- |
| `dq_execution_dispatch_events_total` | counter | `executor`, `engine_type`, `service`, `operation`, `result` | Accepted or completed dispatch/start/schedule events that feed throughput panels |

Recommended additional label:
- `execution_shape` for grouped throughput views.

### 8. Executor Heartbeat

| Canonical metric | Type | Required labels | Meaning |
| --- | --- | --- | --- |
| `dq_executor_heartbeat_timestamp_seconds` | gauge | `executor`, `service`, `queue_key` | Unix timestamp of the most recent executor heartbeat |
| `dq_executor_heartbeat_ttl_seconds` | gauge | `executor`, `service`, `queue_key` | Expected heartbeat freshness threshold used for stale-heartbeat alerting |

### 9. Supplemental Run-Health Gauges

These gauges are optional but allowed on the top-level dashboard when they are emitted or derived in a runtime-agnostic shape.

| Canonical metric | Type | Required labels | Meaning |
| --- | --- | --- | --- |
| `dq_execution_stale_running_runs` | gauge | `executor`, `engine_type`, `service` | Number of currently stale running executions according to the platform freshness rule |
| `dq_execution_oldest_running_age_seconds` | gauge | `executor`, `engine_type`, `service` | Age in seconds of the oldest currently running execution |

### 10. Async Queue Telemetry

These metrics are supplemental for execution-adjacent async work such as data-definition automation, profiling dispatch, and test-data materialization. They let shared dashboards discover new queues by labels instead of adding queue-specific panels.

| Canonical metric | Type | Required labels | Meaning |
| --- | --- | --- | --- |
| `dq_queue_backlog` | gauge | `service`, `queue_type`, `queue_key` | Current queue length for a configured async queue |
| `dq_queue_events_total` | counter | `service`, `queue_type`, `stage`, `result` | Queue lifecycle events such as enqueue, start, completion, or failure |

## Dashboard Category Mapping

The top-level Execution Monitoring dashboard should map to the taxonomy as follows:

| Dashboard category | Canonical metric family |
| --- | --- |
| Pending runs / Running runs / Current runs by status | `dq_execution_runs` |
| Run transitions | `dq_execution_run_transitions_total` |
| Executor latency | `dq_execution_latency_ms` |
| Execution results and failures | `dq_execution_results_total`, `dq_execution_failures_total` |
| Compile success/failure trend | `dq_execution_compile_events_total` |
| Run throughput by execution shape | `dq_execution_dispatch_events_total` |
| Executor heartbeat age vs threshold | `dq_executor_heartbeat_timestamp_seconds`, `dq_executor_heartbeat_ttl_seconds` |
| Stale running / oldest running age | `dq_execution_stale_running_runs`, `dq_execution_oldest_running_age_seconds` |
| Async queue backlog / queue activity | `dq_queue_backlog`, `dq_queue_events_total` |

## Legacy GX Mapping

The current GX implementation is the first concrete emitter and still exposes legacy GX-specific series. Until the runtime implementation is migrated, recording rules or dashboard queries may map the legacy series into the canonical categories below.

| Legacy series | Canonical family |
| --- | --- |
| `gx_execution_runs_total` | `dq_execution_runs` |
| `gx_execution_run_transitions_last_24h_total` | `dq_execution_run_transitions_total` |
| `dq_gx_worker_execution_duration_ms_milliseconds_bucket` | `dq_execution_latency_ms{phase="execution"}` |
| `dq_gx_worker_source_read_duration_ms_milliseconds_bucket` | `dq_execution_latency_ms{phase="source_read"}` |
| `dq_gx_worker_expectation_results_total` | `dq_execution_results_total` |
| `dq_gx_worker_failure_total` | `dq_execution_failures_total` |
| `dq_gx_operation_events_total{operation="save_suite",...}` | `dq_execution_compile_events_total` |
| `dq_gx_operation_events_total{operation=~"start_suite_run\|schedule_suite_run",...}` | `dq_execution_dispatch_events_total` |
| `dq_gx_worker_heartbeat_timestamp_seconds` | `dq_executor_heartbeat_timestamp_seconds` |
| `dq_gx_worker_heartbeat_ttl_seconds` | `dq_executor_heartbeat_ttl_seconds` |
| `gx_execution_runs_stale_running_total` | `dq_execution_stale_running_runs` |
| `gx_execution_runs_oldest_running_age_seconds` | `dq_execution_oldest_running_age_seconds` |

Migration rule:
- New runtimes should emit the canonical `dq_` execution-monitoring families directly.
- Existing GX telemetry may continue to emit legacy series while compatibility rules or updated dashboard queries bridge the gap.
- In the current implementation, worker and API code emit canonical latency/result/failure/compile/dispatch/heartbeat families directly, while Prometheus recording rules bridge the remaining DB-exported GX run-state gauges into canonical names.
- GX-specific alerts and drilldown dashboards should prefer canonical metric families filtered with `executor="gx"` or `engine_type="gx"` where a shared equivalent exists, and fall back to legacy GX-only series only for signals that do not yet have a canonical shared family.
- The top-level dashboard should converge on canonical metric names once at least one non-GX runtime is onboarded.

## Cardinality Guardrails

- Do not add `run_id`, `rule_id`, `suite_id`, `trace_id`, `correlation_id`, or object/version identifiers as labels.
- Do not add raw exception messages or stack traces as labels.
- Prefer controlled enums over free-form strings for `operation`, `result`, `status`, `phase`, and `failure_kind`.
- If a new dimension is needed for operational triage, prove that it is low-cardinality and shared across runtimes before adding it to the canonical taxonomy.

## ISO 27001 Baseline Impact

This taxonomy is part of the monitoring baseline required by [LOGGING_AND_MONITORING_POLICY_ISO27001.md](/docs/technical/LOGGING_AND_MONITORING_POLICY_ISO27001/):
- it enables the aggregated cross-executor Execution Monitoring dashboard required by Annex A 8.16 monitoring expectations
- it keeps observability evidence comparable across runtimes and services
- it reduces ambiguity in quarterly compliance review and incident evidence collection