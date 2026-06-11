# Release v0.8.5 — Build, Reseed, and Validation Alignment

**Release date**: 2026-04-26
**UI version**: `0.8.5`
**API version**: `0.8.5`

## Summary

This patch release aligns three pieces of repo operations that had drifted apart: image build scope, database reseed/startup sequencing, and default validation execution.

The main objective is operational correctness. The repo now keeps schema-owning images aligned during seeded startup, exposes an honest distinction between the standard core image build and the full repo-managed image build, and makes the validation runner default match what operators expect when they ask for `all`.

## Included in this release

- UI package metadata is aligned to `0.8.5`
- API package metadata is aligned to `0.8.5`
- Version markers in `VERSION_MANIFEST.json` are aligned to `0.8.5` for the release and the changed tracked components: `Infrastructure`, `Documentation`, and `Testautomation`
- `scripts/start-containers.sh` now rebuilds `api` and `db-seed` together before Postgres reseed/init flows and runs the Postgres reseed before full stack startup
- `scripts/build_and_push_all.sh` now distinguishes `core` and `repo` image scopes, with repo scope including auxiliary repo-managed images such as `db-seed`, metadata helpers, `container-metrics`, and `zammad-seed`
- `scripts/calculate_versions.sh` now hashes actual Docker build inputs per image, including frontend assets, runtime scripts, and auxiliary image contexts
- `scripts/validate.sh` now treats the default `all` group as the union of smoke scripts and all included validate scripts
- Validation and versioning docs were updated so the documented behavior matches the current scripts

## User-visible impact

- Fresh-stack startup with `./scripts/start-containers.sh --all --seed-all --init-db` no longer relies on stale schema-owner images during reseed
- Operators can choose whether to build only the core product images or the broader set of repo-managed custom images
- Running `scripts/validate.sh` with no group now gives the broader validation coverage implied by the default `all` group

## Key implementation files

- [scripts/start-containers.sh](../../scripts/start-containers.sh)
- [dq-db/scripts/reseed_in_container.sh](../../dq-db/scripts/reseed_in_container.sh)
- [scripts/build_and_push_all.sh](../../scripts/build_and_push_all.sh)
- [scripts/calculate_versions.sh](../../scripts/calculate_versions.sh)
- [scripts/validate.sh](../../scripts/validate.sh)
- [scripts/VALIDATION.md](../../scripts/VALIDATION.md)
- [AUTOMATIC_VERSIONING.md](../../AUTOMATIC_VERSIONING.md)

## Documentation updated

- [README.md](../../README.md)
- [RELEASE_NOTES_USER.md](../../RELEASE_NOTES_USER.md)
- [dq-ui/public/release-notes/RELEASE_NOTES_USER.md](../../dq-ui/public/release-notes/RELEASE_NOTES_USER.md)
- [TECHNICAL.md](../../TECHNICAL.md)
- [docs/releases/README.md](./README.md)
- [AUTOMATIC_VERSIONING.md](../../AUTOMATIC_VERSIONING.md)
- [docs/technical/AUTOMATIC_VERSIONING.md](../../docs/technical/AUTOMATIC_VERSIONING.md)
- [scripts/VALIDATION.md](../../scripts/VALIDATION.md)

## Notes

- This is primarily an infrastructure and operator-workflow release.
- The new build-scope split changes orchestration clarity, not the underlying per-service build scripts.
- The validation runner still excludes helper-only scripts marked with `# validate: include=false`.