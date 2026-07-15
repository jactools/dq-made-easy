# EDR-012 [DB]: CSV-First Seeding and Schema Bootstrap Rules

**Status**: Accepted
**Date**: 2026-04-20
**Tag**: DB

## Context
The repository relies on seeded data for local environments, smoke tests, UI history rendering, and data-delivery bootstrap flows. Several failures showed that seeded behavior becomes unreliable when generated SQL, image-baked fallback artifacts, or ad hoc fixtures are treated as the source of truth instead of the current workspace seed definitions.

Repeated issues exposed a few durable rules:

- canonical mock data belongs in source CSV files, not in generated SQL output
- seed application order must respect foreign-key dependencies explicitly
- live reseed and smoke-test bootstrap must use the current workspace schema and scripts, not stale image-baked state
- in-memory seeded fixtures used by API and UI smoke checks should mirror backend lifecycle history rather than frontend-only shortcuts
- seed validators should fail fast on source-data drift instead of relaxing constraints to accommodate inconsistent mock data

## Decision
Adopt the following seeding and bootstrap rules:

- CSV files are the canonical source of truth for repository seed data; generated SQL is a derivative artifact.
- Fix seed drift in the source CSV rather than patching generated seed SQL or weakening validation logic.
- Seed generation and reseed scripts must preserve deterministic table ordering where foreign keys require it, including placing dependent seed sets immediately after their parents.
- Live reseed/bootstrap flows must copy and use the current workspace `dq-db/init` content and reseed scripts inside the running database container when rebuilding a seeded environment.
- When the live schema cannot rely on Alembic head alone, bootstrap must use the repository’s explicit schema bootstrap path rather than assuming the current migration head fully materializes the schema.
- In-memory seed fixtures used for API/UI smoke behavior should represent full backend lifecycle history chains and backend-shaped audit data rather than frontend-only mock shortcuts.
- Seed wrappers for delivery-object generation must pass the required compose profiles and runtime environment explicitly so seeding behavior matches the active stack topology.

## Rationale
- CSV-first seeding keeps the human-reviewed source data visible and easier to repair than generated SQL.
- Foreign-key-sensitive ordering prevents nondeterministic seed application failures.
- Stale image-baked SQL or stale container bootstrap assets can make reseed appear successful while silently missing newer schema or data expectations.
- Full lifecycle seed chains make UI and endpoint smoke checks more realistic and contract-driven.
- Fail-fast validation is preferable to accepting contradictory mock data that later breaks delivery, smoke, or profiling flows.

## Scope Boundaries
This decision applies to repository seed sources, generated SQL seed workflows, seeded smoke/bootstrap flows, and backend-owned in-memory seed fixtures.

It does not by itself define:
- every production migration practice for non-seeded environments
- every data-delivery runtime path outside seed/bootstrap concerns
- the complete permission model after the database is seeded
- long-term archival policy for generated seed artifacts

## Consequences
**Positive**
- Seed repairs happen at the real source of truth instead of being hidden in generated artifacts.
- Seeded environments and smoke tests become more reproducible across rebuilds.
- UI and API smoke flows can rely on seeded lifecycle history that matches backend contracts.
- Schema/bootstrap drift is easier to diagnose when reseed uses current workspace content explicitly.

**Negative**
- Seed scripts and wrapper ordering need to stay deliberate rather than opportunistic.
- Live reseed remains operationally explicit and sometimes must work around incomplete migration-head behavior.
- CSV and model-header alignment requires ongoing maintenance as schemas evolve.

## Implementation Guidance
- Keep mock-data source edits in CSV files and regenerate seed SQL from those sources.
- Preserve FK-aware ordering in seed scripts, especially where dependent entities such as notes, versions, or child records follow parent tables.
- For seeded smoke/bootstrap flows, copy current workspace schema/init assets into the running DB container before reseeding.
- Keep in-memory backend seed fixtures aligned with backend contract expectations, including lifecycle history and audit examples.
- Validate CSV headers against repository row models and keep snake_case headers aligned with model field names or explicit generator mappings.
- Treat compose profile and runtime-env setup as part of seed correctness for data-delivery object generation.

## Related Artifacts
- `/memories/repo/dq-rulebuilder-contact-v3-seed-duplicate-attributes-note.md`
- `/memories/repo/dq-rulebuilder-data-delivery-note-seed-csv.md`
- `/memories/repo/dq-rulebuilder-fastapi-rule-status-history-seed-note.md`
- `/memories/repo/dq-rulebuilder-seeded-smoke-schema-bootstrap-and-profiling-fk-note.md`
- `/memories/repo/dq-rulebuilder-delivery-object-seed-compose-profile-note.md`
- `/memories/repo/dq-rulebuilder-delivery-object-seed-workspace-layer-name-note.md`
- `/memories/repo/dq-rulebuilder-dq-db-rules-csv-created-by-alias-note.md`
- `/memories/repo/dq-rulebuilder-role-permissions-runtime-seed-note.md`
- `dq-db/mock-data/`
- `docker-compose.yml` (`delivery-seed`)
- `dq-api/fastapi/app/infrastructure/repositories/in_memory_test_data.py`
- `dq-api/scripts/generate_sql_seeds.py`
- `scripts/stack_seed.sh` (or `scripts/stack.sh dev seed`)
- `scripts/reseed_running_db.sh`
- `scripts/seed_delivery_objects.py`