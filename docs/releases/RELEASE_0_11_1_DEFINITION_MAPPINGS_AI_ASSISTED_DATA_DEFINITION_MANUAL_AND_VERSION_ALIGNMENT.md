# Release v0.11.1 - Definition Mappings AI-Assisted Data Definition Manual and Version Alignment

**Release date**: 2026-05-27
**UI version**: `0.11.1`
**Docs-site version**: `0.11.1`
**API version**: `0.11.0`

## Summary

This release publishes the AI-assisted Definition Mappings user manual, aligns the repo version markers for the documentation surface, and moves the public docs portal release line to `0.11.1`.

## Included in this release

- UI package metadata is aligned to `0.11.1`
- Docs-site package metadata is aligned to `0.11.1`
- Version markers in `VERSION_MANIFEST.json` are aligned for the changed tracked component: `Documentation`
- The Definition Mappings user manual now explains the AI-assisted data-definition workflow end to end
- The manual covers draft generation, steward review, board approval, validation, and OpenMetadata import
- Release, deployment, and versioning docs now point at the `v0.11.1` release line

## User-visible impact

- Users can follow the Definition Mappings workflow using the real UI labels and action buttons
- Steward review and board approval steps are documented in one place instead of being spread across implementation notes
- The OpenMetadata import step is documented as an explicit approval-gated action

## Key implementation files

- [VERSION_MANIFEST.json](../../VERSION_MANIFEST.json)
- [dq-ui/package.json](../../dq-ui/package.json)
- [dq-ui/docs-site/package.json](../../dq-ui/docs-site/package.json)
- [docs/user-manuals/data-definition.md](../user-manuals/data-definition.md)
- [dq-ui/docs-site/docs/user-manuals/data-definition.md](../../dq-ui/docs-site/docs/user-manuals/data-definition.md)
- [docs/user-manuals/README.md](../user-manuals/README.md)

## Documentation updated

- [RELEASE_NOTES_USER.md](../../RELEASE_NOTES_USER.md)
- [dq-ui/public/release-notes/RELEASE_NOTES_USER.md](../../dq-ui/public/release-notes/RELEASE_NOTES_USER.md)
- [docs/releases/README.md](./README.md)
- [docs/releases/index.md](./index.md)
- [docs/user-manuals.md](../../docs/user-manuals.md)
- [docs/user-manuals/README.md](../user-manuals/README.md)

## Notes

- The API app marker remains on `0.11.0` because this release changes the documentation publishing surface rather than API runtime behavior.
- The public docs portal should stay aligned with the root user-manual source tree.