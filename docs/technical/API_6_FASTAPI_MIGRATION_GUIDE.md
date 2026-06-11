# DOC-6.1 FastAPI Migration Guide (Developers and Operators)

This guide documents the final API-6 migration state after FastAPI cutover and legacy API decommissioning.

## Audience

- Developers working in `dq-api/fastapi`
- Operators running the stack in Docker Compose/Kong environments

## Final Architecture

- Active API runtime: FastAPI (`dq-api/fastapi`)
- Active API container build target: `dq-api/Dockerfile.fastapi`
- API service port (container/host): `4010`
- Gateway: Kong on `9111` (public API entry)
- Legacy API code is archived under `dq-api/server-archive/` and is not part of active runtime paths

## Developer Workflow

### Local FastAPI run

From repository root:

```bash
cd dq-api/fastapi
/Users/jacbeekers/gitrepos/dq-rulebuilder/venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 4010 --reload
```

Or from `dq-api`:

```bash
cd dq-api
npm run start
```

### Test commands

Focused FastAPI tests:

```bash
cd dq-api/fastapi
/Users/jacbeekers/gitrepos/dq-rulebuilder/venv/bin/python -m pytest -q -o addopts='' tests/api tests/core tests/smoke
```

Repository-level FastAPI unit and API tests:

```bash
cd dq-api
npm run test:fastapi:unit
npm run test:fastapi:smoke
```

## Operator Workflow

### Rebuild and start updated API + gateway

```bash
cd /Users/jacbeekers/gitrepos/dq-rulebuilder
docker compose up -d --build api kong
```

### Validate health and routing

1. API container status:

```bash
docker compose ps api
```

Expected: `Up ... (healthy)`

2. FastAPI health endpoint:

```bash
curl -s http://localhost:4010/api/system/v1/health
```

3. Kong smoke checks:

```bash
./scripts/smoke_test_stack.sh
```

Expected checks include:
- protected route returns `401`
- auth redirect route returns `302`
- login route is publicly reachable

## Key Configuration Expectations

- `docker-compose.yml` `api` service uses `Dockerfile.fastapi`
- Kong bootstrap upstream points to `http://api:4010`
- Public auth endpoints remain explicitly routed in Kong (`/auth/v1/redirect`, `/auth/v1/callback`, `/auth/v1/login`, `/auth/v1/logout`)
- Public OIDC callback construction should use the browser-facing Kong/API base. FastAPI prefers `OIDC_REDIRECT_BASE_URL` and otherwise reuses `KONG_PUBLIC_URL`.

## Known Migration-Specific Notes

- `httpx` must remain in `dq-api/fastapi/requirements.txt` because OIDC auth flow imports it directly
- Health endpoints (`/health`, `/system/v1/health`, `/system/v1/readiness`) are intentionally public in auth compatibility logic so container health checks succeed
- Docker healthcheck uses Python `urllib` instead of `curl` in the FastAPI container image

## Rollback (Emergency)

API-6 target state is FastAPI-only. If emergency rollback is required for incident response:

1. Restore prior compose/bootstrap references from git history
2. Rebuild and restart `api` + `kong`
3. Re-run smoke checks and auth redirect checks

Use rollback only under incident management controls; keep this guide and the API-6 migration document as the source of truth for the intended steady state.

## Related Documents

- `docs/implementation-details/API_6_FASTAPI_MIGRATION.md`
- `TECHNICAL.md`
- `scripts/smoke_test_stack.sh`
