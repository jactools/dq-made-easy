# FastAPI Baseline (API-6.1)

This folder contains the API-6.1 FastAPI foundation for migration work.

## Included in this baseline

- Application factory and centralized settings
- Entity-first layering (domain entities, repositories, use-cases)
- pydantic-resolve based response assembly for nested read models
- Shared middleware:
  - Correlation ID propagation (`X-Correlation-ID`)
  - Request timing (`X-Process-Time-MS`)
  - CORS from env
  - Auth and gateway compatibility middleware for `/v1/*` contract behavior
- Standardized RFC7807-style error envelope
- Versioned API router prefix (`/api/v1`)
- Hidden compatibility alias for external `/v1` routing
- Health and readiness endpoints
- Pagination helper schema and utilities

## Local run

```bash
cd dq-api/fastapi
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp ../../.env.dev.example ../../.env.dev.local
set -a
source ../../.env.dev.local
set +a
uvicorn app.main:app --reload --host 0.0.0.0 --port 4010
```

## Unit tests and coverage

```bash
cd <repo-root>
pip install -r dq-api/fastapi/requirements-dev.txt
./scripts/testing/run_unit_with_pylint.sh
```

This script enforces fixture usage for non-ORM tests, then runs `pylint` (error and fatal checks), and finally executes the unit test folders (`tests/api`, `tests/application`, `tests/core`, `tests/domain`, `tests/infrastructure`, `tests/middleware`).

It also writes review artifacts to `test-results/`:
- `unit-pylint.log`
- `unit-pytest.log`
- `unit-junit.xml` (when pytest runs)
- `unit-review-summary.md`

Run smoke tests only (dedicated directory):

```bash
cd dq-api/fastapi
pytest -q -o addopts='' tests/smoke
```

Or from the `dq-api` workspace folder:

```bash
cd dq-api
npm run test:fastapi:smoke
```

Coverage outputs are written to:
- `../test-results/coverage.xml`
- `../test-results/coverage.json`

Coverage defaults are centralized in `../.coveragerc`.

To persist run history for trend reporting (without querying git history), use:

```bash
cd dq-api/fastapi
python scripts/testing/run_tests_with_history.py
python scripts/testing/generate_history_report.py --limit 30
```

Historical artifacts are stored in:
- `test-results/history/test-runs.jsonl` (append-only run history)
- `test-results/history/report.md` (generated summary report)

## API-6.2 Contract Baseline and Parity

Capture legacy contract baseline (example from running legacy Nest API):

```bash
cd dq-api/fastapi
python scripts/contracts/capture_openapi_baseline.py --source url --url http://localhost:4001/v1/openapi.json --output contracts/baseline/openapi-legacy-v1.json
```

Run FastAPI parity check against baseline:

```bash
cd dq-api/fastapi
python scripts/contracts/check_openapi_parity.py --baseline contracts/baseline/openapi-legacy-v1.json --current-source app --current contracts/current/openapi-fastapi-v1.json --strip-prefix /api
```

Run migration-aware parity check for API-6.4 migrated reads (requires operations, ignores expected additions):

```bash
cd dq-api/fastapi
python scripts/contracts/check_openapi_parity.py --baseline contracts/baseline/openapi-legacy-v1.json --current-source app --current contracts/current/openapi-fastapi-v1.json --strip-prefix /api --ignore-new-operations --required-operations contracts/required/api64-wave1-migrated-reads.json
```

Run migration-aware parity check for API-6.5 wave-2 core reads/writes only (requires operations, ignores expected additions):

```bash
cd dq-api/fastapi
python scripts/contracts/check_openapi_parity.py --baseline contracts/baseline/openapi-legacy-v1.json --current-source app --current contracts/current/openapi-fastapi-v1.json --strip-prefix /api --ignore-new-operations --required-operations contracts/required/api65-wave2-migrated-core.json
```

Run migration-aware parity check for cumulative migrated surface (API-6.4 reads + API-6.5 core reads/writes; requires operations, ignores expected additions):

```bash
cd dq-api/fastapi
python scripts/contracts/check_openapi_parity.py --baseline contracts/baseline/openapi-legacy-v1.json --current-source app --current contracts/current/openapi-fastapi-v1.json --strip-prefix /api --ignore-new-operations --required-operations contracts/required/api65-cumulative-migrated-surface.json
```

Run migration-aware parity check for API-6.6 wave-3 admin/config/edge endpoints (requires operations, ignores expected additions):

```bash
cd dq-api/fastapi
python scripts/contracts/check_openapi_parity.py --baseline contracts/baseline/openapi-legacy-v1.json --current-source app --current contracts/current/openapi-fastapi-v1.json --strip-prefix /api --ignore-new-operations --required-operations contracts/required/api66-wave3-admin-edge.json
```

The parity script exits non-zero when required operations, params, request bodies, or baseline response codes drift.

## API-6.9 Dual-Run Behavior Diff Reporting

Run dual-run behavior comparison between legacy and FastAPI endpoints:

```bash
cd dq-api/fastapi
python scripts/contracts/run_behavior_dual_run.py --legacy-base-url http://localhost:4001 --fastapi-base-url http://localhost:4010 --scenarios contracts/verification/api69-dual-run-smoke.json --output contracts/current/api69-behavior-diff-report.json --markdown-output contracts/current/api69-behavior-diff-report.md
```

Use `--dry-run` to validate scenario definitions without executing HTTP calls.
Behavior reports are produced in:
- `contracts/current/api69-behavior-diff-report.json`
- `contracts/current/api69-behavior-diff-report.md`

Run the same behavior diff with automatic service startup and shutdown:

```bash
cd dq-api
npm run contract:behavior:diff:with-services
```

This starts legacy API on `:4001` and FastAPI on `:4010`, waits for health, runs dual-run comparison, writes reports, and stops both processes.

## Endpoints

- `GET /api/v1/health`
- `GET /api/v1/readiness`
- `GET /api/v1/rules/{rule_id}`
- `GET /api/v1/rules/{rule_id}/versions`
- `GET /api/v1/rules/{rule_id}/versions/rollback-history`
- `GET /api/v1/rules/{rule_id}/versions/stats`
- `GET /api/v1/rules/{rule_id}/versions/{version_1}/compare/{version_2}`
- `GET /api/v1/rules/{rule_id}/versions/{version_id}`
- `POST /api/v1/rules/{rule_id}/rollback`
- `POST /api/v1/rules/{rule_id}/test-with-data`
- `POST /api/v1/rules/{rule_id}/test`
- `POST /api/v1/rules/{rule_id}/test-with-generated-data`
- `PATCH /api/v1/rules/{rule_id}/versions/{version_id}/mark-for-rollback`
- `PATCH /api/v1/rules/{rule_id}/versions/{version_id}/tags`
- `GET /api/v1/data-products`
- `GET /api/v1/data-objects`
- `GET /api/v1/data-sets`
- `GET /api/v1/data-objects-catalog`
- `GET /api/v1/data-object-versions`
- `GET /api/v1/attributes-catalog`
- `GET /api/v1/data-deliveries`
- `GET /api/v1/rule-attributes`
- `POST /api/v1/rule-attributes`
- `GET /api/v1/attribute-rule-counts`
- `GET /api/v1/system-info`
- `POST /api/v1/login`
- `POST /api/v1/logout`
- `GET /api/v1/auth/redirect`
- `GET /api/v1/auth/callback`
- `GET /api/v1/approvals`
- `GET /api/v1/approvals/audit`
- `POST /api/v1/approvals`
- `PUT /api/v1/approvals/{approval_id}`
- `DELETE /api/v1/approvals/{approval_id}`
- `GET /api/v1/workspaces`
- `POST /api/v1/workspaces`
- `PUT /api/v1/workspaces/{workspace_id}`
- `DELETE /api/v1/workspaces/{workspace_id}`
- `GET /api/v1/app-config`
- `PUT /api/v1/app-config`
- `GET /api/v1/users`
- `GET /api/v1/roles`
- `PUT /api/v1/users/{user_id}`
- `POST /api/v1/users/{user_id}/reset-profile`
- `POST /api/v1/users/{user_id}/reset-settings`
- `GET /api/v1/me`
- `PUT /api/v1/me`
- `POST /api/v1/batch-test-requests`
- `GET /api/v1/batch-test-requests`
- `GET /api/v1/batch-test-requests/{id}`
- `POST /api/v1/batch-test-requests/{id}/run`
- `POST /api/v1/data-object-versions/{version_id}/generate-test-data`
- `GET /api/v1/test-proofs/{rule_id}`
- Hidden compatibility aliases under `GET /v1/*`

## API-6.3 Auth and gateway compatibility

- Protected routes now enforce legacy-style scope requirements using bearer JWTs.
- Public routes remain available without auth (`/`, `/v1/login`, `/v1/logout`, `/v1/auth/redirect`, `/v1/auth/callback`).
- Gateway-facing `/v1/*` paths are served alongside `/api/v1/*` without duplicating OpenAPI schema entries.
- Supported bearer sources: `Authorization`, `X-Auth-Request-Access-Token`, `X-Forwarded-Access-Token`.
- Scope expansion mirrors the legacy API conventions for `dq:admin`, `dq:rules:write`, and `dq:rules:read`.
- Local compatibility login now returns a JWT-shaped bearer token, so the migrated FastAPI middleware can authenticate follow-up requests without legacy in-process session storage.

## API-6.4 Migration wave 1 progress

- First two low-risk catalog read batches plus configuration/system/testing metadata reads are now available in FastAPI.
- Migrated reads currently cover products, data sets, data objects, data object versions, attributes, deliveries, rule attributes, attribute-rule counts, system-info, app-config, admin users/roles, current-user profile, and batch-test-request reads.
- Migrated mutations currently cover rule version rollback/tag workflows, rule test execution flows, `POST /rule-attributes`, auth/session compatibility (`login`, `logout`, OIDC redirect/callback), `PUT /app-config`, and admin user update/reset flows.
- Migrated edge-case reads now also include approvals list and approvals audit endpoints used by the UI (`GET /approvals`, `GET /approvals/audit`).
- Migrated edge-case approval mutations now include create/update/delete parity (`POST/PUT/DELETE /approvals`) with requester guard rails and audit logging behavior.
- Migrated edge-case workspace management endpoints now include list/create/update/delete parity (`GET/POST/PUT/DELETE /workspaces`) with max-workspace config limit enforcement.
- `DATABASE_URL` enables live Postgres-backed reads; without it, FastAPI falls back to deterministic in-memory fixtures for local/test isolation.

## Entity-first + resolver layout

```text
app/
  domain/
    entities/
    repositories/
  application/
    use_cases/
    resolvers/
  infrastructure/
    repositories/
  api/v1/
    endpoints/
    schemas/
```

The `GET /api/v1/rules/{rule_id}` endpoint demonstrates end-to-end flow:
entity retrieval -> use-case -> pydantic-resolve enrichment -> API response model.

## Notes

- This runtime is now the active API implementation after API-6.11 decommissioning.
- API-6.2 and API-6.3 should layer contract parity checks and auth/gateway compatibility on top of this foundation.
