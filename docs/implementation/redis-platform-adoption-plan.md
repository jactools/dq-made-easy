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
| W1. Map DQ Redis usage | Not started | 5 | 0 | 0% |
| W2. Add DQ Redis config surfaces | Not started | 6 | 0 | 0% |
| W3. Wire DQ workloads to platform Redis | Not started | 6 | 0 | 0% |
| W4. Validate Redis-backed DQ behavior | Not started | 6 | 0 | 0% |

## Workstream 1: Map DQ Redis usage

### Goal

Confirm exactly which DQ features and workloads depend on Redis.

### Tasks

- [ ] Inventory all queue-dependent DQ endpoints and background workloads
- [ ] Confirm the required Redis env vars for each workload
- [ ] Define DQ queue keys and key prefixes under the tenant contract
- [ ] Confirm whether DQ uses a single logical Redis DB or additional partitioning
- [ ] Document DQ-specific validation flows for Redis-backed features

### Deliverable

A DQ-owned Redis usage map covering workloads, env vars, queue keys, and validation paths.

## Workstream 2: Add DQ Redis config surfaces

### Goal

Add DQ-side config and secret references without embedding platform infra logic.

### Tasks

- [ ] Create or update DQ ConfigMaps for `REDIS_HOST`, `REDIS_PORT`, `REDIS_TLS_ENABLED`, optional `REDIS_DB`, and queue defaults
- [ ] Create or update DQ Secrets for `REDIS_USERNAME`, `REDIS_PASSWORD`, and trust-bundle references
- [ ] Ensure DQ manifest structure keeps Redis connection settings in DQ-owned config only
- [ ] Keep queue keys and key prefixes DQ-specific
- [ ] Ensure DQ workloads reference tenant-issued Redis credentials only
- [ ] Document the mapping from the platform contract to DQ config names

### Deliverable

DQ manifests contain all Redis connection references needed to consume the platform Redis contract.

## Workstream 3: Wire DQ workloads to platform Redis

### Goal

Make Redis-backed DQ features use the platform Redis service through DQ-owned workload manifests.

### Tasks

- [ ] Update API workloads that depend on Redis-backed queues
- [ ] Update any worker, consumer, or background workloads that depend on Redis
- [ ] Ensure DQ queue keys stay under the DQ tenant prefix
- [ ] Ensure TLS trust-bundle references are mounted where Redis clients need them
- [ ] Keep all rollout changes declarative through DQ manifests
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

## Acceptance criteria

- [ ] DQ stores Redis connection references only in DQ-owned manifests and secrets
- [ ] DQ queue names and key prefixes are tenant-specific
- [ ] DQ does not modify platform Redis infrastructure components
- [ ] DQ workload rollout stays declarative through ArgoCD-managed manifests
- [ ] Redis-backed DQ endpoints and workers validate successfully in dev and test

## Next steps

1. Wait for the platform Redis consumer contract to land.
2. Map DQ queue usage and env vars.
3. Add DQ Redis Secrets and ConfigMaps.
4. Validate queue-dependent DQ flows after ArgoCD sync.