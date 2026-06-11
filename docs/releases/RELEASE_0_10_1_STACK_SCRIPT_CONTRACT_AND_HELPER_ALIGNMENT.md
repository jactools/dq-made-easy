# Release v0.10.1 — Stack Script Contract and Helper Alignment

**Release date**: 2026-05-09
**UI version**: `0.10.1`
**API version**: `0.10.1`

## Summary

This patch release tightens the stack startup and seeding contract around the shared shell primitives, fixes the repo-root resolution used by the helper layers, and documents the canonical script surface for operators and maintainers.

## Included in this release

- UI package metadata is aligned to `0.10.1`
- API package metadata is aligned to `0.10.1`
- Version markers in `VERSION_MANIFEST.json` are aligned for the changed tracked components: `Infrastructure` and `Documentation`
- Stack startup, seeding, validation, and teardown helpers now share the canonical shell primitives and repo-root resolution
- Validation and smoke helpers assume services are already running instead of managing Compose lifecycle themselves
- `STACK_SCRIPT_CONTRACT.md` documents the canonical script surface, dependency flow, and stop-order contract

## User-visible impact

- The common startup wrapper and the underlying helper scripts now follow the same repo-root and logging conventions
- Validation and smoke flows fail fast when the stack is not already running, which keeps lifecycle ownership in the startup and stop scripts
- Release, deployment, and versioning docs now point at the `v0.10.1` release line

## Key implementation files

- [VERSION_MANIFEST.json](../../VERSION_MANIFEST.json)
- [dq-ui/package.json](../../dq-ui/package.json)
- [dq-api/package.json](../../dq-api/package.json)
- [scripts/start-containers.sh](../../scripts/start-containers.sh)
- [scripts/start_stack.sh](../../scripts/start_stack.sh)
- [scripts/supporting/env/selection.sh](../../scripts/supporting/env/selection.sh)
- [scripts/supporting/compose/invocation.sh](../../scripts/supporting/compose/invocation.sh)
- [scripts/supporting/auth.sh](../../scripts/supporting/auth.sh)
- [scripts/supporting/teardown.sh](../../scripts/supporting/teardown.sh)
- [docs/implementation-details/STACK_SCRIPT_CONTRACT.md](../../docs/implementation-details/STACK_SCRIPT_CONTRACT.md)

## Documentation updated

- [RELEASE_NOTES_USER.md](../../RELEASE_NOTES_USER.md)
- [dq-ui/public/release-notes/RELEASE_NOTES_USER.md](../../dq-ui/public/release-notes/RELEASE_NOTES_USER.md)
- [README.md](../../README.md)
- [docs/releases/README.md](./README.md)
- [docs/technical/DEPLOYMENT.md](../technical/DEPLOYMENT.md)
- [docs/technical/QUICKSTART_DEPLOY.md](../technical/QUICKSTART_DEPLOY.md)
- [docs/technical/AUTOMATIC_VERSIONING.md](../technical/AUTOMATIC_VERSIONING.md)
- [TECHNICAL.md](../../TECHNICAL.md)

## Notes

- Repo-managed Docker image tags stay on the `0.10-<hash>` release line because image tags derive from the `major.minor` base in `VERSION_MANIFEST.json`.
- The release note copy under `dq-ui/public/release-notes/` should stay in sync with the root `RELEASE_NOTES_USER.md`.
