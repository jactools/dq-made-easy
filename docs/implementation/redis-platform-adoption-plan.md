# Redis Platform Adoption Plan

**Status**: Draft  
**Date**: 2026-08-10  
**Audience**: DQ repository maintainers

This plan covers the DQ-side adoption of the platform-managed Redis service.

Redis infrastructure remains platform-owned. DQ adopts Redis only through workload configuration, secret references, queue naming, and validation inside the `dq-made-easy` repository.

## Objective and scope

The goal is to make DQ consume the platform Redis contract without taking ownership of platform Redis infrastructure.

This plan covers:

- DQ-side Secrets and ConfigMaps that reference platform Redis
- DQ queue keys and key prefixes
- DQ workload updates needed for Redis-backed features
- DQ validation of Redis-backed endpoints and workers

This plan does not cover platform Redis deployment, TLS, storage, or ACL infrastructure.

## Preconditions

Before DQ can adopt Redis:

- the platform must deploy `platform-redis`
- the platform must publish the Redis consumer contract
- DQ must receive tenant-specific Redis credentials and trust-bundle references

## DQ-owned changes

DQ owns the following application-level decisions:

- which workloads require Redis
- which queue keys or prefixes are used by DQ features
- which Secrets and ConfigMaps carry Redis connection references inside the DQ namespace
- how DQ validates Redis connectivity and queue-dependent endpoints

DQ does not own Redis infrastructure, tenant ACL rules, or platform Redis lifecycle.

## Progress summary

| Workstream | Status | Tasks | Complete | Progress |
|---|---|---:|---:|---:|
| W1. Map DQ Redis usage | In progress | 5 | 5 | 100% |
| W2. Add DQ Redis config surfaces | In progress | 6 | 6 | 100% |
| W3. Wire DQ workloads to platform Redis | In progress | 6 | 5 | 83% |
| W4. Validate Redis-backed DQ behavior | Not started | 6 | 0 | 0% |

## Workstream 1: Map DQ Redis usage

### Goal

Confirm exactly which DQ features and workloads depend on Redis.

### Tasks

- [x] Inventory all queue-dependent DQ endpoints and background workloads
- [x] Confirm the required Redis env vars for each workload
- [x] Define DQ queue keys and key prefixes under the tenant contract
- [x] Confirm whether DQ uses a single logical Redis DB or additional partitioning
- [x] Document DQ-specific validation flows for Redis-backed features

### Deliverable

A DQ-owned Redis usage map covering workloads, env vars, queue keys, and validation paths.

## Workstream 2: Add DQ Redis config surfaces

### Goal

Add DQ-side config and secret references without embedding platform infra logic.

### Tasks

- [x] Create or update DQ ConfigMaps for `REDIS_HOST`, `REDIS_PORT`, `REDIS_TLS_ENABLED`, optional `REDIS_DB`, and queue defaults
- [x] Create or update DQ Secrets for `REDIS_USERNAME`, `REDIS_PASSWORD`, and trust-bundle references
- [x] Ensure DQ manifest structure keeps Redis connection settings in DQ-owned config only
- [x] Keep queue keys and key prefixes DQ-specific
- [x] Ensure DQ workloads reference tenant-issued Redis credentials only
- [x] Document the mapping from the platform contract to DQ config names

### Deliverable

DQ manifests contain all Redis connection references needed to consume the platform Redis contract.

## Workstream 3: Wire DQ workloads to platform Redis

### Goal

Make Redis-backed DQ features use the platform Redis service through DQ-owned workload manifests.

### Tasks

- [x] Update API workloads that depend on Redis-backed queues
- [x] Update any worker, consumer, or background workloads that depend on Redis
- [x] Ensure DQ queue keys stay under the DQ tenant prefix
- [x] Ensure TLS trust-bundle references are mounted where Redis clients need them
- [x] Keep all rollout changes declarative through DQ manifests
- [ ] Align dev and test overlays with the same Redis contract shape

### Deliverable

DQ workloads consume Redis through tenant-owned configuration and ArgoCD-managed manifest changes.

## Workstream 4: Validate Redis-backed DQ behavior

### Goal

Verify that DQ features using Redis behave correctly in Kubernetes.

### Tasks

- [ ] Validate workload startup with Redis enabled
- [ ] Validate Redis client connectivity using the DQ runtime or debug checks
- [ ] Validate queue-dependent endpoints no longer fail due to missing Redis config
- [ ] Validate DQ uses only tenant-scoped queue keys or prefixes
- [ ] Validate the same behavior in dev and test
- [ ] Capture an implementation summary after the adoption work is complete

### Deliverable

DQ can use platform Redis successfully without owning or mutating Redis infrastructure.

## Immediate next actions

### DQ dev rollout verification

- [ ] Sync or restart DQ workloads that consume Redis:
  - `tenant-dq-shared`
  - `tenant-dq-api`
  - `tenant-dq-engine`
- [ ] Verify runtime Redis env/config inside DQ pods:
  - `REDIS_HOST`
  - `REDIS_USERNAME`
  - `REDIS_TLS_ENABLED=true`
  - `REDIS_CA_BUNDLE=/etc/ssl/certs/platform-root-ca.pem`
- [ ] Verify Redis-backed API behavior in dev:
  - validation plan replay no longer fails from missing Redis configuration
- [ ] Verify worker connectivity in dev:
  - `dq-engine` connects to Redis successfully
  - `dq-profiling` connects to Redis successfully when deployed

### DQ test alignment

- [ ] Mirror the Redis contract from dev into test overlays:
  - API config
  - engine config
  - profiling config
  - CA bundle mounts where needed
- [ ] Ensure DQ test secret generation also reads platform Redis credentials

### DQ consumer credential transition

- [ ] Update `dq-made-easy/scripts/generate_secrets.sh` to switch from platform admin Redis credentials to application-principal Redis credentials when platform issuance is available
- [ ] Map consumer principals explicitly:
  - API -> `dq-api`
  - engine -> `dq-engine`
  - profiling -> `dq-profiling`

### DQ test verification

- [ ] Validate Redis-backed endpoints and workers in test after the test overlay is aligned
- [ ] Capture an implementation summary after dev/test verification is complete

## Acceptance criteria

- [x] DQ stores Redis connection references only in DQ-owned manifests and secrets
- [x] DQ queue names and key prefixes are tenant-specific
- [x] DQ does not modify platform Redis infrastructure components
- [x] DQ workload rollout stays declarative through ArgoCD-managed manifests
- [ ] Redis-backed DQ endpoints and workers validate successfully in dev and test

## Next steps

1. Complete rollout and live verification in dev after image build/load + Argo sync.
2. Validate queue-dependent DQ flows after ArgoCD sync.
3. Align test overlays with the same Redis contract shape.
4. Capture implementation summary after verification is complete.