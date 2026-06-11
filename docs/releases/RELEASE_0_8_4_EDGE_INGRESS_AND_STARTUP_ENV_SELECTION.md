# Release v0.8.4 — Edge Ingress and Startup Environment Selection

**Release date**: 2026-04-26
**UI version**: `0.8.4`
**API version**: `0.8.4`

## Summary

This patch release packages the ingress and startup-flow work into a coherent deployment story.

The main objective is operational clarity: the repo now distinguishes local `*.jac.dot` development from the public `jacloud.nl` single-host deployment model, and the standard startup wrapper can explicitly choose which env file drives the full startup chain.

## Included in this release

- UI package metadata is aligned to `0.8.4`
- API package metadata is aligned to `0.8.4`
- Version markers in `VERSION_MANIFEST.json` are aligned to `0.8.4` for the release and the changed tracked components: `Infrastructure`, `Authentication`, `Documentation`, `Telemetry`, and `Testautomation`
- `docker-compose.yml` now supports the dedicated `edge` service, env-driven public host bindings, and path-prefix-ready Keycloak, OpenMetadata, and Grafana wiring
- `.env.example` and `.env.deployment.example` now document distinct local and public topologies, while `.env.deployment.local` provides the ignored machine-local public runtime copy consumed by the startup wrappers
- `common_startup.sh`, `start-containers.sh`, `start_stack.sh`, `seed_stack.sh`, and `dq-ui/scripts/start_local.sh` now honor the selected env file through startup, seeding, and local UI launch flows
- Local wildcard cert generation and focused ingress validation scripts were added so the edge model can be checked repeatably
- Deployment and feature docs were updated to explain the new env-selection workflow and the single-edge public routing model

## User-visible impact

- Local development can keep using the familiar `*.jac.dot` hostname model
- Public deployments can now standardize on `https://www.jacloud.nl` with path-prefixed service access under `/iam`, `/metadata`, `/observability`, `/support`, and `/ops/kong`
- Operators can choose the intended env file directly from the common startup wrapper instead of manually reshaping `.env` before each run

## Key implementation files

- [docker-compose.yml](../../docker-compose.yml)
- [.env.example](../../.env.example)
- [.env.deployment.example](../../.env.deployment.example)
- `.env.deployment.local` (ignored machine-local runtime copy created from the template)
- [scripts/common_startup.sh](../../scripts/common_startup.sh)
- [scripts/start-containers.sh](../../scripts/start-containers.sh)
- [scripts/start_stack.sh](../../scripts/start_stack.sh)
- [scripts/seed_stack.sh](../../scripts/seed_stack.sh)
- [dq-ui/scripts/start_local.sh](../../dq-ui/scripts/start_local.sh)
- [dq-edge/docker-entrypoint.d/40-render-edge-config.sh](../../dq-edge/docker-entrypoint.d/40-render-edge-config.sh)
- [scripts/validate_edge_local_ingress.sh](../../scripts/validate_edge_local_ingress.sh)
- [scripts/validate_edge_public_ingress.sh](../../scripts/validate_edge_public_ingress.sh)

## Documentation updated

- [README.md](../../README.md)
- [RELEASE_NOTES_USER.md](../../RELEASE_NOTES_USER.md)
- [dq-ui/public/release-notes/RELEASE_NOTES_USER.md](../../dq-ui/public/release-notes/RELEASE_NOTES_USER.md)
- [TECHNICAL.md](../../TECHNICAL.md)
- [docs/releases/README.md](./README.md)
- [DEPLOYMENT.md](../../DEPLOYMENT.md)
- [QUICKSTART_DEPLOY.md](../../QUICKSTART_DEPLOY.md)
- [docs/technical/DEPLOYMENT.md](../../docs/technical/DEPLOYMENT.md)
- [docs/technical/QUICKSTART_DEPLOY.md](../../docs/technical/QUICKSTART_DEPLOY.md)
- [FEATURES.md](../../FEATURES.md)
- [docs/features/FEATURES.md](../../docs/features/FEATURES.md)
- [docs/implementation-details/KONG_SINGLE_HTTPS_INGRESS_IMPLEMENTATION_PLAN.md](../../docs/implementation-details/KONG_SINGLE_HTTPS_INGRESS_IMPLEMENTATION_PLAN.md)
- [docs/implementation-details/KONG_SINGLE_HTTPS_INGRESS_FILE_CHECKLIST.md](../../docs/implementation-details/KONG_SINGLE_HTTPS_INGRESS_FILE_CHECKLIST.md)

## Notes

- This is primarily an infrastructure, startup-workflow, and documentation release.
- The public ingress layout is validated through renderer/config checks; a full live public deployment smoke with real certificates and DNS is still a separate operational step.