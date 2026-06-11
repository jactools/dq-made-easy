# Release v0.8.6 — UI Selector and Header Navigation Alignment

**Release date**: 2026-04-27
**UI version**: `0.8.6`
**API version**: `0.8.5`

## Summary

This patch release packages the current UI alignment work into a coherent frontend update.

The main objective is consistency: workspace-scope selection now uses the same segmented pill control across the major list and workflow screens, and settings navigation that used to disappear while scrolling now stays attached to the header where it remains visible.

## Included in this release

- UI package metadata is aligned to `0.8.6`
- API package metadata remains at `0.8.5`
- Version markers in `VERSION_MANIFEST.json` are aligned to `0.8.6` for the UI release and the changed tracked components: `Approval`, `Rules`, `Admin`, `Shared`, `Templates`, `Settings`, `Report`, `DataCatalog`, and `Documentation`
- The shared segmented pill control is now reused across Data Catalog, Operations, Assign Attributes, Rules, Governance, and Templates
- Rules filter styling now matches the updated selector treatment and no longer inherits the wrong global filter-group pill container styling
- Admin Application Settings keeps “Jump to section” in the page header instead of inside the scrolling panel body
- User Settings moves the old left-side section rail into the header as segmented pills for the main settings areas

## User-visible impact

- Scope switching feels consistent when moving between catalog, operations, governance, rules, and template workflows
- The Rules screen no longer shows the incorrect rounded wrapper around the Status dropdown
- Settings navigation remains visible while scrolling instead of disappearing lower in the page

## Key implementation files

- [dq-ui/src/components/WorkspaceScopeSegmentedControl.tsx](../../dq-ui/src/components/WorkspaceScopeSegmentedControl.tsx)
- [dq-ui/src/components/WorkspaceScopeSegmentedControl.css](../../dq-ui/src/components/WorkspaceScopeSegmentedControl.css)
- [dq-ui/src/components/DataBrowser.tsx](../../dq-ui/src/components/DataBrowser.tsx)
- [dq-ui/src/components/Reports.tsx](../../dq-ui/src/components/Reports.tsx)
- [dq-ui/src/components/AssignAttributesModal.tsx](../../dq-ui/src/components/AssignAttributesModal.tsx)
- [dq-ui/src/components/rules/RulesHeader.tsx](../../dq-ui/src/components/rules/RulesHeader.tsx)
- [dq-ui/src/components/Rules.tsx](../../dq-ui/src/components/Rules.tsx)
- [dq-ui/src/components/Approvals.tsx](../../dq-ui/src/components/Approvals.tsx)
- [dq-ui/src/components/Templates.tsx](../../dq-ui/src/components/Templates.tsx)
- [dq-ui/src/components/ApplicationSettings.tsx](../../dq-ui/src/components/ApplicationSettings.tsx)
- [dq-ui/src/components/AdminPageHeader.tsx](../../dq-ui/src/components/AdminPageHeader.tsx)
- [dq-ui/src/components/Settings.tsx](../../dq-ui/src/components/Settings.tsx)
- [dq-ui/src/components/Settings.css](../../dq-ui/src/components/Settings.css)
- [dq-ui/package.json](../../dq-ui/package.json)
- [VERSION_MANIFEST.json](../../VERSION_MANIFEST.json)

## Documentation updated

- [README.md](../../README.md)
- [RELEASE_NOTES_USER.md](../../RELEASE_NOTES_USER.md)
- [dq-ui/public/release-notes/RELEASE_NOTES_USER.md](../../dq-ui/public/release-notes/RELEASE_NOTES_USER.md)
- [docs/releases/README.md](./README.md)

## Notes

- This is a UI-only patch release.
- The API package version stays at `0.8.5` because this release does not change backend behavior or contracts.