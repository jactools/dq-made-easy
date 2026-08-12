# Shared Image Version Pinning and Upgrades

This guide documents how consumers should pin and upgrade the shared platform
image tags for the ingestion runner and platform services.

## Scope

This guidance applies to all shared and platform images published to
`docker-registry.dev.jac.dot`:

- `docker-registry.dev.jac.dot/jacbeekers/platform-ingestion-runner`
- `docker-registry.dev.jac.dot/jacbeekers/platform-kong`
- `docker-registry.dev.jac.dot/jacbeekers/platform-keycloak`
- `docker-registry.dev.jac.dot/jacbeekers/platform-airflow`
- `docker-registry.dev.jac.dot/jacbeekers/platform-llm`
- `docker-registry.dev.jac.dot/jacbeekers/platform-trino`
- `docker-registry.dev.jac.dot/jacbeekers/platform-observability-*`

The pinning rules are the same for all images: pin a published version for
repeatability, and only use a moving alias for ad hoc local testing.

## Pinning rule

Consumers should pin the shared image tag in their environment file or
runtime override file:

- `PLATFORM_SHARED_INGESTION_RUNNER_TAG=<published-version>`
- `PLATFORM_KONG_TAG=<published-version>`
- `PLATFORM_KEYCLOAK_TAG=<published-version>`
- etc. (see [Platform Service Image Contract](./PLATFORM_SERVICE_IMAGE_CONTRACT.md))

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
2. Confirm the versioned tag exists in `docker-registry.dev.jac.dot`.
3. Update the consumer env file to the new tag.
4. Pull the platform image scope or the specific tag.
5. Start the stack and run the relevant validation flow.

Example:

```bash
cd ../platform-foundation
scripts/build_shared_images.sh --image ingestion-runner --version 0.1.1 --push

cd ../dq-made-easy
# update PLATFORM_SHARED_INGESTION_RUNNER_TAG=0.1.1 in the selected env file
./scripts/pull_images.sh --scope platform --image platform-ingestion-runner:0.1.1
./scripts/stack_ctl.sh pull --scope platform --image platform-ingestion-runner:0.1.1
```

## Rollback workflow

If the new tag regresses, revert the consumer env file to the previous known
good tag and repeat the pull/start cycle.

```bash
PLATFORM_SHARED_INGESTION_RUNNER_TAG=0.1.0
./scripts/pull_images.sh --scope platform --image platform-ingestion-runner:0.1.0
```

## Why pin tags instead of overriding the registry

Pinning the tag keeps the shared image source consistent while still allowing
consumer repos to move deliberately.

Do not change `PLATFORM_REGISTRY` or `PLATFORM_NAMESPACE` for
normal upgrades. Those values represent the shared publication contract.

## Relation to other guides

- [Platform Service Image Contract](./PLATFORM_SERVICE_IMAGE_CONTRACT.md)
- [Shared Image Local Development Overrides](./SHARED_IMAGE_LOCAL_DEVELOPMENT.md)
- [Deployment Guide](./DEPLOYMENT.md)
- [Automatic Docker Image Versioning](./AUTOMATIC_VERSIONING.md)
