# Release v0.9.3 — Role Access and Version Alignment

**Release date**: 2026-05-02
**UI version**: `0.9.3`
**API version**: `0.9.3`

## Summary

This patch release aligns the read-only role experience with the current UI and backend access model, and refreshes the release-facing docs to match the new `0.9.3` baseline.

## Included in this release

- UI package metadata is aligned to `0.9.3`
- API package metadata is aligned to `0.9.3`
- Version markers in `VERSION_MANIFEST.json` are aligned for the release and the changed tracked components: `Admin`, `UserManagement`, `RoleManagement`, `DataCatalog`, `Authentication`, `Documentation`, and `Testautomation`
- Auditor and regulator users now see an explicit role badge in the header
- Delivery Inventory now renders for read-only users with data-catalog read access instead of hard-coding admin/data-steward roles
- Admin read pages now follow the same canonical read-access contract as the rest of the updated role-based UI

## User-visible impact

- Auditor and regulator users can tell at a glance which role is active in the header
- Read-only users can open the Delivery Inventory and the admin read pages without needing mutable admin privileges
- Release and deployment docs now point at the `0.9.3` release line

## Key implementation files

- [VERSION_MANIFEST.json](../../VERSION_MANIFEST.json)
- [dq-ui/package.json](../../dq-ui/package.json)
- [dq-api/package.json](../../dq-api/package.json)
- [dq-ui/src/components/Header.tsx](../../dq-ui/src/components/Header.tsx)
- [dq-ui/src/components/DeliveryInventory.tsx](../../dq-ui/src/components/DeliveryInventory.tsx)
- [dq-ui/src/App.tsx](../../dq-ui/src/App.tsx)
- [dq-ui/src/components/Sidebar.tsx](../../dq-ui/src/components/Sidebar.tsx)
- [dq-api/fastapi/app/core/auth.py](../../dq-api/fastapi/app/core/auth.py)
- [dq-ui/src/components/Header.test.tsx](../../dq-ui/src/components/Header.test.tsx)
- [dq-ui/src/components/DeliveryInventory.test.tsx](../../dq-ui/src/components/DeliveryInventory.test.tsx)
- [README.md](../../README.md)
- [RELEASE_NOTES_USER.md](../../RELEASE_NOTES_USER.md)
- [TECHNICAL.md](../../TECHNICAL.md)

## Documentation updated

- [RELEASE_NOTES_USER.md](../../RELEASE_NOTES_USER.md)
- [dq-ui/public/release-notes/RELEASE_NOTES_USER.md](../../dq-ui/public/release-notes/RELEASE_NOTES_USER.md)
- [TECHNICAL.md](../../TECHNICAL.md)
- [README.md](../../README.md)
- [DEPLOYMENT.md](../../DEPLOYMENT.md)
- [QUICKSTART_DEPLOY.md](../../QUICKSTART_DEPLOY.md)
- [AUTOMATIC_VERSIONING.md](../../AUTOMATIC_VERSIONING.md)
- [docs/releases/README.md](./README.md)
- [docs/technical/DEPLOYMENT.md](../technical/DEPLOYMENT.md)
- [docs/technical/QUICKSTART_DEPLOY.md](../technical/QUICKSTART_DEPLOY.md)
- [docs/technical/AUTOMATIC_VERSIONING.md](../technical/AUTOMATIC_VERSIONING.md)

## Notes

- Repo-managed Docker image tags stay on the `0.9-<hash>` release line for this patch release because image tags derive from the `major.minor` base in `VERSION_MANIFEST.json`.
- The release note copy under `dq-ui/public/release-notes/` should stay in sync with the root `RELEASE_NOTES_USER.md`.
