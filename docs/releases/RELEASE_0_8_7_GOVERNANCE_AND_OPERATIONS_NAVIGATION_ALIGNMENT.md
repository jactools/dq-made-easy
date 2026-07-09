# Release v0.8.7 — Governance and Operations Navigation Alignment

**Release date**: 2026-04-27
**UI version**: `0.8.7`
**API version**: `0.8.5`

## Summary

This patch release finalizes the user-facing rollout of the rule-related navigation model.

The main objective is product clarity. The UI now uses `Rule Quality`, `Governance`, and `Operations` consistently in navigation, page naming, telemetry, and user-facing documentation so the live experience matches the intended information architecture.

## Included in this release

- UI package metadata is aligned to `0.8.7`
- API package metadata remains at `0.8.5`
- Version markers in `VERSION_MANIFEST.json` are aligned to `0.8.7` for the UI release and the changed tracked components: `Approval`, `Shared`, `Documentation`, `Report`, and `Telemetry`
- Governance is now the visible navigation home for approval queues, lifecycle controls, exception handling, and the governance overview preview
- Operations is now the visible navigation home for operational metrics, validation test results, aggregation, and execution monitoring
- Page-view telemetry now maps approval routes to `governance` and report routes to `operations`
- Walkthrough and current-state docs were refreshed so users no longer see the outdated `Approvals` and `Reports` top-level wording for these rule-related flows

## User-visible impact

- Users can navigate rule review, lifecycle, and exception workflows under Governance without the older mixed naming
- Users can find metrics, validation history, and execution-oriented follow-on capabilities under Operations
- Release notes, feature summaries, and quick-reference walkthroughs now match the live sidebar and page headings

## Key implementation files

- [dq-ui/src/components/Sidebar.tsx](../../dq-ui/src/components/Sidebar.tsx)
- [dq-ui/src/components/Approvals.tsx](../../dq-ui/src/components/Approvals.tsx)
- [dq-ui/src/components/Reports.tsx](../../dq-ui/src/components/Reports.tsx)
- [dq-ui/src/components/Documentation.tsx](../../dq-ui/src/components/Documentation.tsx)
- [dq-ui/src/telemetry.ts](../../dq-ui/src/telemetry.ts)
- [VERSION_MANIFEST.json](../../VERSION_MANIFEST.json)
- [dq-ui/package.json](../../dq-ui/package.json)

## Documentation updated

- [RELEASE_NOTES_USER.md](../../RELEASE_NOTES_USER.md)
- [dq-ui/public/release-notes/RELEASE_NOTES_USER.md](../../dq-ui/public/release-notes/RELEASE_NOTES_USER.md)
- [docs/features/FEATURES.md](../../docs/features/FEATURES.md)
- [docs/features/DQ_FEATURES.md](../../docs/features/DQ_FEATURES.md)
- [docs/user-manuals/DQ-2_QUICK_REFERENCE.md](../../docs/user-manuals/DQ-2_QUICK_REFERENCE.md)
- [docs/features/MANAGEMENT_FEATURE_SUMMARY.md](../../docs/features/MANAGEMENT_FEATURE_SUMMARY.md)
- [docs/implementation-details/DQ_1_RULE_VALIDATION_STANDARD_FEATURE_IMPLEMENTATION_PLAN.md](../../docs/implementation-details/DQ_1_RULE_VALIDATION_STANDARD_FEATURE_IMPLEMENTATION_PLAN.md)

## Notes

- This is a UI and documentation alignment release.
- No backend API contracts changed in this patch.