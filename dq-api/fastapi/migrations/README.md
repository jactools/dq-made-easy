# Alembic Migrations

This directory is the authoritative home for database schema changes for the FastAPI application.

Policy:

- All future table creation and schema modification must be implemented as Alembic revisions.
- Alembic is the **sole DDL authority** for all schema creation. The legacy `dq-db/init` SQL DDL files have been baselined into migration `0001` and archived under `dq-db/init/backup/`.
- New tables and schema changes must be introduced through Alembic revisions rather than direct edits to init SQL files.

Common commands:

```bash
alembic upgrade head
alembic downgrade base
alembic revision -m "describe change"
alembic revision --autogenerate -m "describe change"
```

Notes:

- `env.py` imports the SQLAlchemy ORM models and uses `Base.metadata` for autogeneration.
- `DATABASE_URL` is read from the environment when available and normalized to use `postgresql+psycopg://`.
- The API container runs `alembic upgrade head` automatically on startup (before uvicorn) via `Dockerfile.fastapi`.
- The `dq-db` container only initialises the `pg_stat_statements` extension on first boot; all table creation is handled by Alembic via the API container.
- Reseed flows use a 3-phase process: (1) reset schema in the DB container, (2) `alembic upgrade head` from the host, (3) apply seed data in the DB container.

Migration chain:

| File | Revision | Description |
|---|---|---|
| `20260322_0001_legacy_schema_baseline.py` | `0001` | Full legacy schema (25 tables from `01_schema`, `02_profiling_schema`, `04_rule_versioning`, `05_rule_compiler_artifacts`, `06_validation_run_history`) |
| `20260322_0002_add_gx_suite_registry.py` | `0002` | GX suite registry tables |
| `20260322_0003_add_gx_audit_trail.py` | `0003` | GX audit trail tables |
| `20260406_0004_add_gx_execution_run_lifecycle.py` | `0004` | GX execution run metadata and lifecycle history tables |
| `20260406_0005_add_gx_execution_violation_store.py` | `0005` | GX execution violation rows scoped by `data_object_version_id` |