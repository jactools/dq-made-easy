# EDR-015 [DB]: PostgreSQL Transaction Isolation and Mutation Semantics

**Status**: Accepted
**Date**: 2026-04-20
**Tag**: DB

## Context
Several repository issues that first appeared as API or UI failures were actually database mutation and schema-state problems:

- serializing ORM-backed rows after the SQLAlchemy session closes can turn normal update flows into detached-row 500s
- reused database volumes can drift away from required runtime extension state even when the stack appears healthy
- placeholder or incomplete migration-head behavior can leave seeded environments missing required columns at runtime
- entity migration work can break older tests and helpers if repository return types change before compatibility shims and explicit response shaping are in place
- role and scope changes are only real once the database schema and seeded permissions actually exist at runtime

These are durable PostgreSQL and repository-mutation rules, not isolated bug fixes.

## Decision
Adopt the following PostgreSQL mutation and schema rules:

- Repository mutation paths must serialize or materialize response payloads before the database session closes when the returned object depends on ORM-backed state.
- Required runtime database extensions must be enforced explicitly during stack startup rather than assumed from reused volumes.
- Seeded and smoke-test database bootstrap must use the repository's explicit bootstrap path when migration head alone is insufficient to materialize the live schema.
- Missing schema columns or role-permission fields at runtime are migration/bootstrap failures and must be repaired at the database layer, not papered over in frontend or API logic.
- During entity-model migration, backward compatibility for legacy tests/helpers may be preserved through entity compatibility shims, but endpoint response shaping must stay explicit and contract-driven.
- Scope and permission migrations are complete only when seed data, generated realm/config artifacts, and live database schema all agree on the non-legacy permission model.

## Rationale
- Detached-row failures are avoidable if repositories finalize the serializable payload while the session is still valid.
- Reused local volumes frequently preserve partial state, so startup guardrails are safer than optimistic assumptions.
- A green-looking stack with missing columns or extensions is worse than a fail-fast startup because it produces misleading downstream failures.
- Entity migration needs compatibility for internal callers, but API output must remain intentionally shaped rather than inherited from model internals.
- Permission and scope migrations span schema, seed data, and generated auth artifacts; treating any one layer as sufficient causes drift.

## Scope Boundaries
This decision applies to PostgreSQL-backed repository mutation behavior, runtime schema/bootstrap enforcement, and compatibility expectations during entity migration.

It does not by itself define:
- all application-level authorization semantics
- full Alembic authoring standards for every future migration
- frontend permission rendering behavior outside the requirement that runtime DB schema be correct
- every stack startup check beyond the required schema and extension guardrails already adopted

## Consequences
**Positive**
- Repository update flows are less likely to fail on detached ORM rows.
- Reused local/prototype database volumes fail fast when required extension or schema state is missing.
- Schema and permission drift is diagnosed at the right layer.
- Entity migration can progress without silently breaking contract-facing API responses.

**Negative**
- Startup and reseed flows remain more explicit than a naive "run migrations and hope" model.
- Compatibility shims may temporarily increase complexity during entity migration.
- Database/bootstrap issues surface earlier and more noisily, which is operationally stricter but intentional.

## Implementation Guidance
- In repository update methods, build the serialized response payload before the session is torn down if the return value depends on ORM-loaded state.
- Enforce required runtime extensions such as `pg_stat_statements` during stack startup and fail fast if preload prerequisites are missing.
- Use the explicit seeded bootstrap path for live reseed/smoke flows when Alembic head is not sufficient to create the expected runtime schema.
- Treat missing runtime columns such as role-permission fields as migration/bootstrap defects; repair schema and reseed rather than masking the problem in callers.
- Preserve compatibility helpers for legacy internal dict-style access only as a migration aid, and keep endpoint response shaping explicit with model dumps or dedicated view models.
- Keep non-legacy scope/permission migrations synchronized across seed CSVs, generated auth artifacts, and live DB schema.

## Related Artifacts
- `/memories/repo/dq-rulebuilder-postgres-update-serialize-in-session-note.md`
- `/memories/repo/dq-rulebuilder-dqdb-pg-stat-statements-startup-enforcement-note.md`
- `/memories/repo/dq-rulebuilder-fastapi-entity-migration-compat-note.md`
- `/memories/repo/dq-rulebuilder-nonlegacy-scope-migration-note.md`
- `/memories/repo/dq-rulebuilder-role-permissions-runtime-seed-note.md`
- `/memories/repo/dq-rulebuilder-seeded-smoke-schema-bootstrap-and-profiling-fk-note.md`
- `scripts/stack_start.sh` (or `scripts/stack.sh dev start`)
- `scripts/stack_seed.sh` (or `scripts/stack.sh dev seed`)
- `scripts/reseed_running_db.sh`
- `dq-api/fastapi/app/domain/entities/base.py`