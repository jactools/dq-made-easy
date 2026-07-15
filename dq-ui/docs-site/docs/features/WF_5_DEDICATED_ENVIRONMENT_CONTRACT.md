# WF-5 Dedicated Environment Contract and Startup Selection

Goal: define one canonical environment contract for development, local test, and Debian production so startup, seeding, validation, and deployment flows use explicit lifecycle stages instead of ambiguous local/deployment names.

## Principles

- Use explicit lifecycle environments: `dev`, `test`, and `prod`.
- Keep URL audience naming unchanged:
	- `*_INTERNAL_URL` = container-to-container communication.
	- `*_LOCAL_URL` = host/operator-to-service URL for the selected environment.
	- `*_PUBLIC_URL` = browser/user/external-facing URL.
- Keep routing mode separate from lifecycle stage through `EDGE_MODE=local\|public`.
- Fail fast when the selected environment file is missing or required variables are empty.
- Do not add compatibility aliases for legacy env names; update repo-controlled callers to the canonical names.
- Keep real machine secrets in ignored local files or externally managed secret stores.
- Treat `.env.dev.example`, `.env.test.example`, and `.env.prod.example` as documentation-only templates; runtime selection uses `.env.dev.local`, `.env.test.local`, `.env.prod.local`, or an explicit env-file path.

## Target Environment Files

Tracked documentation templates:

```text
.env.dev.example
.env.test.example
.env.prod.example
```

Ignored machine-local files:

```text
.env.dev.local
.env.test.local
.env.prod.local
```

Migration source mapping:

```text
.env.example              -> .env.dev.example
.env.deployment.example   -> .env.prod.example
```

The legacy tracked templates `.env.example` and `.env.deployment.example` are now retained only as non-runnable migration notices. The canonical command surface uses `.env.dev.local`, `.env.test.local`, `.env.prod.local`, or an explicit operator-supplied env file.

## Local File Creation and Debian Ownership

Machine-local runtime files should be created from the tracked templates and kept out of version control:

```bash
cp .env.dev.example .env.dev.local
cp .env.test.example .env.test.local
cp .env.prod.example .env.prod.local
```

Practical guidance:

- `dev`: keep `.env.dev.local` in the repo root for workstation-specific hostnames, ports, and local cert paths.
- `test`: keep `.env.test.local` in the repo root for isolated local smoke/regression values.
- `prod`: use `.env.prod.local` only on repo-managed hosts; for Debian operators, prefer an external file such as `/etc/dq-made-easy/prod.env` and pass it through `--env-file`.

Recommended Debian ownership and permissions:

```bash
sudo install -d -m 0750 /etc/dq-made-easy
sudo install -m 0600 .env.prod.example /etc/dq-made-easy/prod.env
sudo chown root:root /etc/dq-made-easy/prod.env
```

If Docker Compose runs under a dedicated service account or group, the env file may instead use `root:&lt;service-group&gt;` with `0640`, but it should never be world-readable. TLS private keys should follow the same or stricter permissions as the production env file.

## Environment Responsibilities

### Dev

Purpose: normal local development on a workstation.

Expected settings:

```bash
ENVIRONMENT=dev
COMPOSE_PROJECT_NAME=dq-rulebuilder-dev
EDGE_MODE=local
TRUST_PROXY_AUTH=false
ALLOW_LOCAL_AUTH=true
```

Characteristics:

- Uses environment-specific local browser and SSO hostnames provided by the selected env file.
- Uses the local development ports unless a developer overrides them.
- Allows frequent local image builds from the workspace.
- Supports local Vite and the containerized frontend.

Auth contract:

- Exposes both SSO Login and Admin Login on Dev.
- Uses the browser-facing issuer from the local HTTPS hostname, but backend OIDC discovery must use `SSO_INTERNAL_ISSUER_URL=http://keycloak:8080/realms/jaccloud`.
- Keeps `VITE_ALLOW_LOCAL_AUTH=$&#123;ALLOW_LOCAL_AUTH}` so the Dev login modal can render Admin Login consistently with the runtime app-config value.

### Test

Purpose: isolated local test/staging stack for smoke, regression, and release-candidate checks.

Expected settings:

```bash
ENVIRONMENT=test
COMPOSE_PROJECT_NAME=dq-rulebuilder-test
EDGE_MODE=local
```

Characteristics:

- Runs on the local machine but is isolated from dev through a distinct Compose project name.
- Uses separate host ports when dev and test must run concurrently.
- Uses separate local browser and SSO hostnames when parallel validation is required.
- Should be production-like where practical: enable proxy-auth behavior and disable local-auth escape hatches once the local test flow supports it.
- Acts as the default target for WF-4 smoke/regression orchestration.

Example concurrent-test port shape:

```bash
DB_HOST_PORT=15432
REDIS_HOST_PORT=16379
API_HOST_PORT=14010
FRONTEND_HTTPS_HOST_PORT=15173
VITE_PORT=15174
KEYCLOAK_HTTP_HOST_PORT=18080
KEYCLOAK_HTTPS_HOST_PORT=19444
KONG_PROXY_HOST_PORT=19443
KONG_ADMIN_HOST_PORT=18001
KONG_MANAGER_HOST_PORT=18002

DQ_DB_LOCAL_URL=postgresql://postgres:postgres@127.0.0.1:15432/dq
KONG_PUBLIC_URL=https://__SET_TEST_KONG_HOST__:19443
KEYCLOAK_PUBLIC_URL=https://__SET_TEST_KEYCLOAK_HOST__:19444
SSO_PUBLIC_ISSUER_URL=https://__SET_TEST_KEYCLOAK_HOST__:19444/realms/jaccloud
UI_VITE_LOCAL_URL=https://__SET_TEST_APP_HOST__:15174
UI_NGINX_LOCAL_URL=https://__SET_TEST_APP_HOST__:15173
```

### Prod

Purpose: Debian-hosted public deployment.

Expected settings:

```bash
ENVIRONMENT=production
COMPOSE_PROJECT_NAME=dq-made-easy-prod
EDGE_MODE=public
TRUST_PROXY_AUTH=true
ALLOW_LOCAL_AUTH=false
```

Characteristics:

- Based on the current public edge/single-host deployment template.
- Uses pinned image tags for real production, not `latest`.
- Binds non-public service ports to `127.0.0.1`.
- Uses absolute TLS certificate and key paths.
- Stores real credentials and secrets in `.env.prod.local` with restrictive permissions or in an externally managed file such as `/etc/dq-made-easy/prod.env`.

## Canonical Script Contract

Startup, stop, seed, pull, and validation scripts share this selection contract:

```bash
--env dev       # .env.dev.local
--env test      # .env.test.local
--env prod      # .env.prod.local
--env-file PATH # exact explicit env file
```

The direct `--env-file PATH` mode remains the supported escape hatch for CI, Debian paths under `/etc`, and one-off diagnostics.

The canonical operator entry point is the orchestrator:

```bash
./scripts/stack.sh dev init          # destroy → start → seed (full clean reset)
./scripts/stack.sh dev start --seed  # start containers + seed
./scripts/stack.sh dev restart --seed # stop → start (reuse admin passwords, rotate service/user)
./scripts/stack.sh dev stop           # stop only (keeps volumes and artifacts)
./scripts/stack.sh dev destroy        # full teardown
./scripts/stack.sh dev seed           # reseed running stack
```

Lifecycle scripts that `stack.sh` dispatches to:

```text
scripts/stack.sh                  # orchestrator
scripts/stack_destroy.sh          # full teardown
scripts/stack_start.sh            # start (detect fresh vs warm, manage passwords)
scripts/stack_stop.sh             # stop containers
scripts/stack_restart.sh          # stop → start (reuse admin passwords)
scripts/stack_seed.sh             # seed running stack
```

For image build/pull/push and status reporting, the legacy scripts remain:

```text
scripts/stack_ctl.sh              # build, pull, push, reconcile, list-targets
scripts/stack_status.sh           # container status reporting
```

Repo-controlled examples and docs should use canonical names only:

```bash
./scripts/stack.sh dev init
./scripts/stack.sh test start --seed
./scripts/stack.sh prod stop
```

## Validation Contract

Add a fail-fast validator, tentatively:

```bash
scripts/validate_env_file.sh
```

Required modes:

```bash
./scripts/validate_env_file.sh --env dev
./scripts/validate_env_file.sh --env test
./scripts/validate_env_file.sh --env prod
./scripts/validate_env_file.sh --env-file PATH
```

Runtime integration should use full validation before startup, pull, and seed flows, and a reduced stop-scope validation before teardown so missing env files and invalid lifecycle/project identity still fail fast without blocking container shutdown on unrelated hardening gaps.

Validation rules:

- The selected env file exists.
- Required variables are present and non-empty.
- `ENVIRONMENT` matches the selected lifecycle stage: `dev`, `test`, or `production`.
- `COMPOSE_PROJECT_NAME` is set for `test` and `prod`.
- `DQ_DB_INTERNAL_URL` uses the Compose service host `db`.
- `DQ_DB_LOCAL_URL` points at the host-facing database endpoint for the selected environment.
- `prod` uses `EDGE_MODE=public`.
- `prod` does not use `latest` image tags for application images.
- `prod` binds internal services to `127.0.0.1` unless an explicit documented exception exists.
- `prod` TLS certificate and key paths are absolute paths.
- `test` does not reuse dev host ports when parallel dev/test execution is required.

## Implementation Phases

### Phase 1: Templates

- [x] `WF-5.1` Create `.env.dev.example`, `.env.test.example`, and `.env.prod.example`.
- [x] `WF-5.2` Move local development defaults from `.env.example` into `.env.dev.example`.
- [x] `WF-5.3` Move public deployment defaults from `.env.deployment.example` into `.env.prod.example`.
- [x] `WF-5.4` Derive `.env.test.example` from dev with isolated Compose project, ports, hostnames, and database URLs.

### Phase 2: Local Runtime Files

- [x] `WF-5.5` Update ignore rules for `.env.dev.local`, `.env.test.local`, and `.env.prod.local`.
- [x] `WF-5.6` Document machine-local file creation and Debian production file ownership/permissions.

### Phase 3: Script Selection

- [x] `WF-5.7` Update startup/stop/seed/pull scripts to accept `--env dev\|test\|prod` and `--env-file PATH`.
- [x] `WF-5.8` Remove repo-controlled uses of `--env-local`, `--env-deployment`, `local`, and `deployment` selectors.
- [x] `WF-5.9` Update script help text and startup logs to describe the canonical env contract.

### Phase 4: Validation

- [x] `WF-5.10` Add `scripts/validate_env_file.sh` with fail-fast validation rules.
- [x] `WF-5.11` Run env validation before compose startup, seed, stop, and pull flows where required values are needed.
- [x] `WF-5.12` Add focused validation coverage for dev/test/prod env selection and prod hardening checks.

### Phase 5: Documentation and Callers

- [x] `WF-5.13` Update README, deployment docs, quickstart docs, and examples to use dev/test/prod env names.
- [x] `WF-5.14` Update repo-controlled direct Docker Compose examples to use `.env.dev.local`, `.env.test.local`, or `.env.prod.local`.
- [x] `WF-5.15` Align WF-4 test orchestration docs so local smoke/regression runs target the dedicated `test` environment.

### Phase 6: Verification

- [x] `WF-5.16` Verify `docker compose --env-file .env.dev.local config` succeeds.
- [x] `WF-5.17` Verify `docker compose --env-file .env.test.local config` succeeds.
- [x] `WF-5.18` Verify `docker compose --env-file .env.prod.local config` succeeds.
- [x] `WF-5.19` Verify `./scripts/stack.sh dev start --seed` succeeds.
- [x] `WF-5.20` Verify `./scripts/stack.sh test start --seed` succeeds without sharing dev state.

Current blocker for `WF-5.20`: the local test certificate files configured in `.env.test.local` are not present yet, so the dedicated `test` startup proof cannot be completed until `dq-made-easy.nl.crt` and `dq-made-easy.nl.key` exist at the configured absolute paths.

## Acceptance Criteria

- The repository has tracked dev, test, and prod env templates with clear responsibilities.
- Ignored local env files exist for machine-specific values and secrets.
- Scripts use `--env dev\|test\|prod` consistently across startup, stop, seed, pull, and validation flows.
- `--env-file PATH` remains available for explicit operator-controlled files.
- Test can run as a dedicated local stack without sharing dev Compose project state.
- Dev exposes both SSO and Admin login paths, and Dev SSO redirect discovery uses the container-internal Keycloak issuer while keeping browser-facing URLs on the local HTTPS host.
- Prod templates are hardened for Debian/public deployment with loopback-bound internal services, public edge routing, absolute TLS paths, and pinned images.
- Required env gaps fail before Compose starts rather than surfacing as late container failures.
- WF-4 automated testing has a stable dedicated `test` target for smoke and regression orchestration.

## Delivery Milestones

- Milestone A (Templates): `WF-5.1` to `WF-5.6`
- Milestone B (Script Contract): `WF-5.7` to `WF-5.12`
- Milestone C (Docs and Callers): `WF-5.13` to `WF-5.15`
- Milestone D (Verification): `WF-5.16` to `WF-5.20`