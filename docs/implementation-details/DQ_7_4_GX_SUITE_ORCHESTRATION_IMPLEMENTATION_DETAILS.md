# DQ-7.4 Great Expectations Suite Orchestration - Implementation Details

> **Deprecated:** Historical implementation note for the DQ-7.4 GX suite orchestration slice. New contract, lowering, assistant, and rollout guidance live in the DQ-7 DSL 2.0 docs.
> Start with [DQ-7 Rule DSL Contract](../technical/DQ-7_RULE_DSL_CONTRACT.md) and [DQ-7 Engine-Independent DSL Implementation Plan](DQ_7_ENGINE_INDEPENDENT_DSL_IMPLEMENTATION_PLAN.md).

Status: [~] Phase A Complete — Phase B Complete — Phase C Complete — Phase D Complete
Last updated: 2026-04-20
Related feature tracker: ../features/DQ_FEATURES.md
Related decision record: ../../architecture/adr/ADR-014-gx-suite-registry-pyspark-execution-and-exception-store-separation.md
Related compiler progress: ./DQ_7_3_RULE_COMPILER_IMPLEMENTATION_PROGRESS.md
Canonical contract: ../contracts/gx-artifact-envelope/v1/schema.json
Canonical example: ../contracts/gx-artifact-envelope/v1/example.json

## Goal

Implement the DQ-7.4 adapter and runtime so DQ rules are converted into Great Expectations (GX) suites and executed in a scalable, observable way across multiple data source types.

The neutral `validation_run_plans` contract remains the canonical run-plan surface. GX suite orchestration projects from that neutral plan model so current GX execution and future Soda or SQL run plans can flow through the same run and execution-plan interfaces.

Bookkeeping note:
- Registry, retrieval, PySpark execution, persistence separation, observability, and runtime traceability slices are implemented.
- Remaining DQ-7.4 scope is the broader multi-source adapter/runtime breadth and the open design decisions tracked later in this document.

## Worked Example: One Data Object Version Run

This example shows the current end-to-end path for one active GX suite that applies rules to a single `dataObjectVersionId`, reports the run outcome, and stores row-level exception facts separately.

Example input:

- target data object version: `dov_123`
- rule: `rule_1`
- rule version: `rule_version_7`
- GX suite: `gx_suite_8f40b9ea` version `3`
- correlation id: `corr_20260406_001`

1. A steward or operator selects the object version in the UI, which resolves to a retrieval query such as:

```http
GET /api/rulebuilder/v1/gx/suites?dataObjectVersionId=dov_123&status=active&latestOnly=true
```

2. The API validates that exactly one primary scope was provided, fetches the active GX suite envelope, and returns the resolved execution target:

```json
{
  "suiteId": "gx_suite_8f40b9ea",
  "suiteVersion": 3,
  "assignmentScope": {
    "dataObjectId": "do_123",
    "datasetId": "ds_456",
    "dataProductId": "odcs.dp.sales-001"
  },
  "resolvedExecutionScope": {
    "dataObjectVersionIds": ["dov_123"]
  },
  "executionContract": {
    "engineTarget": "pyspark",
    "executionShape": "single_object",
    "traceability": {
      "ruleId": "rule_1",
      "ruleVersionId": "rule_version_7",
      "gxSuiteId": "gx_suite_8f40b9ea",
      "gxSuiteVersion": 3,
      "dataObjectVersionId": "dov_123"
    }
  }
}
```

3. The grouped planner batches all suites that share `dov_123`, starts one Spark session for the batch, loads the source data once, and runs every suite in that group.

4. The worker reports the completed run back to the API run lifecycle store. A successful run summary looks like this:

```json
{
  "runId": "run_20260406_001",
  "suiteId": "gx_suite_8f40b9ea",
  "suiteVersion": 3,
  "dataObjectVersionId": "dov_123",
  "status": "succeeded",
  "passedCount": 12,
  "failedCount": 1,
  "startedAt": "2026-04-06T13:15:00Z",
  "finishedAt": "2026-04-06T13:18:22Z",
  "correlationId": "corr_20260406_001"
}
```

5. The failed row is written to the separate exception store, not the rule/result database. The GX-specific repository-backed shape keeps the violation fact minimal and preserves the lineage needed for reporting:

```json
{
  "dataPrimaryKey": "order_id=4711",
  "ruleId": "rule_1",
  "violationReason": "customer_address is null",
  "recordIdentifierType": "primary_key",
  "recordIdentifierValue": "4711",
  "reasonCode": "completeness_not_null_violation",
  "reasonText": "customer_address must not be null",
  "dataObjectVersionId": "dov_123",
  "runId": "run_20260406_001",
  "observedAt": "2026-04-06T13:18:22Z"
}
```

6. The monitoring UI can then show the aggregate run result from the run lifecycle store and the separate exception detail from the exception store. The important boundary is that the run summary and the row-level failure evidence travel through different stores and APIs.

If you are looking at the ABS-1 minimal base record rather than the GX repository-backed row, the stored violation fact is still the same separation boundary: primary key or business key, `ruleId`, and violation reason remain the durable fact, while optional operational metadata stays out of the rule/result database.

## Scope Assumption

1. [x] `SA-01` `dataObjectId` is the steward-facing assignment scope for a specific Data Object.
2. [x] `SA-02` Data Products in this scope are ODCS Data Products.
3. [x] `SA-03` `dataProductId` in retrieval and execution scope means the canonical ODCS Data Product identifier.
4. [x] `SA-04` DQ execution always runs against one or more `dataObjectVersionId` targets resolved from assignment scope.
5. [x] `SA-05` The neutral validation plan is the canonical run-plan contract; GX run plans are projections of it, and future Soda or SQL run plans should follow the same abstraction.

## Required Adjustments (Confirmed)

1. [ ] `RA-01` GX suites must run against a variety of data sources.
2. [x] `RA-02` Initial execution container is PySpark-based.
3. [x] `RA-03` Rules/suites for the same data object should execute clubbed in one run window to avoid repeated spin-up/spin-down.
4. [x] `RA-04` Detailed DQ outcomes and exception records must be captured separately.
5. [x] `RA-05` Exception records store only: primary key, ruleId, and violation reason.
6. [x] `RA-06` Exception records must not be stored in the rule/result database.
7. [x] `RA-07` End-to-end logging and monitoring are mandatory.
8. [x] `RA-08` GX suites are retrievable objects through API for external execution.
9. [x] `RA-09` API retrieval supports data object, data object version, data set, and data product scopes.
10. [x] `RA-10` Data product scope is ODCS-aligned and uses ODCS Data Product IDs.

## Target Architecture

### Compile and Registry

1. [x] `CR-01` Input: DQ rule (expression or checkType/checkTypeParams) + assignment context.
2. [x] `CR-02` Compiler output: normalized intermediate model (already in DQ-7.3).
3. [x] `CR-03` GX adapter output: GX suite object + metadata envelope.
4. [x] `CR-04` Persist suite metadata, assignment scope, and resolved execution-version references in a GX suite registry.
5. [x] `CR-05` Persist the neutral validation plan as the canonical run-plan record, then project engine-specific GX run-plan views from that canonical state.

### Execution Runtime (PySpark-first)

1. [x] `ER-01` Executor container base image: PySpark runtime with GX dependencies.
2. [x] `ER-02` One execution batch is formed per data object version.
3. [x] `ER-03` Batch contains all active suites/rules mapped to that data object version.
4. [x] `ER-04` Single Spark session per batch minimizes cold-start overhead.

### Outcome Persistence Separation

1. [x] `OP-01` Rule/result database stores aggregate and operational run metadata only.
2. [x] `OP-02` Exception records are stored in a dedicated exception store (separate database/schema).
3. [x] `OP-03` Exception store row shape includes:
  1. [x] `OP-03a` recordIdentifierType
  2. [x] `OP-03b` recordIdentifierValue
  3. [x] `OP-03c` reasonCode
  4. [x] `OP-03d` reasonText
  5. [x] `OP-03e` ruleId
  6. [x] `OP-03f` runId (recommended operational key)
  7. [x] `OP-03g` observedAt (recommended operational timestamp)

Repository-backed DB migration target for this row shape:
- Keep relational columns for `data_object_version_id`, `id`, `execution_run_id`, `rule_id`, `detected_at`, `created_at`, and `updated_at`.
- Persist `record_identifier_type` and `record_identifier_value` for every exception fact.
- Persist `reason_code` and `reason_text` for every exception fact.
- Replace the current wide optional columns and raw diagnostic payload with a single `ops_metadata_json` field for optional metadata such as `suite_id`, `suite_version`, `rule_version_id`, `correlation_id`, and `failure_class`.
- For the current reseeded prototype, callers should emit the canonical payload directly and the migration can recreate `gx_execution_violations` instead of translating legacy rows or preserving a compatibility shim.
- This repository-backed schema has been validated locally by applying Alembic head `20260418_0024` and rerunning the live ORM schema and GX retrieval integration slice against Postgres.

### Observability

1. [x] `OB-01` Structured logs are present on major GX API and worker execution paths.
2. [x] `OB-02` Metrics, dashboards, and alerts are present for major GX surfaces.
3. [x] `OB-03` Tracing and correlation IDs are propagated on major GX API and worker paths.
4. [x] `OB-04` Observability is validated end to end across compile, retrieval, execution, and persistence.

Compile-plus-retrieval and execution-plus-persistence observability validation are complete.

Compile-plus-retrieval validation evidence for `OB-04`:
- Log-field contract: [scripts/validate_logging_required_fields_contract.sh](../../scripts/validate_logging_required_fields_contract.sh)
- Correlation propagation contract: [scripts/validate_correlation_propagation.sh](../../scripts/validate_correlation_propagation.sh)
- Compiler behavior slice: [dq-api/fastapi/tests/application/services/test_rule_compiler.py](../../dq-api/fastapi/tests/application/services/test_rule_compiler.py) and [dq-api/fastapi/tests/unit/test_rules_helpers_more.py](../../dq-api/fastapi/tests/unit/test_rules_helpers_more.py)
- Retrieval behavior slice: [dq-api/fastapi/tests/infrastructure/integration/test_gx_retrieval_integration.py](../../dq-api/fastapi/tests/infrastructure/integration/test_gx_retrieval_integration.py)
- Monitoring assets and baseline validator: [observability/grafana/provisioning/dashboards/dq-api-observability.json](../../observability/grafana/provisioning/dashboards/dq-api-observability.json), [observability/prometheus/alerts.yml](../../observability/prometheus/alerts.yml), and [scripts/validate_monitoring_baseline.sh](../../scripts/validate_monitoring_baseline.sh)

Execution-plus-persistence validation evidence for `OB-04`:
- Execution API behavior slice: [dq-api/fastapi/tests/api/test_execution_monitoring.py](../../dq-api/fastapi/tests/api/test_execution_monitoring.py)
- Delivery-linked persistence separation slice: [dq-api/fastapi/tests/api/test_delivery_linked_execution_endpoints.py](../../dq-api/fastapi/tests/api/test_delivery_linked_execution_endpoints.py)
- Exception storage slice: [dq-api/fastapi/tests/application/services/test_exception_storage.py](../../dq-api/fastapi/tests/application/services/test_exception_storage.py)
- Worker execution and correlation slice: [dq-engine/tests/test_gx_dispatch_worker.py](../../dq-engine/tests/test_gx_dispatch_worker.py) and [dq-engine/tests/test_correlation_runtime_chain.py](../../dq-engine/tests/test_correlation_runtime_chain.py)
- Monitoring assets and baseline validator: [observability/grafana/provisioning/dashboards/dq-execution-monitoring.json](../../observability/grafana/provisioning/dashboards/dq-execution-monitoring.json), [observability/prometheus/alerts.yml](../../observability/prometheus/alerts.yml), and [scripts/validate_monitoring_baseline.sh](../../scripts/validate_monitoring_baseline.sh)

## Data Source Strategy (Variety Requirement)

GX execution layer must support pluggable datasource adapters:

1. [x] `DS-01` Spark DataFrames (initial, default path)
2. [ ] `DS-02` JDBC-backed sources via Spark connectors
3. [ ] `DS-03` Files (Parquet/Delta/CSV) via Spark readers
4. [x] `DS-04` Lightweight Pandas path explicitly dropped from scope in favor of the Spark-only worker runtime

Adapter contract:

1. [x] `AD-01` resolve_asset(scope)
2. [x] `AD-02` load_dataframe(asset_ref)
3. [ ] `AD-03` materialize_primary_key(df, primary_key_config)
4. [ ] `AD-04` emit_validation_target(df, gx_context)

## Clubbed Execution Strategy (Data Object Scoped)

### Grouping Key

Primary grouping key:
1. [x] `CE-01` dataObjectVersionId

Secondary grouping (optional optimization):
1. [ ] `CE-02` datasetId
2. [ ] `CE-03` dataProductId

### Execution Flow

1. [ ] `CE-04` Collect due suites by scheduling criteria.
2. [x] `CE-05` Group suites by dataObjectVersionId.
3. [x] `CE-06` For each group:
  1. [x] `CE-06a` start (or reuse) one Spark session
  2. [x] `CE-06b` load source data once
  3. [x] `CE-06c` execute all suites in the group
  4. [x] `CE-06d` write aggregate outcomes
  5. [x] `CE-06e` write exception records to exception store
4. [ ] `CE-07` Close session after group completion or idle timeout.

## API Design for GX Suite Retrieval

All endpoints return portable GX suite payloads and metadata required by external executors.

Routing note:
- Gateway/public (through Kong): `/rulebuilder/v1/...`
- Internal FastAPI (direct, bypassing Kong): `/api/rulebuilder/v1/...`

### By Data Object

1. [x] `API-01` GET /rulebuilder/v1/gx/suites?dataObjectId={id}

### By Data Object Version

1. [x] `API-02` GET /rulebuilder/v1/gx/suites?dataObjectVersionId={id}

### By Data Set

1. [x] `API-03` GET /rulebuilder/v1/gx/suites?datasetId={id}

### By Data Product

1. [x] `API-04` GET /rulebuilder/v1/gx/suites?dataProductId={id}
2. [x] `API-04a` `dataProductId` corresponds to ODCS Data Product identifier.

### Direct Suite Fetch

1. [x] `API-05` GET /rulebuilder/v1/gx/suites/{suiteId}

### Response Envelope (minimum)

1. [x] `API-06` suiteId
2. [x] `API-07` suiteVersion
3. [x] `API-08` assignmentScope:
  1. [x] `API-08a` dataObjectId
  2. [x] `API-08b` datasetId
  3. [x] `API-08c` dataProductId
4. [x] `API-09` resolvedExecutionScope:
  1. [x] `API-09a` dataObjectVersionIds[]
5. [x] `API-10` gxSuite (GX-native suite JSON)
6. [x] `API-11` compiledFrom:
  1. [x] `API-11a` ruleIds[]
  2. [x] `API-11b` compilerVersion
  3. [x] `API-11c` generatedAt
7. [x] `API-12` executionHints:
  1. [x] `API-12a` recommendedEngine: pyspark
  2. [x] `API-12b` primaryKeyFields[]

## Persistence Boundaries

### Rule/Result DB (allowed)

1. [x] `PB-01` run summary
2. [x] `PB-02` pass/fail totals
3. [x] `PB-03` execution timing
4. [x] `PB-04` suite registry metadata
5. [x] `PB-05` artifact references

### Exception Store (separate, required)

1. [x] `PB-06` violation row facts only:
  1. [x] `PB-06a` dataPrimaryKey
  2. [x] `PB-06b` ruleId
  3. [x] `PB-06c` violationReason
2. [x] `PB-07` optional ops fields:
  1. [x] `PB-07a` runId
  2. [x] `PB-07b` observedAt
  3. [x] `PB-07c` dataObjectVersionId

Note: no raw payload columns beyond the primary key should be required in the initial scope.

For the repository-backed DB backend, this means the current `details_json` column should be retired rather than repurposed as a raw diagnostic dump. If optional operational metadata remains necessary, it should live in `ops_metadata_json`, not in the base violation fact, and repository reads should return that same minimal-fact shape rather than a legacy compatibility projection.

## Logging and Monitoring Requirements

### Logging

1. [x] `LG-01` JSON structured logging in API, compiler, and executor.
2. [x] `LG-02` Mandatory fields:
  1. [x] `LG-02a` correlationId
  2. [x] `LG-02b` runId
  3. [x] `LG-02c` suiteId
  4. [x] `LG-02d` dataObjectVersionId
  5. [x] `LG-02e` datasetId
  6. [x] `LG-02f` dataProductId
  7. [x] `LG-02g` component
  8. [x] `LG-02h` event

### Monitoring

1. [x] `MN-01` Dashboards:
  1. [x] `MN-01a` compile success/failure trend
  2. [x] `MN-01b` suite retrieval latency and error rate
  3. [x] `MN-01c` execution throughput by scope
  4. [x] `MN-01d` exception volume trend by rule/data object
2. [x] `MN-02` Alerts:
  1. [x] `MN-02a` repeated compile failures
  2. [x] `MN-02b` executor timeout spikes
  3. [x] `MN-02c` exception store write failures
  4. [x] `MN-02d` missing heartbeat from executor workers

Implemented slice:
- `dq-engine/gx_dispatch_worker.py` now emits OTEL spans and metrics for dispatch, grouped batch execution, source reads, and expectation result counts.
- Grafana execution monitoring now includes GX worker latency and result panels backed by the new worker metrics.
- Grafana execution monitoring now also includes GX compile success/failure trend and GX run throughput-by-execution-shape panels for the MN-01 dashboard slice.
- Prometheus alerts now cover GX worker execution latency, source-read latency, and worker failure spikes.
- Grafana execution monitoring now also includes a GX executor heartbeat age-vs-threshold panel for direct visibility into the MN-02d stale-heartbeat alert condition.
- Prometheus alerts now also cover stale GX executor-worker heartbeats, driven by shared worker heartbeat timestamp and TTL metrics emitted from the Redis-backed heartbeat path.
- Grafana execution monitoring now also includes GX suite save/fetch latency and outcome panels for the API-side observability path.
- Prometheus alerts now cover GX suite save and fetch failures on the GX API surface.
- The top-level Execution Monitoring dashboard now uses runtime-agnostic panel naming for shared run, status, transition, latency, results/failures, compile, throughput, and heartbeat categories, even though GX remains the first concrete telemetry emitter underneath those panels.
- Rule Execution Monitoring in the app now includes an in-app failed-record hotspot dashboard backed by a dedicated exception-store analytics endpoint, with trend bars plus top rule and data-object summaries computed from persisted violation rows.
- A shared GX suite envelope adapter now centralizes GX artifact assembly for compiler auto-publish and GX suite repair flows.
- A shared GX execution-source adapter now centralizes asset resolution and source-handle loading for the PySpark executor.
- A grouped execution planner now groups GX suites by `dataObjectVersionId` and keeps batch ordering deterministic for clubbed execution.
- The PySpark executor now consumes grouped batches with one Spark session per execution run, reusing the loaded source for each suite in the batch.
- A shared GX exception storage service now centralizes batched violation persistence with deterministic row IDs for reproducible replay.
- The exception storage backend is object-storage-backed (AIStor or S3-compatible storage with a dedicated GX exceptions bucket) for raw exception facts; analytical aggregations may be stored in a database or an object-store projection depending on query needs.

## Incremental Delivery Plan

### Phase A - GX Registry + Retrieval API

1. [x] `PHA-01` Add GX suite registry model and storage.
2. [x] `PHA-02` Expose retrieval API by object, object version, dataset, and product.
3. [x] `PHA-03` Return portable GX suite payloads.

## Phase A Step 1 - Contract and Registry Baseline (Lock Before Build)

This section defines the implementation contract to freeze before coding APIs and storage.

Canonical source of truth in Git:

- [x] JSON Schema contract: `docs/contracts/gx-artifact-envelope/v1/schema.json`
- [x] JSON example payload: `docs/contracts/gx-artifact-envelope/v1/example.json`
- [x] YAML rendering for review: `docs/contracts/gx-artifact-envelope/v1/example.yaml`

### Step 1 Deliverable Status

- [x] Define canonical suite artifact envelope (v1).
- [x] Define GX suite registry logical schema.
- [x] Define retrieval API query semantics and response shape.
- [x] Implement DB migration and API endpoints in FastAPI.

### Canonical Identifier Semantics

- [x] `dataObjectId`: internal stable Data Object identifier used for steward-facing assignment scope.
- [x] `dataObjectVersionId`: internal immutable execution-target identifier derived from assignment scope resolution.
- [x] `datasetId`: internal dataset identifier used by assignment scope.
- [x] `dataProductId`: canonical ODCS Data Product identifier.
- [x] Exactly one primary scope is required per retrieval query (`dataObjectId` or `dataObjectVersionId` or `datasetId` or `dataProductId`).
- [x] Assignment scope and execution scope are distinct: users assign rules to Data Objects or Data Sets, while runtime executes resolved Data Object Versions.

### GX Artifact Envelope (v1)

```json
{
  "suiteId": "gx_suite_8f40b9ea",
  "suiteVersion": 3,
  "artifactVersion": "v1",
  "assignmentScope": {
    "dataObjectId": "do_123",
    "datasetId": "ds_456",
    "dataProductId": "odcs.dp.sales-001"
  },
  "resolvedExecutionScope": {
    "dataObjectVersionIds": ["dov_123", "dov_124"]
  },
  "gxSuite": {
    "expectation_suite_name": "dq_sales_orders_v3",
    "expectations": [],
    "meta": {}
  },
  "compiledFrom": {
    "ruleIds": ["rule_1", "rule_2"],
    "compilerVersion": "dq-compiler-7.3",
    "generatedAt": "2026-03-22T10:30:00Z"
  },
  "executionHints": {
    "recommendedEngine": "pyspark",
    "primaryKeyFields": ["order_id"]
  }
}
```

Envelope constraints:

- [x] `artifactVersion` is required and starts at `v1`.
- [x] `suiteId` is immutable across versions; `suiteVersion` is monotonically increasing.
- [x] `gxSuite` stores GX-native suite JSON without lossy transformation.
- [x] `assignmentScope.dataProductId` must be ODCS identifier when provided.
- [x] `resolvedExecutionScope.dataObjectVersionIds[]` must contain one or more execution targets.

### Registry Storage Contract (Logical)

Table: `gx_suite_registry` (migration `20260322_0002` + `20260322_0003`)

- [x] `id` UUID PK
- [x] `suite_id` TEXT NOT NULL
- [x] `suite_version` INTEGER NOT NULL
- [x] `artifact_version` TEXT NOT NULL DEFAULT 'v1'
- [x] `status` TEXT NOT NULL DEFAULT 'active' (allowed: active, deprecated, disabled)
- [x] `data_object_id` TEXT NULL
- [x] `dataset_id` TEXT NULL
- [x] `data_product_id` TEXT NULL (ODCS)
- [x] `gx_suite_json` JSONB NOT NULL
- [x] `compiler_version` TEXT NOT NULL
- [x] `generated_at` TIMESTAMPTZ NOT NULL
- [x] `created_at` TIMESTAMPTZ NOT NULL DEFAULT now()
- [x] `updated_at` TIMESTAMPTZ NOT NULL DEFAULT now()
- [x] `saved_by` TEXT NULL — identity that last saved the suite
- [x] `source_pipeline` TEXT NULL — e.g. `rule-compiler` or `api`

Indexes and constraints:

- [x] Unique: (`suite_id`, `suite_version`)
- [x] Query index: (`data_object_id`, `status`)
- [x] Query index: (`dataset_id`, `status`)
- [x] Query index: (`data_product_id`, `status`)
- [x] Check constraint: at least one scope column is non-null.
- [x] Check constraint: `data_product_id` follows ODCS ID format policy (enforced by app validation first; DB regex optional).

Table: `gx_suite_execution_target_map`

- [x] `suite_id` TEXT NOT NULL
- [x] `suite_version` INTEGER NOT NULL
- [x] `data_object_version_id` TEXT NOT NULL
- [x] Unique: (`suite_id`, `suite_version`, `data_object_version_id`)
- [x] Query index: (`data_object_version_id`)

Table: `gx_suite_rule_map`

- [x] `suite_id` TEXT NOT NULL
- [x] `suite_version` INTEGER NOT NULL
- [x] `rule_id` TEXT NOT NULL
- [x] Unique: (`suite_id`, `suite_version`, `rule_id`)

Table: `gx_suite_status_history` (migration `20260322_0003`)

- [x] `id` TEXT PK (UUID)
- [x] `suite_id` TEXT NOT NULL
- [x] `suite_version` INTEGER NOT NULL
- [x] `from_status` TEXT NULL — null on initial insert
- [x] `to_status` TEXT NOT NULL
- [x] `changed_by` TEXT NULL — principal from `get_user_id()` context
- [x] `changed_at` TIMESTAMPTZ NOT NULL DEFAULT now()
- [x] `reason` TEXT NULL — optional free-text reason for transition
- [x] Index: (`suite_id`, `suite_version`)
- [x] Index: `changed_at`

### Write and Status API Contract (Phase A)

- [x] `POST /rulebuilder/v1/gx/suites?status={status}` — persist or overwrite a GX suite envelope.
  - [x] Optional: `?expectedExistingHash={sha256}` — rejects with `409` when current artifact hash does not match.
  - [x] Optional: `?sourcePipeline={name}` — recorded in `source_pipeline` column.
  - [x] Returns `201` on insert, `200` on update.
- [x] `PATCH /rulebuilder/v1/gx/suites/{suiteId}/status?status={status}` — transition suite status.
  - [x] Optional: `?reason={text}` — recorded in status history trail.
  - [x] Returns `404` when suite not found.
- [x] `GET /rulebuilder/v1/gx/suites/{suiteId}/status-history` — full chronological status trail.
  - [x] Optional: `?suiteVersion={n}` — filters history to a specific version.
  - [x] Returns `[]` (empty list) when no history entries match.

### Retrieval API Contract (Phase A)

Endpoint:

- [x] `GET /rulebuilder/v1/gx/suites`
  (internal FastAPI path: `GET /api/rulebuilder/v1/gx/suites`)

Query rules:

- [x] One and only one primary scope filter is allowed:
  - [x] `dataObjectId`
  - [x] `dataObjectVersionId`
  - [x] `datasetId`
  - [x] `dataProductId` (ODCS)
- [x] Optional: `status` (default `active`)
- [x] Optional: `latestOnly` (default `true`)
- [x] `dataObjectVersionId` queries filter via `gx_suite_execution_target_map`.
- [x] `dataObjectId` and `datasetId` queries use assignment scope identifiers.

Responses:

- [x] `200` returns list of artifact envelopes.
- [x] `400` when none or multiple primary scope filters are provided.
- [x] `404` when direct suite fetch target does not exist.

Direct fetch:

- [x] `GET /rulebuilder/v1/gx/suites/{suiteId}`
- [x] Optional query: `suiteVersion`; when omitted, return latest active version.

### API Validation Rules (Mandatory)

- [x] Validate `dataProductId` as ODCS ID in request layer.
- [x] Reject unsupported combinations early with explicit `400` details.
- [x] Include `artifactVersion` and `suiteVersion` in every response.
- [x] Include `X-Correlation-Id` passthrough in response headers.
- [x] Reject accidental overwrite for existing `suiteId` + `suiteVersion` unless `expectedExistingHash` matches current artifact hash.
- [x] `PATCH /rulebuilder/v1/gx/suites/{suiteId}/status` — dedicated status transition endpoint (active → deprecated → disabled) without requiring full re-PUT or hash.

### Definition of Done for Step 1

- [x] Contract published in this implementation details document.
- [x] Versioned contract files created in Git.
- [x] Matching Pydantic schemas created in API module.
- [x] Matching Alembic revision created for registry tables.
- [x] OpenAPI examples added for all retrieval variants.
- [x] Write path: `POST /rulebuilder/v1/gx/suites` — persist envelope + status.
- [x] Hash-based overwrite protection: `expectedExistingHash` query param; returns `409` on mismatch.
- [x] `PATCH /rulebuilder/v1/gx/suites/{suiteId}/status` — status transition with optional `reason` query param.
- [x] Audit metadata columns (`saved_by`, `source_pipeline`) on `gx_suite_registry` (Alembic revision `20260322_0003`).
- [x] Status history trail: `gx_suite_status_history` table records every status transition with `from_status`, `to_status`, `changed_by`, `changed_at`, `reason`.
- [x] `GET /rulebuilder/v1/gx/suites/{suiteId}/status-history` — chronological audit trail endpoint; optional `suiteVersion` filter.
- [x] Compiler auto-publish: `POST /{ruleId}/activate` accepts optional `GxSuiteAutoPublishRequest` body; when assignment scope is provided, auto-creates GX suite stub via `_persist_gx_suite_from_compiler` (`source_pipeline="rule-compiler"`).
- [x] `get_user_id()` context var wired for `saved_by` / `changed_by` in all write paths.
- [x] 24 tests passing (16 unit + 8 integration).

Migration policy note:

- [x] FastAPI migration tooling bootstrapped with Alembic.
- [x] Legacy baseline Alembic revision created for pre-Alembic schema state.
- [x] First DQ-7.4 GX registry Alembic revision created.
- [x] Seeded startup flow runs `alembic upgrade head` before data seeding completes.
- [x] GX registry tables must be introduced through Alembic, not direct SQL init edits.
- [x] Legacy `dq-db/init` SQL files remain transitional until a full Alembic baseline replaces bootstrap schema creation. **DONE** — All DDL baselined into migration `0001`; init DDL files archived under `dq-db/init/backup/`; API container runs `alembic upgrade head` on startup.

### Phase B - PySpark Executor (Clubbed)

- [x] Add grouped execution planner by dataObjectVersionId.
- [x] Execute grouped suites in one Spark session.
- [x] Persist aggregate run outcomes.

### Phase C - Exception Store Split

- [x] Introduce dedicated exception persistence target.
- [x] Write violation records with strict minimal schema.
- [x] Ensure no exception rows are written to rule/result database.

### Phase D - Observability Hardening

- [x] Add structured logs and tracing.
1. [x] `PD-01` Add metrics and dashboards.
2. [x] `PD-02` Add SLO alerts for compile, retrieval, and execution.
3. [x] `PD-03` Validate observability end to end across compile, retrieval, execution, and persistence.

## Acceptance Criteria

1. [x] `ACC-01` GX suite retrieval API supports all three scopes: data object version, dataset, and data product.
2. [x] `ACC-02` GX suite retrieval API supports all four scopes: data object, data object version, dataset, and data product.
3. [x] `ACC-03` Executor uses a PySpark-based container in initial implementation.
4. [x] `ACC-04` Suites for one data object version execute in a clubbed batch.
5. [x] `ACC-05` Detailed outcomes and exceptions are stored separately.
6. [x] `ACC-06` Exception records do not live in the rule/result database.
7. [x] `ACC-07` Exception schema minimally includes primary key, ruleId, and reason.
8. [x] `ACC-08` Logging, metrics, tracing, and alerting are in place and validated.

## Remaining Implementation Backlog

This section replaces the older phase-era “open items” summary with the actual remaining DQ-7.4 backlog after the registry, retrieval, PySpark execution, persistence-separation, observability, and runtime-traceability slices already delivered.

### Source Adapter Breadth

1. [ ] `BK-01` Add JDBC-backed sources via Spark connectors.
2. [ ] `BK-02` Extend file-source breadth beyond the current parquet/delta path where needed (for example CSV).

### Runtime Policy Hardening

1. [x] `BK-04` Due-suite collection is explicit: the runtime may collect suites only from a direct schedule request, a grouped activation request, or another explicitly requested selector-backed batch. It must not infer hidden schedule windows or silently poll for due work.
  - Current direct schedule and grouped dispatch flows already require explicit suite or scope selectors; any future scheduler must preserve that fail-fast contract instead of introducing implicit scanning.
2. [x] `BK-05` Spark session lifecycle is batch-scoped: one grouped execution batch owns one Spark session, and the worker must close that session immediately after batch completion.
  - If session creation, execution, or shutdown fails, the worker must mark the run failed rather than keeping a dangling session alive.
3. [x] `BK-06` Grouped runs split only on an explicit batch-cap policy per `dataObjectVersionId`.
  - Default behavior is one grouped batch per resolved `dataObjectVersionId`; if a future deployment needs to cap batch size, the split must be driven by an explicit configured maximum rather than an implicit timeout or heuristic.

### Persistence and Operations Decisions

1. [x] `BK-07` Raw exception facts live in object storage; analytical aggregations may be stored in a database or object store.
  - The raw store remains append-only object storage, while analysis can use whichever projection store best fits the reporting path.
2. [x] `BK-08` Retention and purge for persisted exception records follows the retention and purge policy of the owning data object.
   - Exception facts inherit the lifecycle of the data object containing the data; when the owning data object is retained or purged, the linked exception records follow that policy.
  - The runtime resolves the canonical policy from `data_object_versions.storage_options_json.retention_policy` and applies it per data object version during exception retention maintenance.

## Follow-On Implementation Plan - Engine-Independent Exception Fact Store And Reason Analytics

This follow-on plan extends the existing exception-store separation model so row-level failure evidence can be persisted and analyzed consistently across GX, Soda, and future execution engines.

The target outcome is:

- persist one exception fact per failed record and failed rule at a specific execution point in time
- keep the exact record identifier used by the runtime (`primary_key` or `business_key`)
- attach the failure fact to delivery, execution plan, suite or artifact, data object version, rule version, and runtime identity
- store a stable failure reason snapshot that supports reporting at that point in time
- support very large volumes, including millions of exception records
- provide aggregated reason analytics and reason fluctuation reporting over time without mixing exception facts into the rule/result database

### Scope

#### In scope

- a canonical engine-independent exception fact contract
- explicit runtime capability requirements for row-level exception emission
- separate persistence for raw exception facts and aggregated reason analytics
- support for record identifiers using either primary key or business key
- support for delivery-linked execution context and execution-plan context
- trend and hotspot analytics by failure reason over time
- report-oriented read APIs for detailed exceptions and aggregated summaries

#### Out of scope

- silent fallback to aggregate-only execution when an engine cannot emit exception facts
- storing exception facts in the rule/result database
- logging raw exception identifiers into observability pipelines
- forcing every engine to expose the same native diagnostics shape internally

### Plan Assumptions

1. `EF-01` Exception facts remain a separate persistence concern from aggregate execution results.
2. `EF-02` Execution engines are allowed to differ internally, but every supported engine must map its row-level failures into one canonical exception fact contract.
3. `EF-03` If an engine cannot emit record-level exception facts for a requested execution mode, that path fails fast instead of degrading to aggregate-only success.
4. `EF-04` The record identifier stored for an exception fact is the canonical identifier available at runtime: primary key where available, otherwise approved business key.
5. `EF-05` Reason analytics must be generated from persisted exception facts, not inferred later from aggregate counts.

### Target Architecture

#### 1. Canonical Exception Fact Contract

Define an engine-independent exception fact envelope above the current GX-only storage payload.

Required fact fields:

- `exception_fact_id`
- `engine_type`
- `delivery_id`
- `execution_plan_id`
- `execution_plan_version_id`
- `execution_run_id`
- `suite_id` or `artifact_id`
- `suite_version` or `artifact_version`
- `data_object_version_id`
- `rule_id`
- `rule_version_id`
- `record_identifier_type` with allowed values `primary_key` or `business_key`
- `record_identifier_value`
- `reason_code`
- `reason_text`
- `detected_at`

Optional operational metadata:

- `correlation_id`
- `dataset_id`
- `data_product_id`
- `delivery_note_id`
- `failure_class`
- `engine_metadata`

Contract rules:

- [x] `EF-06` `record_identifier_value` is required for every persisted exception fact.
- [x] `EF-07` `reason_code` should be stable within a runtime adapter; `reason_text` stores the user-readable snapshot at that point in time.
- [x] `EF-08` `rule_version_id` is required so historical reports remain correct when the underlying rule later changes.
- [x] `EF-09` `engine_type` is required so GX, Soda, and later engines are explicit in persistence and analytics.
- [x] `EF-10` `delivery_id` and `execution_plan_id` are nullable only for flows that genuinely do not execute in those contexts; they are not inferred later by fallback logic.

#### 2. Engine Adapter Contract

Add an exception-emission seam parallel to the existing runtime-neutral validation-artifact seam.

Each supported engine adapter must implement:

- [x] `EA-01` `collect_exception_facts(run_result, execution_context)`
- [x] `EA-02` `normalize_reason(native_failure)` -> `{reason_code, reason_text, failure_class}`
- [x] `EA-03` `resolve_record_identifier(native_failure, execution_context)` -> `{record_identifier_type, record_identifier_value}`
- [x] `EA-04` `emit_exception_fact_batch(...)`

Fail-fast rules:

- [x] `EA-05` Reject execution for engines that cannot produce record identifiers for the selected execution mode.
- [x] `EA-06` Reject execution for engines that cannot produce a normalized failure reason.
- [x] `EA-07` Do not mark a run fully successful when aggregate results exist but exception-fact persistence was required and failed.

#### 3. Persistence Model

Use a two-layer exception-store model so detailed facts and reporting summaries scale together.

- [x] Layer A - Raw exception fact store:

- append-only canonical exception facts
- partitioned by `detected_at` and scoped identifiers such as `delivery_id` or `data_object_version_id`
- optimized for large write volume and replay
- remains outside the rule/result database

- [ ] Layer B - Analytics projection store:

- reason-level rollups derived from raw exception facts
- optimized for query and reporting workloads
- stores bucketed aggregates by time and execution scope

- [x] Recommended raw fact columns:

- all required fact fields from the canonical contract
- optional metadata in `ops_metadata_json`

- [ ] Recommended analytics dimensions:

- `bucket_start`
- `engine_type`
- `delivery_id`
- `execution_plan_id`
- `execution_plan_version_id`
- `suite_id` or `artifact_id`
- `data_object_version_id`
- `rule_id`
- `rule_version_id`
- `reason_code`
- `reason_text_snapshot`

- [ ] Recommended analytics measures:

- `failed_record_count`
- `distinct_record_identifier_count`
- `distinct_execution_run_count`

#### 4. Reason Analytics Model

- [ ] Introduce a dedicated reason analytics projection rather than extending the current totals-only summary shape.

- [ ] Required analytics outputs:

- [ ] `RAA-01` Top failure reasons by scope and time window.
- [ ] `RAA-02` Trend over time for one failure reason.
- [ ] `RAA-03` Trend over time for all failure reasons within one scope.
- [ ] `RAA-04` Delivery report summary showing record counts by reason for one delivery.
- [ ] `RAA-05` Execution-plan report summary showing fluctuation by reason across successive runs.
- [ ] `RAA-06` Rule-version report summary showing whether one rule version introduced a new dominant failure reason.

- [ ] Required group-by scopes:

- [ ] by delivery
- [ ] by execution plan
- [ ] by suite or validation artifact
- [ ] by data object version
- [ ] by rule version
- [ ] by engine type

#### 5. Read APIs

- [x] Add engine-neutral exception read APIs rather than keeping the reporting shape GX-specific.

- [x] Suggested API direction:

- [x] `GET /rulebuilder/v1/exceptions/facts`
- [x] `GET /rulebuilder/v1/exceptions/facts/{exception_fact_id}`
- [x] `GET /rulebuilder/v1/exceptions/reason-analytics`
- [x] `GET /rulebuilder/v1/exceptions/reason-analytics/trends`
- [x] `GET /rulebuilder/v1/deliveries/{delivery_id}/exception-summary`
- [x] `GET /rulebuilder/v1/execution-plans/{execution_plan_id}/exception-summary`

- [x] Common filters:

- [x] `delivery_id`
- [x] `execution_plan_id`
- [x] `execution_plan_version_id`
- [x] `execution_run_id`
- [x] `suite_id` or `artifact_id`
- [x] `data_object_version_id`
- [x] `rule_id`
- [x] `rule_version_id`
- [x] `engine_type`
- [x] `reason_code`
- [x] `detected_after`
- [x] `detected_before`

#### 6. Delivery And Execution-Lineage Requirements

Every exception fact should preserve the lineage needed for downstream reporting and audit.

- [x] `EL-01` Delivery-linked runs must stamp `delivery_id` onto every exception fact.
- [x] `EL-02` Execution-plan-driven runs must stamp `execution_plan_id` and `execution_plan_version_id`.
- [x] `EL-03` Artifact-driven runs must stamp `suite_id` or neutral `artifact_id` plus version.
- [x] `EL-04` Rule lineage must include both `rule_id` and `rule_version_id`.
- [x] `EL-05` Reports must be able to explain which rule version and which failure reason were in effect when the exception fact was written.

#### 7. Scalability Strategy

The system must handle millions of exception records without relying on ad hoc scans of the raw fact store.

Required scaling choices:

- [x] `SC-01` Partition raw exception facts by time and high-cardinality execution scope.
  - Use `detected_at` as the time partition key and scope by identifiers such as `data_object_version_id`, `delivery_id`, `execution_plan_id`, `rule_id`, and `engine_type`.
- [x] `SC-02` Keep raw facts append-only and immutable after write, except for retention and purge operations.
- [x] `SC-03` Build incremental analytics rollups from raw facts rather than recomputing full-history reports on demand.
  - Rollups should aggregate by bounded time buckets and scope keys, and full-history recomputation should be reserved for controlled backfill or rebuild jobs only.
- [x] `SC-04` Add retention tiers: hot queryable projections, warm object-storage facts, and pre-aggregated long-term reason trends.
  - Hot queryable projections may live in a database or query-optimized object-store projection; warm raw facts remain immutable object-storage archives; cold long-term trend summaries may use whichever projection store best fits reporting needs.
- [x] `SC-05` Support paged detail retrieval by scope without requiring full delivery scans.

#### 8. Security And Governance

- `exception_fact_reader` is the workspace-scoped JIT role for list, summary, and analytics access only.
- `exception_fact_investigator` is the workspace-scoped JIT role for raw fact detail access only.
- Neither exception-fact JIT role includes export access.
- A JIT request must come from a user who already has another role in the same workspace.
- A workspace admin approves the request.
- Approved duration is capped by `exceptionFactJitRoleMaxDurationMinutes` in App Settings.

- [x] `SG-01` Exception identifiers are stored in the exception store only and must not be copied into logs or telemetry payloads.
- [x] `SG-02` Access to detailed exception facts remains authorization-scoped by workspace and delivery/execution ownership.
- [x] `SG-03` Reports may expose aggregated counts by reason without exposing record identifiers when the caller lacks detail access.
- [x] `SG-04` Retention and purge policy must be explicit for raw facts and analytics projections.

### Incremental Delivery Plan

#### Phase E1 - Canonical Contract And Engine Capability Gate

1. [x] `E1-01` Define the engine-independent exception fact schema in [docs/contracts/exception-fact/v1](../contracts/exception-fact/v1/schema.json).
2. [x] `E1-02` Introduce explicit engine capability flags for row-level exception recording in `docs/contracts/execution-engine-capabilities/v1`.
3. [x] `E1-03` Fail fast when an execution engine cannot emit the required exception facts.

Exit criteria:

- [x] `E1-EC-01` One canonical exception fact contract exists above GX/Soda/native runtimes.
- [x] `E1-EC-02` Every supported engine declares whether row-level exception facts are supported.
- [x] `E1-EC-03` Unsupported paths reject explicitly.

#### Phase E2 - Raw Exception Fact Persistence Upgrade

1. [x] `E2-01` Extend persistence to carry delivery, execution-plan, artifact, rule-version, and engine-type lineage.
2. [x] `E2-02` Add `record_identifier_type` and `record_identifier_value`.
3. [x] `E2-03` Preserve `reason_code` and `reason_text` as point-in-time facts.

Exit criteria:

- [x] `E2-EC-01` Raw facts persist all required lineage identifiers.
- [x] `E2-EC-02` One failed record against one rule creates one durable exception fact.
- [x] `E2-EC-03` The store remains separate from the rule/result database.

#### Phase E3 - Reason Analytics Projection

1. [x] `E3-01` Add reason-level rollup tables or materialized projections.
2. [x] `E3-02` Aggregate by time bucket and required scopes.
3. [x] `E3-03` Support trend queries for fluctuation reporting over time.

Exit criteria:

- [x] `E3-EC-01` Top reasons can be queried by delivery, plan, suite, object version, and rule version.
- [x] `E3-EC-02` Trend buckets exist for failure reasons over time.
- [x] `E3-EC-03` Analytics no longer stop at totals by rule or data object only.

#### Phase E4 - API And Reporting Surface

1. [x] `E4-01` Add detail and summary APIs for exception facts and reason analytics.
2. [x] `E4-02` Add delivery-level and execution-plan-level report views.
3. [x] `E4-03` Add report exports using the analytics projection instead of raw fact scans.

Exit criteria:

- [x] `E4-EC-01` Detailed exception facts are queryable with paging and authorization.
- [x] `E4-EC-02` Aggregated reason reports are queryable without raw-fact scans.
- [x] `E4-EC-03` Report generation can show fluctuation per failure reason over time.

#### Phase E5 - Operations, Retention, And Backfill

1. [x] `E5-01` Define retention and purge policy for raw facts and analytics projections.
2. [x] `E5-02` Backfill legacy GX exception records into the canonical contract where possible.
3. [x] `E5-03` Add validation, monitoring, and alerts for exception-fact persistence and analytics freshness.

Current E5-01 policy:

- raw exception facts inherit the retention and purge policy of the owning data object containing the data
- object-storage-backed exception fact archives remain append-only and are purged when the owning data object policy requires removal
- the canonical per-version policy lives on `data_object_versions.storage_options_json.retention_policy`
- future materialized analytics projections may use their own retention window, but they must not outlive the owning data object policy for the raw facts they summarize unless a separate governance decision says otherwise
- purge automation reads the canonical data-object retention policy and applies object-storage deletion through `python scripts/maintain_exception_retention.py --execute`
- the current GX analytics surface remains query-time only, so there is no separate projection-table purge path until a materialized projection store exists

Current E5-02 path:

- repository-backed legacy rows are upgraded in place by `python scripts/backfill_legacy_gx_exception_facts.py --source repository --execute`
- object-storage-backed legacy batches are replayed into the canonical Postgres exception repository by `python scripts/backfill_legacy_gx_exception_facts.py --source object-storage --execute`
- repository backfill deterministically derives `record_identifier_type=primary_key` from `data_primary_key`, derives `reason_code` from `violation_reason`, defaults `engine_type=gx`, and upgrades `validation_artifact_id` / `validation_artifact_version` from stored `suite_id` / `suite_version`
- replay preserves existing `violation_id` values when present and otherwise derives stable IDs from the canonical violation payload hash
- rows or archived violations missing `rule_version_id` or validation-artifact lineage are reported as unresolved and skipped rather than silently approximated

Current E5-03 path:

- Postgres exporter queries now expose non-canonical exception-fact counts, oldest unresolved age, and latest canonical exception-fact age for the execution observability surface
- Prometheus records and alerts now flag persistent canonical-contract drift and analytics freshness lag alongside the existing exception-store write-failure alert
- the execution Grafana dashboard now shows non-canonical fact count, oldest unresolved age, and latest canonical fact age without surfacing raw exception payloads
- repo validation for this slice runs through `scripts/validate_exception_fact_observability.sh`, which checks the exporter, alert, recording-rule, and dashboard assets stay aligned

Exit criteria:

- [x] `E5-EC-01` Retention is explicit and automated.
- [x] `E5-EC-02` Analytics freshness is monitored.
- [x] `E5-EC-03` Backfill and replay paths are deterministic.

### Acceptance Criteria

- [ ] `EFACC-01` Every supported execution engine emits canonical exception facts with no fallback to aggregate-only behavior.
- [ ] `EFACC-02` Each exception fact stores the record identifier, rule version, execution lineage, and failure reason at the time of detection.
- [x] `EFACC-03` Delivery-level and execution-plan-level reports can show failed-record counts by reason.
- [x] `EFACC-04` Time-series analytics can show fluctuation per failure reason over time.
- [ ] `EFACC-05` The implementation scales to millions of exception facts through partitioning and incremental rollups.
- [ ] `EFACC-06` Exception facts remain outside the rule/result database and outside observability payloads.

### Follow-Up Investigations

1. [x] `INV-01` Great Expectations Data Docs are explicitly excluded from the neutral exception-reporting surface; use protected row-level analysis capability instead.
  - See [ADR-035](../../architecture/adr/ADR-035-exclude-great-expectations-data-docs-and-require-protected-row-level-analysis-capability.md).

### Recommended Next Decisions

Decision record: `architecture/adr/ADR-034-engine-neutral-exception-fact-contract-family-and-storage-authority.md`

1. [x] `ND-01` Choose the canonical name for the engine-neutral exception store contract and APIs so the current GX naming can be retired at the boundary.
2. [x] `ND-02` Raw exception facts use immutable object-storage archives as the source of truth; analytical projections may be stored in a database or object store as query needs evolve.
3. [x] `ND-03` Decide whether `record_identifier_value` must be stored plaintext, encrypted, or paired with a deterministic hash for dedupe and join workflows.
4. [x] `ND-04` Define the controlled taxonomy for `reason_code` so cross-engine analytics can compare like-for-like failure classes.

Resolved ND decisions:

- `ND-01`: `exception-fact`, `exceptions`, and `exception analytics` are the canonical public family names; `gx_execution_violation` remains an internal transitional detail only.
- `ND-02`: production architecture uses immutable object-storage exception archives as the raw source of truth, with analytical projections allowed in a database or object store depending on reporting and query requirements.
- `ND-03`: `record_identifier_value` remains plaintext in authorized raw-fact storage and raw-fact APIs, must be kept out of observability and summary exports, and should be paired with `identifier_hash` in `sha256:<64 hex>` form.
- `ND-04`: `reason_code` is a controlled cross-engine analytics key using shared families such as `completeness_*`, `uniqueness_*`, `validity_*`, `consistency_*`, `referential_integrity_*`, `range_*`, `freshness_*`, `volume_*`, and `custom_*`; engine-native expectation names stay in metadata.

Follow-up implementation status:

- GX report ingestion now normalizes runtime `reason_code` values into the controlled taxonomy before persistence and preserves the raw GX `expectation_type` in metadata.
- The FastAPI API boundary now uses neutral `ExceptionFactRepository` and `ExceptionAnalyticsView` names even though concrete repository class names remain part of the deeper internal migration backlog.

### External Contract and Governance Decisions

1. [x] `BK-09` API auth scope for external GX suite retrieval clients is `dq:rules:read` on the Kong-protected `/api/rulebuilder/v1/gx/suites` and `/api/rulebuilder/v1/gx/suites/{suiteId}` surfaces.
  - See [dq-api/fastapi/tests/api/test_gx_suite_list_endpoints.py](../../dq-api/fastapi/tests/api/test_gx_suite_list_endpoints.py) and the Kong JWT / ACL bootstrap path in [dq-kong/README.md](../../dq-kong/README.md).
2. [x] `BK-10` Assignment scope resolution is implemented as a fail-fast mapping from `dataObjectId`, `datasetId`, or `dataProductId` to one or more active `dataObjectVersionId` targets.
  - See [dq-api/fastapi/app/application/services/source_data_resolver.py](../../dq-api/fastapi/app/application/services/source_data_resolver.py), [dq-api/fastapi/app/domain/entities/gx_suite.py](../../dq-api/fastapi/app/domain/entities/gx_suite.py), and the GX retrieval repository in [dq-api/fastapi/app/infrastructure/repositories/postgres_gx_suite_repository.py](../../dq-api/fastapi/app/infrastructure/repositories/postgres_gx_suite_repository.py).
