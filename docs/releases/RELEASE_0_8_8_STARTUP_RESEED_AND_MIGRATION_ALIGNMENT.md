# Release v0.8.8 — Startup, Reseed, and Migration Alignment

**Release date**: 2026-04-27
**UI version**: `0.8.8`
**API version**: `0.8.6`

## Summary

This release tightens the runtime contract around stack startup and reseeding. Normal startup now applies schema migrations through an explicit one-shot migrator service, deployment-mode startup and seed helpers consistently use the selected env file, and containerized reseeding uses current workspace seed logic without forcing an unrelated `dq-api` rebuild.

## Included in this release

- UI package metadata is aligned to `0.8.8`
- API package metadata is aligned to `0.8.6`
- Version markers in `VERSION_MANIFEST.json` are aligned for the release and the changed tracked components: `Infrastructure` and `Documentation`
- `docker-compose.yml` now provides an `api-migrate` one-shot service using the existing `dq-api` image, and `api` waits for it before starting
- `dq-api/fastapi/docker-entrypoint.sh` now starts Uvicorn without an inline Alembic step because schema migration ownership moved to `api-migrate`
- Env-aware startup, stop, warmup, support-seed, and `db-seed` flows now use `ROOT_ENV_FILE` instead of pinning `.env`
- `db-seed` now runs against bind-mounted workspace seed sources so current seed and migration code is used during reseed without rebuilding `dq-api`
- `start-containers.sh` help text and startup logs now document the build/migration contract for `--no-build`, `--force-build`, `api-migrate`, and reseed flows

## User-visible impact

- Normal stack startup applies database migrations explicitly before the API service becomes healthy
- Deployment startup and helper services follow `.env.deployment.local` consistently when selected through the startup chain or `docker compose --env-file`
- Postgres reseeding picks up current workspace seed logic immediately instead of depending on a previously rebuilt `dq-api` image
- Operators can see the migration/build contract directly in `./scripts/start-containers.sh --help` and in startup logs

## Key implementation files

- [docker-compose.yml](../../docker-compose.yml)
- [scripts/start-containers.sh](../../scripts/start-containers.sh)
- [scripts/start_stack.sh](../../scripts/start_stack.sh)
- [scripts/seed_stack.sh](../../scripts/seed_stack.sh)
- [scripts/stop_stack.sh](../../scripts/stop_stack.sh)
- [scripts/stop-all.sh](../../scripts/stop-all.sh)
- [dq-api/fastapi/docker-entrypoint.sh](../../dq-api/fastapi/docker-entrypoint.sh)
- [dq-db/scripts/run_db_seed_container.sh](../../dq-db/scripts/run_db_seed_container.sh)
- [scripts/generate_external_id_patch.py](../../scripts/generate_external_id_patch.py)

## Documentation updated

- [README.md](../../README.md)
- [RELEASE_NOTES_USER.md](../../RELEASE_NOTES_USER.md)
- [dq-ui/public/release-notes/RELEASE_NOTES_USER.md](../../dq-ui/public/release-notes/RELEASE_NOTES_USER.md)
- [TECHNICAL.md](../../TECHNICAL.md)
- [docs/releases/README.md](./README.md)

## Notes

- The one-shot migrator uses the existing `dq-api` image; if new Alembic revisions are introduced, the `dq-api` image must still be rebuilt before a normal `--no-build` startup can apply them.
- The reseed path is intentionally different: it now uses the `db-seed` service with bind-mounted workspace sources, so seed logic changes do not require rebuilding `dq-api`.