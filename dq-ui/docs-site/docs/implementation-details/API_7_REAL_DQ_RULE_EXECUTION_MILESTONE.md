# API-7 Real DQ Rule Execution Milestone

Build a real rule-running pipeline that executes compiled DQ rules against source data, not just generated mock data. Keep generated-data testing intact, but make it a separate path from real source execution.

Related feature plan: [API-7 Real DQ Rule Execution](/docs/status/current/API_7_REAL_DQ_RULE_EXECUTION/)

## Phase 1: Contract
- [x] (API7-P1-01) Define the runtime chain: rule version -> compiled artifact -> GX suite envelope -> source target.
- [x] (API7-P1-02) Lock the primary execution identifiers: `ruleId`, `ruleVersionId`, `gxSuiteId`, `gxSuiteVersion`, `dataObjectVersionId`.
- [x] (API7-P1-03) Confirm the compiler emits everything the executor needs.
- [x] (API7-P1-04) Fail fast on missing or unresolved source targets.

### Draft Contract Shape
- `executionContract` is the runtime handoff from the GX suite envelope to the executor.
- `executionContract.engineTarget` remains `pyspark` for API-7.
- `executionContract.traceability` keeps the immutable execution identifiers.
- `executionContract.executionShape` is `single_object` for direct object runs or `join_pair` for ETL-materialized joins.
- `single_object` uses one resolved `dataObjectVersionId` directly.
- `join_pair` requires a separate landing-zone ETL artifact that materializes the join before the executor runs.
- The landing-zone contract must identify object A, object B, the join keys, and the produced output location.
- The executor must not join source objects itself.
- Missing source inputs, missing landing-zone artifacts, or missing traceability identifiers must fail fast.

## Phase 2: Resolution and Planning
- [x] (API7-P2-01) Add a source-data resolver for assignment scope to active `dataObjectVersionId` targets.
- [x] (API7-P2-02) Map logical source versions to physical datasets or tables.
- [x] (API7-P2-03) Add a grouped planner that batches compatible suites by `dataObjectVersionId`.

## Phase 3: Real Execution
- [x] (API7-P3-01) Implement the first PySpark executor for compiled rules or GX suite envelopes.
- [x] (API7-P3-02) Run grouped batches in one Spark session where possible and delegate validation to an injected Spark-aware runner.
- [x] (API7-P3-03) Return explicit run status, timestamps, diagnostics, and correlation ids.
- [x] (API7-P3-04) Add an explicit backend trigger for on-demand source-data runs.

## Phase 4: Persistence
- [x] (API7-P4-01) Store run metadata, status transitions, and diagnostics in the rule/result store.
- [x] (API7-P4-02) Write row-level violations to a separate exception store or schema, scoped strictly to a single `dataObjectVersionId`.
- [x] (API7-P4-03) Keep the violation schema minimal and isolated per `dataObjectVersionId`.
- [x] (API7-P4-04) Record pending, running, succeeded, failed, and cancelled states explicitly.
- The GX execution run lifecycle is now persisted in `gx_execution_runs` and `gx_execution_run_status_history` with explicit correlation ids and audit timestamps.

## Phase 5: Scheduling and Dispatch
- [x] (API7-P5-01) Add scheduling only after manual execution is stable.
- [x] (API7-P5-02) Reuse the same planner and executor contract for scheduled runs.
- [x] (API7-P5-03) Add queueing or worker dispatch only if it improves reliability or throughput.
- Never silently fall back to synchronous execution when a worker is required.
- GX scheduled runs now enqueue a Redis dispatch payload with `scheduledAt`, `queueMessageId`, `executorTarget`, and `dispatchMode`.

### How scheduling works today

Scheduling is now exposed in dq-made-easy through the Rule Execution & Monitoring screen, which lets a user pick a catalog scope, choose an active GX suite, submit a scheduled run, and immediately inspect the resulting run lifecycle.

Important scope boundary:
- The current implementation schedules an executable GX run directly.
- It does not create a separate persisted run-plan resource.
- It does not distinguish a draft / to-be run plan from an active run plan.
- It does not provide a review, approval, or activation step that promotes a to-be plan into an active plan.

To schedule a single GX run for a suite:

1) Identify the GX suite you want to run (`suite_id`) and (optionally) the `suiteVersion` you want to target.
2) Call the schedule endpoint:

`POST /api/rulebuilder/v1/gx/suites/&#123;suite_id&#125;/runs/schedule?suiteVersion=&lt;n&gt;`

Request body (snake_case):

```json
{
	"scheduled_at": "2026-04-06T13:15:00Z"
}
```

Notes:
- On success, the API responds `202 Accepted` and returns a dispatch handoff payload including `run_id` (same value as `queue_message_id`), plus queue metadata (`queue_key`, `dispatch_mode`, `executor_target`).
- This endpoint fails fast with `503` if the dispatch queue is unavailable / not configured.
- This endpoint also fails fast with `503` if no active `dq-engine-gx-worker` heartbeat is present in Redis, so runs are not accepted when they would otherwise remain stuck in `pending`.
- After scheduling, the monitoring UI can be used to inspect the persisted lifecycle by entering the returned run id.

## Phase 6: Observability
- [x] (API7-P6-01) Expose run state in the monitoring UI.
- [x] (API7-P6-02) Expose queue length and queue position in the monitoring UI.
- [x] (API7-P6-03) Expose executor progress (beyond lifecycle state transitions) in the monitoring UI.
- [x] (API7-P6-04) Add structured logs/metrics/tracing for GX surfaces.
- [x] (API7-P6-05) Alert on missing source mappings.
- [x] (API7-P6-06) Alert on GX failure events (including dispatch queue failures).
- [x] (API7-P6-07) Alert on unavailable executor dependencies.

## Open Items / Missing Steps (Tracking)

This is the short list of known gaps required for end-to-end, meaningful real execution. Detailed GX-suite orchestration backlog lives in [DQ-7.4 Great Expectations Suite Orchestration - Implementation Details](/docs/implementation-details/DQ_7_4_GX_SUITE_ORCHESTRATION_IMPLEMENTATION_DETAILS/).

- [x] (API7-OI-01) **Populate executable GX suites**: translate compiler output into a non-empty GX `expectations` list (or adopt an explicit alternative execution payload) so runs validate something real.
- [x] (API7-OI-02) **Define “runnable suite” validation** (fail-fast): starting/scheduling a run must reject placeholder artifacts (e.g., missing `execution_contract`, missing targets, or empty/no-op validations) with clear 4xx errors.
- [x] (API7-OI-03) **Worker consumption exists**: extend `dq-engine` to consume the Redis GX dispatch queue, execute the suite(s), and report results back to the API run lifecycle store.

Notes (current implementation)
- The worker runs as `dq-engine-gx-worker` (same image as `dq-engine`) and consumes `GX_EXECUTION_QUEUE_KEY` from Redis.
- It does **not** connect to Postgres directly. All lifecycle transitions + result summary/diagnostics are reported via the FastAPI **through Kong** (`/rulebuilder/v1/gx/runs/&#123;run_id&#125;/report`).
- Execution requires physical source mapping persisted in the data catalog DB (`data_object_versions.storage_uri`, `storage_format`, `storage_options_json`). The worker resolves these fields via the API.
- Initial execution path reads from S3-compatible storage (AIStor locally) using Spark and supports `parquet` and `delta` formats.
- Delivery-level reruns and latest-vs-pinned delivery selection are tracked in [API_7_DATA_DELIVERY_RESOLUTION.md](/docs/implementation-details/API_7_DATA_DELIVERY_RESOLUTION/).

Configuration notes (storage mapping)
- For each `data_object_version_id` you intend to execute, set its persisted location in Postgres:

```sql
UPDATE data_object_versions
SET storage_uri = 's3a://<bucket>/<path>',
	storage_format = 'parquet',
	storage_options_json = '{}'::jsonb
WHERE id = '<data_object_version_id>';
```

- The worker requires S3-compatible credentials + endpoint via env vars (`DQ_S3_ENDPOINT`, `DQ_S3_ACCESS_KEY`, `DQ_S3_SECRET_KEY`).
- The worker also requires API access via Kong: `KONG_INTERNAL_URL` (default `http://kong:8000`) plus OIDC client-credentials env vars.

## Generating test source data (Parquet/Delta on AIStor)

Before exercising the real-data execution pipeline, you can generate a small dataset for a specific `data_object_version_id` and materialize it to AIStor as an engine-supported format (`parquet` or `delta`).

Notes:
- This path is **API-driven and offloaded**: FastAPI enqueues a job to Redis, and a `dq-engine` worker writes the dataset to AIStor via Spark.
- The API enforces basic queue capacity limits (pending + in-flight) and fails fast with `429` when the queue is saturated.

Prerequisites:
- Start AIStor and the workers (for local: `./scripts/common_startup.sh --with-observability --force-build` starts the stack and workers).

API usage:

1) Enqueue a materialization job (snake_case):

`POST /api/rulebuilder/v1/test-data/materializations`

```json
{
	"data_object_version_id": "<data_object_version_id>",
	"sample_count": 1000,
	"output_format": "parquet"
}
```

2) Poll for completion:

`GET /api/rulebuilder/v1/test-data/materializations/&#123;request_id&#125;`

On success the response includes `result.output_uri` (an `s3a://...` path) which can be used as the source location for real-data GX runs.

Current limitation:
- Persisting the generated `output_uri` into `data_object_versions.storage_uri` is not yet exposed as an API operation; it currently requires an explicit DB update.

Authentication notes (worker -> Kong -> API)
- The worker does not support static bearer tokens.
- Configure Keycloak client-credentials for a service account and set `DQ_ENGINE_OIDC_ISSUER` (or `DQ_ENGINE_OIDC_TOKEN_URL`), `DQ_ENGINE_OIDC_CLIENT_ID`, and `DQ_ENGINE_OIDC_CLIENT_SECRET`. The worker will mint and auto-refresh access tokens.
- [x] (API7-OI-04) **Backend scheduled dispatch completes lifecycle**: backend-scheduled queued runs transition `pending -> running -> succeeded/failed` from the worker, and scheduling now fails fast when no active worker heartbeat is present.
- [x] (API7-OI-05) **Grouped scheduling by scope**: support scheduling a single grouped run per `data_object_version_id` (or dataset/product scope) that executes all applicable suites in one Spark session to avoid repeated source reads.
- [x] (API7-OI-06) **User-facing scheduled-run submission UX**: dq-made-easy provides a UI flow for selecting a scope, choosing an active GX suite, scheduling a run, and managing that scheduled run through the monitoring view.
- [x] (API7-OI-07) **Separate to-be run plans from active run plans**: introduce a first-class run-plan model so users can create a proposed plan, review or validate it, and explicitly activate it before it becomes executable scheduling behavior.
	- Partial slice implemented on 2026-04-10:
		- backend `POST/GET /gx/run-plans`, `GET /gx/run-plans/&#123;run_plan_id&#125;`, `POST /gx/run-plans/&#123;run_plan_id&#125;/versions`, `POST /gx/run-plans/&#123;run_plan_id&#125;/versions/&#123;run_plan_version_id&#125;/governance-state`, and `POST /gx/run-plans/&#123;run_plan_id&#125;/versions/&#123;run_plan_version_id&#125;/activate` now exist.
		- run-plan versions now carry explicit governance states including `pending_validation`, `validation_failed`, `pending_review`, `approved_pending_activation`, `active`, `superseded`, and `cancelled`.
		- an active logical plan can now spawn a new to-be branch under the same `run_plan_id`; the active version remains executable while the new version moves through governance.
		- activation now requires `approved_pending_activation`; it still reuses the existing GX scheduled-dispatch path and still fails fast when queue/worker dependencies are unavailable.
		- grouped-scope scheduling is now attached to the run-plan object shape (`planning_mode = grouped_scope` plus grouped selector snapshot), so `API7-OI-05` lands on the same model instead of a parallel scheduling surface.
		- grouped-scope scheduling and activation now use the grouped dispatch payload path, and the grouped API/worker smoke tests cover the end-to-end flow.
		- dq-made-easy now exposes an Administration > GX Run Plans screen for current-workspace plan listing, draft creation, draft version creation, and explicit activation.
	- Verified on 2026-04-12 with focused run-plan lifecycle smoke tests.

Notes (scope distinction)
- `API7-OI-04` is about backend scheduled-dispatch lifecycle execution for queued runs.
- `API7-OI-06` is about product/UI support so users can submit and inspect scheduled GX runs without calling the API directly.
- `API7-OI-07` is the missing lifecycle distinction between a to-be run plan and an active run plan.

## Draft Design: Run Plan Model and State Machine

This section describes the missing design needed if scheduling must distinguish a proposed plan from an active plan.

### Canonical entities

- `run_plan` is the user-managed scheduling object.
- `run_plan_version` is the immutable snapshot of plan content under review.
- `scheduled_run` remains the executable occurrence created from an active plan version or from an ad hoc schedule request.

### Why this split is needed

- A plan lifecycle is a governance concern.
- A scheduled run lifecycle is an execution concern.
- Mixing them makes it impossible to review, validate, or approve a proposed schedule without also making it executable immediately.

### Proposed `run_plan` shape

- `run_plan_id`: stable public identifier for the plan.
- `workspace_id`: owning workspace / scope root.
- `scope_selector`: canonical scope payload (for example object version, dataset, or product scope).
- `planning_mode`: `single_suite` or `grouped_scope`.
- `current_active_version_id`: nullable pointer to the active version.
- `status`: high-level lifecycle state for the plan.
- `created_by`, `created_at`, `updated_at`.

### Proposed `run_plan_version` shape

- `run_plan_version_id`: immutable version identifier.
- `run_plan_id`: parent plan.
- `gx_suite_selection`: selected suite ids / versions, or grouped planner selector.
- `schedule_definition`: timing payload such as one-time timestamp or recurring schedule expression.
- `execution_contract_snapshot`: frozen executor/planner inputs needed for later validation/audit.
- `validation_status`: explicit validation result.
- `review_status`: optional human governance decision.
- `effective_from`: when this version becomes active.
- `supersedes_version_id`: prior draft or active version if applicable.
- `created_by`, `created_at`.

Scheduling-time convention:
- All canonical scheduled timestamps are UTC-based instants.
- The UI may accept or display local time for operator convenience, but it must convert to and from UTC at the API boundary.
- Timezone-native scheduling semantics are out of scope: no persisted timezone identifier, no “run at 09:00 Europe/Amsterdam” behavior, and no activation logic based on user locale.

### Proposed state machine

`run_plan.status`:
- `draft`: editable to-be plan exists and is not yet submitted for validation/review.
- `pending_validation`: plan content is frozen pending automated validation.
- `validation_failed`: validation failed; cannot activate.
- `pending_review`: validation passed and governance review is required.
- `approved_pending_activation`: approved but not yet active because `effective_from` is in the future or activation has not been executed.
- `active`: this plan version is the executable plan used to create scheduled runs.
- `superseded`: replaced by a newer active version.
- `cancelled`: plan withdrawn and no longer activatable.

`scheduled_run.status` remains execution-oriented:
- `pending`, `running`, `succeeded`, `failed`, `cancelled`.

### Required transitions

1. `draft -> pending_validation`
	Triggered when a user submits a to-be plan for checking.
2. `pending_validation -> validation_failed`
	Triggered when planner, suite, dependency, or policy validation fails.
3. `pending_validation -> pending_review`
	Triggered when validation passes and governance review is required.
4. `pending_validation -> approved_pending_activation`
	Triggered when validation passes and no human review is required.
5. `pending_review -> approved_pending_activation`
	Triggered by explicit approval.
6. `approved_pending_activation -> active`
	Triggered by explicit activation or by reaching `effective_from`.
7. `active -> superseded`
	Triggered when a newer version becomes active.
8. `draft\|validation_failed\|pending_review\|approved_pending_activation -> cancelled`
	Triggered by explicit withdrawal.

### Fail-fast rules

- If plan validation is required and the validator is unavailable, the transition to `pending_review` or `approved_pending_activation` must fail fast.
- If activation requires a scheduler/worker subsystem and it is unavailable, activation must fail fast rather than silently creating an immediate active plan or direct run.
- If a plan is not `active`, it must not emit executable scheduled runs.
- Editing an active plan in place is not allowed; changes create a new to-be version.

### Minimal product behavior

- The current Rule Execution & Monitoring screen can remain the UX for direct scheduled-run submission.
- A separate run-plan screen is needed for draft/review/activation behavior.
- The UI should present draft/to-be plans and active plans as different objects with different actions.
- Monitoring should continue to show scheduled runs, not act as the source of truth for plan governance.

## Proposed Requirements (New)

These are new requirements proposed on 2026-04-07; they are not implemented yet.

- [ ] (API7-PR-01) **Suite versioning on rule lifecycle**: when a rule is activated or deactivated, generate a new `gx_suite_version` for that rule’s suite id (rather than overwriting in-place).
- [ ] (API7-PR-02) **Race-safe version allocation**: suite-version increments must be allocated atomically (database transaction/lock/sequence), not derived from timestamps, to avoid collisions when multiple lifecycle operations happen within the same second.
- [ ] (API7-PR-03) **Effective activation/deactivation time**: extend the approval/deactivation flow to accept a user-chosen timestamp (e.g., `effective_at` in snake_case) for when the rule becomes active/deactivated.
- [ ] (API7-PR-04) **No fallbacks on scheduling**: if scheduled lifecycle transitions require a scheduler/worker and it is unavailable, fail fast with explicit errors (no silent immediate activation/deactivation).
- [ ] (API7-PR-05) **Do not expose internal PK/FK ids in external APIs**: introduce stable public identifiers for external consumers and treat internal primary keys as implementation details; the UI may use internal ids, but externally-facing API contracts must not.
- [ ] (API7-PR-06) **Separate internal ids from ODCS identifiers**: treat ODCS data product identifiers as a distinct attribute (e.g., `odcs_data_product_id`) rather than overloading `data_product_id` / `dataProductId`.
- [ ] (API7-PR-07) **GX suite “to-be” generation + enforced validation before lifecycle transitions**: it must be possible to generate a *to-be* (proposed) GX suite for a rule lifecycle change and have it reviewed/tested before the rule is activated or deactivated.
    - Governance requires a new status value to represent “validation required / pending validation” (exact enum name TBD).
    - Enforcement rules:
      - A workspace admin can enforce this requirement for the workspace(s) they administer.
      - A cross-admin can enforce this requirement globally across all workspaces; when enabled globally, no user or workspace admin can overrule/disable it.
      - A user (or admin) can request a validation run/review, but cannot change whether enforcement is enabled.
    - Fail-fast behavior:
      - If enforcement is enabled and a lifecycle transition would occur without a validated/reviewed *to-be* GX suite, the API must reject the operation with an explicit 4xx/5xx error (no silent bypass).
      - If enforcement requires a validator/worker/scheduler subsystem and it is unavailable, the lifecycle transition must fail fast (no silent immediate activation/deactivation).

- [x] (API7-PR-08) **Airflow integration operator**: provide an Apache Airflow operator (and supporting packaging/docs) so Airflow DAGs can invoke DQ rule / GX suite execution via the existing API in a first-class way.
	- The operator must support triggering a run and (optionally) waiting/polling for completion.
	- Fail-fast behavior: if the API is unreachable, returns a non-success response, or the run transitions to a failed state, the Airflow task must fail (no silent retries beyond Airflow’s normal retry policy).
	- Observability: propagate a `correlation_id` (or accept one provided by Airflow) and surface `run_id` in logs/XCom for downstream tasks.
	- Testing approach:
		- Unit tests: contract-based tests that execute the operator code directly and mock the API surface (trigger + polling + terminal states).
		- Integration tests: run a minimal Airflow in a Docker container (no scheduler required) and execute a small DAG/task using the operator against a running dq-made-easy API.

- [ ] (API7-PR-09) **Airflow DAG generation for specific suites**: provide a way to generate (or export) Airflow DAG definitions that invoke the Airflow operator for a specific `gx_suite_id` (and optional version/schedule parameters), so Airflow can integrate with dq-made-easy with minimal manual DAG coding.
	- The generated DAG must be explicit about which suite (and version) it targets and which API endpoint it calls.
	- Fail-fast behavior: DAG generation must fail if required inputs/config (API URL, auth settings, suite identifiers) are missing.
	- Observability: generated tasks must pass through `correlation_id` and expose `run_id` (via XCom/logs) for downstream dependencies.

- [ ] (API7-PR-10) **User-initiated real-data test runs using a real GX suite**: a user must be able to trigger a test run against real source data using a non-placeholder, executable GX suite (real `expectations`), without activating/deactivating the rule.
	- The test run must execute through the same real-data resolution/planning/executor pipeline used for production runs.
	- The test run must not mutate governance lifecycle state (no implicit activation/deactivation); it is purely an execution.
	- Fail-fast behavior: the API must reject test-run requests when the GX suite is not runnable (e.g., empty/no-op expectations), required source mappings are missing, or required execution dependencies are unavailable.
	- Observability: return `run_id` and `correlation_id` and persist the run lifecycle like other real executions.

### Draft API Contract: `effective_at` for lifecycle transitions

This draft is intentionally minimal and biased toward explicit, fail-fast behavior.

#### API changes (approvals)

Add a new optional field to approval requests and approval responses:

- `effective_at` (string, RFC 3339 / ISO 8601 with timezone, e.g. `2026-04-07T13:15:00Z`)

Endpoints:

1) Create approval request

`POST /api/rulebuilder/v1/approvals`

Request body (snake_case):

```json
{
	"rule_id": "<rule_id>",
	"request_type": "deactivation",
	"comments": "optional",
	"effective_at": "2026-04-07T13:15:00Z"
}
```

Response body (snake_case) extends `ApprovalView` with `effective_at`:

```json
{
	"id": "<approval_id>",
	"rule_id": "<rule_id>",
	"status": "pending",
	"request_type": "deactivation",
	"effective_at": "2026-04-07T13:15:00Z",
	"requested_at": "2026-04-07T12:00:00Z"
}
```

2) Review approval request

`PUT /api/rulebuilder/v1/approvals/&#123;approval_id&#125;`

Request body (snake_case):

```json
{
	"status": "approved"
}
```

Behavior when `request_type == "deactivation"` and `status` becomes `approved`:

- If `effective_at` is **omitted**: treat as immediate deactivation (equivalent to `effective_at = now`).
- If `effective_at` is **present and &lt;= now**: deactivate immediately.
- If `effective_at` is **present and > now**: schedule the deactivation for that time.

Fail-fast scheduling rule:

- If `effective_at > now` but the scheduler/worker subsystem is unavailable, the API must fail the request with `503` and must not silently deactivate immediately.
- Preferred behavior is to leave the approval in its prior state (i.e., do not advance to `approved` if scheduling could not be created).

Note:
- Until a lifecycle scheduler exists, deactivation approvals that require future effect (i.e., `effective_at` in the future) cannot be approved and will fail fast.

#### Validation rules

- `effective_at` must be parseable as a timezone-aware timestamp (reject naive timestamps without timezone).
- If provided, `effective_at` must be >= current time (with at most a small clock-skew tolerance); otherwise return `422`.
- Attempts to change `effective_at` after an approval has been reviewed (terminal) should return `409`.

#### Error response shape (draft)

For lifecycle scheduling failures, return a machine-readable error body:

```json
{
	"error": "downstream_unavailable",
	"service": "lifecycle-scheduler",
	"message": "lifecycle-scheduler is unavailable",
	"correlation_id": "<uuid>"
}
```

#### Notes / Non-goals

- This draft covers approval-driven deactivation because that is already routed through `/api/rulebuilder/v1/approvals`.
- Activation `effective_at` is supported on `POST /api/rulebuilder/v1/rules/&#123;rule_id&#125;/activate` as an `effective_at` query parameter; until a lifecycle scheduler exists, future-dated activation fails fast.

## Acceptance Criteria
- A compiled rule can execute against one real source target and persist a completed run record.
- Multiple rules sharing one `dataObjectVersionId` execute in a grouped batch.
- Missing source mappings or unavailable executor dependencies fail fast with explicit errors.
- Violations are written outside the rule/result database.
- The monitoring UI can display the run lifecycle for real source execution.

## Tracked Work Items
- [x] `API-7.1` Source execution contract and runtime identifiers
- [x] `API-7.2` Source-data resolver service
- [x] `API-7.3` Grouped execution planner
- [x] `API-7.4` PySpark executor for real source runs
- [x] `API-7.5` Explicit run trigger endpoint or worker handoff
- [x] `API-7.6` Run metadata and lifecycle persistence
- [x] `API-7.7` Dedicated violation store/schema with strict `dataObjectVersionId` isolation
- [x] `API-7.8` Scheduling and dispatch integration
- [x] `API-7.9` Execution monitoring UI wiring
- [x] `API-7.10` Metrics, tracing, and alerting
- [x] `API-7.11` Integration tests and smoke path

## Milestones
- Milestone A: Contract (`API-7.1` to `API-7.2`)
- Milestone B: Planning (`API-7.3`)
- Milestone C: Executor (`API-7.4` to `API-7.5`)
- Milestone D: Persistence (`API-7.6` to `API-7.7`)
- Milestone E: Schedule/Dispatch (`API-7.8`)
- Milestone F: UX/Operations (`API-7.9` to `API-7.10`)
- Milestone G: Validation (`API-7.11`)

## Decisions
- Keep generated-data testing separate from real execution.
- Treat PostgreSQL/registry data as the source of execution metadata.
- Start with PySpark for the executor.
- Add scheduling after the manual run path is stable.
- Use fail-fast behavior whenever a required source mapping, executor, or scheduler dependency is unavailable.
