# Shared Platform Image and Build Inventory

**Status**: Complete  
**Date**: 2026-08-03  
**Work item**: SHARED-I-W1-03

## Purpose

Inventory repository-managed DQ images, classify shared image candidates, and identify duplicated Dockerfile/build mechanics across DQ and MaaS.

## DQ Image Classification

| Image or family | Source | Classification | Decision |
|---|---|---|---|
| API | `dq-api/Dockerfile.fastapi` | DQ-owned | Keep DQ API code/runtime image in DQ; consume shared wheels. |
| Engine and worker modes | `dq-engine/Dockerfile.engine` | DQ-owned with shared ingestion-runtime potential | Keep GX/Spark execution image in DQ. Define a smaller shared ingestion runner instead of sharing the full engine. |
| Frontend | `dq-ui/Dockerfile.frontend` | DQ-owned | Do not move. |
| Primary DB and DB seed | `dq-db/Dockerfile.db`; `Dockerfile.dq-db.seed` | DQ-owned | Schema, migrations, and seed contents are DQ-specific. |
| Profiling worker | `dq-profiling/Dockerfile.profiling` | DQ-owned | Keep profiling runtime and queue behavior in DQ. |
| DQ base | `dq-base/Dockerfile.base` | DQ-owned for now | It is a Node/build-tools base tailored to current DQ images, not a neutral shared Python/ingestion base. |
| Keycloak runtime | `dq-keycloak/Dockerfile.keycloak`; entrypoint/trust scripts | **Shared candidate** | Move reusable Keycloak TLS, trust, health, and startup mechanics to a platform image. Consumer repos supply realms and clients. |
| Keycloak seed artifacts | `dq-keycloak/Dockerfile.keycloak.seed` | Split | Share generator runtime only; DQ realm, roles, clients, users, and redirects remain DQ inputs. |
| Trust-bundle utility | `docker/trust-bundle/Dockerfile` | **Shared candidate** | Platform ownership is appropriate because all consumers need the same trust artifact mechanics. |
| Airflow | `docker/airflow/Dockerfile.airflow` | Conditional shared candidate | Share a neutral Airflow/OIDC base only if MaaS needs it. DQ DAGs, SDK/operator wheels, and FAB role mapping remain DQ layers. |
| OpenMetadata DB/server/configure wrappers | `dq-metadata/Dockerfile.*` | Conditional shared vendor wrappers | Centralize only if both consumers deploy the same OpenMetadata/TLS/agent baseline. DQ mapping/configure logic stays DQ-owned. |
| Kong | `dq-kong/Dockerfile.kong` | Conditional platform candidate | Gateway binary/TLS plugin baseline may be shared; DQ routes/bootstrap remain DQ-owned. |
| Edge relay | `dq-edge/Dockerfile.edge` | Conditional platform candidate | Share only if both products adopt the same SNI/TCP routing model. Host and route config remain consumer-owned. |
| Kafka broker wrapper | `dq-kafka/Dockerfile.kafka` | Conditional infrastructure candidate | Not part of first ingestion/SSO extraction; keep until a second consumer exists. |
| Kafka consumer | `dq-kafka-consumer/Dockerfile.kafka-consumer` | DQ-owned | Violation/exception processing is DQ-specific. |
| Trino | `dq-trino/Dockerfile.trino` | DQ-owned for now | DQ execution/catalog configuration is product-specific. |
| LLM | `dq-llm/Dockerfile.llm` | DQ-owned | Do not move. |
| Zammad origin/seed | `docker/Dockerfile.zammad-origin`; `Dockerfile.zammad.seed` | DQ-owned support integration | Do not move. |
| Loki wrapper | `docker/loki/Dockerfile` | Conditional observability candidate | Outside the first ingestion/SSO slice; centralize only with a platform observability contract. |
| Container metrics | `observability/container-metrics/Dockerfile.container-metrics` | Conditional observability candidate | Same as Loki. |
| Local pypiserver | `platform-foundation/docker-compose.pypiserver.yml` | Platform-owned; complete | Canonical local wheel-sharing service already lives in `platform-foundation`. |
| Upstream-only Redis, Prometheus, Grafana, Tempo, search, object storage | Compose image references | Not repository image ownership | Keep version pins in consumer deployment manifests until a shared deployment contract is defined. |

## First Shared Image Set

The first defensible platform-owned image set is:

1. a small ingestion runner built from the extracted file/S3 ingestion package
2. Keycloak runtime baseline with TLS/trust/readiness but no product realm
3. trust-bundle generation/assembly utility
4. optionally a Keycloak realm-artifact generator runtime with consumer-owned inputs

Do not move the DQ engine image merely to obtain Spark support; it carries DQ execution behavior and dependencies that MaaS does not need.

## Duplicate Build Mechanics

### Within DQ

The following scripts repeat registry login, build arguments, buildx setup, tagging, cache, multi-arch, and push behavior:

- `dq-api/scripts/build_and_push.sh`
- `dq-base/scripts/build_and_push.sh`
- `dq-db/scripts/build_and_push.sh`
- `dq-engine/scripts/build_and_push.sh`
- `dq-keycloak/scripts/build_and_push.sh`
- `dq-kong/scripts/build_and_push.sh`
- `dq-profiling/scripts/build_and_push.sh`
- `dq-ui/scripts/build_and_push.sh`
- `scripts/build_and_push_all.sh`
- `scripts/build_and_push_one.sh`

These mechanics are platform tooling candidates; service-specific context, Dockerfile, build args, and tags should be declarative inputs.

### Across DQ and MaaS

MaaS `scripts/docker_images.sh` and its Python-service Dockerfiles repeat the same broad concerns found in DQ:

- wheel refresh before image builds
- NexusCloud `PIP_INDEX_URL` handling
- Python slim base selection
- requirements installation
- local wheel installation
- non-root runtime setup
- image tagging and publishing

A shared build helper can own these mechanics, but Dockerfiles should not be collapsed into one universal image. Each service should retain a thin product Dockerfile or manifest describing its runtime dependencies and entrypoint.

### Repeated Dockerfile Concerns

- Python package/wheel installation: DQ API/engine/profiling/metadata helpers and MaaS API/BFF/coordinator/orchestrator/control-plane/central-repo/scenario-catalog.
- Internal CA/trust bundle installation: DQ API, engine, Keycloak, Kong, OpenMetadata, Airflow, and support wrappers.
- TLS healthcheck conventions: repeated across DQ service Dockerfiles/Compose definitions.
- Build metadata/version labels: repeated in service build scripts.
- Multi-architecture buildx publication: repeated in DQ per-service and aggregate scripts.

## Ownership Boundary

`platform-foundation` should own:

- shared Docker build/publish tooling
- platform image naming/tagging contract
- neutral ingestion, auth runtime, and trust-bundle images
- local wheel index and shared package build support

Consumer repositories should own:

- application images and entrypoints
- product configuration and policy
- database schemas and seed images
- realm/client artifacts
- service-specific dependency manifests

## Next Image Work

Workstream 4 should begin with the ingestion runner image after the shared ingestion kernel exists. Keycloak and trust-bundle images follow. Generic build tooling can be extracted independently, but no DQ image should be deleted until both consumers use a published platform replacement.
