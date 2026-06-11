## Seed/Re-seed Repair and Profiling Smoke Fixes (2026-04-04)

Summary
-------
- Restored a reliable live reseed path when Alembic head is a placeholder by bootstrapping from SQL backups and stamping Alembic after bootstrap.
- Ensured the live DB container receives the latest workspace `dq-db/init` files and reseed scripts before reseed, preventing stale image-baked fallback SQL from being used.
- Added missing fallback schema columns that caused seeded-list failures: `rules.manual_override_by`, `rules.manual_override_at`, `test_proofs.metrics`, `test_proofs.diagnostics`.
- Hardened Keycloak host-side seed generation (token client fallbacks and localhost readiness fallback).
- Added profiling lifecycle validators and integrated them into the standard smoke flow; profiling smoke now auto-discovers FK-safe rows when overrides are absent.
- Disabled OTEL exporters during pytest runs (tests/conftest.py) to avoid exporter shutdown log noise interfering with test output.

Files changed (high level)
-------------------------
- `scripts/reseed_running_db.sh` — copy current `dq-db/init` into container, detect placeholder Alembic head, bootstrap from `dq-db/init/backup/*.alembic_migrated` and stamp Alembic head.
- `dq-db/init/backup/01_schema.sql.alembic_migrated` — added `manual_override_by`, `manual_override_at`, `metrics`, `diagnostics`.
- `dq-db/scripts/reseed_in_container.sh` — restored proper DROP/CREATE public schema SQL.
- `scripts/seed_stack.sh` — wait for Keycloak readiness and re-enabled live reseed invocation.
- `scripts/generate_external_id_patch.py` — fallback to `KEYCLOAK_ADMIN_ID` and `admin-cli`; prefer direct HTTP requests for tokens when available.
- `scripts/start-containers.sh` + smoke helpers — reorder smoke steps; added `run_profiling_lifecycle_smoke_test` and seeded FastAPI verification wrapper.
- `dq-api/fastapi/tests/conftest.py` — set OTEL env vars to disable exporters during tests.
- Various profiling worker and test helper updates to align snake_case payloads and status updates (dq-profiling/python/*).

Behavioral/Operational Notes
----------------------------
- Reseed now reliably uses the current workspace schema files. If you previously relied on image-baked DB init files, you must re-run reseed to pick up the workspace changes.
- With Alembic head being a placeholder (the repo's current migration file is a no-op), the fallback bootstrap path is the only reliable way to create schema for fresh reseed runs; this is intentional until proper Alembic migrations are implemented.
- OTEL exporters are disabled only within the test environment (via `tests/conftest.py`) to prevent exporter threads logging errors during pytest shutdown; production telemetry remains unchanged.

Risks and Follow-ups
---------------------
- Long-term: convert the fallback SQL to canonical Alembic migrations so the bootstrap path isn't necessary; avoid schema drift.
- Confirm all backup `*.alembic_migrated` SQL files are kept in sync with ORM models; consider adding a CI check to detect mismatch.
- Consider adding an explicit integration test to guard against re-introducing stale container-baked init files (e.g., a CI job that runs reseed and verifies table columns).
- Tests: repository-wide coverage remains far below the `fail-under=90` gate; focused tests pass. Don't rely on `--no-cov` for CI; instead expand unit/test coverage or relax the gate if intentional.

Verification
------------
- Focused pytest selection (rules/test_proofs surface) now passes: `pytest tests/api/test_list_endpoints_non_empty.py -k 'rules or batch_test_requests or rule_versions'` (3 passed).
- Full seeded smoke: `./scripts/start-containers.sh --with-core --with-redis --with-gateway --with-auth --with-profiling --seed-postgres --smoke-test` completed successfully; logs saved at `tmp/start_containers_smoke.log`.

Suggested PR description (copy-paste)
-------------------------------------
Fix reseed/bootstrap and seeded smoke failures

- Ensure the running DB reseed uses current workspace `dq-db/init` files and applies fallback SQL when Alembic head is a placeholder. Add missing fallback schema columns required by ORM reads.
- Harden Keycloak host-side seed generation and prefer direct token requests when available. Add profiling lifecycle smoke tests and auto-discovery of FK-safe rows.
- Disable OTEL exporters during pytest to avoid exporter shutdown noise.

Files modified: scripts/reseed_running_db.sh, dq-db/init/backup/01_schema.sql.alembic_migrated, dq-db/scripts/reseed_in_container.sh, scripts/seed_stack.sh, scripts/generate_external_id_patch.py, scripts/start-containers.sh, dq-api/fastapi/tests/conftest.py, dq-profiling/python/*, plus small test harness updates.

— End of release note
