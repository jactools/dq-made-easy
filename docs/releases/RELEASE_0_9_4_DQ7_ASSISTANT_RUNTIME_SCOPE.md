# Release v0.9.4 — DQ7 Assistant Runtime Scope

**Release date**: 2026-05-04
**UI version**: `0.9.4`
**API version**: `0.9.4`

## Summary

This patch release aligns the DQ7 read-only assistant with the actual implemented runtime surface. The assistant now reports only implemented engine support, currently GX, while future SodaCL, SQL, PySpark, and custom-worker targets remain represented only as roadmap or registry planning surfaces.

## Included in this release

- UI package metadata is aligned to `0.9.4`
- API package metadata is aligned to `0.9.4`
- Version markers in `VERSION_MANIFEST.json` are aligned for the release and the changed tracked components: `DataCatalog`, `Templates`, `Documentation`, and `Testautomation`
- The DQ7 assistant endpoint filters capability rows to implemented runtime targets before returning guidance
- Assistant compiler hints and notes now describe the current GX lowerer and fail-fast behavior
- Backend and UI tests assert that planned engines are not shown as available assistant support

## User-visible impact

- Rule authors no longer see SodaCL, SQL, PySpark, or custom-worker rows in the read-only assistant until those runtimes are actually implemented
- Assistant guidance is clearer about what can execute today: GX-supported subsets pass through the GX lowerer, and unsupported shapes fail fast
- The rule wizard continues to show assistant output as read-only guidance; backend validation and persistence remain the contract gate

## Key implementation files

- [VERSION_MANIFEST.json](../../VERSION_MANIFEST.json)
- [dq-ui/package.json](../../dq-ui/package.json)
- [dq-api/package.json](../../dq-api/package.json)
- [dq-api/fastapi/app/api/v1/endpoints/suggestions.py](../../dq-api/fastapi/app/api/v1/endpoints/suggestions.py)
- [dq-api/fastapi/tests/api/test_suggestions_endpoints.py](../../dq-api/fastapi/tests/api/test_suggestions_endpoints.py)
- [dq-ui/src/components/Templates.modal.test.tsx](../../dq-ui/src/components/Templates.modal.test.tsx)
- [docs/features/DQ-7_RULE_DSL_CONTRACT.md](../features/DQ-7_RULE_DSL_CONTRACT.md)
- [docs/implementation-details/DQ_7_ENGINE_INDEPENDENT_DSL_IMPLEMENTATION_PLAN.md](../implementation-details/DQ_7_ENGINE_INDEPENDENT_DSL_IMPLEMENTATION_PLAN.md)

## Documentation updated

- [RELEASE_NOTES_USER.md](../../RELEASE_NOTES_USER.md)
- [dq-ui/public/release-notes/RELEASE_NOTES_USER.md](../../dq-ui/public/release-notes/RELEASE_NOTES_USER.md)
- [README.md](../../README.md)
- [docs/releases/README.md](./README.md)
- [docs/features/DQ-7_RULE_DSL_CONTRACT.md](../features/DQ-7_RULE_DSL_CONTRACT.md)
- [docs/implementation-details/DQ_7_ENGINE_INDEPENDENT_DSL_IMPLEMENTATION_PLAN.md](../implementation-details/DQ_7_ENGINE_INDEPENDENT_DSL_IMPLEMENTATION_PLAN.md)
- [docs/user-manuals/engine-capability-guidance.md](../user-manuals/engine-capability-guidance.md)
- [docs/user-manuals/ui-capability-matrix.md](../user-manuals/ui-capability-matrix.md)

## Notes

- Repo-managed Docker image tags stay on the `0.9-<hash>` release line for this patch release because image tags derive from the `major.minor` base in `VERSION_MANIFEST.json`.
- The release note copy under `dq-ui/public/release-notes/` should stay in sync with the root `RELEASE_NOTES_USER.md`.