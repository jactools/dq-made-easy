# Data Quality Made Easy

A lightweight React + Vite UI for building and managing data-quality rules.

## Quick start

Prerequisites: Node.js 22+ and npm 11.14.1.

Install dependencies:

```bash
npm install
```

Run the dev server:

```bash
npm run dev
```

Run the stack with explicit profiles (convenience wrapper):

```bash
./scripts/start-containers.sh --with-core --with-redis --with-gateway
```

Run everything (all profiles):

```bash
./scripts/start-containers.sh --all
```

Run smoke validation separately after startup:

```bash
./scripts/smoke_stack.sh
```

Deployment workflows:

- WF6 Kubernetes image deployment: [docs/features/WF_6_KUBERNETES_IMAGE_DEPLOYMENT.md](docs/features/WF_6_KUBERNETES_IMAGE_DEPLOYMENT.md)
- WF7 Azure Container Apps deployment: [docs/features/WF_7_AZURE_CONTAINER_APPS_ENVIRONMENT_DEPLOYMENT.md](docs/features/WF_7_AZURE_CONTAINER_APPS_ENVIRONMENT_DEPLOYMENT.md)
- Local Kubernetes bootstrap: [scripts/k8s/ensure_local_cluster.sh](scripts/k8s/ensure_local_cluster.sh)
- Local Kubernetes pipeline wrappers: [scripts/k8s/local_pipeline.sh](scripts/k8s/local_pipeline.sh) and [scripts/k8s/local_pipeline_batch.sh](scripts/k8s/local_pipeline_batch.sh)

Use the common local startup wrapper:

```bash
./scripts/common_startup.sh
./scripts/common_startup.sh --with-observability
./scripts/common_startup.sh --with-observability --force-build
```

Select which env file the startup chain should use:

```bash
# Default dev env
./scripts/common_startup.sh --env dev

# Dedicated local test env
./scripts/common_startup.sh --env test

# Repo-managed prod-style env file
./scripts/common_startup.sh --env prod

# Explicit file path
./scripts/common_startup.sh --env-file /etc/dq-made-easy/prod.env
./scripts/start-containers.sh --env-file /etc/dq-made-easy/prod.env --with-core --with-gateway
```

Notes:

- `common_startup.sh` defaults to `.env.dev.local`.
- `--env dev`, `--env test`, and `--env prod` select `.env.dev.local`, `.env.test.local`, and `.env.prod.local`.
- Create local runtime files from the tracked templates: `.env.dev.example`, `.env.test.example`, and `.env.prod.example`.
- For Debian or other operator-managed hosts, prefer `--env-file /etc/dq-made-easy/prod.env` over keeping production secrets in the repo root.
- `start-containers.sh` accepts the same canonical selectors: `--env dev|test|prod` and `--env-file PATH`.
- Normal startup now runs the `api-migrate` one-shot service before `api` starts.
- With the default `--no-build` path, new Alembic revisions are picked up only after `--force-build` or another `dq-api` image rebuild.
- Postgres reseeding uses the `db-seed` service and current workspace-mounted seed logic; it does not require rebuilding `dq-api` for migration correctness.

## Profile Cheatsheet

Use `./scripts/start-containers.sh` with one or more `--with-*` flags, or `--all` to enable every profile.
Docs hub version: [docs/README.md](docs/README.md#container-profile-cheatsheet).

Current profile groups in `docker-compose.yml`:

- `base`: `base`
- `redis`: `redis`
- `core`: `db`, `redis`, `api`, `frontend`
- `auth`: `keycloak`
- `engine`: `dq-engine`
- `workers`: `profiling-worker`
- `profiling`: `profiling-worker`
- `observability`: `db`, `redis`, `api`, `grafana`, `loki`, `prometheus`, `tempo`, `otel-collector`, `pushgateway`, `profiling-worker`, `redis-exporter`
- `gateway`: `kong-db`, `kong-migrations`, `kong`
- `metadata`: `openmetadata-db`, `openmetadata-search`, `openmetadata-migrate`, `openmetadata-server`, `openmetadata-configure`, `openmetadata-ingestion`

The metadata profile provides the OpenMetadata backend that can carry governed product definitions (Open Data Product Specification 4.1) and catalog metadata. When started through `scripts/start-containers.sh --with-metadata`, startup also enables the auth profile, reconciles the Keycloak `openmetadata` client, reseeds the generated Keycloak credentials, and then mints the OpenMetadata OIDC token. ODCS 3.1 remains the separate contract layer for data-quality and delivery contracts.

Common startup combinations:

```bash
# Typical app stack (UI + API + DB + Redis + gateway)
./scripts/start-containers.sh --with-core --with-gateway

# Add auth and engine
./scripts/start-containers.sh --with-core --with-gateway --with-auth --with-engine

# Add auth, engine, workers, and a distributed Spark cluster
./scripts/start-containers.sh --with-core --with-gateway --with-auth --with-engine --with-workers --with-spark

# OpenMetadata, including Keycloak auth reconciliation and credential reseed
./scripts/start-containers.sh --with-metadata

# Full stack
./scripts/start-containers.sh --all

# Full local wrapper using the dedicated test env
./scripts/common_startup.sh --env test --with-observability
```

Build for production:

```bash
npm run build
```

Run tests:

```bash
npm test
```

## Release Notes

- Latest UI release: v0.10.3 (May 13, 2026)
- Latest API release: v0.10.3 (May 13, 2026)
- End-user release notes: [RELEASE_NOTES_USER.md](RELEASE_NOTES_USER.md)
- Detailed release doc: [docs/releases/RELEASE_0_10_3_AISTOR_MIGRATION_AND_RUNTIME_STABILITY_ALIGNMENT.md](docs/releases/RELEASE_0_10_3_AISTOR_MIGRATION_AND_RUNTIME_STABILITY_ALIGNMENT.md)
- UI packaged copy: [dq-ui/public/release-notes/RELEASE_NOTES_USER.md](dq-ui/public/release-notes/RELEASE_NOTES_USER.md)

## OpenMetadata LDD Import

For converting Logical Data Definitions Excel workbooks into OpenMetadata-ready CSV files,
see `dq-metadata/LDD_TO_OPENMETADATA.md`.

For governed data products, the intended layering is:
- Open Data Product Specification 4.1 for the product-level business definition
- ODCS 3.1 for the delivery and data-quality contract layer
- OpenMetadata as the registry backend for governed metadata and lineage

## GitHub Project Try-Out

To copy the actionable information from the repository markdown into the GitHub Project Data Quality Made Easy at owner `jactools`, project `1`, use the existing sync flow:

```bash
./scripts/sync_markdown_backlog_to_github_project.sh --scope all --dry-run
./scripts/sync_markdown_backlog_to_github_project.sh --scope all --owner jactools --project-number 1
```

Notes:

- The flow reads markdown files in this repo and leaves them in place.
- It creates GitHub Project draft items through `gh` and writes a local sync state under `tmp/` so repeated runs do not duplicate items.
- Use `--reset-state` if you want to re-sync from scratch.

## Unified Stack Control

Use `./scripts/stack_ctl.sh` as the common operator entrypoint when you want one selector model across image and container actions.

Examples:

```bash
# Build selected images locally
./scripts/stack_ctl.sh build --image dq-api --image dq-frontend --no-cache

# Pull the full repo-managed image set for prod
./scripts/stack_ctl.sh pull --env prod --all

# Start a functional slice of the stack
./scripts/stack_ctl.sh start --profile core --profile gateway --profile auth

# Restart only the UI and API
./scripts/stack_ctl.sh restart --service frontend --service api

# Stop support services only
./scripts/stack_ctl.sh stop --profile support

# Seed only Postgres and delivery objects
./scripts/stack_ctl.sh seed --seed-target postgres --seed-target deliveries --wipe-aistor

# Build and push selected images
./scripts/stack_ctl.sh push --image dq-api --image dq-kong
```

Selector model:

- `--env dev|test|prod` and `--env-file PATH` work across all actions.
- `--profile` and `--service` target compose lifecycle actions.
- `--image` targets repo-managed image operations.
- `--seed-target` targets the discrete seed flows implemented by `seed_stack.sh`.
- `./scripts/stack_ctl.sh list-targets` prints the current supported profiles, images, seed targets, and compose services.

AIStor free edition backs the local S3-compatible object-storage profile. Put your free-tier license at the path configured by `AISTOR_LICENSE_FILE` (default: `./tmp/aistor/minio.license`) before starting `--with-observability`, because AIStor fails fast without a license file.

## Docker image build/push scripts

You can build and push service images either per service or all at once.

Build/push the core product images in order (`dq-base`, `dq-api`, `dq-engine`, `dq-profiling`, `dq-frontend`, `dq-kong`, `dq-db`, `dq-keycloak`):

```bash
./scripts/build_and_push_all.sh
```

Build the wider repo-managed image set as well (seed/configure/helper images):

```bash
./scripts/build_and_push_all.sh --scope repo
```

Dry-run build only (no push):

```bash
./scripts/build_and_push_all.sh --no-push
```

Build without cache:

```bash
./scripts/build_and_push_all.sh --no-cache
```

Show the calculated Docker-input-aware tags without building:

```bash
./scripts/calculate_versions.sh --display
```

Per-service scripts:

```bash
./dq-base/scripts/build_and_push.sh [--no-cache] [--no-push]
./dq-api/scripts/build_and_push.sh [--no-cache] [--no-push]
./dq-engine/scripts/build_and_push.sh [--no-cache] [--no-push]
./dq-profiling/scripts/build_and_push.sh [--no-cache] [--no-push]
./dq-ui/scripts/build_and_push.sh [--no-cache] [--no-push]
./dq-kong/scripts/build_and_push.sh [--no-cache] [--no-push]
./dq-db/scripts/build_and_push.sh [--no-cache] [--no-push]
./dq-keycloak/scripts/build_and_push.sh [--no-cache] [--no-push]
```

### Required `.env` variables

These variables are expected by the scripts:

```dotenv
# Base image used by dq-base build and as parent for dq-api/dq-profiling
NODE_REGISTRY=
NODE_NAMESPACE=
NODE_IMAGE=
NODE_TAG=

DQ_BASE_REGISTRY=
DQ_BASE_NAMESPACE=
DQ_BASE_IMAGE=
DQ_BASE_TAG=

# API image
DQ_API_REGISTRY=
DQ_API_NAMESPACE=
DQ_API_IMAGE=
DQ_API_TAG=

# Engine image
DQ_ENGINE_REGISTRY=
DQ_ENGINE_NAMESPACE=
DQ_ENGINE_IMAGE=
DQ_ENGINE_TAG=

# Profiling image
DQ_PROFILING_REGISTRY=
DQ_PROFILING_NAMESPACE=
DQ_PROFILING_IMAGE=
DQ_PROFILING_TAG=

# Frontend image
DQ_FRONTEND_REGISTRY=
DQ_FRONTEND_NAMESPACE=
DQ_FRONTEND_IMAGE=
DQ_FRONTEND_TAG=
KONG_LOCAL_URL=
KONG_PUBLIC_URL=

# SSO defaults (applied when app_config rows are not present)
SSO_PROVIDER=
SSO_PUBLIC_ISSUER_URL=
SSO_INTERNAL_ISSUER_URL=
SSO_CLIENT_ID=
SSO_ENABLED=
ALLOW_LOCAL_AUTH=

# Frontend SSO defaults
VITE_SSO_PROVIDER=
VITE_SSO_ISSUER_URL=
VITE_SSO_CLIENT_ID=

# Kong image
DQ_KONG_REGISTRY=
DQ_KONG_NAMESPACE=
DQ_KONG_IMAGE=
DQ_KONG_TAG=

# Database image
DQ_DB_REGISTRY=
DQ_DB_NAMESPACE=
DQ_DB_IMAGE=
DQ_DB_TAG=

# Keycloak image
DQ_KEYCLOAK_REGISTRY=
DQ_KEYCLOAK_NAMESPACE=
DQ_KEYCLOAK_IMAGE=
DQ_KEYCLOAK_TAG=

# Frontend base image for Dockerfile.frontend
NGINX_REGISTRY=
NGINX_NAMESPACE=
NGINX_IMAGE=
NGINX_TAG=
```

Notes:

- `NGINX_NAMESPACE` may be empty (for official Docker Hub `nginx` images).
- `dq-ui` image build expects `dq-ui/dist` to be present before running `./dq-ui/scripts/build_and_push.sh`.
- `dq-rules-ui/` is preserved as unsupported legacy material only and is excluded from supported frontend, schema, and entity-model claims. References to `dq-rules-ui` in auth settings usually mean the Keycloak client ID, not the legacy subtree.
- Frontend API target can be changed at container runtime using `KONG_PUBLIC_URL` without rebuilding the frontend image.
- SSO values resolve from environment defaults first, and runtime values in `app_config` override them when present.

- When using Kong for browser auth:
	- `KONG_PUBLIC_URL` should point to Kong directly.
	- `TRUST_PROXY_AUTH=true` must be set for both the API and Kong bootstrap path.
	- `SSO_PUBLIC_ISSUER_URL` must match the canonical public Keycloak issuer exactly.
	- Changes to `dq-kong/scripts/bootstrap_kong.sh` or `dq-api/fastapi` auth middleware require rebuilding `kong` and `api`; a plain restart is not enough.
- When using Keycloak + Kong JWT:
	- `SSO_PUBLIC_ISSUER_URL` must be a fully-qualified URL (include `http(s)://` and the realm path), e.g. `http://keycloak.jac.dot:8080/realms/jaccloud`.
	- Kong validates tokens by matching the JWT `iss` claim against a Kong JWT credential `key`. If you see `No credentials found for given 'iss'`, Kong is missing that issuer key.
	- Changes to Kong’s bootstrap script (or env vars like `SSO_PUBLIC_ISSUER_URL` / `KEYCLOAK_PUBLIC_HOSTNAME`) require recreating the `kong` container (a plain `docker compose restart kong` will not apply new environment variables):

		```bash
		docker compose --env-file .env.dev.local build kong
		docker compose --env-file .env.dev.local up -d --force-recreate kong
		```

	- To verify the issuer key exists:

		```bash
		curl -s http://localhost:8001/consumers/oidc-issuer/jwt | jq -r '.data[]?.key'
		```
- Authenticate first when pushing to Docker Hub:

```bash
docker login docker.io
```

## Deploying from Docker Hub

To pull and run pre-built Docker images on a different machine:

### Quick Deploy

```bash
# 1. Pull all repo-managed images using the tags from .env.prod.local
./scripts/pull_images.sh          # pulls repo-managed images from the selected env file
./scripts/pull_images.sh 0.3.2    # pulls specific version

# 2. Start services
docker compose --env-file .env.prod.local up -d
```

To include the optional Zammad support stack, start the support profile as well:

```bash
docker compose --env-file .env.prod.local --profile support up -d
```

### Documentation

- **[Quick Start Deployment Guide](./docs/technical/QUICKSTART_DEPLOY.md)** - Simple commands to get running fast
- **[Full Deployment Guide](./docs/technical/DEPLOYMENT.md)** - Comprehensive deployment instructions including:
  - Version management
  - Air-gapped deployments
  - Production configurations
  - Troubleshooting
  - Health checks

### Using Specific Versions

Edit `.env.prod.local` to pin versions:

```bash
DQ_API_TAG=0.3.2-6e9ca2e
DQ_ENGINE_TAG=0.3.2-14aefcc
DQ_PROFILING_TAG=0.3.2-5a2a995
DQ_FRONTEND_TAG=0.3.2-6725b17
DQ_KONG_TAG=0.3.2-0aaabb2
```

Then pull and start:

```bash
docker compose --env-file .env.prod.local pull
docker compose --env-file .env.prod.local up -d
```

See [.env.prod.example](./.env.prod.example) for the tracked production template, then copy it to `.env.prod.local` for repo-managed hosts or install it as `/etc/dq-made-easy/prod.env` for operator-managed Debian deployments.

---

API server: see the `server/` folder for the backend entrypoint and instructions.

Smoke test: there is a small smoke-test script that checks the frontend root, the `/applied` page and a handful of API endpoints. It's located at `scripts/smoke_test.sh` and can be run directly:

```bash
./scripts/smoke_test.sh
```

Reseed the database while containers are already running (no `docker compose down/up`):

```bash
bash ./scripts/reseed_running_db.sh
```

The reseed command executes `/opt/dq-db/scripts/reseed_in_container.sh` inside the running `db` container, using SQL and seed assets baked into the `dq-db` image.

You can also run reseed directly from the container image without repository scripts:

```bash
docker exec -it <db-container-name> bash /opt/dq-db/scripts/reseed_running_db.sh
```

Healthcheck-safe verification (no schema/data changes):

```bash
docker exec -i <db-container-name> bash -lc 'test -x /opt/dq-db/scripts/reseed_running_db.sh && psql -U postgres -d dq -c "SELECT 1" >/dev/null'
```

## Rule Suggestions flow

The `Suggestions` page supports requesting data profiling and then reviewing generated rule suggestions.

### UI flow

1. Log in and navigate to `Rule Quality -> Rule Suggestions`.
2. If no suggestions are currently shown, use **Run Data Profiling**:
	 - Select a data source from the dropdown.
	 - Click **Run Data Profiling**.
3. The UI calls the backend, then shows either:
	 - success feedback (request accepted), or
	 - error feedback (for example permission/cooldown errors).
4. Once profiling completes, pending suggestions are returned and rendered in the list.

### Backend API sequence

The frontend uses the following endpoints:

- `GET /api/suggestions/data-sources`
	- Returns available profileable sources.
- `POST /api/suggestions/data-sources/:dataSourceId/request-profiling`
	- Creates a profiling request (requires role `admin`, `analyst`, or `data-steward`).
	- Enforces cooldown/rate limiting on repeated requests.
- `GET /api/suggestions/profiling-requests/:profilingRequestId/status`
	- Returns request status (`pending`, `running`, `completed`, `failed`).
- `GET /api/suggestions?status=pending&dataSourceId=:dataSourceId`
	- Returns generated pending suggestions for display.

### Local verification commands

Use these commands against a running local stack:

```bash
# list available sources
curl -sS http://localhost:4001/api/suggestions/data-sources | jq .

# request profiling (example admin user id: u0)
curl -sS -X POST \
	http://localhost:4001/api/suggestions/data-sources/demo-azure-payments-sql/request-profiling \
	-H 'x-user-id: u0' | jq .

# check pending suggestions for a source
curl -sS 'http://localhost:4001/api/suggestions?status=pending&dataSourceId=demo-azure-payments-sql' | jq .
```

Current seeded demo data sources include:

- `demo-azure-customer-blob`
- `demo-azure-payments-sql`

Rule Suggestions is now a standard Rule Quality capability and no longer requires preview opt-in. Other unfinished features may still appear under `Settings -> Display -> Preview Features` until they graduate.

## Contributing

Feel free to open issues or pull requests. Create feature branches off `main`.

Repository merge policy:

- Do not use squash merges for pull requests in this repository.
- Prefer `Create a merge commit` for long-lived or multi-commit feature branches so commit ancestry remains intact.
- Use `Rebase and merge` only when intentionally rewriting branch SHAs into a linear history.

## License

This project is licensed under the MIT License — see the `LICENSE` file for details.
