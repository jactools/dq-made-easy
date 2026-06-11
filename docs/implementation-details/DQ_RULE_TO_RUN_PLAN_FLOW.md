# DQ Rule to Run Plan Flow

This diagram shows how a dq-made-easy user creates a DQ rule in the UI, how the API stores it in PostgreSQL, and how an approved run plan activates execution through dq-engine.

SVG asset: [DQ_RULE_TO_RUN_PLAN_FLOW.svg](./DQ_RULE_TO_RUN_PLAN_FLOW.svg)

## Flow Diagram


```mermaid
flowchart TD
  subgraph UI["dq-made-easy UI"]
    RULE_UI["Rules screen / New Rule Wizard"]
    PLAN_UI["GX Run Plans Admin"]
  end

  subgraph API["FastAPI application"]
    RULES_API["POST /api/v1/rules"]
    RULE_CREATE["create_rule use case"]
    RULE_VALIDATE["validate rule use case\ncompiler / GX lowering"]
    GX_PLAN_API["POST /api/v1/gx/run-plans\nPOST /api/v1/gx/run-plans/{run_plan_id}/versions\nPOST /api/v1/gx/run-plans/{run_plan_id}/versions/{run_plan_version_id}/validate\nPOST /api/v1/gx/run-plans/{run_plan_id}/versions/{run_plan_version_id}/activate"]
    SEED_RESOLVER["GX run plan seed resolver\n+grouped execution planner"]
    ACTIVATE["Activation dispatcher"]
  end

  subgraph PG["PostgreSQL"]
    RULE_TABLES["rules\nrule_versions\nrule_current_version"]
    PLAN_TABLES["gx_run_plans\ngx_run_plan_versions\ngx_run_plan_transitions"]
    RUN_TABLES["gx_execution_runs\ngx_execution_run_status_history"]
    VIOLATION_TABLES["gx_execution_violations\nseparate exception store"]
  end

  subgraph RUNTIME["Execution runtime"]
    QUEUE["Redis dispatch queue"]
    ENGINE["dq-engine / gx worker"]
    SPARK["PySpark executor"]
    TARGETS["Resolved dataObjectVersionId targets"]
  end

  RULE_UI -->|Submit rule| RULES_API
  RULES_API --> RULE_CREATE
  RULE_CREATE --> RULE_TABLES
  RULE_TABLES --> RULE_UI

  RULE_TABLES --> RULE_VALIDATE
  RULE_VALIDATE -->|Rule validated and compiled into GX artifacts| SEED_RESOLVER
  PLAN_UI -->|Create or edit draft plan| GX_PLAN_API
  GX_PLAN_API --> SEED_RESOLVER
  SEED_RESOLVER --> PLAN_TABLES
  PLAN_UI -->|Validate version| GX_PLAN_API
  GX_PLAN_API --> PLAN_TABLES
  PLAN_UI -->|Activate approved version| GX_PLAN_API
  GX_PLAN_API --> ACTIVATE
  ACTIVATE --> QUEUE
  QUEUE --> ENGINE
  ENGINE --> SPARK
  SPARK --> TARGETS
  ENGINE --> RUN_TABLES
  ENGINE --> VIOLATION_TABLES
```

## Reading The Diagram

1. The rule authoring UI sends the rule payload to the rules API.
2. The API persists the rule in PostgreSQL before the rule appears back in the UI.
3. The run-plan UI creates a draft GX run plan from the compiled GX artifact and its execution contract.
4. Validation updates the run-plan version state in PostgreSQL.
5. Activation enqueues a dispatch payload, and dq-engine executes the resulting batch against the resolved `dataObjectVersionId` targets.
6. Execution metadata stays in the run tables, while row-level violations go to the separate exception store.

## Worked Example

This sequence shows the current end-to-end path for one `dataObjectVersionId` run, including the separate result and exception persistence paths.

```mermaid
sequenceDiagram
  participant UI as dq-made-easy UI
  participant API as FastAPI /rulebuilder/v1
  participant GX as GX retrieval API
  participant PLAN as GX run-plan / dispatch
  participant Q as Redis dispatch queue
  participant W as dq-engine / gx worker
  participant SPARK as PySpark executor
  participant RUN as gx_execution_runs
  participant EX as gx_execution_violations

  UI->>API: Select dataObjectVersionId dov_123 and request execution
  API->>GX: GET /gx/suites?dataObjectVersionId=dov_123&status=active&latestOnly=true
  GX-->>API: GX suite envelope with resolvedExecutionScope.dataObjectVersionIds=["dov_123"]
  API->>PLAN: Create schedule / activation payload for suiteId gx_suite_8f40b9ea
  PLAN->>Q: Enqueue dispatch payload
  Q-->>W: Deliver GX dispatch message
  W->>SPARK: Execute suites for dov_123 in one Spark session
  SPARK-->>W: Run outcome with passedCount, failedCount, diagnostics, correlationId
  W->>RUN: Persist run summary and status history
  W->>EX: Persist row-level exception facts
  RUN-->>UI: Run summary is available in monitoring views
  EX-->>UI: Exception details are available in exception-reporting views
```

Example result shape:

```json
{
  "runId": "run_20260406_001",
  "suiteId": "gx_suite_8f40b9ea",
  "suiteVersion": 3,
  "dataObjectVersionId": "dov_123",
  "status": "succeeded",
  "passedCount": 12,
  "failedCount": 1,
  "correlationId": "corr_20260406_001"
}
```

Example exception-row shape:

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
  "runId": "run_20260406_001"
}
```

The key boundary is that the aggregate run result and the row-level exception facts are persisted and read back through different stores and views.

## Notes

- Rule creation does not trigger execution by itself; a run plan is the explicit handoff into scheduling and runtime dispatch.
- The run-plan lifecycle is immutable at the version level, so each activation works from a specific snapshot.
- If the execution contract or required source mapping is missing, the runtime fails fast rather than substituting a fallback path.
