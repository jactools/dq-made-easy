# DQ-7.3 Rule Compiler Implementation Progress

Status: [x] Complete (DQ-7.3 scope)
Last updated: 2026-03-16
Related feature tracker: ../features/DQ_FEATURES.md
Related user guidance: ../user-manuals/DQ-1_RULE_VALIDATION_USER_GUIDE.md and ../user-manuals/DQ-2_JOIN_CONDITIONS_USER_GUIDE.md

## Scope

DQ-7.3 implements a compiler stage that transforms a stored rule expression into an intermediate executable model for the DSL runtime.

Target pipeline:
- Rule expression -> normalized expression -> intermediate model -> executable artifact mapping

## Implemented in this iteration

### 1) Compiler service added

File:
- dq-api/fastapi/app/application/services/rule_compiler.py

Primary entrypoint:
- compile_rule_to_intermediate_model(...)

Current behavior:
- Normalizes filter expressions (logical operators, inequality token, whitespace)
- Validates filter expressions using existing DQ-7.2 validation logic
- Parses lightweight predicate fragments for intermediate representation
- Infers alias expectations
- Normalizes optional join definitions and surfaces join diagnostics
- Emits compiler diagnostics (error-oriented)
- Produces deterministic artifact key based on rule id/version/expression hash
- Returns compilable true/false

Intermediate model shape (current):
- artifactKey
- compilerVersion
- target
- rule
- filter
- join
- diagnostics
- compilable

### 2) API validate endpoint integrated with compiler output

File:
- dq-api/fastapi/app/api/v1/endpoints/rules.py

Endpoint:
- POST /api/rulebuilder/v1/rules/{rule_id}/validate

Current behavior:
- Compiles rule through DQ-7.3 service
- Returns normalized compiledExpression
- Returns inferredAliases from intermediate model
- Returns compiler metadata:
  - artifactKey
  - compilerVersion
  - target
  - intermediateModel
- Maps compiler diagnostics into endpoint diagnostics
- Computes summary counts from diagnostics

### 3) Tests added and updated

Compiler service tests:
- dq-api/fastapi/tests/application/services/test_rule_compiler.py

Rules endpoint tests:
- dq-api/fastapi/tests/api/test_rules_endpoint.py

Coverage of current tests includes:
- Successful compile path
- Unsupported construct diagnostics
- Join normalization path
- Invalid join diagnostics
- Validate endpoint includes compiler fields and consistent artifact data

### 4) Fixture policy tightening for application service tests

Files:
- dq-api/fastapi/scripts/testing/check_fixture_usage.py
- dq-api/fastapi/tests/fixtures/rule_compiler_fixtures.py
- dq-api/fastapi/tests/conftest.py

Current behavior:
- Enforcer now checks fixture usage and detects complex inline payload literals in tests/application/services/
- Compiler join payload moved to fixture source to satisfy policy

## Validation results

Executed successfully:
- Focused compiler and endpoint tests
- Full unit runner: dq-api/fastapi/scripts/testing/run_unit_with_pylint.sh
- Broader FastAPI backend sweep: `tests/api` + `tests/application/services` + `tests/infrastructure/unit/repositories`

Latest result after DQ-7.3 integration work:
- 489 passed

Latest result after DQ-7.3 compatibility/traceability hardening:
- 410 passed (broader backend sweep)

Latest result after scheduler-handoff contract increment:
- 411 passed (broader backend sweep)

Latest result after batch lifecycle transition increment:
- 413 passed (broader backend sweep)

Latest result after failed lifecycle-path increment:
- 416 passed (broader backend sweep)

Latest result after enriched runtime-failure diagnostics increment:
- 417 passed (broader backend sweep)

Validation note:
- One transient compatibility failure surfaced in in-memory proof listing for legacy seed rows where `executionTrace` was absent.
- Resolved by normalizing proof-list output to always emit baseline execution trace fields (`executionId`, `executedAt`, `resultStatus`) during read mapping.

## Progress snapshot

Completed (DQ-7.3 foundation):
- [x] Compiler module and deterministic artifact key
- [x] Intermediate model generation
- [x] Compiler-aware validate endpoint response
- [x] Initial diagnostics flow
- [x] Test coverage for compiler basics
- [x] Internal compiler artifact persistence foundation (ORM + repositories)

In progress:
- [x] Intermediate model schema hardening and versioning strategy
- [x] Diagnostic taxonomy refinement (error/warning/info codes)
- [x] Compiler output contract alignment with downstream dq-engine execution

DQ-7.3 depth completed:
- [x] Full AST fidelity for all grammar constructs in DQ-7.2
- [x] Explicit executable artifact persistence/version mapping store
- [x] End-to-end compile artifact handoff into scheduler/executor pipeline

Deferred to DQ-7.6 implementation phase:
- [ ] Enrich execution-result traceability lifecycle persistence with deeper downstream executor integration.
- [ ] Expand downstream executor-originated failure diagnostics beyond current runtime/fallback metadata.

## Next implementation steps

- [x] Introduce typed schema models for intermediate model and diagnostics in API layer.
- [x] Expand parser coverage to BETWEEN, IN, LIKE/RLIKE and grouped logical precedence fidelity.
- [x] Add compiler contract tests for deterministic artifact keys and stable serialization.
- [x] Add backward-compatibility policy for compilerVersion and model evolution.
- [x] Prepare handoff contract for DQ-7.6 execution-result traceability fields.
- [x] Add rule-version compiler artifact storage model and repository APIs.

## Intermediate model schema hardening and versioning strategy

Implemented hardening:
- Added explicit `schemaVersion` to intermediate model payload (`1.1.0`).
- Hardened API schema constraints:
  - `target` is constrained to `dsl`.
  - `compilerVersion` must match `dq-<major>.<minor>.<patch>`.
  - `schemaVersion` must match semantic version format `<major>.<minor>.<patch>`.
  - `logicalOperators` constrained to `AND|OR|NOT`.
- Added `executionContract` block for downstream alignment:
  - `engineTarget: dq-engine`
  - `inputFormat: dq.intermediate-model.v1`
  - `traceability` fields (`ruleId`, `ruleVersionId`, `artifactKey`, `compilerVersion`, `schemaVersion`)
  - `requiredExecutionResultFields` declaration for DQ-7.6 execution traceability handoff
- Added contract tests for deterministic serialization and version field shape.

Versioning strategy:
- `compilerVersion` tracks compiler implementation releases and may change independently of schema.
- `schemaVersion` tracks the intermediate model contract consumed downstream.
- Policy:
  - Patch (`x.y.Z`): non-breaking fixes/normalization stability.
  - Minor (`x.Y.z`): additive, backward-compatible fields only.
  - Major (`X.y.z`): breaking contract changes requiring downstream adapter updates.
- Compatibility rule:
  - Downstream consumers must gate parsing on `schemaVersion`.
  - Current supported schema series: `1.x.x`.

## Full AST fidelity delivery (DQ-7.2 grammar coverage)

Implemented in compiler service:
- Added recursive-descent parser over normalized expressions.
- Added AST emission under `filter.ast` with node types:
  - `logical` (`AND`, `OR`)
  - `unary` (`NOT`)
  - `predicate`
- Added predicate coverage for grammar constructs:
  - Comparison operators (`=`, `!=`, `<>`, `>`, `>=`, `<`, `<=`)
  - `IS NULL` / `IS NOT NULL`
  - `[NOT] IN (...)`
  - `[NOT] BETWEEN ... AND ...`
  - `[NOT] LIKE`, `[NOT] RLIKE`, and regex aliases (`~`, `!~`)
- Preserved additive compatibility by keeping existing `predicates` and `logicalOperators` fields.

## Execution handoff slice (scheduler/executor integration)

Implemented in this slice:
- Test execution endpoints now return `executionContext` containing handoff metadata sourced from rule-version compiler artifacts.
- Batch test run endpoint now also returns `executionContext` for the underlying request rule.
- Batch run now returns explicit scheduler handoff envelope in `executionContext.schedulerHandoff`:
  - `handoffId`, `batchRequestId`, `submittedAt`, `executorTarget`, `handoffStatus`, `handoffReady`.
- Batch request lifecycle state now persists on run for existing requests:
  - Repository-backed transition `pending -> running` in both in-memory and Postgres repositories.
  - Batch request GET/list APIs reflect updated status after run.
- Batch rule test execution now persists completion lifecycle fields for existing requests:
  - Transition `running -> completed` with `proofId` linkage and `completedAt` timestamp.
  - Run endpoint now returns `completed` for executed requests and request detail view exposes persisted completion fields.
- Batch rule test execution now supports failed lifecycle persistence for existing requests:
  - Transition `running -> failed` on executor/runtime exceptions during batch run execution.
  - Failed requests persist `completedAt`, keep `proofId=null`, and store failure metadata under `testDataConfig.executionFailure`.
  - Failure metadata now includes structured diagnostics fields for downstream correlation:
    - `reason`, `errorType`, `message`
    - `errorCode` (default `EXECUTOR_RUNTIME_ERROR`, overridden when executor provides one)
    - `correlationId` (generated fallback, overridden when executor provides one)
- Proof traceability now threads `correlationId` across write/read surfaces where proofs exist:
  - Rule test proof logging (`POST /api/rulebuilder/v1/rules/{rule_id}/test`) now includes `correlationId` in `executionTrace`.
  - Proof storage repositories persist `correlationId` in `proofData.executionTrace`.
  - Proof retrieval (`GET /api/rulebuilder/v1/test-proofs/{rule_id}`) and top-level `executionTrace` views expose `correlationId`.
- Batch execution handoff now also carries `correlationId` for end-to-end trace continuity:
  - `executionContext.correlationId` is emitted on batch run responses.
  - `executionContext.schedulerHandoff.correlationId` is emitted and matches the same value.
- Batch request records now persist the same trace key for follow-up retrieval:
  - Repositories persist correlation ID state during batch run execution.
  - `GET /api/rulebuilder/v1/batch-test-requests/{request_id}` and batch list responses expose the persisted value as top-level `executionCorrelationId`.
  - Run response correlation IDs are now sourced from persisted request state (not a transient-only response value).
  - Since no production deployment has occurred yet, this contract was simplified without backward-compat aliases.
- Test proof logging now persists `executionTrace` payload fields tied to compiler artifact context (`artifactKey`, `ruleVersionId`) and generated `executionId`.
- Test proof read endpoint now surfaces persisted `proofData.executionTrace` so downstream systems can retrieve traceability after execution.
- Test executor paths (`test-with-data`, `test-with-generated-data`) now consume artifact `compiledExpression` when available and expose `executedExpressionSource` in `executionContext`.
- Compiler execution contract now includes explicit `compatibilityPolicy` (`schemaVersioning`, `compilerVersioning`, `supportedSchemaSeries`, minor-version compatibility rule).
- Proof write/read models now expose top-level `executionTrace` for DQ-7.6 handoff fields (`executionId`, `executedAt`, `resultStatus`, `artifactKey`, `ruleVersionId`, compiler/schema metadata).
- Included traceability and readiness fields:
  - `ruleVersionId`, `ruleVersionNumber`
  - `artifactKey`, `compilerVersion`, `compilerRevision`, `schemaVersion`, `compileStatus`
  - `executionContract` (from persisted intermediate model)
  - `handoffReady` flag to indicate whether an execution-ready artifact contract is available.

Current status:
- This completes the API-level handoff contract exposure for test execution paths, including completion-state persistence for batch rule test execution.
- Remaining work is intentionally deferred to DQ-7.6 execution work and is not part of the current DQ-7.3 completion scope.
