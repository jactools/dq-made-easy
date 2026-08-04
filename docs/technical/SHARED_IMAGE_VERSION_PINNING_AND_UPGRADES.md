# Shared Image Version Pinning and Upgrades

This guide documents how consumers should pin and upgrade the shared platform
image tags for the ingestion runner.

## Scope

This guidance currently applies to the shared ingestion runner image:

- `docker.io/jacbeekers/platform-ingestion-runner`

Keycloak and trust-bundle image contracts may be added later, but the pinning
rules should stay the same: pin a published version for repeatability, and
only use a moving alias for ad hoc local testing.

## Pinning rule

Consumers should pin the shared image tag in their environment file or
runtime override file:

- `PLATFORM_SHARED_INGESTION_RUNNER_TAG=<published-version>`

Recommended sources of truth:

- `.env.prod.local` or an external production env file for deployed systems
- `.env.test.local` for repeatable test or smoke environments
- `.env.dev.local` when you want a stable local-debugging target

Avoid relying on `latest` for deployment or regression validation.

## Allowed tags

Use these tag patterns:

- immutable published version: `0.1.0`
- temporary local-debug tag: `dev-local`
- moving alias: `latest` for exploratory local use only

## Upgrade workflow

1. Publish the new shared image in `platform-foundation`.
2. Confirm the versioned tag exists in the registry.
3. Update the consumer env file to the new tag.
4. Pull the shared image scope or the specific tag.
5. Start the stack and run the relevant validation flow.

Example:

```bash
cd ../platform-foundation
scripts/build_shared_images.sh --image ingestion-runner --version 0.1.1 --push

cd ../dq-made-easy
# update PLATFORM_SHARED_INGESTION_RUNNER_TAG=0.1.1 in the selected env file
./scripts/pull_images.sh --scope shared --image platform-ingestion-runner:0.1.1
./scripts/stack_ctl.sh pull --scope shared --image platform-ingestion-runner:0.1.1
```

## Rollback workflow

If the new tag regresses, revert the consumer env file to the previous known
good tag and repeat the pull/start cycle.

```bash
PLATFORM_SHARED_INGESTION_RUNNER_TAG=0.1.0
./scripts/pull_images.sh --scope shared --image platform-ingestion-runner:0.1.0
```

## Why pin tags instead of overriding the registry

Pinning the tag keeps the shared image source consistent while still allowing
consumer repos to move deliberately.

Do not change `PLATFORM_SHARED_REGISTRY` or `PLATFORM_SHARED_NAMESPACE` for
normal upgrades. Those values represent the shared publication contract.

## Relation to other guides

- [Shared Image Local Development Overrides](./SHARED_IMAGE_LOCAL_DEVELOPMENT.md)
- [Deployment Guide](./DEPLOYMENT.md)
- [Automatic Docker Image Versioning](./AUTOMATIC_VERSIONING.md)
