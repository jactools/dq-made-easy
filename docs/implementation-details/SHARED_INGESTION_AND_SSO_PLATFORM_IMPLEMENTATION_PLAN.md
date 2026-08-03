# Shared Ingestion and SSO Platform Implementation Plan

**Status**: Proposed  
**Target**: Shared ingestion runtime, shared SSO/OIDC support, and centralized reusable container images for `dq-made-easy` and MaaS  
**Date**: 2026-08-03

Related ADR: [ADR-036 Shared Ingestion and SSO Platform Boundary and Image Ownership](../../architecture/adr/ADR-036-shared-ingestion-and-sso-platform-boundary-and-image-ownership.md)
Related design: [Shared Ingestion and SSO Platform Design](../design/SHARED_INGESTION_AND_SSO_PLATFORM_DESIGN.md)
Related checklist: [Shared Ingestion and SSO Platform Repo Migration Checklist](./SHARED_INGESTION_AND_SSO_PLATFORM_REPO_MIGRATION_CHECKLIST.md)

---

## Overview

This plan turns the shared-platform design into an executable migration path.

The goal is to extract reusable ingestion and SSO capabilities out of the application repositories, while centralizing the reusable container images in one place. Both `dq-made-easy` and MaaS should remain thin consumers of that shared foundation.

This is intentionally a staged migration: inventory first, then extraction, then centralized image ownership, then application adoption, then cleanup.

## Scope Definition

### In Scope

- Inventory of reusable ingestion code in `dq-made-easy`
- Inventory of reusable SSO/OIDC code in `dq-made-easy`
- Definition of the shared platform package/repository boundary
- Extraction of reusable ingestion helpers, fixtures, and runtime support
- Extraction of reusable SSO/OIDC helpers
- Centralized build/publish flow for shared runtime images
- Adoption wiring in `dq-made-easy` and MaaS
- Removal of duplicate code paths and image definitions

### Out of Scope for the First Cut

- Rewriting app-specific DQ workflows
- Reworking MaaS domain logic beyond the shared integration seam
- Replacing the identity provider itself
- Redesigning unrelated service containers

## Workstream 1: Inventory and Boundary Definition

- [ ] (SHARED-I-W1-01) Catalog all real-data ingestion code paths in `dq-made-easy` and classify each one as shared or app-specific.
- [ ] (SHARED-I-W1-02) Catalog all SSO/OIDC code paths in `dq-made-easy` and classify each one as shared or app-specific.
- [ ] (SHARED-I-W1-03) Identify shared container images and identify duplicate Dockerfiles or build logic.
- [ ] (SHARED-I-W1-04) Decide the shared platform home: a new repository, or an explicitly versioned shared package area if the team prefers to stage extraction incrementally.
- [ ] (SHARED-I-W1-05) Record the boundary rules so future changes do not reintroduce duplication.

## Workstream 2: Extract Shared Ingestion Capability

- [ ] (SHARED-I-W2-01) Move reusable ingestion connectors and helpers into the shared platform.
- [ ] (SHARED-I-W2-02) Move reusable test-data generation or fixture-backed real data sources into the shared platform.
- [ ] (SHARED-I-W2-03) Provide a shared CLI or job entrypoint for running the ingestion workloads.
- [ ] (SHARED-I-W2-04) Keep application-specific orchestration wrappers in `dq-made-easy` and MaaS.
- [ ] (SHARED-I-W2-05) Add tests that prove the shared ingestion package can be consumed without copying code into the app repos.

## Workstream 3: Extract Shared SSO / OIDC Capability

- [ ] (SHARED-I-W3-01) Move common OIDC configuration helpers into the shared platform.
- [ ] (SHARED-I-W3-02) Move issuer/JWKS validation helpers into the shared platform.
- [ ] (SHARED-I-W3-03) Move claims-to-role mapping helpers into the shared platform where the behavior is common.
- [ ] (SHARED-I-W3-04) Keep application-specific authorization policy inside each repository.
- [ ] (SHARED-I-W3-05) Define the environment-variable contract that both apps will use for shared auth settings.

## Workstream 4: Centralize Shared Images

- [ ] (SHARED-I-W4-01) Create or adapt the shared image build pipeline so reusable images are built in one place.
- [ ] (SHARED-I-W4-02) Publish shared images to a registry under a stable namespace and version scheme.
- [ ] (SHARED-I-W4-03) Replace duplicate image build definitions in the application repos with references to the shared tags.
- [ ] (SHARED-I-W4-04) Provide local-development overrides only where repo-specific debugging genuinely requires them.
- [ ] (SHARED-I-W4-05) Document how image version pinning and upgrades should work for consumers.

## Workstream 5: Adopt in `dq-made-easy` and MaaS

- [ ] (SHARED-I-W5-01) Update `dq-made-easy` to consume the shared ingestion package and shared auth helpers.
- [ ] (SHARED-I-W5-02) Update MaaS to consume the same shared ingestion package and shared auth helpers.
- [ ] (SHARED-I-W5-03) Add repo-specific adapters only where product behavior diverges.
- [ ] (SHARED-I-W5-04) Verify that both repositories build and run against the same published images.
- [ ] (SHARED-I-W5-05) Remove temporary compatibility shims once both consumers are stable.

## Workstream 6: Cleanup, Validation, and Evidence

- [ ] (SHARED-I-W6-01) Remove duplicate code that has been superseded by the shared platform.
- [ ] (SHARED-I-W6-02) Remove duplicate Dockerfiles and image build paths that are no longer needed.
- [ ] (SHARED-I-W6-03) Add validation that flags reintroduced duplication in future changes.
- [ ] (SHARED-I-W6-04) Capture evidence that the shared ingestion paths and SSO paths work in both repos.
- [ ] (SHARED-I-W6-05) Record any remaining exceptions explicitly instead of leaving them implicit.

## Recommended Sequencing

1. Finish Workstream 1 before extracting anything.
2. Finish Workstream 2 and Workstream 3 before cutting over consumers.
3. Land Workstream 4 before removing duplicate image definitions.
4. Use Workstream 5 to migrate `dq-made-easy` first, then MaaS.
5. Use Workstream 6 to delete legacy copies and enforce the new boundary.

## Acceptance Criteria

- [ ] (SHARED-I-AC-01) Reusable ingestion logic exists in one shared location rather than being copied into both repositories.
- [ ] (SHARED-I-AC-02) Reusable SSO/OIDC helpers exist in one shared location rather than being copied into both repositories.
- [ ] (SHARED-I-AC-03) Shared images are built and published once and are consumed by both repositories through versioned tags.
- [ ] (SHARED-I-AC-04) `dq-made-easy` and MaaS keep only thin adapters around shared ingestion and auth capabilities.
- [ ] (SHARED-I-AC-05) Duplicate code paths and duplicate image definitions have been removed or explicitly justified.
- [ ] (SHARED-I-AC-06) The migration is documented with enough detail for future maintenance and upgrades.

## Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Shared platform grows too broad | Hard to maintain ownership | Keep extraction narrow and review every addition against the shared boundary |
| Version drift between repos | Behavior inconsistency | Pin shared artifact versions and upgrade intentionally |
| Auth behavior differs subtly between apps | Integration bugs | Share only the low-level primitives; keep policy in app-specific code |
| Image registry dependency complicates local development | Slower onboarding | Provide local overrides for development only |
| Migration leaves duplicate code behind | Long-term maintenance cost | Add explicit cleanup tasks and duplication checks |

## Next Steps

1. Approve the shared boundary and image ownership model.
2. Use the repo migration checklist to confirm the first extraction candidates.
3. Identify the first reusable ingestion module to extract.
4. Identify the first reusable auth helper to extract.
5. Define the shared image naming and tagging scheme.
6. Start the extraction with `dq-made-easy` as the first consumer.
