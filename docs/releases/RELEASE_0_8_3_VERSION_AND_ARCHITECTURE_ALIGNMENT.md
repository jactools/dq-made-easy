# Release v0.8.3 — Version and Architecture Alignment

**Release date**: 2026-04-25
**UI version**: `0.8.3`
**API version**: `0.8.3`

## Summary

This patch release aligns the repo-owned version markers and refreshes the architecture documentation so the current codebase structure, diagrams, and latest-release references all describe the same system.

The immediate goal is consistency: the app and component version metadata should match the release-facing docs, and the architecture diagrams should match the refactored FastAPI adapter and application seams already present in the codebase.

## Included in this release

- UI package metadata is aligned to `0.8.3`
- API package metadata is aligned to `0.8.3`
- Version markers in `VERSION_MANIFEST.json` and tracked components are aligned to `0.8.3`
- `architecture/api-layering.md` and `architecture/ddd-implementation.md` now reflect the explicit API-adapter split, application use cases and services, typed domain seams, and fail-fast runtime boundaries
- `architecture/api-layering.mmd` and `architecture/ddd-implementation.mmd` were updated to match the written architecture docs
- `architecture/api-layering.svg` and `architecture/ddd-implementation.svg` were regenerated from the updated Mermaid sources
- Root and published release-note copies were synchronized to the new latest release

## User-visible impact

- In-app and repository release references now consistently show `v0.8.3`
- Architecture documentation is easier to trust during implementation and review because the diagrams and prose now match the current backend structure
- No end-user workflow changes are introduced by this patch release

## Documentation updated

- [README.md](../../README.md)
- [RELEASE_NOTES_USER.md](../../RELEASE_NOTES_USER.md)
- [dq-ui/public/release-notes/RELEASE_NOTES_USER.md](../../dq-ui/public/release-notes/RELEASE_NOTES_USER.md)
- [TECHNICAL.md](../../TECHNICAL.md)
- [docs/releases/README.md](./README.md)
- [architecture/api-layering.md](../../architecture/api-layering.md)
- [architecture/ddd-implementation.md](../../architecture/ddd-implementation.md)
- [architecture/api-layering.mmd](../../architecture/api-layering.mmd)
- [architecture/ddd-implementation.mmd](../../architecture/ddd-implementation.mmd)
- [architecture/api-layering.svg](../../architecture/api-layering.svg)
- [architecture/ddd-implementation.svg](../../architecture/ddd-implementation.svg)

## Notes

- This release is documentation- and metadata-focused.
- Hash-pinned container image tags and third-party dependency versions were intentionally left unchanged.