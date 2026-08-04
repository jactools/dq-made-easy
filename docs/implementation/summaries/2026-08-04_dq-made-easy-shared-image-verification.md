# Implementation Summary: dq-made-easy shared image verification

**Date**: 2026-08-04  
**Status**: Complete

## Objective and Scope

This change closes **SHARED-I-W5-03** by verifying that `dq-made-easy` can resolve, pull, and run against the shared ingestion runner image contract without relying on public Docker Hub access.

Because public Docker Hub access is not available in this environment, the verification used the locally available Nexus mirror reference for the same shared image artifact:

- `nexus-docker.rabobank.nl/jacbeekers/platform-ingestion-runner:latest`

The scope of the change was:

- verify the shared ingestion runner image runs as a container
- verify `scripts/pull_images.sh` resolves the shared image through the repo contract
- verify `scripts/stack_ctl.sh pull` delegates to the shared-image pull path correctly
- keep the verification aligned with the published shared-image naming contract, without using docker.io directly

## Results

| Metric | Before | After |
|---|---|---|
| Shared image runtime proof | No local run proof in this follow-up | `docker run --rm nexus-docker.rabobank.nl/jacbeekers/platform-ingestion-runner:latest --help` succeeds |
| Repo pull tooling proof | Shared-image path not rechecked after cleanup | `scripts/pull_images.sh --scope shared --image platform-ingestion-runner:latest` succeeds against the local Nexus mirror |
| Stack operator proof | Shared-image operator flow only dry-run tested | `scripts/stack_ctl.sh pull --env-file <temp-env> --scope shared --image platform-ingestion-runner:latest` succeeds |
| Workstream 5 task W5-03 | Open | Complete |

## New modules/files created

- `docs/implementation/summaries/2026-08-04_dq-made-easy-shared-image-verification.md`

## Updated files

- `docs/implementation-details/SHARED_INGESTION_AND_SSO_PLATFORM_IMPLEMENTATION_PLAN.md`
- `docs/implementation/summaries/README.md`
- `docs/implementation/summaries/2026-08-04_dq-made-easy-shared-image-compatibility-cleanup.md`

## Validation

- `docker run --rm nexus-docker.rabobank.nl/jacbeekers/platform-ingestion-runner:latest --help`
- `TLS_INTERNAL_CA_BUNDLE=tmp/certs/internal-ca-bundle.pem bash scripts/pull_images.sh --env-file <temp-env> --scope shared --image platform-ingestion-runner:latest`
- `TLS_INTERNAL_CA_BUNDLE=tmp/certs/internal-ca-bundle.pem bash scripts/stack_ctl.sh pull --env-file <temp-env> --scope shared --image platform-ingestion-runner:latest`

## Known Issues or Remaining Work

- Public Docker Hub is not used for this verification path; the test relies on the locally available Nexus mirror tag for the same shared image artifact.
- Workstream 6 cleanup and evidence capture remain open.

## Next Steps

1. Continue with Workstream 6 cleanup and evidence capture.
2. Keep the shared-image contract aligned with the published registry namespace and tag policy.
3. Use the same local-mirror verification pattern when future shared-image additions need a non-public registry proof.
