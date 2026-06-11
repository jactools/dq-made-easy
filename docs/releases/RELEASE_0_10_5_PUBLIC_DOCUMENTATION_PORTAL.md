# Release v0.10.5 - Public Documentation Portal

**Release date**: 2026-05-22
**UI version**: `0.10.5`
**Docs-site version**: `0.10.5`
**API version**: `0.10.4` unchanged

## Summary

This release promotes the public documentation portal to the current release line. The UI now builds and serves a static Docusaurus documentation site from `/docs/`, with repository docs and architecture docs published through one unified docs tree.

## Included in this release

- UI package metadata is aligned to `0.10.5`
- Docs-site package metadata is aligned to `0.10.5`
- Version markers in `VERSION_MANIFEST.json` are aligned for the changed tracked components: `Infrastructure`, `Documentation`, and `Testautomation`
- The public docs build reads `docs/` and `architecture/` directly as the authored source trees
- The Docusaurus site consumes the two roots without mirroring them into a site-local authoring tree
- Release, deployment, and versioning docs now point at the `v0.10.5` release line

## User-visible impact

- Operators and users can open the public documentation portal at `/docs/` without signing in
- Documentation navigation now includes current status, roadmap, release notes, engineering decisions, architecture, features, implementation details, contracts, runbooks, fixes, and user manuals
- The portal keeps default Docusaurus styling while supporting light and dark color modes

## Key implementation files

- [VERSION_MANIFEST.json](../../VERSION_MANIFEST.json)
- [dq-ui/package.json](../../dq-ui/package.json)
- [dq-ui/docs-site/package.json](../../dq-ui/docs-site/package.json)
- [dq-ui/docs-site/docusaurus.config.js](../../dq-ui/docs-site/docusaurus.config.js)
- [dq-ui/docs-site/sidebars.js](../../dq-ui/docs-site/sidebars.js)
- [dq-ui/docs-site/sidebars-utils.js](../../dq-ui/docs-site/sidebars-utils.js)
- [dq-ui/scripts/build-public-docs.sh](../../dq-ui/scripts/build-public-docs.sh)
- [docs/technical/DQ_PUBLIC_DOCUMENTATION_PORTAL_ROLLOUT_AND_OPERATOR_NOTES.md](../technical/DQ_PUBLIC_DOCUMENTATION_PORTAL_ROLLOUT_AND_OPERATOR_NOTES.md)

## Documentation updated

- [RELEASE_NOTES_USER.md](../../RELEASE_NOTES_USER.md)
- [dq-ui/public/release-notes/RELEASE_NOTES_USER.md](../../dq-ui/public/release-notes/RELEASE_NOTES_USER.md)
- [TECHNICAL.md](../../TECHNICAL.md)
- [docs/releases/README.md](./README.md)
- [docs/technical/DEPLOYMENT.md](../technical/DEPLOYMENT.md)
- [docs/technical/QUICKSTART_DEPLOY.md](../technical/QUICKSTART_DEPLOY.md)
- [docs/technical/AUTOMATIC_VERSIONING.md](../technical/AUTOMATIC_VERSIONING.md)

## Notes

- Repo-managed Docker image tags stay on the `0.10-<hash>` release line because image tags derive from the `major.minor` base in `VERSION_MANIFEST.json`.
- The API app marker remains on `0.10.4` because this release changes the UI documentation publishing surface rather than API runtime behavior.