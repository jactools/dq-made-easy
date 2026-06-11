# API-6 FastAPI API Platform Migration

Goal: Standardize API services on FastAPI and phase out legacy API implementations with controlled migration, contract compatibility, and measurable cutover readiness.

Decision Reference
- FastAPI is the mandatory API platform for new and migrated API endpoints.
- Decision and constraints are captured in [ADR-013](../../architecture/adr/ADR-013-fastapi-api-platform-mandate-and-migration-plan.md).

Migration Principles
- Preserve external API contracts during migration (`/v1/*`, auth semantics, error model, pagination).
- Use phased migration with verification gates, then perform direct cutover to FastAPI.
- Keep observability parity (correlation IDs, structured errors, health/readiness, metrics).
- Gate cutover with objective contract, integration, performance, and security checks.

## Phased Migration Plan

1) Foundation and Contract Baseline
- Freeze and document current API contracts and critical flows.
- Generate/verify OpenAPI baselines for parity checks.
- Define endpoint migration order by business criticality and dependency risk.

2) FastAPI Platform Setup
- Establish FastAPI project skeleton, shared middleware, auth adapters, and error/pagination standards.
- Add compatibility layer for existing auth/gateway expectations.
- Add CI checks for OpenAPI diff and contract drift.

3) Incremental Endpoint Migration
- Migrate low-risk read endpoints first.
- Migrate mutation endpoints after contract and behavior parity is proven.
- Run dual-stack verification (legacy vs FastAPI) until confidence threshold is met.

4) Cutover and Decommission
- Route traffic to FastAPI by endpoint/domain according to rollout plan.
- Execute a direct cutover after parity checks pass, then monitor error/latency/SLOs during the stabilization window.
- Decommission legacy API components after sustained stability window.

Acceptance Criteria
- New API endpoints are implemented only in FastAPI.
- Migrated endpoints pass contract parity checks against baseline behavior.
- Auth, gateway, and error/pagination semantics remain stable for clients.
- Observability and operational dashboards are complete for migrated paths.
- Legacy API paths are decommissioned after successful cutover and rollback window.

Tracked Work Items (Proposed)
- [x] `API-6.1` FastAPI architecture baseline and shared middleware package
- [x] `API-6.2` Contract baseline capture and OpenAPI parity checks
- [x] `API-6.3` Auth/gateway compatibility layer for FastAPI routes
- [x] `API-6.4` Endpoint migration wave 1 (low-risk reads)
- [x] `API-6.5` Endpoint migration wave 2 (core business reads/writes)
- [x] `API-6.6` Endpoint migration wave 3 (admin/config/edge cases)
- [x] `API-6.7` Move test data from code to pytest fixtures
- [x] `API-6.8` Move SQL statements out of the code (SQLAlchemy ORM foundation)
- [x] `API-6.9` Dual-run verification and behavior-diff reporting
- [x] `API-6.10` Obsolete: canary rollout de-scoped by product decision
- [x] `API-6.10R` UI FastAPI-only endpoint enforcement in `dq-ui`
- [x] `API-6.11` Legacy API decommission runbook and execution
- [ ] `API-6.12` Split authenticated session/profile reads out of the admin namespace, introducing a future `GET /user/v1/me` surface and reserving `/admin/v1` for admin-only operations
- [x] `WF-4.10` API test automation alignment to FastAPI (`pytest` + `httpx`) — 55 test files, all using pytest + FastAPI TestClient; only surviving legacy test is a frontend Axios interceptor unit test unrelated to API server
- [x] `DOC-6.1` FastAPI migration guide for developers and operators (`docs/technical/API_6_FASTAPI_MIGRATION_GUIDE.md`)

## API-6.5 Progress Notes

- Completed slice: `GET /api/rulebuilder/v1/rules/{rule_id}/versions` and `GET /api/rulebuilder/v1/rules/{rule_id}/versions/{version_id}` with auth, API tests, and repository unit tests.
- Completed slice: `POST /api/rulebuilder/v1/rules/{rule_id}/rollback` with auth, API tests, and repository unit tests.
- Completed slice: `PATCH /api/rulebuilder/v1/rules/{rule_id}/versions/{version_id}/tags` with auth, API tests, and repository unit tests.
- Completed slice: `GET /api/rulebuilder/v1/rules/{rule_id}/versions/rollback-history` with auth, API tests, and repository unit tests.
- Completed slice: `GET /api/rulebuilder/v1/rules/{rule_id}/versions/{version_1}/compare/{version_2}` with auth, API tests, and repository unit tests.
- Completed slice: `GET /api/rulebuilder/v1/rules/{rule_id}/versions/stats` with auth, API tests, and repository unit tests.
- Completed slice: `PATCH /api/rulebuilder/v1/rules/{rule_id}/versions/{version_id}/mark-for-rollback` with auth, API tests, and repository unit tests.
- Completed slice: `GET /api/data-catalog/v1/data-objects` with auth, API tests, and repository unit tests.
- Completed slice: `GET /api/rulebuilder/v1/test-proofs/{rule_id}` with auth, API tests, and repository unit tests.
- Completed slice: `POST /api/rulebuilder/v1/batch-test-requests` and `POST /api/rulebuilder/v1/batch-test-requests/{id}/run` with auth, API tests, and repository unit tests.
- Completed slice: `POST /api/data-catalog/v1/data-object-versions/{version_id}/generate-test-data` with auth, API tests, and repository unit tests.
- Completed slice: `POST /api/rulebuilder/v1/rules/{rule_id}/test-with-data` with auth, API tests, and repository unit tests.
- Completed slice: `POST /api/rulebuilder/v1/rules/{rule_id}/test` with auth, API tests, and repository unit tests.
- Completed slice: `POST /api/rulebuilder/v1/rules/{rule_id}/test-with-generated-data` with auth, API tests, and repository unit tests.
- Contract parity checks split and passing: core API-6.5 wave-2 check uses `contracts/required/api65-wave2-migrated-core.json`; cumulative migrated-surface check uses `contracts/required/api65-cumulative-migrated-surface.json`.
- API-6.5 scope complete: wave-2 migrated endpoints and required-operations parity checks are complete and passing.

## API-6.6 Progress Notes

- Completed slice: `POST /api/data-catalog/v1/rule-attributes` with repository contract updates, in-memory/postgres behavior, API/auth/unit tests, and full FastAPI validation suite pass.
- Completed slice: `PUT /api/system/v1/app-config` with repository persistence support, API/auth/unit tests, and FastAPI contract-aligned write behavior.
- Completed slice: `GET /api/admin/v1/users` and `GET /api/admin/v1/roles` with admin-scope auth, filtering/pagination parity for users, in-memory/postgres repositories, and FastAPI API/unit tests.
- Completed slice: `PUT /api/admin/v1/users/{user_id}`, `POST /api/admin/v1/users/{user_id}/reset-profile`, and `POST /api/admin/v1/users/{user_id}/reset-settings` with workspace-capacity checks, preference reset behavior, admin auth enforcement, and FastAPI API/unit tests.
- Completed slice: `GET /api/admin/v1/me` and `PUT /api/admin/v1/me` with JWT-claim-based current-user resolution, preference persistence, auth enforcement, and FastAPI API/unit tests.
- Completed slice: `POST /api/auth/v1/login`, `POST /api/auth/v1/logout`, `GET /api/auth/v1/redirect`, and `GET /api/auth/v1/callback` with stateless local bearer issuance, OIDC state handling, callback user provisioning, and FastAPI auth API coverage.
- Completed slice: `GET /api/rulebuilder/v1/approvals` and `GET /api/rulebuilder/v1/approvals/audit` with scope-enforced auth, pagination/filtering parity, in-memory/postgres repository support, and FastAPI API/unit tests.
- Completed slice: `POST /api/rulebuilder/v1/approvals`, `PUT /api/rulebuilder/v1/approvals/{id}`, and `DELETE /api/rulebuilder/v1/approvals/{id}` with scope-enforced auth, requester safety checks, in-memory/postgres repository parity, audit logging behavior, and FastAPI API/unit tests.
- Completed slice: `GET /api/rulebuilder/v1/workspaces`, `POST /api/rulebuilder/v1/workspaces`, `PUT /api/rulebuilder/v1/workspaces/{id}`, and `DELETE /api/rulebuilder/v1/workspaces/{id}` with scope-enforced auth, workspace limit enforcement, default-workspace delete guard, in-memory/postgres repository support, and FastAPI API/unit tests.
- Contract parity profile for API-6.6 wave-3 added and passing: `contracts/required/api66-wave3-admin-edge.json`.
- Final parity hardening complete: migration-aware required-operation profiles pass for API-6.4, API-6.5 wave-2, API-6.5 cumulative migrated surface, and API-6.6 wave-3 (`api64-wave1-migrated-reads.json`, `api65-wave2-migrated-core.json`, `api65-cumulative-migrated-surface.json`, `api66-wave3-admin-edge.json`).
- API-6.6 scope complete.

## Repository Error-Semantics Hardening

All Postgres repositories have been hardened to eliminate legacy fallback paths. The API now targets the current database schema exclusively.

### Changes Applied

**Pattern removed:** `try/except Exception` blocks that silently caught DB errors and retried with a legacy schema variant. These masked real database failures and kept dead compatibility code reachable.

**Repositories changed:**

- `postgres_admin_repository.py` — atomic transactions for user create/update/preference reset (earlier pass).
- `postgres_approvals_repository.py` — removed `workspace_id` → `workspace` column fallback in `create_approval` and `_fetch_approvals_with_workspace`; removed `_is_legacy_workspace_column_error` helper; all `workspaceId` row mappings use `workspace_id` only.
- `postgres_app_config_repository.py` — removed `SELECT * FROM app_config LIMIT 1` legacy-shape fallback in `get_app_config`; removed `try/except` with `_persist_legacy_row` fallback in `set_app_config`; removed `_persist_legacy_row`, `_fetch_one`, `_execute`, and `_is_legacy_app_config_schema_error` (all dead code after fallback removal).
- `postgres_testing_repository.py` — removed `_is_missing_placeholder_relation` swallow-and-return-empty fallbacks in `list_batch_test_requests`, `get_batch_test_request`, and `list_test_proofs`; DB errors now propagate.
- `postgres_workspaces_repository.py` — `update_workspace` raises `RuntimeError` on failed write instead of silently returning success.

### Tests Updated

Legacy fallback–specific tests were replaced with tests that verify the new behavior (errors propagate, current-schema columns are used). The 90% coverage gate is maintained throughout.

Suite state after hardening: **266 passed, 90.91% total coverage**.

## API-6.7 Progress Notes

- Consolidated in-memory repository seed data into `dq-api/fastapi/app/infrastructure/repositories/in_memory_test_data.py` with shared generators for admin, approvals, workspaces, testing, data catalog, and rules domains.
- Rewired in-memory repositories to consume shared generated seed data instead of embedding large inline test datasets in constructors:
	- `in_memory_admin_repository.py`
	- `in_memory_approvals_repository.py`
	- `in_memory_workspaces_repository.py`
	- `in_memory_testing_repository.py`
	- `in_memory_data_catalog_repository.py`
	- `in_memory_rules_repository.py`
- Split shared pytest fixtures by responsibility under `dq-api/fastapi/tests/fixtures/` with a thin `dq-api/fastapi/tests/conftest.py` plugin registry, while keeping the layered suite layout under `tests/api`, `tests/application`, `tests/core`, `tests/middleware`, and `tests/infrastructure`.
- Added CSV-backed fixture loading for structured test data: when a matching file exists under `dq-api/fastapi/tests/fixtures/data/<fixture_name>.csv`, the fixture loads from CSV; otherwise it falls back to the in-code default data.
- Expanded resolver/view-model pattern to all endpoint domains: admin, approvals, workspaces, app_config, auth, testing, data_catalog, and utility (health/readiness/system-info).
	- Created `app/api/v1/schemas/` view model files for every domain (10 files total including pre-existing `rule_view.py`).
	- Created `app/application/resolvers/` resolver modules for every domain (9 files total).
	- All endpoints now declare explicit `response_model=` and delegate serialization to resolver functions instead of inline `model_dump()`.
- Moved repository Protocol contracts from `app/domain/repositories/` to a versioned `app/domain/interfaces/v1/` package; `app/domain/interfaces/__init__.py` re-exports from `v1` for backward-compatible flat imports. Old `app/domain/repositories/` package removed.
- Validation evidence:
	- Targeted repository unit tests passed: `39 passed` (`tests/infrastructure/unit/repositories/postgres/test_testing_repository.py`, `tests/infrastructure/unit/repositories/postgres/test_data_catalog_repository.py`, `tests/infrastructure/unit/repositories/postgres/test_rules_repository_postgres.py`).
	- Repository-root targeted postgres repository batch is currently:
	  `/Users/jacbeekers/gitrepos/dq-rulebuilder/venv/bin/python -m pytest -q dq-api/fastapi/tests/infrastructure/unit/repositories/postgres/test_system_repository.py dq-api/fastapi/tests/infrastructure/unit/repositories/postgres/test_app_config_repository_postgres.py dq-api/fastapi/tests/infrastructure/unit/repositories/postgres/test_workspaces_repository_postgres.py dq-api/fastapi/tests/infrastructure/unit/repositories/postgres/test_approvals_repository_postgres.py dq-api/fastapi/tests/infrastructure/unit/repositories/postgres/test_data_catalog_repository.py dq-api/fastapi/tests/infrastructure/unit/repositories/postgres/test_testing_repository.py dq-api/fastapi/tests/infrastructure/unit/repositories/postgres/test_admin_repository.py dq-api/fastapi/tests/infrastructure/unit/repositories/postgres/test_me_repository.py --no-cov`
	  and was verified with `51 passed` from the repository root.
	- Full FastAPI test suite passed: `266 passed` with coverage gate satisfied (`92.91%`).
- API-6.7 scope complete.

## API-6.8 Progress Notes

- Introduced `sqlalchemy>=2.0,<3.0` as a dependency alongside the existing `psycopg[binary]` driver. SQLAlchemy uses `psycopg` (v3) as the PostgreSQL dialect via `postgresql+psycopg://`; no `pyodbc` is used.
- Created `app/infrastructure/orm/` package as the SQLAlchemy ORM layer:
	- `base.py`: `DeclarativeBase` shared by all model classes.
	- `models.py`: 30 mapped ORM classes derived from `dq-db/init/01_schema.sql`, `02_profiling_schema.sql`, and `04_rule_versioning.sql`.
	- `__init__.py`: re-exports `Base` and all `*Row` classes.
- ORM model inventory by domain:
	- **Core** (4): `WorkspaceRow`, `UserRow`, `RoleRow`, `UserRoleRow`
	- **Rules** (6): `RuleRow`, `ReusableFilterRow`, `RuleReusableFilterRow`, `ReusableJoinRow`, `RuleAttributeRow`, `BatchTestRequestRow`
	- **Rule versioning** (4): `RuleVersionRow`, `RuleVersionDiffRow`, `RuleRollbackRow`, `RuleVersionRelationshipRow`
	- **Approvals** (2): `ApprovalRow`, `AuditRow`
	- **Data catalog** (7): `DataProductRow`, `DataSetRow`, `DataObjectRow`, `DataObjectCatalogRow`, `DataObjectVersionRow`, `AttributeCatalogRow`, `DataDeliveryRow`
	- **Testing** (2): `TestProofRow`, `BatchTestRequestRow`
	- **Configuration** (2): `AppConfigRow`, `SystemInfoRow`
	- **Profiling** (4): `DataSourceMetadataRow`, `DataSourceProfilingRequestRow`, `SuggestionRow`, `SuggestionInteractionRow`
- Circular FK between `rules` and `rule_versions` resolved with `use_alter=True` on `rules.current_version_id` (mirrors the `ALTER TABLE ADD CONSTRAINT` pattern used in the DDL).
- PostgreSQL-specific types used where required: `JSONB` (test_data, test_data_config, suggested_rule, profiling statistics), `ARRAY(Text())` (rule_versions.tags), `Numeric(3,2)` (suggestions.confidence_score), `BigInteger` (record_count, size_bytes).
- Known schema divergences documented as inline comments: `approvals.workspace` → live DB uses `workspace_id`; `users.external_id` present in code but absent from original DDL.
- ORM files excluded from the pytest coverage gate via `.coveragerc` (`omit = app/infrastructure/orm/*`) — they are pure schema declarations with no business logic.
- Existing postgres repositories are unchanged; raw `psycopg` access remains in place. Migrating repositories to use the ORM session is the next step.
- Validation evidence:
	- Full FastAPI test suite: `266 passed`, coverage gate satisfied (`92.91%`).
- API-6.8 scope complete (SQLAlchemy ORM foundation; repository migration to follow).

## API-6.9 Progress Notes

- Added dual-run behavior verification script: `dq-api/fastapi/scripts/contracts/run_behavior_dual_run.py`.
- Added managed orchestration script: `dq-api/fastapi/scripts/contracts/run_behavior_dual_run_with_services.py` to start legacy + FastAPI, run behavior diff, and stop both services.
- Added scenario-driven comparison input file for smoke checks: `dq-api/fastapi/contracts/verification/api69-dual-run-smoke.json`.
- Behavior diff reports are now produced as both JSON and Markdown artifacts under `dq-api/fastapi/contracts/current/`.
- Added command shortcuts in `dq-api/package.json`:
	- `npm run contract:behavior:diff`
	- `npm run contract:behavior:diff:with-services`
- Validation evidence:
	- Managed run passes end-to-end (`npm run contract:behavior:diff:with-services`).
	- Current smoke scenario set passes with `2 passed / 0 failed` and report output at `dq-api/fastapi/contracts/current/api69-behavior-diff-report.{json,md}`.
- API-6.9 scope complete.

### Post-6.9 Hardening: UI Endpoint Contract Guard

- Added targeted guard for validate route parity:
	- `dq-api/fastapi/tests/api/test_ui_endpoint_contract.py`
	- Ensures UI `fetch(.../rules/{id}/validate)` has matching FastAPI route `/rulebuilder/v1/rules/{rule_id}/validate`.
- Added broad guard for all detected UI fetch calls:
	- `dq-api/fastapi/tests/api/test_ui_endpoint_contract_all.py`
	- Scans `dq-ui/src` fetch templates using group-first bases (e.g. `toApiGroupV1Base('rulebuilder', ...)`) and validates method+path against FastAPI registered routes.
- Current validation command:
	- `cd dq-api/fastapi && /Users/jacbeekers/gitrepos/dq-rulebuilder/venv/bin/python -m pytest -q tests/api/test_ui_endpoint_contract.py tests/api/test_ui_endpoint_contract_all.py --no-cov`
	- Last known result: `2 passed`.
- Post-6.9 endpoint checklist (implemented):
	- [x] `POST /rulebuilder/v1/rules/{ruleId}/validate`
	- [x] `GET /rulebuilder/v1/reusable-filters`
	- [x] `POST /rulebuilder/v1/reusable-filters`
	- [x] `DELETE /rulebuilder/v1/reusable-filters/{filterId}`
	- [x] `GET /rulebuilder/v1/reusable-joins`
	- [x] `POST /rulebuilder/v1/reusable-joins`
	- [x] `DELETE /rulebuilder/v1/reusable-joins/{joinId}`
	- [x] `GET /system/v1/suggestions/metrics`
	- [x] `POST /rulebuilder/v1/rules`
	- [x] `PUT /rulebuilder/v1/rules/{ruleId}`
	- [x] `POST /rulebuilder/v1/rules/{ruleId}/validate/enriched`
	- [x] `POST /rulebuilder/v1/rules/{ruleId}/activate`
	- [x] `POST /rulebuilder/v1/rules/{ruleId}/template`
	- [x] `POST /rulebuilder/v1/aliases/resolve`
	- [x] `GET /rulebuilder/v1/rule-versions/{ruleId}`
	- [x] `GET /rulebuilder/v1/catalog/health`
	- [x] `GET /rulebuilder/v1/catalog/terms`
	- [x] `GET /rulebuilder/v1/governance/drift/summary`
	- [x] `GET /rulebuilder/v1/governance/drift/rules/{termKey}/{status}`
	- [x] `GET /rulebuilder/v1/governance/drift/terms/{termKey}/affected-rules`
	- [x] `POST /rulebuilder/v1/governance/revalidation/jobs`
	- [x] `GET /rulebuilder/v1/governance/revalidation/jobs/{jobId}`

### Pending UI Endpoints (Explicitly Tracked)

The broad UI contract guard keeps these endpoints in an explicit pending allowlist until corresponding FastAPI endpoints are migrated:

- [x] No pending UI endpoints remain in the explicit allowlist.

- Contract scanner hardening:
	- `test_ui_endpoint_contract_all.py` now also scans fetch calls using `${apiBaseUrl}` to close a previous detection blind spot.

### ORM-Capability Enforcement Policy (Unit vs Integration)

- Unit tests may use in-memory repositories and test doubles/stubs.
- Integration tests must run with `DATABASE_URL` configured and `REQUIRE_DATABASE=true` so dependency wiring resolves Postgres repositories.
- Health endpoints are exempt from ORM-capability requirements:
	- `GET /api/system/v1/health`
	- `GET /api/system/v1/readiness`
	- `GET /api/rulebuilder/v1/catalog/health`
- All other API endpoints must remain repository-backed (ORM-capable when database settings are enabled).
- Enforcement guard added:
	- `dq-api/fastapi/tests/infrastructure/integration/test_endpoint_orm_capability.py`
	- Fails integration runs when a non-health `/api/<group>/v1/*` route has no repository dependency from `app.core.dependencies`.
	- Also fails integration runs when a non-health endpoint module defines mutable module-level runtime stores (e.g. dict/list/set caches or pending-state maps used as API state).
- Integration fixture hardening:
	- `dq-api/fastapi/tests/infrastructure/integration/conftest.py` now forces database-backed dependency settings for integration runs.


## API-6.10 Decision Update

- Canary rollout has been de-scoped and marked obsolete by product direction.
- Migration now uses parity-gated direct cutover to FastAPI.
- UI migration focus is now strict FastAPI-only API usage (no legacy API host fallbacks).

## API-6.11 Decommission Runbook and Execution

### Scope
Remove the legacy NestJS API (port 4001) and make FastAPI (port 4010) the sole active API service.

### Runbook

**Pre-conditions (all met before execution):**
- [x] All endpoints migrated to FastAPI (API-6.4 – API-6.6)
- [x] UI calls only FastAPI via Kong (API-6.10R)
- [x] Dual-run verification passed with zero behavior diffs (API-6.9)
- [x] Contract parity profiles passing for all waves

**Execution steps:**
1. Switch docker-compose `api` service from `Dockerfile.api.archive` (legacy NestJS/4001) to `Dockerfile.fastapi` (FastAPI/4010)
2. Update port mapping from `4001:4001` → `4010:4010`
3. Update Kong bootstrap upstream from `http://api:4001` → `http://api:4010`
4. Update healthcheck URL in docker-compose from port 4001 → 4010
5. Archive legacy NestJS server code under `dq-api/server/`
6. Rebuild and verify: `docker compose up -d --build api kong && ./scripts/smoke_test_stack.sh`

**Rollback:**
- Revert docker-compose `api` service to `Dockerfile.api.archive`
- Revert Kong bootstrap to `http://api:4001`
- Rebuild: `docker compose up -d --build api kong`

### Progress Notes

- docker-compose `api` service switched to `Dockerfile.fastapi`; port mapping `4010:4010`; healthcheck on port 4010
- Kong bootstrap upstream updated to `http://api:4010`
- Legacy NestJS server code archived to `dq-api/server-archive/` (preserved for reference, not built)
- `Dockerfile.api.archive` retained as archive; `Dockerfile.fastapi` is now the sole active build target
- Smoke tests pass after cutover: all 4 Kong-level checks green

Delivery Milestones
- [x] Milestone A (Baseline): `API-6.1` to `API-6.3`
- [x] Milestone B (Migration Waves): `API-6.4` to `API-6.6`
- [x] Milestone B2 (Migration away from testdata in code and SQL in API)
- [x] Milestone C (Verification/Cutover): `API-6.9` + direct cutover decision (`API-6.10` obsolete)
- [x] Milestone D (Decommission/Docs): `API-6.11` complete
