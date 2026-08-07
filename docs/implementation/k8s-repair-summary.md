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
| `api/keycloak.yaml` | `shared/jobs/keycloak-seed.yaml` | Seeds Keycloak realm/clients |
| `api/kong.yaml` | `shared/jobs/kong-bootstrap.yaml` | Configures Kong routes/services |
| `api/kafka.yaml` | `shared/jobs/kafka-topics.yaml` | Creates topics on platform Kafka |
| `api/airflow.yaml` | *(removed)* | Airflow DAG upload TBD |
| `engine/trino.yaml` | `shared/jobs/trino-catalog.yaml` | Registers catalogs on platform Trino |

### Overlay Restructuring ✅

Created `shared-dev` overlay to prevent ArgoCD resource conflicts. Component overlays no longer reference shared resources.

| Overlay | Resources |
|---------|-----------|
| `shared-dev` | Namespace, ConfigMaps, Ingresses, Jobs (6) |
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

**Images pinned (15 total)**:

| Image | Overlay |
|-------|---------|
| `dq-made-easy-api` | shared-dev, dev-api |
| `dq-made-easy-db` | dev-api |
| `dq-made-easy-frontend` | dev-ui |
| `dq-made-easy-engine` | dev-engine |
| `dq-made-easy-profiling` | dev-engine |
| `dq-made-easy-llm` | dev-engine |
| `dq-made-easy-kafka-consumer` | dev-engine |
| `dq-made-easy-openmetadata-db` | dev-engine |
| `dq-made-easy-openmetadata` | dev-engine |
| `dq-made-easy-keycloak` | shared-dev |
| `dq-made-easy-kong` | shared-dev |
| `dq-made-easy-trino` | shared-dev |
| `dq-made-easy-metadata-configure` | shared-dev |
| `apache/kafka:3.9.1` | shared-dev (already pinned) |

### DNS/Ingress Fix ✅

Updated all hostnames to use `.dev.jac.dot` convention and ingress port 10443:

| Before | After |
|--------|-------|
| `dq-made-easy.jac.dot` | `dq-made-easy.dev.jac.dot` |
| `keycloak.jac.dot:9444` | `keycloak.dev.jac.dot:10443` |
| `openmetadata.jac.dot:8585` | `openmetadata.dev.jac.dot:10443` |

## Remaining Tasks

### Task C3: Persistent Volumes 🔴

**Status**: Open  
**Issue**: Stateful services (`dq-db`, `dq-openmetadata-db`) use `emptyDir`  
**Fix**: Add volume mounts with `emptyDir` (dev) or PVC (test/prod)  
**Files**: `infra/k8s/base/api/db.yaml`, `infra/k8s/base/engine/openmetadata-db.yaml`

### Task M1: TLS Secrets ⚠️

**Status**: Open  
**Issue**: Ingresses reference `dq-dev-*` secrets that don't exist  
**Fix**: Generate certs and create TLS secrets via platform scripts  
**Files**: Platform repo scripts

### Task M2: Secret Values ⚠️

**Status**: Open  
**Issue**: All secrets contain `CHANGE_ME_DEV` placeholders  
**Fix**: Generate real passwords and update secrets  
**Files**: Platform repo `deploy_dq_dev.sh`

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
- [ ] Stateful services have persistent volumes
- [ ] TLS secrets exist for Ingresses
- [ ] Real secret values (no placeholders)
- [ ] Kafka topics Job configured correctly
- [ ] Resource requests/limits on all containers
- [ ] Platform labels/annotations present
- [ ] `validate_service_instance_lifecycle.sh` passes

## Related Documents

- [K8s Repair Plan](./k8s-repair-plan.md)
- [Consumer Onboarding Guide](https://github.com/org/platform-foundation/blob/main/docs/infra/CONSUMER_ONBOARDING.md)
- [Operator Manual](https://github.com/org/platform-foundation/blob/main/docs/infra/OPERATOR_MANUAL.md)
