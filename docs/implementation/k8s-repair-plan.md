# K8s Manifest Repair Plan

**Status**: Complete  
**Date**: 2026-08-07  
**Completed**: 2026-08-08  
**Audience**: DQ repository maintainers

This plan tracks the remediation of critical and medium-severity issues in the `dq-made-easy` Kubernetes manifests. The audit was performed against known issues discovered during platform service debugging.

---

## Scope

All 14 DQ deployments across 3 overlays (`dev-api`, `dev-ui`, `dev-engine`):

| Overlay | Service | Image |
|---|---|---|
| `dev-api` | `dq-api` | `jacbeekers/dq-made-easy-api:latest` |
| `dev-api` | `dq-db` | `jacbeekers/dq-made-easy-db:latest` |
| `dev-api` | `dq-keycloak` | `jacbeekers/dq-made-easy-keycloak:latest` |
| `dev-api` | `dq-kong` | `jacbeekers/dq-made-easy-kong:latest` |
| `dev-api` | `dq-kafka` | `jacbeekers/dq-made-easy-kafka:latest` |
| `dev-api` | `dq-airflow` | `jacbeekers/dq-made-easy-airflow:latest` |
| `dev-ui` | `dq-frontend` | `jacbeekers/dq-made-easy-frontend:latest` |
| `dev-engine` | `dq-engine` | `jacbeekers/dq-made-easy-engine:latest` |
| `dev-engine` | `dq-profiling` | `jacbeekers/dq-made-easy-profiling:latest` |
| `dev-engine` | `dq-trino` | `jacbeekers/dq-made-easy-trino:latest` |
| `dev-engine` | `dq-llm` | `jacbeekers/dq-made-easy-llm:latest` |
| `dev-engine` | `dq-kafka-consumer` | `jacbeekers/dq-made-easy-kafka-consumer:latest` |
| `dev-engine` | `dq-openmetadata-db` | `jacbeekers/dq-made-easy-openmetadata-db:latest` |
| `dev-engine` | `dq-openmetadata-server` | `jacbeekers/dq-made-easy-openmetadata:latest` |

---

## Audit results

### Critical (block deployment)

| # | Issue | Severity | Affected |
|---|---|---|---|
| C1 | No `readinessProbe` or `livenessProbe` on DQ Deployments | ✅ Done | All 9 DQ services |
| C2 | All images tagged `:latest` — no version pinning | ✅ Done | All 9 DQ services (pinned to `0.1.0`) |
| C3 | No persistent volumes for stateful DQ services | ✅ Done | `dq-db`, `dq-openmetadata-db` (`emptyDir` for dev) |

### Medium (will cause runtime failures)

| # | Issue | Severity | Affected |
|---|---|---|---|
| M1 | Ingress TLS secrets (`dq-dev-*`) not generated | ✅ Done | 2 DQ ingresses (keycloak removed — platform-owned) |
| M2 | All secrets contain placeholder values (`CHANGE_ME_DEV`) | ✅ Done | Secrets created by script, not managed by ArgoCD (zero drift) |
| M3 | Kafka topics Job verified against source code | ✅ Done | `dq-job-kafka-topics` |
| M4 | No `resources` (CPU/memory) requests or limits | ✅ Done | All 9 deployments |
| M5 | Missing required platform labels (`environment`, `tenant`, `service`) | ✅ Done | All services via `labels.yaml` transformers |

---

## Tasks

### Task C1: Add health probes to all deployments

**Goal**: Every Deployment has a `readinessProbe` and `livenessProbe` appropriate to its service type.

**Probe strategy per service type**:

| Service type | Readiness probe | Liveness probe |
|---|---|---|
| HTTP services (api, engine, frontend, profiling, openmetadata-server, llm) | `httpGet /health` | `httpGet /health` |
| Databases (db, openmetadata-db) | `tcpSocket 5432` | `tcpSocket 5432` |
| Keycloak | `httpGet /health/ready` on 8080 | `httpGet /health` on 8080 |
| Kong | `httpGet /status` on 8001 | `httpGet /status` on 8001 |
| Kafka | `tcpSocket 9092` | `tcpSocket 9092` |
| Kafka consumer | `httpGet /health` (if available) or `tcpSocket` | `tcpSocket` |
| Trino | `httpGet /v1/info` on 8080 | `httpGet /v1/info` on 8080 |
| Airflow | `httpGet /api/v2/monitor/health` on 8080 | `httpGet /api/v2/monitor/health` on 8080 |

**Acceptance criteria**:
- [ ] Every Deployment in `base/api/`, `base/frontend/`, and `base/engine/` has both probes
- [ ] `initialDelaySeconds` set per service (30s for HTTP, 45s for databases, 60s for Kafka)
- [ ] `periodSeconds: 10`, `timeoutSeconds: 5`, `failureThreshold: 3`
- [ ] `kubectl kustomize infra/k8s/overlays/dev-api` renders without errors

**Location**: `infra/k8s/base/*/` (base manifests)

---

### Task C2: Pin image tags ✅ and add Kustomize image overrides

**Status**: Complete

**Goal**: Base manifests use a default tag; overlays pin specific versions for each environment.

**Approach**:
1. Base manifests use a pinned default tag (e.g., `0.1.0`)
2. Each overlay (`dev-api`, `dev-ui`, `dev-engine`, `test`, `prod`) uses Kustomize `images:` to override the tag per environment

**Acceptance criteria**:
- [ ] Base manifests use `:0.1.0` (or current latest digest) instead of `:latest`
- [ ] Each overlay has `images:` section in `kustomization.yaml` pinning the tag
- [ ] No `:latest` references remain in any manifest
- [ ] `imagePullPolicy: IfNotPresent` (not `Always`) for pinned tags

**Location**: `infra/k8s/base/*/` (base), `infra/k8s/overlays/*/kustomization.yaml` (overlays)

---

### Task C3: Add persistent volumes ✅ for stateful services

**Goal**: Stateful services survive pod restarts.

**Services requiring volumes**:

| Service | Data | Volume type (dev) | Volume type (test/prod) |
|---|---|---|---|
| `dq-db` | PostgreSQL data | `emptyDir` | PVC (`ReadWriteOnce`) |
| `dq-kafka` | KRaft metadata | `emptyDir` | PVC (`ReadWriteOnce`) |
| `dq-openmetadata-db` | PostgreSQL data | `emptyDir` | PVC (`ReadWriteOnce`) |

**Acceptance criteria**:
- [ ] Base manifests include `volumeMounts` + `volumes` with `emptyDir` for dev
- [ ] Test/prod overlays patch `emptyDir` → `persistentVolumeClaim` via strategic merge
- [ ] Data directory paths match each service's expectations (`/var/lib/postgresql/data`, `/var/lib/kafka/data`, etc.)
- [ ] `kubectl kustomize infra/k8s/overlays/dev-api` renders with volume mounts

**Location**: `infra/k8s/base/*/` (base), `infra/k8s/overlays/*/` (prod/test patches)

---

### Task M1: Generate Ingress TLS secrets

**Goal**: TLS certificates exist for all DQ ingress hosts.

**TLS secrets needed**:

| Secret name | Namespace | Certificate | Host |
|---|---|---|---|
| `dq-dev-tls-cert` | `dq-made-easy-dev` | `dq-made-easy.jac.dot` | DQ frontend (via Kong) |
| `dq-dev-keycloak-tls-cert` | `dq-made-easy-dev` | `keycloak.jac.dot` | DQ Keycloak (via Kong) |
| `dq-dev-openmetadata-tls-cert` | `dq-made-easy-dev` | `openmetadata.jac.dot` | OpenMetadata (via Kong) |

**Approach**:
- Coordinate with platform team to add these hosts to `generate_dev_certs.sh`
- Platform team updates `generate_secrets.sh` to create the DQ TLS secrets

**Acceptance criteria**:
- [ ] Certificates generated for `dq-made-easy.jac.dot`, `keycloak.jac.dot`, `openmetadata.jac.dot`
- [ ] K8s TLS secrets created in `dq-made-easy-dev` namespace
- [ ] Ingresses reference existing secrets (no `secret not found` errors)

**Location**: Platform repo — `scripts/generate_dev_certs.sh`, `scripts/generate_secrets.sh`, `.env.dev.local`

---

### Task M2: Generate real secret values for DQ

**Goal**: Replace `CHANGE_ME_DEV` placeholders with dynamically generated passwords.

**Secrets requiring real values**:

| Secret name | Key | Source |
|---|---|---|
| `dq-api-secrets` | `API_SECRET_PLACEHOLDER` | Generate random (or real value) |
| `dq-db-secrets` | `POSTGRES_PASSWORD` | Generate random |
| `dq-engine-secrets` | `ENGINE_SECRET_PLACEHOLDER` | Generate random (or real value) |
| `dq-profiling-secrets` | `PROFILING_SECRET_PLACEHOLDER` | Generate random (or real value) |
| `dq-trino-secrets` | `TRINO_SECRET_PLACEHOLDER` | Generate random (or real value) |
| `dq-llm-secrets` | `DQ_LLM_API_KEY` | Generate random (or real value) |
| `dq-kafka-consumer-secrets` | `KAFKA_CONSUMER_DB_URL` | Construct from DB credentials |
| `dq-openmetadata-db-secrets` | `OM_DB_PASSWORD` | Generate random |
| `dq-openmetadata-server-secrets` | `OM_TOKEN` | Generate random |

**Approach**:
- Platform team extends `deploy_dq_dev.sh` to generate and apply all secrets
- Credentials stored in `tmp/.credentials/dq-dev-credentials.json`

**Acceptance criteria**:
- [ ] All placeholder values replaced with generated passwords
- [ ] Credentials stored in `tmp/.credentials/`
- [ ] `deploy_dq_dev.sh --env dev` creates all secrets idempotently

**Location**: Platform repo — `scripts/deploy_dq_dev.sh`, `infra/k8s/overlays/*/config/service-secrets-placeholder.yaml`

---

### Task M3: Verify DQ Kafka KRaft configuration

**Goal**: DQ Kafka starts without KRaft controller errors.

**Checks**:
- [ ] Docker image uses KRaft mode (not ZooKeeper)
- [ ] `KAFKA_LISTENER_SECURITY_PROTOCOL_MAP` includes `CONTROLLER:PLAINTEXT`
- [ ] `KAFKA_CONTROLLER_QUORUM_VOTERS` uses `localhost` for single-pod
- [ ] `KAFKA_TLS_ENABLED` defaults to `false` for dev
- [ ] `KAFKA_NODE_ID`, `KAFKA_PROCESS_ROLES` set correctly
- [ ] ConfigMap has `KAFKA_CONTROLLER_LISTENER_NAMES` and `KAFKA_INTER_BROKER_LISTENER_NAME`

**Location**: `infra/k8s/overlays/*/config/service-config.yaml` (or `dq-kafka-config` ConfigMap), `docker/kafka/` (Dockerfile)

---

### Task M4: Add resource ✅ requests and limits

**Goal**: Every container has resource requests and limits to enable proper scheduling.

**Baseline per service type**:

| Service type | Requests CPU | Requests Memory | Limits CPU | Limits Memory |
|---|---|---|---|---|
| API (FastAPI) | 100m | 256Mi | 500m | 1Gi |
| Database (PostgreSQL) | 250m | 512Mi | 1000m | 2Gi |
| Keycloak | 250m | 512Mi | 1000m | 2Gi |
| Kong | 100m | 128Mi | 500m | 1Gi |
| Kafka | 500m | 1Gi | 2000m | 4Gi |
| Trino | 500m | 1Gi | 2000m | 4Gi |
| LLM | 250m | 512Mi | 1000m | 2Gi |
| Frontend | 50m | 64Mi | 200m | 256Mi |
| Engine/worker | 250m | 512Mi | 1000m | 2Gi |
| Kafka consumer | 100m | 128Mi | 500m | 1Gi |
| OpenMetadata server | 250m | 512Mi | 1000m | 2Gi |

**Acceptance criteria**:
- [ ] Every container in base manifests has `resources` block
- [ ] Values above are used as defaults; overlays can override for test/prod

**Location**: `infra/k8s/base/*/` (all base Deployment manifests)

---

### Task M5: Add required ✅ platform labels

**Goal**: All DQ resources carry the platform label set so they can be discovered by lifecycle validation.

**Labels required on all resources**:

| Label | Value |
|---|---|
| `platform.jaccloud.nl/managed-by` | `argocd` |
| `platform.jaccloud.nl/environment` | `dev` (set by overlay) |
| `platform.jaccloud.nl/tenant` | `dq` |
| `platform.jaccloud.nl/service` | `<service-name>` (e.g., `dq-api`, `dq-db`) |

**Annotations required on Deployments**:

| Annotation | Value |
|---|---|
| `platform.jaccloud.nl/target-id` | `CLUSTER` (placeholder) |
| `platform.jaccloud.nl/workload-kind` | `service` (or `job`) |
| `platform.jaccloud.nl/maas-register` | `true` (services) / `false` (jobs) |

**Approach**:
- Update base `metadata/labels.yaml` transformers to include platform labels
- Add `platform.jaccloud.nl/environment` via overlay labels
- Update base `metadata/annotations.yaml` transformers for workload-kind annotations

**Acceptance criteria**:
- [ ] `validate_service_instance_lifecycle.sh --env dev --namespaces dq-made-easy-dev` passes
- [ ] `kubectl kustomize infra/k8s/overlays/dev-api` shows all platform labels on every resource
- [ ] No `commonLabels` used anywhere

**Location**: `infra/k8s/base/*/metadata/labels.yaml`, `infra/k8s/base/*/metadata/annotations.yaml`, `infra/k8s/overlays/*/kustomization.yaml`

---

## Sequencing

| Phase | Tasks | Status |
|---|---|---|
| **Phase 1: Critical — make pods startable** | C1 ✅, C2 ✅, C3 ✅ | Complete |
| **Phase 2: Medium — make services functional** | M1 ✅, M2 ✅, M3 ✅, M4 ✅ | Complete |
| **Phase 3: Platform compliance** | M5 ✅ | Complete |

## Acceptance criteria

All tasks complete when:

- [x] `kubectl kustomize infra/k8s/overlays/dev-api` renders without errors
- [x] `kubectl kustomize infra/k8s/overlays/dev-ui` renders without errors
- [x] `kubectl kustomize infra/k8s/overlays/dev-engine` renders without errors
- [x] All 9 deployments have readiness + liveness probes
- [x] No `:latest` image tags remain
- [x] Stateful services have volume mounts
- [x] All TLS secrets exist and are referenced by ingresses
- [x] All secrets have real (non-placeholder) values
- [x] DQ Kafka topics Job matches source code
- [x] All containers have resource requests/limits
- [ ] `validate_service_instance_lifecycle.sh --env dev --namespaces dq-made-easy-dev` passes (requires cluster deployment)
- [x] All platform labels and annotations present

## Related documents

- [Consumer onboarding guide](https://github.com/org/platform-foundation/blob/main/docs/infra/CONSUMER_ONBOARDING.md)
- [Operator manual](https://github.com/org/platform-foundation/blob/main/docs/infra/OPERATOR_MANUAL.md)
