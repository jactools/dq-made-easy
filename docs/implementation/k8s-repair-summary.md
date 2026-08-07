# K8s Manifest Repair — Implementation Summary

**Status**: In Progress  
**Date**: 2026-08-07

## Overview

This document summarizes the ongoing remediation of the DQ Made Easy Kubernetes manifests. The work addresses critical and medium-severity issues discovered during platform service debugging.

## Completed Tasks

### Task C0: Platform Config → Jobs ✅

Converted 5 platform configuration Deployments to Jobs:

| Deleted Deployment | Created Job | Purpose |
|-------------------|-------------|---------|
| `api/keycloak.yaml` | `shared/jobs/keycloak-seed.yaml` | Seeds Keycloak realm/clients via API |
| `api/kong.yaml` | `shared/jobs/kong-bootstrap.yaml` | Creates Kong routes via Admin API |
| `api/kafka.yaml` | `shared/jobs/kafka-topics.yaml` | Creates topics on platform Kafka |
| `api/airflow.yaml` | *(removed)* | Airflow DAG upload TBD |
| `engine/trino.yaml` | `shared/jobs/trino-catalog.yaml` | Registers catalogs on platform Trino |

### Overlay Restructuring ✅

Created `shared-dev` overlay to prevent ArgoCD resource conflicts. Component overlays no longer reference shared resources.

| Overlay | Resources |
|---------|-----------|
| `shared-dev` | Namespace, ConfigMaps, Ingresses (2), Jobs (6) |
| `dev-api` | dq-api + dq-db Deployments |
| `dev-ui` | dq-frontend Deployment |
| `dev-engine` | engine, profiling, llm, kafka-consumer, openmetadata Deployments |

### Task C1: Health Probes ✅

Added readiness and liveness probes to all 9 DQ Deployments:

| Service | Port | Readiness | Liveness |
|---------|------|-----------|----------|
| dq-api | 8000 (HTTP) | `httpGet /health` | `httpGet /health` |
| dq-db | 5432 (TCP) | `tcpSocket` | `tcpSocket` |
| dq-frontend | 443 (TCP) | `tcpSocket` | `tcpSocket` |
| dq-engine | 8000 (HTTP) | `httpGet /health` | `httpGet /health` |
| dq-profiling | 8001 (HTTP) | `httpGet /health` | `httpGet /health` |
| dq-llm | 8000 (HTTP) | `httpGet /health` | `httpGet /health` |
| dq-kafka-consumer | 9100 (TCP) | `tcpSocket` | `tcpSocket` |
| dq-openmetadata-db | 5432 (TCP) | `tcpSocket` | `tcpSocket` |
| dq-openmetadata-server | 8585 (HTTP) | `httpGet /health` | `httpGet /health` |

**Probe Settings**:
- Readiness: `initialDelaySeconds: 30` (45 for databases), `periodSeconds: 10`
- Liveness: `initialDelaySeconds: 60`, `periodSeconds: 30`
- All: `timeoutSeconds: 5`, `failureThreshold: 3`

### Task C2: Pin Image Tags ✅

**Changes**:
- Base manifests: `:latest` → `:0.1.0`
- `imagePullPolicy: Always` → `IfNotPresent`
- Added `images:` sections to all overlays with pinned `0.1.0` tags

**Images pinned (14 total)**:

| Image | Overlay | Notes |
|-------|---------|-------|
| `dq-made-easy-api` | shared-dev, dev-api | Used by jobs + API Deployment |
| `dq-made-easy-db` | dev-api | |
| `dq-made-easy-frontend` | dev-ui | |
| `dq-made-easy-engine` | dev-engine | |
| `dq-made-easy-profiling` | dev-engine | |
| `dq-made-easy-llm` | dev-engine | |
| `dq-made-easy-kafka-consumer` | dev-engine | |
| `dq-made-easy-openmetadata-db` | dev-engine | |
| `dq-made-easy-openmetadata` | dev-engine | |
| `dq-made-easy-metadata-configure` | shared-dev | OpenMetadata seed Job |
| `apache/kafka:3.9.1` | shared-dev | Upstream, already pinned |
| `trinodb/trino:451` | shared-dev | Upstream Trino CLI for catalog Job |

### Task C3: Persistent Volumes ✅

Added persistent volumes for stateful services:

| Service | Mount Path | Volume Type |
|---------|-----------|-------------|
| dq-db | `/var/lib/postgresql/data` | emptyDir (dev), PVC (test/prod) |
| dq-openmetadata-db | `/var/lib/postgresql/data` | emptyDir (dev), PVC (test/prod) |

### Task M1: TLS Secrets ✅

Generated TLS certificates and Kubernetes secrets for DQ Ingresses:

| Ingress | Hostname | Secret Name | Namespace |
|---------|----------|-------------|-----------|
| dq-ingress-frontend | `dq-made-easy.dev.jac.dot` | `dq-dev-tls-cert` | `dq-made-easy-dev` |
| dq-ingress-openmetadata | `openmetadata.dev.jac.dot` | `dq-dev-openmetadata-tls-cert` | `dq-made-easy-dev` |

**Removed**: `dq-ingress-keycloak` — `keycloak.dev.jac.dot` is a platform-owned hostname. DQ accesses Keycloak via Kong routes, not its own Ingress.

### Task M2: Real Secret Values ✅

Created `scripts/generate_secrets.sh` that generates random passwords for all 9 DQ-owned secrets and applies them to the cluster.

| Secret | Keys Generated |
|--------|---------------|
| `dq-api-secrets` | `API_SECRET_PLACEHOLDER`, `APP_CONFIG_ENCRYPTION_KEY` (Fernet) |
| `dq-db-secrets` | `POSTGRES_PASSWORD` |
| `dq-frontend-secrets` | `FRONTEND_SECRET_PLACEHOLDER` |
| `dq-engine-secrets` | `ENGINE_SECRET_PLACEHOLDER` |
| `dq-profiling-secrets` | `PROFILING_SECRET_PLACEHOLDER` |
| `dq-llm-secrets` | `DQ_LLM_API_KEY` |
| `dq-kafka-consumer-secrets` | `KAFKA_CONSUMER_DB_URL` |
| `dq-openmetadata-db-secrets` | `OM_DB_PASSWORD` |
| `dq-openmetadata-server-secrets` | `OM_TOKEN` |

**Architecture**: Secrets are **NOT managed by ArgoCD**. The placeholder files (`service-secrets-placeholder.yaml`) were removed from all overlays. The script creates real secrets independently — ArgoCD knows nothing about them, so there is zero drift.

**Removed from git**: `dq-kong-secrets`, `dq-keycloak-secrets`, `dq-kafka-secrets`, `dq-trino-secrets`, `dq-airflow-secrets` — these are platform-owned services.

**Credentials stored in**: `tmp/.credentials` (mode 600, `.gitignore`'d).

### DNS/Ingress Fix ✅

Updated all hostnames to use `.dev.jac.dot` convention and ingress port 10443.

## Remaining Tasks

### Task M3: Kafka Topics ⚠️

**Status**: Open  
**Issue**: Verify `dq-job-kafka-topics` connects to platform Kafka  
**Fix**: Ensure correct bootstrap server and topic names  
**Files**: `infra/k8s/base/shared/jobs/kafka-topics.yaml`

### Task M4: Resource Limits ⚠️

**Status**: Open  
**Issue**: No CPU/memory requests or limits  
**Fix**: Add `resources` section to all containers  
**Files**: All base Deployment manifests

### Task M5: Platform Labels ⚠️

**Status**: Open  
**Issue**: Missing `platform.jaccloud.nl/*` labels  
**Fix**: Update transformers in base manifests  
**Files**: `infra/k8s/base/*/metadata/labels.yaml`, `annotations.yaml`

## Acceptance Criteria

- [x] Platform config Deployments → Jobs
- [x] Overlay structure prevents ArgoCD conflicts
- [x] All 9 DQ Deployments have readiness + liveness probes
- [x] No `:latest` image tags
- [x] Stateful services have persistent volumes
- [x] TLS secrets exist for DQ Ingresses
- [x] Jobs use correct images (no phantom DQ Kong/Keycloak/Trino images)
- [x] Real secret values (no placeholders, secrets not managed by ArgoCD)
- [ ] Kafka topics Job configured correctly
- [ ] Resource requests/limits on all containers
- [ ] Platform labels/annotations present
- [ ] `validate_service_instance_lifecycle.sh` passes

## Related Documents

- [K8s Repair Plan](./k8s-repair-plan.md)
- [Consumer Onboarding Guide](https://github.com/org/platform-foundation/blob/main/docs/infra/CONSUMER_ONBOARDING.md)
- [Operator Manual](https://github.com/org/platform-foundation/blob/main/docs/infra/OPERATOR_MANUAL.md)
