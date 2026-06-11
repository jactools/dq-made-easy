# Release v0.10.0 — DQ7 Migration Closure and Read-Only Reusable Assets

**Release date**: 2026-05-04
**UI version**: `0.10.0`
**API version**: `0.10.0`

## Summary

This release closes the DQ-7 mock-data migration to the canonical `2.0.0` contract, updates the app versions to `0.10.0`, and makes reusable filter and reusable join details visible in read-only mode for locked rules.

## Included in this release

- UI package metadata is aligned to `0.10.0`
- API package metadata is aligned to `0.10.0`
- The DQ-7 mock-data migration plan is marked complete after the canonical seed rewrite and reusable-asset promotion
- Locked rules show reusable filter and reusable join icons in the selected rule card
- Read-only reusable modals show assigned details only and hide available/edit controls
- Release, deployment, and versioning docs now point at the `0.10` release line

## User-visible impact

- Editable rules continue to use the existing action toolbar
- Locked rules can still inspect reusable assets without implying they are assignable
- Repo-managed Docker image tags now derive from the `0.10` major.minor release line

## Key implementation files

- [VERSION_MANIFEST.json](../../VERSION_MANIFEST.json)
- [dq-ui/package.json](../../dq-ui/package.json)
- [dq-api/package.json](../../dq-api/package.json)
- [docs/implementation-details/DQ_7_DSL_MOCK_DATA_2_0_0_MIGRATION_PLAN.md](../implementation-details/DQ_7_DSL_MOCK_DATA_2_0_0_MIGRATION_PLAN.md)
- [dq-ui/src/components/rules/RuleCard.tsx](../../dq-ui/src/components/rules/RuleCard.tsx)
- [dq-ui/src/components/ReusableFiltersModal.tsx](../../dq-ui/src/components/ReusableFiltersModal.tsx)
- [dq-ui/src/components/ReusableJoinsModal.tsx](../../dq-ui/src/components/ReusableJoinsModal.tsx)

## Documentation updated

- [RELEASE_NOTES_USER.md](../../RELEASE_NOTES_USER.md)
- [dq-ui/public/release-notes/RELEASE_NOTES_USER.md](../../dq-ui/public/release-notes/RELEASE_NOTES_USER.md)
- [README.md](../../README.md)
- [docs/releases/README.md](./README.md)
- [docs/implementation-details/DQ_7_DSL_MOCK_DATA_2_0_0_MIGRATION_PLAN.md](../implementation-details/DQ_7_DSL_MOCK_DATA_2_0_0_MIGRATION_PLAN.md)
- [docs/technical/DEPLOYMENT.md](../technical/DEPLOYMENT.md)
- [docs/technical/QUICKSTART_DEPLOY.md](../technical/QUICKSTART_DEPLOY.md)
- [docs/technical/AUTOMATIC_VERSIONING.md](../technical/AUTOMATIC_VERSIONING.md)

## Notes

- Repo-managed Docker image tags now use the `0.10-<hash>` release line because image tags derive from the `major.minor` base in `VERSION_MANIFEST.json`.
- The release note copy under `dq-ui/public/release-notes/` should stay in sync with the root `RELEASE_NOTES_USER.md`.