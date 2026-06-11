# Operator Workflow Guide

**Role:** Platform operator or DevOps engineer responsible for deploying, starting, monitoring, and recovering the dq-made-easy stack.
**Time to read:** 10 minutes
**Last updated:** 2026-05-31

## Responsibilities in scope

- Starting and stopping the stack.
- Seeding and migrating the database.
- Monitoring service health and container status.
- Responding to operational alerts and runbooks.
- Managing environment configuration.

## Core workflows

### 1. Start the full stack

```bash
./scripts/common_startup.sh --env dev --with-observability
```

Add `--force-build` when wheel artifacts or Docker images need rebuilding.

Check readiness after startup:

```bash
./scripts/validate.sh --groups api,repo
```

### 2. Rebuild wheel artifacts before startup

```bash
./scripts/package-releases/build_required_wheels.sh --force-build --with-airflow
```

This builds all core repo Python packages and Airflow SDK/operator wheels used by Docker images.

### 3. Seed or migrate the database

Database seeding and schema migration are handled by the seed container during startup. If you need to run migrations manually:

```bash
cd dq-api/fastapi
alembic upgrade head
```

### 4. Check service health

- API liveness: `GET /health` on the API container.
- Smoke tests: `./scripts/validate.sh --groups api`.
- Container status: `docker compose ps`.
- Logs: `docker compose logs --tail=100 &lt;service&gt;`.

### 5. Respond to an alert

Match the alert to the relevant incident runbook:

| Alert | Runbook |
| --- | --- |
| API 5xx spike | [INCIDENT_API_5XX_SPIKE.md](/docs/runbooks/INCIDENT_API_5XX_SPIKE/) |
| Compile failure spike | [INCIDENT_COMPILE_FAILURE_SPIKE.md](/docs/runbooks/INCIDENT_COMPILE_FAILURE_SPIKE/) |
| Executor timeout spike | [INCIDENT_EXECUTOR_TIMEOUT_SPIKE.md](/docs/runbooks/INCIDENT_EXECUTOR_TIMEOUT_SPIKE/) |
| Exception store write failure | [INCIDENT_EXCEPTION_STORE_WRITE_FAILURE.md](/docs/runbooks/INCIDENT_EXCEPTION_STORE_WRITE_FAILURE/) |

Use `correlationId` from structured logs to trace a request across API → Engine → Worker.

### 6. Rotate or update environment configuration

- Environment configuration lives in `.env.dev.local`, `.env.test.local`, or `.env.prod.local` under the repo root.
- Do not commit these files.
- Templates with safe placeholders are at `.env.dev.example`, `.env.test.example`, and `.env.prod.example`.
- After changing config, restart the relevant service: `docker compose restart &lt;service&gt;`.

## What to check before escalating

1. Is the database reachable and all migrations applied?
2. Are any containers in restart-loop state?
3. Is there a correlation ID in the failing request that points to a specific service?
4. Did a recent deployment change an environment variable or wheel artifact?

## Related guides

- [Incident runbooks](/docs/runbooks/)
- [Documentation ownership policy](/docs/technical/DOCUMENTATION_OWNERSHIP_AND_SOURCE_OF_TRUTH/)
- [User Manuals index](/docs/user-manuals/)
