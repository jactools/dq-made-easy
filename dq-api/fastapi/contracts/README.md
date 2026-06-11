# OpenAPI Contract Baselines (API-6.2)

This folder stores OpenAPI contract artifacts for FastAPI migration parity checks.

## Layout

- `baseline/openapi-legacy-v1.json`: frozen baseline captured from legacy API.
- `current/openapi-fastapi-v1.json`: generated current FastAPI OpenAPI snapshot from the live app route map.
- `current/README.md`: index for the generated OpenAPI artifact set.

The published JSON Schema contract bundles live under `../../docs/contracts/internal-api/` and should be treated as the current versioned internal API contracts for validator and client use.

## Published proof contract

The canonical proof submission contract lives in [../../../docs/contracts/test-proof-payload/README.md](../../../docs/contracts/test-proof-payload/README.md). It is published beside the FastAPI OpenAPI output so callers can use the same snake_case proof envelope that the API stores.

## Capture baseline examples

```bash
cd dq-api/fastapi
python scripts/contracts/capture_openapi_baseline.py --source url --url http://localhost:4001/v1/openapi.json --output contracts/baseline/openapi-legacy-v1.json
```

```bash
cd dq-api/fastapi
python scripts/contracts/capture_openapi_baseline.py --source fastapi --output contracts/baseline/openapi-legacy-v1.json
```

## Run parity check

```bash
cd dq-api/fastapi
python scripts/contracts/check_openapi_parity.py --baseline contracts/baseline/openapi-legacy-v1.json --current-source app --current contracts/current/openapi-fastapi-v1.json --strip-prefix /api
```

A non-zero exit code indicates parity drift.

## Run API-6.9 dual-run behavior diff

```bash
cd dq-api/fastapi
python scripts/contracts/run_behavior_dual_run.py --legacy-base-url http://localhost:4001 --fastapi-base-url http://localhost:4010 --scenarios contracts/verification/api69-dual-run-smoke.json --output contracts/current/api69-behavior-diff-report.json --markdown-output contracts/current/api69-behavior-diff-report.md
```

The script exits non-zero when behavior mismatches are found and writes both JSON and Markdown reports.

Scenario options:
- `compareBody` (default `true`): when `false`, body comparison is skipped.
- `compareStatus` (default `true`): when `false`, status comparison is skipped.
- `compareHeaders` (optional list): compare specific response headers.
- `ignoreJsonPaths` (optional list): drop JSON paths before body comparison.

## Run API-6.9 dual-run behavior diff with managed services

```bash
cd dq-api
npm run contract:behavior:diff:with-services
```

This command starts legacy API (`:4001`) and FastAPI (`:4010`), waits for health checks, runs dual-run scenarios, writes reports, and then shuts both services down.
Service logs are written to:
- `fastapi/contracts/current/api69-legacy.log`
- `fastapi/contracts/current/api69-fastapi.log`
