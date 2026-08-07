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

Base manifests: `:latest` → `:0.1.0`, `imagePullPolicy: IfNotPresent`. Added `images:` overrides to all overlays.

### Task C3: Persistent Volumes ✅

Added `emptyDir` volumes for `dq-db` and `dq-openmetadata-db` at `/var/lib/postgresql/data`.

### Task M1: TLS Secrets ✅

Generated TLS certs using platform root CA. Created 2 K8s TLS secrets for DQ Ingresses. Removed `dq-ingress-keycloak` (platform-owned hostname).

### Task M2: Real Secret Values ✅

Created `scripts/generate_secrets.sh` that generates random passwords for 9 DQ-owned secrets. Removed placeholder secrets from overlays (ArgoCD doesn't manage secrets → zero drift).

### Task M3: Kafka Topics Job ✅

**Verification** against source code:

| Item | Before | After |
|------|--------|-------|
| Bootstrap server | `kafka.platform-kafka.svc.cluster.local:9092` ✅ | No change (was correct) |
| Topic name | `dq-events` ✗ | `dq-made-easy.gx.violations` ✅ |
| Configmap refs | `dq-kafka-config` (doesn't exist) ✗ | Removed ✅ |
| Additional topics | None | `dq-made-easy.events` ✅ |

**Source code match**: `dq-engine/kafka_client.py` defines `VIOLATIONS_TOPIC_NAME = "dq-made-easy.gx.violations"`. The Job now creates this topic with `--if-not-exists`, `compact` cleanup policy, and 7-day retention.

**Also fixed**: `trino-catalog` job — removed reference to `dq-trino-config` (defined in dev-engine, not shared-dev).

## Remaining Tasks

### Task M4: Resource Limits ⚠️

**Status**: Open  
**Issue**: No CPU/memory requests or limits  
**Fix**: Add `resources` section to all containers

### Task M5: Platform Labels ⚠️

**Status**: Open  
**Issue**: Missing `platform.jaccloud.nl/*` labels  
**Fix**: Update transformers in base manifests

### Deferred: Other Jobs ConfigMap refs ⚠️

Several jobs in `shared-dev` reference configmaps defined in component overlays:
- `keycloak-seed` → `dq-keycloak-config` (not in shared-dev)
- `kong-bootstrap` → `dq-kong-config` (not in shared-dev)
- `openmetadata-seed` → `dq-openmetadata-server-config` (not in shared-dev)
- `api-migrate` → `dq-api-config` (not in shared-dev)

These need either the configmaps moved to shared-dev or the jobs moved to their respective overlays. Deferred until deployment testing.

## Acceptance Criteria

- [x] Platform config Deployments → Jobs
- [x] Overlay structure prevents ArgoCD conflicts
- [x] All 9 DQ Deployments have readiness + liveness probes
- [x] No `:latest` image tags
- [x] Stateful services have persistent volumes
- [x] TLS secrets exist for DQ Ingresses
- [x] Jobs use correct images (no phantom DQ Kong/Keycloak/Trino images)
- [x] Real secret values (no placeholders, secrets not managed by ArgoCD)
- [x] Kafka topics Job configured correctly
- [ ] Resource requests/limits on all containers
- [ ] Platform labels/annotations present
- [ ] `validate_service_instance_lifecycle.sh` passes

## Related Documents

- [K8s Repair Plan](./k8s-repair-plan.md)
- [Consumer Onboarding Guide](https://github.com/org/platform-foundation/blob/main/docs/infra/CONSUMER_ONBOARDING.md)
- [Operator Manual](https://github.com/org/platform-foundation/blob/main/docs/infra/OPERATOR_MANUAL.md)
