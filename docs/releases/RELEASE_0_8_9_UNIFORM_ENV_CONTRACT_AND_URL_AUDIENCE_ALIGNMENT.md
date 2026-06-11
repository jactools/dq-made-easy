# Release v0.8.9 — Uniform Environment Contract and URL Audience Alignment

**Release date**: 2026-04-28
**UI version**: `0.8.9`
**API version**: `0.8.7`

## Summary

This release makes the URL and endpoint environment contract explicit across the repo. Routable services now distinguish Docker-network, host-local, and browser-facing access with canonical `INTERNAL`, `LOCAL`, and `PUBLIC` names. The frontend runtime path no longer depends on the older `DQ_UI_API_URL` shim, and current-facing docs now describe the canonical contract directly.

## Included in this release

- UI package metadata is aligned to `0.8.9`
- API package metadata is aligned to `0.8.7`
- Version markers in `VERSION_MANIFEST.json` are aligned for the release and the changed tracked components: `Infrastructure`, `Authentication`, and `Documentation`
- Repo env templates now define audience-scoped URL variables such as `KONG_INTERNAL_URL`, `KONG_LOCAL_URL`, `KONG_PUBLIC_URL`, `KEYCLOAK_INTERNAL_URL`, `KEYCLOAK_LOCAL_URL`, `KEYCLOAK_PUBLIC_URL`, `SSO_INTERNAL_ISSUER_URL`, and `SSO_PUBLIC_ISSUER_URL`
- `docker-compose.yml` now consumes canonical env names at the repo boundary and passes canonical names directly where the containerized code supports them
- Host-side startup, seeding, smoke, and validation scripts now use explicit local URLs for host execution instead of overloading public browser-facing variables
- Frontend runtime config now reads `KONG_PUBLIC_URL` for deployed browser-facing builds, while local Vite/dev flows resolve against `KONG_LOCAL_URL`
- Historical implementation notes that still mention superseded names now carry an explicit superseded note instead of presenting them as current guidance

## User-visible impact

- Public deployment configuration is easier to reason about because public browser URLs are no longer reused for host-local or container-internal traffic
- Local startup and validation scripts now target the correct host-local URLs directly, which reduces ambiguity during operator workflows and troubleshooting
- Frontend container runtime configuration is now aligned with the rest of the stack: `KONG_PUBLIC_URL` is the browser-facing runtime API base, and `KONG_LOCAL_URL` is the host-local counterpart
- Current-facing docs and release notes now point to the canonical env contract instead of the older transitional variable names

## Key implementation files

- [VERSION_MANIFEST.json](../../VERSION_MANIFEST.json)
- [docker-compose.yml](../../docker-compose.yml)
- [scripts/supporting/setup_env.sh](../../scripts/supporting/setup_env.sh)
- [scripts/start-containers.sh](../../scripts/start-containers.sh)
- [scripts/start_stack.sh](../../scripts/start_stack.sh)
- [scripts/seed_all.sh](../../scripts/seed_all.sh)
- [dq-kong/scripts/bootstrap_kong.sh](../../dq-kong/scripts/bootstrap_kong.sh)
- [dq-ui/scripts/start_local.sh](../../dq-ui/scripts/start_local.sh)
- [dq-ui/scripts/docker-entrypoint-runtime-config.sh](../../dq-ui/scripts/docker-entrypoint-runtime-config.sh)
- [dq-ui/vite.config.ts](../../dq-ui/vite.config.ts)
- [dq-api/fastapi/app/api/v1/endpoints/auth.py](../../dq-api/fastapi/app/api/v1/endpoints/auth.py)

## Documentation updated

- [README.md](../../README.md)
- [RELEASE_NOTES_USER.md](../../RELEASE_NOTES_USER.md)
- [dq-ui/public/release-notes/RELEASE_NOTES_USER.md](../../dq-ui/public/release-notes/RELEASE_NOTES_USER.md)
- [TECHNICAL.md](../../TECHNICAL.md)
- [docs/technical/DEPLOYMENT.md](../../docs/technical/DEPLOYMENT.md)
- [docs/technical/QUICKSTART_DEPLOY.md](../../docs/technical/QUICKSTART_DEPLOY.md)
- [docs/releases/README.md](./README.md)

## Notes

- The canonical split is: `*_INTERNAL_URL` for container-to-container traffic, `*_LOCAL_URL` for host-machine traffic, and `*_PUBLIC_URL` for browser-facing or internet-facing traffic.
- Remaining mentions of `DQ_UI_API_URL` exist only inside explicitly marked historical implementation and completion notes.