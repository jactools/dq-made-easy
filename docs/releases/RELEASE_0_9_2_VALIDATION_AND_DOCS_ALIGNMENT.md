# Release v0.9.2 — Validation and Docs Alignment

**Release date**: 2026-05-01
**UI version**: `0.9.2`
**API version**: `0.9.2`

## Summary

This release aligns the current Test/public validation path with the live deployment configuration and refreshes the release-line docs to match the new `0.9.2` baseline.

## Included in this release

- UI package metadata is aligned to `0.9.2`
- API package metadata is aligned to `0.9.2`
- Version markers in `VERSION_MANIFEST.json` are aligned for the release and the changed tracked components: `Authentication`, `Infrastructure`, `Testautomation`, and `Documentation`
- Browser-backed Grafana smoke checks now authenticate through the existing Keycloak login flow instead of assuming basic auth against OAuth-backed datasource APIs
- OpenMetadata readiness and trace validation now target the mounted `/metadata/api/v1/system/version` endpoint
- The UI trace-propagation validator now uses the host-published Kong Admin API, and the edge ingress validator now matches the actual selected Test/public render shape

## User-visible impact

- `./scripts/validate.sh --env test all` now passes against the current Test deployment model
- Public login and observability smoke checks no longer rely on stale local-only assumptions
- Release and deployment docs now point at the `0.9.2` release line

## Key implementation files

- [VERSION_MANIFEST.json](../../VERSION_MANIFEST.json)
- [dq-ui/package.json](../../dq-ui/package.json)
- [dq-api/package.json](../../dq-api/package.json)
- [scripts/validation/validate_dq_api_grafana_otel_smoke.sh](../../scripts/validation/validate_dq_api_grafana_otel_smoke.sh)
- [scripts/validation/validate_openmetadata_otel_smoke.sh](../../scripts/validation/validate_openmetadata_otel_smoke.sh)
- [scripts/validation/validate_ui_api_trace_propagation.sh](../../scripts/validation/validate_ui_api_trace_propagation.sh)
- [scripts/validation/validate_edge_local_ingress.sh](../../scripts/validation/validate_edge_local_ingress.sh)
- [scripts/supporting/grafana_oauth_session.sh](../../scripts/supporting/grafana_oauth_session.sh)
- [README.md](../../README.md)
- [RELEASE_NOTES_USER.md](../../RELEASE_NOTES_USER.md)
- [TECHNICAL.md](../../TECHNICAL.md)
- [DEPLOYMENT.md](../../DEPLOYMENT.md)
- [QUICKSTART_DEPLOY.md](../../QUICKSTART_DEPLOY.md)
- [AUTOMATIC_VERSIONING.md](../../AUTOMATIC_VERSIONING.md)

## Documentation updated

- [RELEASE_NOTES_USER.md](../../RELEASE_NOTES_USER.md)
- [dq-ui/public/release-notes/RELEASE_NOTES_USER.md](../../dq-ui/public/release-notes/RELEASE_NOTES_USER.md)
- [TECHNICAL.md](../../TECHNICAL.md)
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
