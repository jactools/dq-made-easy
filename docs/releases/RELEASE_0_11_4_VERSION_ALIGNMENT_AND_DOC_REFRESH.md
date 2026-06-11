# Release v0.11.4 - Version Alignment and Documentation Refresh

**Release date**: 2026-06-06
**UI version**: `0.11.4`
**Docs-site version**: `0.11.4`
**API version**: `0.11.0`

## Summary

This release aligns the dq-ui and docs-site version markers to `0.11.4` and refreshes the release-facing documentation pointers to the new app version.

## Included in this release

- UI package metadata is aligned to `0.11.4`
- Docs-site package metadata is aligned to `0.11.4`
- Version markers in `VERSION_MANIFEST.json` are aligned for the changed tracked component: `Documentation`
- Release, deployment, and versioning docs now point at the `v0.11.4` release line

## User-visible impact

- The release and versioning docs now reflect the current UI release line
- The public docs portal metadata stays aligned with the app version marker

## Key implementation files

- [VERSION_MANIFEST.json](../../VERSION_MANIFEST.json)
- [dq-ui/package.json](../../dq-ui/package.json)
- [dq-ui/docs-site/package.json](../../dq-ui/docs-site/package.json)
- [docs/releases/README.md](./README.md)
- [docs/releases/index.md](./index.md)
- [docs/technical/AUTOMATIC_VERSIONING.md](../../dq-ui/docs-site/docs/technical/AUTOMATIC_VERSIONING.md)

## Documentation updated

- [RELEASE_NOTES_USER.md](../../RELEASE_NOTES_USER.md)
- [dq-ui/public/release-notes/RELEASE_NOTES_USER.md](../../dq-ui/public/release-notes/RELEASE_NOTES_USER.md)
- [docs/releases/README.md](./README.md)
- [docs/releases/index.md](./index.md)
- [docs/technical/AUTOMATIC_VERSIONING.md](../../dq-ui/docs-site/docs/technical/AUTOMATIC_VERSIONING.md)

## Notes

- The API app marker remains on `0.11.0` because this release changes the documentation and UI release markers rather than API runtime behavior.