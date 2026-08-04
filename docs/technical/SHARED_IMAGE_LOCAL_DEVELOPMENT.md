# Shared Image Local Development Overrides

This guide documents the only supported local-development override pattern for shared and platform images.

## Default rule

Use the published shared image tags by default:

- `docker-registry.dev.jac.dot/jacbeekers/platform-ingestion-runner:<version>`
- `docker-registry.dev.jac.dot/jacbeekers/platform-ingestion-runner:latest`

Do **not** change the shared registry or namespace in normal workstation work. The canonical image should come from the shared platform publish pipeline.

## When an override is justified

Use a local override only when you are actively debugging the shared ingestion runner image itself or a repo-specific integration problem that depends on a custom runner build.

Typical cases:

- validating a fresh `platform-foundation` image build before publishing
- testing a `dq-made-easy` change against a local shared-image tag
- reproducing a local startup issue that only appears with a specific runner revision

## Recommended local flow

1. Build a local shared image tag in `platform-foundation`:

   ```bash
   cd ../platform-foundation
   scripts/build_shared_images.sh --image ingestion-runner --version dev-local
   ```

2. Point your `dq-made-easy` local env file at that tag:

   ```bash
   PLATFORM_SHARED_INGESTION_RUNNER_TAG=dev-local
   ```

3. Pull or run the shared image through the repo tooling:

   ```bash
   ./scripts/pull_images.sh --scope platform
   ./scripts/pull_images.sh --image platform-ingestion-runner:dev-local
   ./scripts/stack_ctl.sh pull --scope platform --image platform-ingestion-runner:dev-local
   ```

### Registry overrides

The `PLATFORM_REGISTRY` env var controls which registry is used. Override it
in your environment file to switch profiles:

```bash
# Default (Nexus) — local development
PLATFORM_REGISTRY="docker-registry.dev.jac.dot/"

# Corporate mirror — pull-only
PLATFORM_REGISTRY="registry.corp.internal/"

# Docker Hub — external distribution
PLATFORM_REGISTRY="docker.io/"
```

See [Platform Service Image Contract](./PLATFORM_SERVICE_IMAGE_CONTRACT.md) for details.

## What not to override

Avoid changing these values unless you are deliberately testing against a private or temporary registry:

- `PLATFORM_REGISTRY`
- `PLATFORM_NAMESPACE`

For most debugging scenarios, only the shared image tag should change.

## Cleanup rule

Remove the override from `.env.dev.local` when the debugging session is done so the workstation returns to the published shared-image contract.

## Related documents

- [Platform Service Image Contract](./PLATFORM_SERVICE_IMAGE_CONTRACT.md)
