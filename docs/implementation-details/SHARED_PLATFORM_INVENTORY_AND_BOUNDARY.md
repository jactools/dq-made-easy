# Shared Platform Inventory and Boundary

**Status**: Complete  
**Date**: 2026-08-03  
**Scope**: Workstream 1 — Inventory and Boundary Definition

## Purpose

This document is the Workstream 1 summary. Detailed inventories remain in `dq-made-easy` because they describe migration and execution decisions rather than the `platform-foundation` target-state.

## Completed Inventories

| Work item | Inventory | Key result |
|---|---|---|
| SHARED-I-W1-01 | [Shared Platform Ingestion Inventory](./SHARED_PLATFORM_INGESTION_INVENTORY.md) | The connector framework syncs metadata, not row data. The first real-data extraction should come from `stage_local_csv_to_s3_parquet.py`. |
| SHARED-I-W1-02 | [Shared Platform SSO and JWKS Inventory](./SHARED_PLATFORM_SSO_JWKS_INVENTORY.md) | Token providers are shared; JWKS verification and claim extraction are next. Product authorization remains consumer-owned. |
| SHARED-I-W1-03 | [Shared Platform Image and Build Inventory](./SHARED_PLATFORM_IMAGE_INVENTORY.md) | Start with an ingestion runner, neutral Keycloak runtime, and trust-bundle utility; do not move the full DQ engine. |
| SHARED-I-W1-04 | Repository decision | Shared source and packages live in `platform-foundation`. |
| SHARED-I-W1-05 | Boundary rules | Shared protocol/runtime mechanics move; product policy and adapters remain with consumers. |
| SHARED-I-W1-06 | Package structure | MaaS-style package layout exists at `platform-foundation/packages/platform-foundation`. |
| SHARED-I-W1-07 | Package distribution | NexusCloud-only wheel build and local Docker pypiserver are operational. |

## Final Boundary

### `platform-foundation` owns

- reusable ingestion transport, transformation, and storage primitives
- provider-neutral OIDC discovery, token acquisition, JWKS verification, and claims extraction
- shared package and wheel distribution tooling
- neutral ingestion/auth/trust container images
- generic image build and publish mechanics

### Consumer repositories own

- DQ or MaaS domain logic and orchestration
- API routes, UI state, permissions, roles, and tenant/workspace policy
- database schemas, migrations, and seed data
- Keycloak realms, clients, users, redirects, and product role mappings
- application Dockerfiles, entrypoints, and service-specific dependencies

## Corrected Ingestion Priority

The earlier candidate list treated playground source bundles as real ingestion. The completed inventory shows that this flow stores source metadata only. The implementation order is now:

1. file-to-object-storage ingestion kernel from `scripts/stage_local_csv_to_s3_parquet.py`
2. schema-driven synthetic multi-format generation from `scripts/seed_delivery_objects.py`
3. connector protocol/provider extraction after comparing the MaaS connector contract

## Next Work

- SHARED-I-W3-02: shared fail-closed JWKS/JWT validator
- SHARED-I-W3-05: shared auth environment contract
- SHARED-I-W2-01: first real-data ingestion kernel
- SHARED-I-W4-01: shared ingestion runner image after the kernel exists
