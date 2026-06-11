# dq-profiling

Standalone background worker for data profiling and rule suggestion generation.

## Purpose

`dq-profiling` consumes profiling jobs from Redis (`data-profiling` queue), profiles data sources, reports request lifecycle status back to the dq-api, and writes generated suggestions/artifacts.

Python ETL
----------
This repository now includes a Python implementation of ETL logic under `dq-profiling/python/etl.py` (preferred over the legacy TypeScript stubs). Use the Python runner for local testing:

```bash
python3 dq-profiling/python/run_etl.py
```

The Python ETL supports `inlineData` and S3 sources and writes artifacts to S3 (or to `tmp/<bucket>/<key>` as a local fallback).

## Prerequisites

- Node.js 20+
- Access to Redis
- Access to dq-api (for profiling request lifecycle reporting)

## Install

```bash
cd dq-profiling
npm install
```

## Run locally

```bash
npm run start
```

This starts the worker process defined in `src/worker.ts`.

## Request generator

For repeatable enqueue traffic against the live stack, use:

```bash
./scripts/generate_profiling_requests.sh
```

The script loads configuration from the selected canonical root env file and defaults to `.env.dev.local`. Use `./scripts/generate_profiling_requests.sh --env test` or `--env-file PATH` when you need a different target. It first authenticates against the Keycloak token endpoint, seeds the matching session row from the JWT `sid` claim, and then sends the bearer token with each enqueue request.

## Build

```bash
npm run build
```

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `DQ_API_INTERNAL_URL` | `http://api:4010` | Internal API base URL used for profiling request status reporting |
| `REDIS_HOST` | `redis` | Redis host |
| `REDIS_PORT` | `6379` | Redis port |
| `REDIS_PASSWORD` | _(empty)_ | Redis password (optional) |
| `PROFILING_WORKER_CONCURRENCY` | `2` | Number of parallel profiling jobs |
| `PROFILING_METRICS_PORT` | _(unset)_ | Prometheus metrics port for worker request/failure counters |

## Docker

Build and run directly:

```bash
docker build -t dq-profiling:latest ./dq-profiling
docker run --rm \
  -e DQ_API_INTERNAL_URL=http://host.docker.internal:4010 \
  -e REDIS_HOST=host.docker.internal \
  -e REDIS_PORT=6379 \
  -e PROFILING_WORKER_CONCURRENCY=2 \
  dq-profiling:latest
```

## Docker Compose integration

The root `docker-compose.yml` already includes:

- `redis`
- `profiling-worker` (built from `./dq-profiling`)

Start the full stack from repository root:

```bash
docker compose --env-file .env.dev.local up --build
```

## Notes

- Current profiling logic is mock/sample logic in `src/worker.ts` (`profileDataSource`).
- Replace that function with Azure Storage profiling logic for production.
- Queue contract must stay aligned with producer in `dq-api/server/job-queue.ts`.
