# DQ-1 Enhanced Rule Validation Logic — Implementation Progress

Status: [x] Complete
Last updated: 2025-07-17
Related feature tracker: ../features/DQ_FEATURES.md

## Scope

DQ-1 extends the existing single-rule validation endpoint with configurable validation
policies, batch execution, cross-rule conflict detection, persistent run history with
export, and real-time feedback in the rule-authoring UI.

---

## DQ-1.1 — Configurable Validation Policies

Status: [x] Complete
Files changed:
- `dq-api/fastapi/app/domain/entities/validation_policy.py` *(new)*
- `dq-api/fastapi/app/domain/entities/app_config.py` — `validationPolicies` field added
- `dq-api/fastapi/app/infrastructure/repositories/app_config_defaults.py` — default policies
- `dq-api/fastapi/app/application/services/validation_policy.py` *(new)*
- `dq-api/fastapi/app/api/v1/schemas/rule_compiler_view.py` — `ValidationPolicyView` added
- `dq-api/fastapi/app/api/v1/endpoints/rules.py` — validate endpoint reads + applies policies

Design: A list of `ValidationPolicyEntity` objects lives inside `app_config.validationPolicies`.
Each entry has:

| Field              | Type                                   | Default    |
|--------------------|----------------------------------------|------------|
| `checkId`          | `str` (e.g. `DQ1_EMPTY_EXPRESSION`)   | required   |
| `enabled`          | `bool`                                 | `true`     |
| `severityOverride` | `"error"\|"warning"\|"info"\|null`     | `null`     |
| `scope`            | `"all"\|"workspace:<name>"`            | `"all"`    |

The `apply_validation_policies` service filters/overrides diagnostics returned by the
compiler before they reach the API response.

Built-in check IDs registered with defaults:

| checkId                         | Default severity | Description                                       |
|---------------------------------|-----------------|---------------------------------------------------|
| `DQ1_EMPTY_EXPRESSION`          | error           | Expression is blank or whitespace-only            |
| `DQ1_EXPRESSION_SYNTAX`         | error           | Expression fails the compiler grammar parser      |
| `DQ1_UNSUPPORTED_KEYWORD`       | error           | Expression contains SQL keywords (SELECT, FROM…)  |
| `DQ1_MISSING_ALIAS`             | warning         | Alias referenced in expression has no mapping     |
| `DQ1_JOIN_VALIDATION`           | warning         | Join definition has structural issues             |
| `DQ1_DUPLICATE_EXPRESSION`      | warning         | Same normalized expression exists on another rule |
| `DQ1_DUPLICATE_NAME`            | warning         | Same rule name (case-insensitive) already exists  |
| `DQ1_CONTRADICTORY_PREDICATES`  | warning         | Predicates on same field are logically redundant  |

---

## DQ-1.2 — Batch Validation API

Status: [x] Complete
Files changed:
- `dq-api/fastapi/app/api/v1/schemas/rule_compiler_view.py` — new batch view models
- `dq-api/fastapi/app/api/v1/endpoints/rules.py` — `POST /rules/validate/batch`

Endpoint:
```
POST /api/rulebuilder/v1/rules/validate/batch
```
Request body:
```json
{ "ruleIds": ["r1", "r2"], "workspace": "default" }
```
Response shape:
```json
{
  "runId": "<uuid>",
  "results": [{ "ruleId": "r1", "valid": true, ... }],
  "conflicts": [...],
  "summary": { "total": 2, "valid": 1, "invalid": 1, "errors": 1, "warnings": 0 }
}
```

- `workspace` is optional; if absent, rules are fetched by ID regardless of workspace.
- `ruleIds` is required and limited to ≤ 100 rules per call (guarded at API layer).
- The response `runId` is the ID of the persisted `validation_run` record.

---

## DQ-1.3 — Cross-Rule Conflict / Inconsistency Detection

Status: [x] Complete
Files changed:
- `dq-api/fastapi/app/application/services/conflict_detection.py` *(new)*
- Batch validation endpoint integrates `detect_conflicts()`

Checks performed:

| Type                         | Check ID                       | Condition                                                    |
|------------------------------|-------------------------------|--------------------------------------------------------------|
| Duplicate expression         | `DQ1_DUPLICATE_EXPRESSION`    | Two rules share the same normalized filter expression         |
| Duplicate name               | `DQ1_DUPLICATE_NAME`          | Two rules share the same name (case-insensitive)              |
| Contradictory predicates     | `DQ1_CONTRADICTORY_PREDICATES`| Same field has logically opposite constraints (heuristic)     |

Conflicts are returned in the batch validation response as a top-level `conflicts` array.
Each item references `ruleId`, `conflictsWith` (rule ID), `conflictType`, `message`.

---

## DQ-1.4 — Validation Run History + Exportable Reports

Status: [x] Complete
Files changed:
- `dq-api/fastapi/app/infrastructure/orm/models.py` — `ValidationRunRow`, `ValidationRunItemRow`
- `dq-api/fastapi/app/domain/interfaces/v1/validation_run_repository.py` *(new)*
- `dq-api/fastapi/app/infrastructure/repositories/in_memory_validation_run_repository.py` *(new)*
- `dq-api/fastapi/app/infrastructure/repositories/postgres_validation_run_repository.py` *(new)*
- `dq-api/fastapi/app/infrastructure/repositories/__init__.py` — exports updated
- `dq-api/fastapi/app/domain/interfaces/v1/__init__.py` — exports updated
- `dq-api/fastapi/app/core/dependencies.py` — `get_validation_run_repository()`
- `dq-api/fastapi/app/api/v1/endpoints/validation_runs.py` *(new)*
- `dq-api/fastapi/app/api/v1/router.py` — router registered

Endpoints:
```
GET  /api/rulebuilder/v1/rules/validation-runs          paginated list of past runs
GET  /api/rulebuilder/v1/rules/validation-runs/{run_id} detail with per-rule items
GET  /api/rulebuilder/v1/rules/validation-runs/{run_id}/export?format=csv|json
```

Schema (DB level):
- `validation_runs(id, workspace, triggered_by, run_at, total, valid_count, invalid_count, status)`
- `validation_run_items(id, run_id FK, rule_id, rule_name, valid, errors, warnings, diagnostics JSONB, conflicts JSONB)`

---

## DQ-1.5 — Real-Time Validation Feedback During Rule Authoring

Status: [x] Complete
Files changed:
- `dq-ui/src/components/features/RuleValidation.tsx` — full implementation replacing placeholder
- `dq-ui/src/components/features/RuleValidation.css` *(new)*

Behaviour:
- Panel accessible from the Rule Validation feature tab.
- Loads all rules in the current workspace.
- "Validate All" button calls `POST /api/rulebuilder/v1/rules/validate/batch` with all rule IDs.
- Per-rule expandable row shows diagnostics (errors and warnings with icons).
- Conflict section shows cross-rule conflicts if detected.
- "Export" button downloads the batch result as a JSON file.
- Past run history summary (last 10 runs) loaded from `GET /api/rulebuilder/v1/rules/validation-runs`.
- Responds to `featureRuleValidation` app_config flag; shows "feature disabled" state when off.

---

## Database Migration Note

`validation_runs` and `validation_run_items` tables must be added to the database.
A migration script is provided at:
- `dq-db/sql/migrations/DQ_1_001_validation_run_history.sql`

The in-memory implementation (used when no `DATABASE_URL` is configured) stores runs
only for the lifetime of the process.

---

## Completion Summary

All 5 sub-items delivered. Key metrics:

- **Tests added**: 41 (11 conflict detection + 12 validation policy + 9 batch endpoint + 10 run endpoint)
- **Regressions**: 0 (24 existing `test_rules_endpoint.py` tests still pass)
- **DB migration**: `dq-db/sql/migrations/DQ_1_001_validation_run_history.sql`
- **UI**: `dq-ui/src/components/features/RuleValidation.tsx` + `RuleValidation.css`

Bugs discovered and fixed during test phase:
- `ValidationRunRepository` missing from `app/domain/interfaces/__init__.py` — added export
- `await config_repository.get_app_config()` was incorrect — `get_app_config()` is synchronous
- `/rules/validation-runs` route was shadowed by dynamic `/{rule_id}` — fixed by registering `validation_runs_router` before `rules_router`
- `ValidationRunItemView.id` was required but not set — `InMemoryValidationRunRepository` now auto-generates `uuid4()` for item ids
