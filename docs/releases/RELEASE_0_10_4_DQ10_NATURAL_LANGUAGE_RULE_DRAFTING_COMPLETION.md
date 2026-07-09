# Release v0.10.4 — Natural-Language Rule Drafting Preview Completion

**Release date**: 2026-05-17
**UI version**: `0.10.4`
**API version**: `0.10.4`

## Summary

This release finalizes the DQ-10 natural-language rule drafting preview and moves its completed current-state snapshot into the current-status documentation set.

## Included in this release

- UI package metadata is aligned to `0.10.4`
- API package metadata is aligned to `0.10.4`
- Version markers in `VERSION_MANIFEST.json` are aligned for the changed tracked components: `Authentication`, `Infrastructure`, `DataCatalog`, `Documentation`, and `Testautomation`
- The DQ-10 current-state snapshot now lives under `docs/features/current`
- The preview flow remains inside Suggestions with ranked candidate attributes, explicit confirmation, and fail-fast ambiguity handling
- Release, deployment, and versioning docs now point at the `v0.10.4` release line

## User-visible impact

- Data stewards can use the existing Suggestions preview flow to describe checks in plain language
- Candidate attribute selection remains explicit and reviewable before a typed draft is saved
- Unsupported prompts and missing dependencies continue to fail fast instead of falling back silently
- The repository now documents the completed current-state snapshot separately from the feature-plan source

## Key implementation files

- [VERSION_MANIFEST.json](../../VERSION_MANIFEST.json)
- [dq-ui/package.json](../../dq-ui/package.json)
- [dq-api/fastapi/pyproject.toml](../../dq-api/fastapi/pyproject.toml)
- [dq-api/fastapi/contracts/current/openapi-fastapi-v1.json](../../dq-api/fastapi/contracts/current/openapi-fastapi-v1.json)
- [docs/features/DQ-10_NATURAL_LANGUAGE_RULE_DRAFTING_PREVIEW.md](../../docs/features/DQ-10_NATURAL_LANGUAGE_RULE_DRAFTING_PREVIEW.md)
- [docs/features/DQ_FEATURES.md](../../docs/features/DQ_FEATURES.md)
- [docs/features/README.md](../../docs/features/README.md)
- [docs/features/FEATURE_ROADMAP_OVERVIEW.md](../../docs/features/FEATURE_ROADMAP_OVERVIEW.md)
- [docs/technical/DQ_10_NATURAL_LANGUAGE_RULE_DRAFTING_ROLLOUT_AND_OPERATOR_NOTES.md](../../docs/technical/DQ_10_NATURAL_LANGUAGE_RULE_DRAFTING_ROLLOUT_AND_OPERATOR_NOTES.md)
- [docs/implementation-details/DQ_10_NATURAL_LANGUAGE_RULE_DRAFTING_IMPLEMENTATION_DETAILS.md](../../docs/implementation-details/DQ_10_NATURAL_LANGUAGE_RULE_DRAFTING_IMPLEMENTATION_DETAILS.md)

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
- The release note copy under `dq-ui/public/release-notes/` should stay in sync with the root `RELEASE_NOTES_USER.md`.