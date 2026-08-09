# GitOps Platform Alignment Plan

**Status**: Draft  
**Date**: 2026-08-09  
**Audience**: DQ repository maintainers

This plan aligns `dq-made-easy` with the shared GitOps structure provided by the platform while keeping DQ responsible for its own runtime workloads and tenant-specific configuration of central platform services.

## Objective and scope

The goal is to make the DQ Kubernetes manifests fit a clean ownership model:

- DQ owns DQ runtime services and their tenant namespace resources
- the platform owns central services such as Kong, Keycloak, Kafka, Trino, and observability
- DQ configures those central services through one-shot Jobs only

This plan covers the `infra/k8s/` manifests and the overlays consumed by ArgoCD in dev and test.

## Current issues

The current DQ layout works but still mixes concerns.

Primary issues:

- `shared-dev` combines tenant-shared runtime resources with central-service configuration Jobs
- not all shared Jobs target the same ownership boundary
- the manifest structure does not yet make the runtime versus platform-configuration split obvious
- the required config maps, secrets, and CA bundles for platform-configuration Jobs need an explicit contract

## Target state

DQ should expose separate deployment units for:

- DQ runtime API workloads
- DQ runtime engine workloads
- DQ runtime UI workloads
- DQ tenant-shared runtime resources
- DQ platform-configuration Jobs for shared platform services

The important boundary is:

- runtime resources remain long-lived DQ-owned workloads
- platform configuration remains one-shot Job-based tenant setup

## Required workload split

### Runtime workloads

These remain part of DQ runtime ownership:

- API deployments and services
- engine deployments and services
- UI deployments and services
- DQ database and other tenant-owned stateful services
- tenant ingress and runtime config
- runtime-only Jobs such as migrations or tenant-local seeding

### Platform-configuration Jobs

These should move into a dedicated platform-configuration slice when they configure shared platform services:

- Keycloak tenant bootstrap
- Kong route or consumer bootstrap
- Kafka topic bootstrap against the shared Kafka broker
- Trino catalog registration against the shared Trino service

Jobs that configure DQ-owned runtime services should stay with runtime resources.

## Progress summary

| Workstream | Status | Tasks | Complete | Progress |
|---|---|---:|---:|---:|
| W1. Classify DQ workloads by ownership | Not started | 6 | 0 | 0% |
| W2. Split manifests into runtime and platform-config | Not started | 7 | 0 | 0% |
| W3. Align overlays and ArgoCD sources | Not started | 6 | 0 | 0% |
| W4. Validate platform-aligned deployment | Not started | 6 | 0 | 0% |

## Workstream 1: Classify DQ workloads by ownership

### Goal

Make the boundary between DQ-owned runtime resources and platform-configuration Jobs explicit.

### Tasks

- [ ] Inventory all resources under `infra/k8s/base/` and `infra/k8s/overlays/`
- [ ] Classify each Job as runtime-local or platform-configuration
- [ ] Classify each config map and secret dependency by owner
- [ ] Classify each ingress and service as DQ runtime or platform-managed dependency
- [ ] Record the expected execution order between runtime and platform-config resources
- [ ] Document exceptions explicitly if a resource does not fit the split cleanly

### Deliverable

A resource inventory that says exactly which manifests belong to DQ runtime and which belong to DQ platform configuration.

## Workstream 2: Split manifests into runtime and platform-config

### Goal

Refactor the DQ manifest tree so the ownership boundary is visible in the filesystem.

### Tasks

- [ ] Create dedicated base directories for runtime and platform-config concerns
- [ ] Move platform-configuration Jobs into a dedicated base
- [ ] Keep runtime deployments, services, ingresses, and runtime-only Jobs in runtime bases
- [ ] Create a shared runtime slice only for tenant runtime resources that are not platform configuration
- [ ] Keep DQ-owned stateful services with runtime workloads
- [ ] Define the config map, secret, and CA-bundle contract for platform-config jobs
- [ ] Add labels or annotations that make `workload-kind` and ownership visible

### Deliverable

`infra/k8s/` expresses the runtime versus platform-configuration split directly.

## Workstream 3: Align overlays and ArgoCD sources

### Goal

Expose the new DQ split cleanly to the ArgoCD repository.

### Tasks

- [ ] Create per-environment overlays for runtime API, runtime engine, runtime UI, shared runtime, and platform-config
- [ ] Keep overlay naming symmetrical between dev and test
- [ ] Ensure overlay namespaces remain tenant-owned only
- [ ] Define which overlay should be referenced by each ArgoCD Application
- [ ] Introduce a dedicated DQ platform-config Application source path
- [ ] Document any sync dependencies between runtime and platform-config overlays

### Deliverable

DQ can be consumed by ArgoCD through clearly named environment overlays with no mixed ownership slices.

## Workstream 4: Validate platform-aligned deployment

### Goal

Prove that DQ still deploys correctly after the manifest split.

### Tasks

- [ ] Validate that runtime overlays render cleanly
- [ ] Validate that platform-config overlays render cleanly
- [ ] Validate that DQ runtime services can sync independently from platform-config Jobs
- [ ] Validate that platform-config Jobs run to completion and do not remain long-lived
- [ ] Validate that required shared-service dependencies are available through the platform contract
- [ ] Capture an implementation summary after the migration is complete

### Deliverable

DQ deploys through the shared platform contract with a clean split between its runtime services and its configuration of central services.

## Acceptance criteria

- [ ] DQ runtime workloads are separated from DQ platform-configuration Jobs
- [ ] Keycloak, Kong, Kafka, and Trino tenant bootstrap actions run as Jobs only
- [ ] Runtime-only Jobs stay with DQ runtime resources
- [ ] Dev and test overlays use the same structural split
- [ ] ArgoCD can target DQ runtime and platform-config slices independently
- [ ] The config contract for platform-config jobs is documented

## Next steps

1. Classify every existing shared Job by owner and target system.
2. Create the dedicated platform-config base and overlays.
3. Align the DQ ArgoCD source paths with the new overlay names.
4. Validate runtime sync and platform-config Job execution separately.