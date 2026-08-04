# Platform Service Image Contract

This document defines the shared image contract for all platform services.
Both `dq-made-easy` and `metadata-as-a-service` consume these images.

---

## 1. Registry

Platform images support three registry profiles. All profiles share the same image
names and tags — only the registry URL changes.

| Profile | Registry URL | Push | Pull |
|---|---|---|---|
| Default (Nexus) | `docker-registry.dev.jac.dot` | ✅ | ✅ |
| Corporate | `<corporate-registry>` | ❌ | ✅ |
| Public (Docker Hub) | `docker.io` | ✅ | ✅ |

### Default (Nexus) — primary publish target

All platform images are built and published to `docker-registry.dev.jac.dot`
(Nexus Docker registry) in `platform-foundation`. This is the canonical source
of truth for all platform images.

```bash
PLATFORM_REGISTRY="docker-registry.dev.jac.dot/"
PLATFORM_NAMESPACE="jacbeekers/"
```

### Corporate — pull-only mirror

Inside a corporate network, the Nexus registry may not be directly reachable or
may have restrictive network policies. A corporate mirror registry can be
configured as a pull-only alternative.

```bash
PLATFORM_REGISTRY="<corporate-registry>/"
PLATFORM_NAMESPACE="jacbeekers/"
```

This profile supports **pull only** — images are never pushed to the corporate
registry. All pushes go to the Nexus registry.

### Public (Docker Hub) — external publish

When publishing to Docker Hub (e.g. for external consumption or as a fallback
registry), override the registry to `docker.io`:

```bash
PLATFORM_REGISTRY="docker.io/"
PLATFORM_NAMESPACE="jacbeekers/"
```

This profile supports both push and pull. Use this for external distribution.

### How consumers choose

Consumers set `PLATFORM_REGISTRY` in their environment file. The namespace and
image names stay identical across all profiles:

```bash
# Default (Nexus) — used in .env.dev.local
PLATFORM_REGISTRY="docker-registry.dev.jac.dot/"

# Corporate mirror — used in .env.corporate.local
PLATFORM_REGISTRY="registry.corp.internal/"

# Docker Hub — used in .env.prod.local or for external publishing
PLATFORM_REGISTRY="docker.io/"
```

The same `--scope platform` pull command works with any profile:

---

## 2. Image Naming

Platform services follow the `platform-<service>` naming convention:

| Service | Image name | Namespace | Notes |
|---|---|---|---|
| Kong | `platform-kong` | `jacbeekers/` | Gateway |
| Keycloak | `platform-keycloak` | `jacbeekers/` | SSO |
| Kafka | `platform-kafka` | `jacbeekers/` | Messaging |
| LLM | `platform-llm` | `jacbeekers/` | AI inference (consumer app code as build context) |
| Airflow | `platform-airflow` | `jacbeekers/` | DAGs deployed via API |
| Trino | `platform-trino` | `jacbeekers/` | Catalog configs mounted by consumer |
| Loki | `platform-observability-loki` | `jacbeekers/` |
| Prometheus | `platform-observability-prometheus` | `jacbeekers/` |
| Grafana | `platform-observability-grafana` | `jacbeekers/` |
| Tempo | `platform-observability-tempo` | `jacbeekers/` |
| Container Metrics | `platform-observability-container-metrics` | `jacbeekers/` |
| OTel Collector | `platform-observability-otel-collector` | `jacbeekers/` |

Existing shared images (non-platform):

| Service | Image name | Namespace |
|---|---|---|
| Ingestion Runner | `platform-ingestion-runner` | `jacbeekers/` |

---

## 3. Tagging

All platform images follow the same tagging scheme as existing repo images:

| Tag type | Example | Usage |
|---|---|---|
| Published version | `0.1.0` | Stable deployment target |
| Local debug | `dev-local` | Active debugging session only |
| Moving alias | `latest` | Exploratory local use only |

Immutable version tags are the canonical deployment reference. `latest` is never used in production.

---

## 4. Version Pinning

Each platform service is pinned through a dedicated environment variable in the consumer's `.env.*.local` file:

| Service | Env var |
|---|---|
| Kong | `PLATFORM_KONG_TAG` |
| Keycloak | `PLATFORM_KEYCLOAK_TAG` |
| Kafka | `PLATFORM_KAFKA_TAG` |
| Airflow | `PLATFORM_AIRFLOW_TAG` |
| LLM | `PLATFORM_LLM_TAG` |
| Trino | `PLATFORM_TRINO_TAG` |
| Loki | `PLATFORM_OBS_LOKI_TAG` |
| Prometheus | `PLATFORM_OBS_PROMETHEUS_TAG` |
| Grafana | `PLATFORM_OBS_GRAFANA_TAG` |
| Tempo | `PLATFORM_OBS_TEMPO_TAG` |
| Container Metrics | `PLATFORM_OBS_CONTAINER_METRICS_TAG` |
| OTel Collector | `PLATFORM_OBS_OTEL_COLLECTOR_TAG` |
| Ingestion Runner | `PLATFORM_SHARED_INGESTION_RUNNER_TAG` |

Registry and namespace are shared across all platform images:

```bash
PLATFORM_REGISTRY="docker-registry.dev.jac.dot/"
PLATFORM_NAMESPACE="jacbeekers/"
```

---

## 5. Full Image Reference

A full image reference is resolved as:

```
<PLATFORM_REGISTRY><PLATFORM_NAMESPACE><IMAGE_NAME>:<TAG>
```

Example:
```
docker-registry.dev.jac.dot/jacbeekers/platform-keycloak:0.1.0
```

---

## 6. Upgrade Workflow

1. Publish the new shared image in `platform-foundation`
2. Confirm the versioned tag exists in `docker-registry.dev.jac.dot`
3. Update the consumer env file to the new tag
4. Pull the platform image scope or the specific tag
5. Start the stack and run the relevant validation flow

Example:
```bash
cd ../platform-foundation
scripts/build_shared_images.sh --image keycloak --version 0.1.1 --push

cd ../dq-made-easy
# update PLATFORM_KEYCLOAK_TAG=0.1.1 in the selected env file
./scripts/pull_images.sh --scope platform --image platform-keycloak:0.1.1
```

---

## 7. Rollback Workflow

Revert the consumer env file to the previous known good tag and repeat the pull/start cycle:

```bash
PLATFORM_KEYCLOAK_TAG=0.1.0
./scripts/pull_images.sh --scope platform --image platform-keycloak:0.1.0
```

---

## 8. Local Development Overrides

Only the tag should change during local debugging. Do not override `PLATFORM_REGISTRY` or `PLATFORM_NAMESPACE` unless deliberately testing against a private or temporary registry.

```bash
# Build local image in platform-foundation
cd ../platform-foundation
scripts/build_shared_images.sh --image keycloak --version dev-local

# Override tag in consumer env
PLATFORM_KEYCLOAK_TAG=dev-local
./scripts/pull_images.sh --scope platform --image platform-keycloak:dev-local
```

Remove the override from `.env.dev.local` when debugging is done.

## 9. Registry Profile Examples

### Default (Nexus) — local development

```bash
# .env.dev.local
PLATFORM_REGISTRY="docker-registry.dev.jac.dot/"
PLATFORM_NAMESPACE="jacbeekers/"
PLATFORM_KEYCLOAK_TAG="dev-local"
```

### Corporate — pull-only mirror

```bash
# .env.corporate.local
PLATFORM_REGISTRY="registry.corp.internal/"
PLATFORM_NAMESPACE="jacbeekers/"
PLATFORM_KEYCLOAK_TAG="0.1.0"
```

### Public (Docker Hub) — external distribution

```bash
# .env.prod.local
PLATFORM_REGISTRY="docker.io/"
PLATFORM_NAMESPACE="jacbeekers/"
PLATFORM_KEYCLOAK_TAG="0.1.0"
```

---

## 10. What Stays in dq-made-easy

Platform service images provide the runtime baseline. App-specific configuration stays in each consuming repository:

| Service | What stays in dq-made-easy |
|---|---|
| Kong | `bootstrap_kong.sh` — deploys routes, services, consumers, ACLs (Kong image/container managed by platform-foundation) |
| Keycloak | Realm JSON, roles, clients, users, redirects |
| Airflow | DAGs, SDK/operator wheels, FAB role mapping |
| LLM | DQ-specific agent logic, prompt templates, datasets |
| Trino | DQ catalog configuration, connector settings |
| Observability | DQ-specific dashboards, alert rules, retention policies |

---

## 11. Kong (managed by platform-foundation)

Kong image and container lifecycle are managed by `platform-foundation`.
The `platform-kong` image is built, versioned, and deployed from there.

**What stays in dq-made-easy:**

- `dq-kong/scripts/bootstrap_kong.sh` — deploys routes, services, consumers, and ACLs to Kong
- `dq-kong/scripts/build_and_push.sh` — Kong image push helper (legacy, retained)

**Bootstrap env vars** — the `bootstrap_kong.sh` script requires these variables
(which are supplied by the platform-foundation Kong service deployment):

| Variable | Required | Description |
|---|---|---|
| `DQ_API_INTERNAL_URL` | Yes | Internal URL of the DQ API service |
| `KEYCLOAK_INTERNAL_URL` | Yes | Internal URL of the Keycloak service |
| `KEYCLOAK_ADMIN_REALM` | Yes | Keycloak admin realm |
| `KEYCLOAK_SYSTEM_ADMIN_USERNAME` | Yes | Keycloak system admin username |
| `KEYCLOAK_SYSTEM_ADMIN_PASSWORD` | Yes | Keycloak system admin password |
| `KEYCLOAK_REALM` | Yes | Application realm name |
| `DQ_ENGINE_OIDC_CLIENT_ID` | Yes | OIDC client ID for the DQ engine |
| `UI_VITE_LOCAL_URL` | Yes | Internal URL of the Vite dev server |
| `UI_NGINX_LOCAL_URL` | Yes | Internal URL of the Nginx UI |
| `KONG_OTEL_ENDPOINT` | Yes | OTLP endpoint for tracing |
| `SSO_ENABLED` | No | Enable/disable JWT enforcement |
| `SSO_PUBLIC_ISSUER_URL` | No | Public OIDC issuer URL |
| `KONG_ADMIN_INTERNAL_URL` | No | Kong Admin API URL (default: `https://localhost:8444`) |
| `KONG_LUA_SSL_TRUSTED_CERTIFICATE` | No | CA bundle for Kong Lua SSL |
| `MAX_RETRIES` | No | Max boot retry count (default: `60`) |
| `CURL_CA_BUNDLE` | No | CA bundle for curl |
| `TRUST_PROXY_AUTH` | No | When `true`, enables JWT + ACL on routes |
| `JWT_JWKS_URL` | No | Override JWKS endpoint |
| `GRAFANA_OIDC_CLIENT_ID` | No | Grafana OIDC client ID (default: `grafana`) |

---

## 12. Related Documents

- [Shared Image Local Development Overrides](./SHARED_IMAGE_LOCAL_DEVELOPMENT.md)
- [Shared Image Version Pinning and Upgrades](./SHARED_IMAGE_VERSION_PINNING_AND_UPGRADES.md)
- [Shared Ingestion and SSO Platform Implementation Plan](../implementation-details/SHARED_INGESTION_AND_SSO_PLATFORM_IMPLEMENTATION_PLAN.md)
- [Shared Platform Exceptions Log](../implementation-details/SHARED_PLATFORM_EXCEPTIONS_LOG.md)
- [Shared Ingestion and SSO Platform Implementation Plan](../implementation-details/SHARED_INGESTION_AND_SSO_PLATFORM_IMPLEMENTATION_PLAN.md)
- [Shared Platform Exceptions Log](../implementation-details/SHARED_PLATFORM_EXCEPTIONS_LOG.md)
