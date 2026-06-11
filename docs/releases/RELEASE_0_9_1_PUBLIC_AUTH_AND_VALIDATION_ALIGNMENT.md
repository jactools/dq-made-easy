# Release v0.9.1 — Public Auth and Validation Alignment

**Release date**: 2026-05-01
**UI version**: `0.9.1`
**API version**: `0.9.1`

## Summary

This release aligns public authentication, seeded demo credentials, and validation entry points across the test stack. Public Keycloak login now renders and posts against the HTTPS public host, stage-specific rotated credentials are written into `tmp/`, and smoke or validation scripts now resolve the selected environment before loading auth inputs.

## Included in this release

- UI package metadata is aligned to `0.9.1`
- API package metadata is aligned to `0.9.1`
- Version markers in `VERSION_MANIFEST.json` are aligned for the release and the changed tracked components: `Authentication`, `Infrastructure`, `Testautomation`, and `Documentation`
- `docker-compose.yml` now passes explicit Keycloak hostname and proxy CLI flags so public login form rendering follows the public HTTPS host behind the edge proxy
- `dq-keycloak/docker-entrypoint.sh` now reconciles the live `dq-rules-ui` Keycloak client redirect URIs and web origins at startup and applies rotated seeded passwords fail-fast against the imported realm
- `dq-keycloak/scripts/generate_seed_artifacts.sh` now writes rotated seeded credentials and helper env files into `tmp/`, including environment-scoped variants such as `tmp/keycloak_seed_user_credentials.test.env`
- `scripts/load_seeded_user_credentials.sh` centralizes loading the selected root env file plus the matching generated seeded-credential file for `dev`, `test`, or `prod`
- `scripts/validate.sh` and the auth-related smoke and validation scripts now honor `--env` and `--env-file` while consuming the generated stage-specific credentials and OIDC helper files
- FastAPI auth endpoint handling now preserves public browser redirects while resolving token and userinfo calls against the canonical internal issuer URL

## User-visible impact

- Public browser SSO login on the test domain now succeeds without the earlier Keycloak `Invalid parameter: redirect_uri` error
- The Keycloak login page no longer renders an HTTP form action for the public hostname, so browsers stop flagging the page as a non-secure form submission
- Operators can inspect the current rotated demo-user credentials directly from `tmp/` without changing tracked CSV seed inputs
- Validation and smoke flows can target the intended stack environment directly instead of silently reusing the wrong root env file or stale generic credentials

## Key implementation files

- [VERSION_MANIFEST.json](../../VERSION_MANIFEST.json)
- [docker-compose.yml](../../docker-compose.yml)
- [dq-keycloak/docker-entrypoint.sh](../../dq-keycloak/docker-entrypoint.sh)
- [dq-keycloak/scripts/generate_seed_artifacts.sh](../../dq-keycloak/scripts/generate_seed_artifacts.sh)
- [scripts/load_seeded_user_credentials.sh](../../scripts/load_seeded_user_credentials.sh)
- [scripts/validate.sh](../../scripts/validate.sh)
- [scripts/validation/validate_user_login_end_to_end.sh](../../scripts/validation/validate_user_login_end_to_end.sh)
- [scripts/validation/smoke_test_auth_kong.sh](../../scripts/validation/smoke_test_auth_kong.sh)
- [scripts/validation/validate_support_request_by_mail.sh](../../scripts/validation/validate_support_request_by_mail.sh)
- [scripts/validation/smoke_adhoc_rule_execution.sh](../../scripts/validation/smoke_adhoc_rule_execution.sh)
- [scripts/validation/validate_rule_lifecycle_gx_supported.sh](../../scripts/validation/validate_rule_lifecycle_gx_supported.sh)
- [scripts/supporting/profiling_validation_common.sh](../../scripts/supporting/profiling_validation_common.sh)
- [dq-api/fastapi/app/api/v1/endpoints/auth.py](../../dq-api/fastapi/app/api/v1/endpoints/auth.py)
- [dq-ui/src/components/AuthModal.tsx](../../dq-ui/src/components/AuthModal.tsx)
- [dq-ui/src/contexts/SettingsContext.tsx](../../dq-ui/src/contexts/SettingsContext.tsx)

## Documentation updated

- [RELEASE_NOTES_USER.md](../../RELEASE_NOTES_USER.md)
- [dq-ui/public/release-notes/RELEASE_NOTES_USER.md](../../dq-ui/public/release-notes/RELEASE_NOTES_USER.md)
- [TECHNICAL.md](../../TECHNICAL.md)
- [DEPLOYMENT.md](../../DEPLOYMENT.md)
- [QUICKSTART_DEPLOY.md](../../QUICKSTART_DEPLOY.md)
- [AUTOMATIC_VERSIONING.md](../../AUTOMATIC_VERSIONING.md)
- [docs/technical/DEPLOYMENT.md](../technical/DEPLOYMENT.md)
- [docs/technical/QUICKSTART_DEPLOY.md](../technical/QUICKSTART_DEPLOY.md)
- [docs/technical/AUTOMATIC_VERSIONING.md](../technical/AUTOMATIC_VERSIONING.md)

## Notes

- Repo-managed Docker image tags stay on the `0.9-<hash>` release line for this patch release because image tags derive from the `major.minor` base in `VERSION_MANIFEST.json`.
- When publishing the release, refresh the build-derived app tags in `VERSION_MANIFEST.json` with the normal version-determination workflow so the manifest captures the new API, frontend, and Keycloak image hashes.