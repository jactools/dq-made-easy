# Operator Workflow Guide

**Role:** Platform operator or DevOps engineer responsible for deploying, starting, monitoring, and recovering the dq-made-easy stack.
**Time to read:** 10 minutes
**Last updated:** 2026-07-14

## Responsibilities in scope

- Starting and stopping the stack.
- Seeding and migrating the database.
- Monitoring service health and container status.
- Responding to operational alerts and runbooks.
- Managing environment configuration.

## Core workflows

### 1. Start the full stack (first time)

Use the orchestrator to do a full clean reset:

```bash
./scripts/stack.sh dev init
```

This destroys any prior state, generates all secrets, starts all containers, and seeds the database.

### 2. Start the stack (volumes already exist)

```bash
./scripts/stack.sh dev start --seed
```

When stateful volumes already exist (after a stop), admin passwords are reused automatically so database credentials stay consistent. Service and user passwords are still rotated.

### 3. Restart the stack

```bash
./scripts/stack.sh dev restart --seed
```

Stops containers, reuses admin passwords, rotates service/user passwords, starts containers, and re-seeds.

### 4. Stop the stack

```bash
./scripts/stack.sh dev stop
```

Stops containers and removes them. Volumes, secrets, and credentials are preserved for a subsequent `start` or `restart`.

### 5. Destroy everything

```bash
./scripts/stack.sh dev destroy
```

Full teardown: stops containers, removes containers and volumes, and deletes all generated artifacts (secrets, rotated passwords, keycloak credentials, TLS certs).

### 6. Reseed the database

```bash
./scripts/stack.sh dev seed
```

Runs all seeding operations (Keycloak, Postgres, Zammad, OpenMetadata) against the running stack.

### 7. Check service health

```bash
# Container status
docker compose --env-file .env.dev.local ps

# Logs
docker compose --env-file .env.dev.local logs --tail=100 <service>

# Smoke validation
./scripts/validate.sh --groups api,repo
```

### 8. Respond to an alert

Match the alert to the relevant incident runbook:

| Alert | Runbook |
| --- | --- |
| API 5xx spike | [INCIDENT_API_5XX_SPIKE.md](/docs/runbooks/INCIDENT_API_5XX_SPIKE/) |
| Compile failure spike | [INCIDENT_COMPILE_FAILURE_SPIKE.md](/docs/runbooks/INCIDENT_COMPILE_FAILURE_SPIKE/) |
| Executor timeout spike | [INCIDENT_EXECUTOR_TIMEOUT_SPIKE.md](/docs/runbooks/INCIDENT_EXECUTOR_TIMEOUT_SPIKE/) |
| Exception store write failure | [INCIDENT_EXCEPTION_STORE_WRITE_FAILURE.md](/docs/runbooks/INCIDENT_EXCEPTION_STORE_WRITE_FAILURE/) |

Use `correlationId` from structured logs to trace a request across API → Engine → Worker.

### 9. Rotate or update environment configuration

- Environment configuration lives in `.env.dev.local`, `.env.test.local`, or `.env.prod.local` under the repo root.
- Do not commit these files.
- Templates with safe placeholders are at `.env.dev.example`, `.env.test.example`, and `.env.prod.example`.
- After changing config, restart the relevant service: `docker compose restart &lt;service&gt;`.

## Password management

The stack scripts manage passwords automatically:

| Password type | Examples | Behavior |
| --- | --- | --- |
| Admin passwords | `DQ_DB_PASSWORD`, `KEYCLOAK_SYSTEM_ADMIN_PASSWORD` | Persisted in stateful volumes. Reused on `start` when volumes exist; regenerated only on fresh start or `destroy`. |
| Service passwords | `DQ_ENGINE_OIDC_CLIENT_SECRET`, `APP_CONFIG_ENCRYPTION_KEY` | Rotated on every `start` or `restart`. |
| User passwords | Keycloak seeded users | Rotated on every `seed`. |

If you encounter database authentication errors after a start, the admin password may be stale. Run `./scripts/stack.sh dev destroy` then `./scripts/stack.sh dev init` for a full reset.

## What to check before escalating

1. Is the database reachable and all migrations applied?
2. Are any containers in restart-loop state?
3. Is there a correlation ID in the failing request that points to a specific service?
4. Did a recent deployment change an environment variable or wheel artifact?

## Related guides

- [Stack Script Contract](/docs/implementation-details/STACK_SCRIPT_CONTRACT/)
- [Incident runbooks](/docs/runbooks/)
- [Documentation ownership policy](/docs/technical/DOCUMENTATION_OWNERSHIP_AND_SOURCE_OF_TRUTH/)
- [User Manuals index](/docs/user-manuals/)
