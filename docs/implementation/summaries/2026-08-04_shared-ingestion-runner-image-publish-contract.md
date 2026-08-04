# Implementation Summary: Shared ingestion runner image publish contract

**Date**: 2026-08-04  
**Status**: Complete

## Objective and Scope

This change completes **SHARED-I-W4-02** by defining the shared image registry destination and versioning contract for the first shared platform image.

The scope of the change was:

- publish the shared ingestion runner image to a stable registry namespace
- tag the image with both an immutable version tag and a moving `latest` alias
- document the registry path and version-pinning rules
- update the shared image build script to use the publish contract by default
- add unit coverage for the publish contract

## Results

| Metric | Before | After |
|---|---|---|
| Shared image destination | Ad hoc / not documented | `docker.io/jacbeekers/platform-ingestion-runner` |
| Version tags | Single version tag only | Version tag + `latest` alias |
| Publish contract documentation | Missing | Documented in `platform-foundation/docs/infra/INGESTION_RUNNER_IMAGE.md` |
| Shared image build defaults | No stable publish defaults | Registry/namespace defaults now resolve to Docker Hub and `jacbeekers` |
| Workstream 4 task W4-02 | Open | Complete |

## New modules/files created

- `docs/implementation/summaries/2026-08-04_shared-ingestion-runner-image-publish-contract.md`

## Updated files

- `../platform-foundation/scripts/build_shared_images.sh`
- `../platform-foundation/docs/infra/INGESTION_RUNNER_IMAGE.md`
- `../platform-foundation/.env.dev.example`
- `../platform-foundation/tests/test_shared_images.py`
- `../platform-foundation/README.md`
- `../platform-foundation/docs/README.md`
- `../platform-foundation/tests/test_shared_images.py`
- `docs/implementation-details/SHARED_INGESTION_AND_SSO_PLATFORM_IMPLEMENTATION_PLAN.md`
- `docs/implementation/summaries/README.md`

## Known Issues or Remaining Work

- The publish contract is now defined, but downstream repositories still need to be switched to the shared image tags in later workstream steps.
- Keycloak and trust-bundle image centralization remains open.
- The shared image registry path may be overridden for other registries, but the documented default is Docker Hub under the `jacbeekers` namespace.

## Next Steps

1. Replace duplicate image build definitions in downstream repositories with the shared tags.
2. Add the remaining shared image types to the same registry contract when they are ready.
3. Document consumer upgrade/pinning guidance in the downstream repo workflows.
4. Continue with the next Workstream 4 and Workstream 5 tasks.
