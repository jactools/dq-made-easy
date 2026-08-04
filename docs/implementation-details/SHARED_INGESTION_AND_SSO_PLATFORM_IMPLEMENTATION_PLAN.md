# Shared Ingestion and SSO Platform Implementation Plan

**Status**: In progress  
**Target**: Shared ingestion runtime, shared SSO/OIDC support, and centralized reusable container images for `dq-made-easy` and MaaS  
**Date**: 2026-08-03  
**Last updated**: 2026-08-04

Related ADR: [ADR-036 Shared Ingestion and SSO Platform Boundary and Image Ownership](../../architecture/adr/ADR-036-shared-ingestion-and-sso-platform-boundary-and-image-ownership.md)
Related design: [Shared Ingestion and SSO Platform Design](../design/SHARED_INGESTION_AND_SSO_PLATFORM_DESIGN.md)
Related checklist: [Shared Ingestion and SSO Platform Repo Migration Checklist](./SHARED_INGESTION_AND_SSO_PLATFORM_REPO_MIGRATION_CHECKLIST.md)

---

## Overview

This plan turns the shared-platform design into an executable migration path.

The goal is to extract reusable ingestion and SSO capabilities out of the application repositories, while centralizing the reusable container images in one place. Both `dq-made-easy` and MaaS should remain thin consumers of that shared foundation.

This is intentionally a staged migration: inventory first, then extraction, then centralized image ownership, then application adoption, then cleanup.

## Progress Summary

| Area | Status | Evidence |
|---|---|---|
| Shared repository and package boundary | Complete | `platform-foundation/packages/platform-foundation` |
| Local wheel distribution | Complete | Docker pypiserver at the env-derived `packages.dev.jac.dot` URL |
| Clean build verification | Complete | `dq-api` and `dq-engine` both build successfully against the local pypiserver. Java moved into `dq-python-base` (no Debian apt-get at build time). Spark jars pre-cached in `tmp/spark-jars-cache/` (no Maven network access at build time). See dq-engine build proof below. |
| First shared OIDC primitive extraction | Complete | `platform_foundation` auth modules; direct `dq-made-easy` imports |
| Shared JWKS/JWT validator extraction | Complete | `JwksCache` + `JwtValidator` + `JwtValidationResult` in `platform_foundation`; 25 unit tests, fail-closed with cryptographic signature verification |
| Shared auth env-var contract | Complete | `AuthConfig` + `load_auth_config()` in `platform_foundation`; canonical `PLATFORM_AUTH_*` prefix with derivation logic |
| Shared claims-to-scope mapping | Complete | `ScopeResolver` + `get_scopes_from_claims()` + `create_dq_scope_resolver()` in `platform_foundation`; hierarchical wildcard + expansion rules; 33 unit tests |
| Shared errors and health packages | Complete | `platform-errors` + `platform-health` in `platform-foundation`; mirrors `metadata-errors` + `metadata-health` with `PLATFORM-*` error IDs |
| dq-engine execution-type cleanup | Complete | `SourceLocation` now lives only in `dq_plan_execution_types`; duplicate definition removed from `gx_dispatch_payload.py` |
| DQ engine shared-type consolidation | Complete | `dq_engine` runtime now uses the single shared `SourceLocation` type and tests cover the default options path |
| Workstream 1 inventories | Complete | Ingestion, SSO/JWKS, and image inventories are linked from the boundary summary |
| Ingestion extraction | Not started | Workstream 2 remains open; file-to-object-storage kernel selected first |
| Shared logging and telemetry packages | Complete | `platform-logging` + `platform-telemetry` in `platform-foundation`; mirrors `metadata-logging` + `metadata-telemetry` |
| Auth extracted to standalone `platform-auth` package | Complete | All auth modules (JWKS/JWT, token providers, auth config, scope mapping) moved to `platform-auth`; `platform-foundation` reverts to config-only. 91 unit tests. No re-exports. |
| dq-made-easy consumers migrated to `platform-auth` | Complete | 10 files across dq-api and dq-engine switched from `platform_foundation` → `platform_auth` imports. requirements.txt updated. |
| MaaS auth adoption | Not started | Workstream 5 remains open |
| Shared ingestion kernel extracted | Complete | `platform-ingestion` package with S3 client, bucket/prefix ops, CSV→Parquet via Spark, and `stage_csv_to_parquet()`. 17 unit tests. Published to pypiserver. |
| Shared ingestion CLI/job entrypoint | Complete | `platform-ingestion-cli` package with engine-agnostic `engine_type` / `runner_type` dispatch; consumers provide the runtime environment. 7 unit tests. |
| dq-made-easy ingestion adapter | Complete | `scripts/stage_local_csv_to_s3_parquet.py` now delegates execution through `platform_ingestion_cli` and registers a DQ-specific runner for the selected transform. 2 adapter tests. |
| Shared test data generator | Complete | `platform-testdata` package with schema-driven deterministic generation, 6 output formats, and Spark column expression builders. 25 unit tests. Published to pypiserver. |
| Shared package test count | 92 tests pass | 9 existing auth + 25 JWKS/JWT + 25 auth_config + 33 scope_mapping |
| Shared image centralization | In progress | `platform-foundation/scripts/build_shared_images.sh`; `platform-foundation/docker/ingestion-runner/Dockerfile` |

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

- [x] (SHARED-I-W1-01) Catalog all real-data ingestion code paths in `dq-made-easy` and classify each one as shared or app-specific. See [ingestion inventory](./SHARED_PLATFORM_INGESTION_INVENTORY.md).
- [x] (SHARED-I-W1-02) Catalog all SSO/OIDC code paths in `dq-made-easy` and classify each one as shared or app-specific. See [SSO/JWKS inventory](./SHARED_PLATFORM_SSO_JWKS_INVENTORY.md).
- [x] (SHARED-I-W1-03) Identify shared container images and identify duplicate Dockerfiles or build logic. See [image inventory](./SHARED_PLATFORM_IMAGE_INVENTORY.md).
- [x] (SHARED-I-W1-04) Decide the shared platform home: use the `platform-foundation` repository with packages under `packages/`.
- [x] (SHARED-I-W1-05) Record the boundary rules so future changes do not reintroduce duplication.
- [x] (SHARED-I-W1-06) Establish the MaaS-style package layout at `platform-foundation/packages/platform-foundation`.
- [x] (SHARED-I-W1-07) Establish NexusCloud-only wheel builds and a Docker-based local pypiserver for cross-repo wheel sharing.

## Workstream 2: Extract Shared Ingestion Capability

- [x] (SHARED-I-W2-01) Move reusable ingestion connectors and helpers into the shared platform.
- [x] (SHARED-I-W2-02) Move reusable test-data generation or fixture-backed real data sources into the shared platform.
- [x] (SHARED-I-W2-03) Provide a shared CLI or job entrypoint for running the ingestion workloads.
- [x] (SHARED-I-W2-04) Keep application-specific orchestration wrappers in `dq-made-easy`.
- [x] (SHARED-I-W2-05) Add tests that prove the shared ingestion package can be consumed without copying code into the app repos.

## Workstream 3: Extract Shared SSO / OIDC Capability

- [x] (SHARED-I-W3-01) Move common OIDC configuration helpers into the shared platform.
- [x] (SHARED-I-W3-02) Move issuer/JWKS validation helpers into the shared platform.
- [x] (SHARED-I-W3-03) Move claims-to-role mapping helpers into the shared platform where the behavior is common.
- [x] (SHARED-I-W3-04) Keep application-specific authorization policy inside each repository.
- [x] (SHARED-I-W3-05) Define the environment-variable contract that both apps will use for shared auth settings.
- [x] (SHARED-I-W3-06) Remove the `dq_utils.auth_utils` compatibility layer and migrate DQ consumers to direct `platform_foundation` imports.
- [x] (SHARED-I-W3-07) Add shared-package unit tests and verify affected DQ API and engine consumers.

## Workstream 4: Centralize Shared Images

- [x] (SHARED-I-W4-01) Create or adapt the shared image build pipeline so reusable images are built in one place. See `platform-foundation/scripts/build_shared_images.sh` and `platform-foundation/docker/ingestion-runner/Dockerfile`.
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

1. Use the completed Workstream 1 inventories as the gate for all additional extraction targets.
2. Finish the remaining Workstream 3 auth contract and validation work before MaaS adoption.
3. Use Workstream 2 to extract the selected file-to-object-storage ingestion kernel.
4. Land Workstream 4 before removing duplicate image definitions.
5. Use Workstream 5 to migrate `dq-made-easy` first, then MaaS, for each shared capability.
6. Use Workstream 6 to delete legacy copies and enforce the new boundary.

## Acceptance Criteria

- [ ] (SHARED-I-AC-01) Reusable ingestion logic exists in one shared location rather than being copied into both repositories.
- [x] (SHARED-I-AC-02) Reusable SSO/OIDC token-provider helpers exist in one shared location rather than being copied into both repositories.
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

1. Extract the file-to-object-storage ingestion kernel selected by the completed ingestion inventory (SHARED-I-W2).
2. Adopt the shared auth package in MaaS (SHARED-I-W5).
3. Define the shared ingestion-runner image naming and tagging scheme.
4. Remove duplicate code paths and enforce the new boundary (SHARED-I-W6).
5. Rebuild and publish `platform_foundation-0.1.1` with auth config + scope mapping to pypiserver.
6. Wire `dq-api` consumers to use `platform_foundation` scope resolver instead of local `auth.py` helpers.
