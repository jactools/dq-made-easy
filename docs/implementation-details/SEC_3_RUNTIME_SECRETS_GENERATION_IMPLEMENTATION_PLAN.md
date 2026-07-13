# SEC-3: Runtime Secrets Generation — Implementation Plan

**Goal:** Eliminate all hardcoded passwords, secrets, and tokens from `.env.*.local` files. Every secret must be generated at startup time and sourced from `tmp/` artifacts.

**Motivation:** Passwords already rotate (Keycloak seed). Hardcoded defaults in `.env.*.local` cause stale credential mismatches (`invalid_grant`) when seeding has already produced new passwords. Secrets must never be part of a Docker image.

## Target Architecture

| Layer | Mechanism | Source |
|-------|-----------|--------|
| **Secret generation** | `generate_secrets.sh` | `tmp/secrets.{env}.env` |
| **Compose / containers** | `--env-file .env.*.local` + `--env-file tmp/secrets.{env}.env` | sourced at startup |
| **Host scripts** | `source tmp/secrets.{env}.env` | sourced from `tmp/` |
| **Seed credentials** | `keycloak-seed-artifacts` | `tmp/keycloak_seed_user_credentials.{env}.env` |
| **Trust-bundle** | `trust-bundle` container | `tmp/certs/trust/truststore-password.txt` |
| **OIDC client secrets** | generated or seed-artifacts | `tmp/dq_engine_oidc.{env}.env` |

## Secret Inventory

### A. Database & Storage Credentials

| Variable | Current Value | Rotation Policy |
|----------|---------------|-----------------|
| `DQ_DB_PASSWORD` | `postgres` | generate at startup |
| `KONG_DB_PASSWORD` | `kongpass` | generate at startup |
| `OM_DB_PASSWORD` | `openmetadata_pass` | generate at startup |
| `OM_DB_ROOT_PASSWORD` | `openmetadata_root` | generate at startup |
| `OPENMETADATA_SEARCH_PASSWORD` | `openmetadata` | generate at startup |
| `ZAMMAD_POSTGRES_PASSWORD` | `zammad` | generate at startup |
| `AISTOR_ROOT_PASSWORD` | `aistoradmin` | generate at startup |
| `DQ_S3_SECRET_KEY` | `aistoradmin` | generate at startup |
| `GX_EXCEPTION_STORAGE_SECRET_KEY` | `aistoradmin` | generate at startup |
| `KONG_ADMIN_PASSWORD` | `kong` | generate at startup |

### B. Application Secrets

| Variable | Current Value | Rotation Policy |
|----------|---------------|-----------------|
| `APP_CONFIG_ENCRYPTION_KEY` | hardcoded base64 | generate at startup (32-byte Fernet key) |
| `AIRFLOW_FAB_CLIENT_SECRET` | `changeme` | generate at startup |
| `DQ_ENGINE_OIDC_CLIENT_SECRET` | `changeme` | generate at startup |
| `GRAFANA_OIDC_SECRET` | `changeme` | generate at startup |
| `OM_AIRFLOW_SECRET_KEY` | `openmetadata_airflow_secret` | generate at startup |
| `CATALOG_OIDC_PASSWORD` | `password` | generate at startup |
| `GRAFANA_ADMIN_PASSWORD` | `admin` | generate at startup |

### C. Keystore/Truststore Passwords

| Variable | Current Value | Rotation Policy |
|----------|---------------|-----------------|
| `KAFKA_TLS_KEYSTORE_PASSWORD` | `changeit` | generate at startup |
| `KEYCLOAK_HTTPS_KEYSTORE_PASSWORD` | `changeit` | generate at startup |

### D. User Passwords (already rotate via seed)

| Variable | Current Value | Source |
|----------|---------------|--------|
| `KEYCLOAK_JACCLOUD_PASSWORD` | `"password"` | `tmp/keycloak_seed_user_credentials.{env}.env` |
| `KEYCLOAK_ADMIN_PASS` | `admin` | `tmp/keycloak_seed_user_credentials.{env}.env` |
| `KEYCLOAK_SYSTEM_ADMIN_PASSWORD` | `admin` | `tmp/keycloak_seed_user_credentials.{env}.env` |
| `SMOKE_LOGIN_PASSWORD` | `password` | `tmp/keycloak_seed_user_credentials.{env}.env` |
| `OPERATOR_LOGIN_PASSWORD` | (unset) | `tmp/keycloak_seed_user_credentials.{env}.env` |
| `OPENMETADATA_OIDC_SEED_PASSWORD` | (unset) | `tmp/keycloak_seed_user_credentials.{env}.env` |
| `CATALOG_OIDC_PASSWORD` | `password` | `tmp/keycloak_seed_user_credentials.{env}.env` |

### E. URLs with Embedded Credentials

| URL Variable | Contains | Fix |
|--------------|----------|-----|
| `DQ_DB_INTERNAL_URL` | `postgres:postgres` | construct from `DQ_DB_USER`/`DQ_DB_PASSWORD` |
| `DQ_DB_LOCAL_URL` | `postgres:postgres` | construct from `DQ_DB_USER`/`DQ_DB_PASSWORD` |
| `KAFKA_CONSUMER_DB_URL` | `postgres:postgres` | construct from `DQ_DB_USER`/`DQ_DB_PASSWORD` |

## Action Items

### Phase 1: Secret Generation Infrastructure

- [x] **SEC-3-01:** Create `scripts/generate_secrets.sh`
  - Generates `tmp/secrets.{env}.env` with all non-user secrets (inventory A, B, C)
  - Uses `openssl rand` for passwords, `cryptography.Fernet` for encryption keys
  - Only generates if file is missing or `--force` flag is set
  - Idempotent: does not regenerate existing secrets on subsequent runs
  - Acceptance: `./scripts/generate_secrets.sh --env dev` produces valid `tmp/secrets.dev.env`

- [x] **SEC-3-02:** Update `.gitignore` and `.dockerignore`
  - Ensure `tmp/secrets.*.env` is excluded from commits and image builds
  - Ensure `tmp/*.env` is excluded broadly
  - Acceptance: `git status` does not show `tmp/secrets.*.env`

### Phase 2: Startup Script Integration

- [x] **SEC-3-03:** Update `scripts/common_startup.sh`
  - Call `generate_secrets.sh` before any compose or seed step
  - Source `tmp/secrets.{env}.env` into the environment
  - Acceptance: secrets are available in `$SECRETS_ENV` or equivalent variable

- [x] **SEC-3-04:** Update `scripts/start_stack.sh` / `scripts/start-containers.sh`
  - Pass `--env-file tmp/secrets.{env}.env` to `docker compose` commands
  - Acceptance: `docker compose` resolves all `${SECRET:?required}` env vars

- [ ] **SEC-3-05:** Update `scripts/seed_containers.sh` / `scripts/seed_stack.sh`
  - Source `tmp/secrets.{env}.env` before seeding
  - Source `tmp/keycloak_seed_user_credentials.{env}.env` for user passwords
  - Acceptance: seed scripts use generated secrets, not env defaults

- [ ] **SEC-3-06:** Update `scripts/auth.sh` (shared auth helper)
  - Read credentials from `tmp/keycloak_seed_user_credentials.{env}.env`
  - Acceptance: `auth.sh` obtains OIDC token without hardcoded passwords

### Phase 3: `.env.*.local` Cleanup

- [ ] **SEC-3-07:** Remove hardcoded secrets from `.env.dev.local`
  - Remove all entries from inventory A, B, C
  - Remove user password entries from inventory D
  - Replace embedded-credential URLs (inventory E) with constructed forms
  - Keep non-secret values (hosts, ports, image refs)
  - Acceptance: file contains zero passwords, secrets, or tokens

- [ ] **SEC-3-08:** Remove hardcoded secrets from `.env.test.local`
  - Same treatment as dev
  - Acceptance: file contains zero passwords, secrets, or tokens

- [ ] **SEC-3-09:** Remove hardcoded secrets from `.env.prod.local`
  - Same treatment as dev
  - Acceptance: file contains zero passwords, secrets, or tokens

- [ ] **SEC-3-10:** Update `.env.*.example` files
  - Replace all secrets with `<<GENERATED>>` or `<<SECRET>>` placeholders
  - Add comments pointing to `generate_secrets.sh`
  - Acceptance: example files are safe to commit with no real secrets

### Phase 4: Container & Compose Wiring

- [ ] **SEC-3-11:** Verify compose files use `${VAR:?required}` pattern
  - All secrets in compose files already use `:?required` syntax
  - No fallback defaults that bypass the `:?required` guard
  - Acceptance: `docker compose config` fails fast if any secret is missing

- [ ] **SEC-3-12:** Fix `DQ_DB_INTERNAL_URL` / `DQ_DB_LOCAL_URL` construction
  - Remove hardcoded `postgres:postgres` from URL templates
  - Construct URLs from `DQ_DB_USER` and `DQ_DB_PASSWORD` variables
  - Same for `KAFKA_CONSUMER_DB_URL`
  - Acceptance: URLs resolve correctly at compose time

- [ ] **SEC-3-13:** Verify no secrets are baked into Docker images
  - Audit all `Dockerfile.*` for `ARG` or `ENV` that reference passwords
  - Ensure trust-bundle, keycloak, kong Dockerfiles use runtime mounts
  - Acceptance: no `RUN echo "password"` in any Dockerfile

### Phase 5: Script Credential Sourcing

- [ ] **SEC-3-14:** Update `scripts/auth.sh` to source credential files
  - Read `SMOKE_LOGIN_PASSWORD` from `tmp/keycloak_seed_user_credentials.{env}.env`
  - Read `KEYCLOAK_ADMIN_PASS` from same file
  - Acceptance: auth helper works without `.env.*.local` defaults

- [ ] **SEC-3-15:** Update `scripts/seeding/openmetadata.sh`
  - Source `tmp/keycloak_seed_user_credentials.{env}.env` for `OM_TOKEN` preparation
  - Acceptance: OpenMetadata seeding obtains valid token

- [ ] **SEC-3-16:** Update `scripts/seeding/zammad.sh`
  - Source `tmp/keycloak_seed_user_credentials.{env}.env` for SSO credentials
  - Acceptance: Zammad seeding works with rotated passwords

- [ ] **SEC-3-17:** Update `scripts/seeding/airflow.sh` (if applicable)
  - Source credential files for `DQ_AIRFLOW_PASSWORD`
  - Acceptance: Airflow seeding works with rotated passwords

### Phase 6: Validation & Testing

- [ ] **SEC-3-18:** Create `scripts/validation/validate_no_secrets_in_env.py`
  - Scan all `.env.*.local` files for password/secret patterns
  - Fail if any hardcoded value is found
  - Acceptance: validation script passes on clean env files

- [ ] **SEC-3-19:** End-to-end validation
  - `./scripts/common_startup.sh --env dev --seed-all` with fresh `tmp/` directory
  - Verify all containers start and seed successfully
  - Verify `invalid_grant` errors do not occur
  - Acceptance: full stack starts green from cold

## Dependencies

- SEC-3-01 must complete before SEC-3-03 through SEC-3-05
- SEC-3-03 through SEC-3-05 must complete before SEC-3-07 through SEC-3-10
- SEC-3-11 through SEC-3-13 can proceed in parallel with SEC-3-07
- SEC-3-14 through SEC-3-17 depend on SEC-3-05 (seed scripts updated)
- SEC-3-18 and SEC-3-19 are final gates

## Notes

- **Idempotency:** `generate_secrets.sh` must be safe to re-run. Existing secrets in `tmp/secrets.{env}.env` are preserved unless `--force` is used. This ensures that a restart does not break running services that depend on stable DB passwords.
- **User secrets vs. service secrets:** User passwords (inventory D) rotate on every seed. Service passwords (inventory A, B, C) are stable across restarts but generated fresh on first startup.
- **No image-baked secrets:** All Dockerfiles must source secrets from runtime environment or mounted volumes. No `ARG PASSWORD=...` or `ENV PASSWORD=...` with real values.
- **Trust-bundle password:** Already generated per-startup and written to `tmp/certs/trust/truststore-password.txt`. No change needed for this one.
