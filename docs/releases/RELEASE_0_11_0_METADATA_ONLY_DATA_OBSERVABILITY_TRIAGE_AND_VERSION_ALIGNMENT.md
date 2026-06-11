# Release v0.11.0 — Metadata-Only Data Observability Triage and Version Alignment

**Release date**: 2026-05-25
**UI version**: `0.11.0`
**Docs-site version**: `0.11.0`
**API version**: `0.11.0`

## Summary

This release promotes the data observability triage flow to a metadata-only incident experience, adds the end-user manual for the new flow, and aligns the repo version markers to `0.11.0`.

## Included in this release

- UI package metadata is aligned to `0.11.0`
- API package metadata is aligned to `0.11.0`
- Docs-site package metadata is aligned to `0.11.0`
- Version markers in `VERSION_MANIFEST.json` are aligned for the changed tracked components: `Report`, `Documentation`, and `Testautomation`
- The incidents API and reports UI now expose metadata only, not raw source records or failure payloads
- The new Data Observability Triage Guide is published in the user-manuals tree
- Release, deployment, and versioning docs now point at the `v0.11.0` release line

## User-visible impact

- Users can triage incidents by status, assignment, scope, severity, and ticket state without seeing raw data
- The triage page now makes the no-raw-data boundary explicit
- The release line for the repo has moved to `0.11`

## Key implementation files

- [VERSION_MANIFEST.json](../../VERSION_MANIFEST.json)
- [dq-ui/package.json](../../dq-ui/package.json)
- [dq-ui/docs-site/package.json](../../dq-ui/docs-site/package.json)
- [dq-api/package.json](../../dq-api/package.json)
- [dq-api/fastapi/app/api/v1/endpoints/incidents.py](../../dq-api/fastapi/app/api/v1/endpoints/incidents.py)
- [dq-ui/src/components/Reports.tsx](../../dq-ui/src/components/Reports.tsx)
- [docs/user-manuals/data-observability-triage-guide.md](../user-manuals/data-observability-triage-guide.md)
- [docs/features/DQ_FEATURES.md](../features/DQ_FEATURES.md)

## Documentation updated

- [RELEASE_NOTES_USER.md](../../RELEASE_NOTES_USER.md)
- [dq-ui/public/release-notes/RELEASE_NOTES_USER.md](../../dq-ui/public/release-notes/RELEASE_NOTES_USER.md)
- [docs/releases/README.md](./README.md)
- [docs/releases/index.md](./index.md)
- [docs/user-manuals.md](../../docs/user-manuals.md)
- [docs/user-manuals/README.md](../user-manuals/README.md)
- [docs/technical/AUTOMATIC_VERSIONING.md](../technical/AUTOMATIC_VERSIONING.md)
- [docs/technical/DQ_PUBLIC_DOCUMENTATION_PORTAL_ROLLOUT_AND_OPERATOR_NOTES.md](../technical/DQ_PUBLIC_DOCUMENTATION_PORTAL_ROLLOUT_AND_OPERATOR_NOTES.md)

## Notes

- Repo-managed Docker image tags now derive from the `0.11` release line.
- The release note copy under `dq-ui/docs-site/docs/releases/` should stay in sync with the root copy.