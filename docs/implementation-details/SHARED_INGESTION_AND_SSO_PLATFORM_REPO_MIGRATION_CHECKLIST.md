# Shared Ingestion and SSO Platform Repo Migration Checklist

**Status**: Draft  
**Date**: 2026-08-03  
**Applies to**: `dq-made-easy` first, then MaaS  
**Related ADR**: [ADR-036 Shared Ingestion and SSO Platform Boundary and Image Ownership](../../architecture/adr/ADR-036-shared-ingestion-and-sso-platform-boundary-and-image-ownership.md)  
**Related design**: [Shared Ingestion and SSO Platform Design](../design/SHARED_INGESTION_AND_SSO_PLATFORM_DESIGN.md)  
**Related implementation plan**: [Shared Ingestion and SSO Platform Implementation Plan](./SHARED_INGESTION_AND_SSO_PLATFORM_IMPLEMENTATION_PLAN.md)

---

## Purpose

This checklist turns the shared-platform design into an actionable repo-level migration path.

The first goal is to identify the earliest reusable extraction points in `dq-made-easy`, then move those capabilities into a shared platform boundary without duplicating code or container images.

---

## Migration Strategy

1. **Start with the most reusable ingestion path**.
2. **Extract the shared auth foundation next**.
3. **Centralize image ownership once the first consumers are stable**.
4. **Adopt the shared artifacts in MaaS**.
5. **Delete the copied code and duplicate images only after both consumers run on the shared versions**.

---

## First Concrete Extraction Candidates from `dq-made-easy`

### Candidate 1: Delivery object seeding / verification ingestion

**Source files**

- `scripts/seed_delivery_objects.py`
- `dq-db/mock-data/data-deliveries.csv`
- `dq-db/mock-data/data-delivery-notes.csv`
- `dq-db/mock-data/data-objects.csv`
- `dq-db/mock-data/data-object-versions.csv`
- `dq-db/mock-data/attributes-catalog.csv`

**Why this is the first candidate**

- It is a real data ingestion path, not just mock seeding.
- It generates and uploads delivery objects into AIStor/S3-compatible storage.
- The logic is broadly useful for verification and demo scenarios.
- The script already depends on reusable Spark/runtime setup, which makes it a good candidate for a shared containerized ingestion runner.

**What should move to the shared platform**

- delivery-plan parsing and validation
- delivery-format generation helpers
- object-key and URI normalization helpers
- Spark runtime configuration helpers for supported delivery formats
- reusable upload/publish service logic
- shared fixture loading for delivery and note CSVs

**What should stay in `dq-made-easy`**

- product-specific defaults
- DQ domain assumptions tied to the current seed data model
- repo-specific CLI wrappers or operator entrypoints

---

### Candidate 2: Playground source bundle ingestion

**Source files**

- `dq-api/fastapi/app/application/services/playground_source_bundles.py`
- `scripts/ingest_playground_source_bundles.py`

**Why this is the second candidate**

- It already implements a reusable ingestion workflow into AIStor.
- The pattern is generic: build records, store JSON payloads, skip duplicates, fail fast on missing config.
- The service already has a clean boundary between orchestration and storage behavior.
- It is a strong model for the shared ingestion style that MaaS can later consume.

**What should move to the shared platform**

- bucket/prefix bootstrapping
- object existence checks and idempotent ingest behavior
- payload hashing and record creation
- generic S3 client creation from env
- reusable ingestion service scaffolding

**What should stay in `dq-made-easy`**

- the specific bundle catalog content
- the DQ-branded bundle list if it is product-specific
- application-specific wrappers and CLI flags

---

### Candidate 3: Shared OIDC token-provider foundation

**Source files**

- `dq-utils/src/dq_utils/auth_utils.py`

**Why this is the first auth candidate**

- The module already contains the reusable auth/token-provider primitives.
- MaaS can reuse the same env-to-provider behavior.
- The code is the natural shared foundation for client-credentials and token URL resolution.

**What should move or be standardized for MaaS**

- `resolve_oidc_token_url`
- `build_token_provider_from_env`
- `build_oidc_token_provider_from_env`
- token provider interfaces and error types
- common retry and caching behavior

**What should stay app-specific**

- route authorization rules
- claims-to-role mappings that differ by app
- UI/session behavior

---

### Candidate 4: Airflow Keycloak adapter logic

**Source file**

- `docker/airflow/webserver_config.py`

**Why this is a candidate**

- It contains the Airflow-specific Keycloak/OIDC adapter code.
- The JWT decoding and role mapping pattern is reusable, even if the exact role mapping is not.
- It is a clear seam for extracting common auth helpers without moving the Airflow integration itself.

**What should move to the shared platform**

- JWKS lookup helper logic
- reusable JWT claim extraction helpers
- generic realm-role normalization helpers
- generic claims-to-app-role mapping helpers

**What should stay in the Airflow adapter**

- Airflow/FAB configuration constants
- the Airflow-specific security manager class
- any Airflow-only auth wiring

---

## Repo-Level Migration Checklist

### Phase 1: Inventory and boundaries

- [ ] Confirm the shared platform home: separate repository or versioned shared package area.
- [ ] Classify each ingestion/auth file as shared, adapter, or app-specific.
- [ ] Identify all Dockerfiles and image build paths that would be duplicated across repos.
- [ ] Record the exact env var contract that the shared platform will own.

### Phase 2: Extract the first ingestion candidate

- [ ] Lift the delivery object seeding logic into a shared ingestion package or shared service module.
- [ ] Move Spark/runtime setup helpers into the shared platform.
- [ ] Move CSV/fixture loading helpers into the shared platform.
- [ ] Keep the DQ-specific wrapper script as a thin entrypoint only.
- [ ] Add tests for the shared ingestion package independent of `dq-made-easy`.

### Phase 3: Extract the first auth candidate

- [ ] Promote `dq-utils.auth_utils` to the canonical shared auth foundation for MaaS and `dq-made-easy`.
- [ ] Extract or normalize JWKS/JWT claim helper logic from the Airflow adapter.
- [ ] Keep app-specific role mapping and authorization policy in each consuming application.
- [ ] Add tests proving both apps can build token providers from the same env contract.

### Phase 4: Centralize images

- [ ] Create one canonical build pipeline for the shared ingestion/auth images.
- [ ] Publish images with versioned tags in one registry namespace.
- [ ] Update `dq-made-easy` to consume those tags instead of rebuilding duplicate images.
- [ ] Update MaaS to consume the same tags.
- [ ] Remove duplicate Dockerfiles after both consumers have switched.

### Phase 5: Adopt in MaaS

- [ ] Wire MaaS to the same shared ingestion package.
- [ ] Wire MaaS to the same shared auth foundation.
- [ ] Add only thin MaaS adapters where behavior differs.
- [ ] Validate MaaS startup against the shared images.

### Phase 6: Cleanup and enforcement

- [ ] Remove temporary compatibility shims.
- [ ] Delete copied logic from `dq-made-easy` and MaaS.
- [ ] Add validation that flags reintroduced duplication.
- [ ] Document the final ownership model.

---

## Suggested Execution Order

1. Extract **Delivery object seeding**.
2. Extract **shared OIDC token-provider behavior**.
3. Centralize the first shared images.
4. Extract **Playground source bundle ingestion** if it is approved as shared beyond `dq-made-easy`.
5. Extract **Airflow Keycloak adapter helpers**.
6. Repeat the same pattern in MaaS.

---

## Acceptance Criteria

- [ ] The first reusable ingestion path has a shared home outside `dq-made-easy`.
- [ ] The first reusable auth foundation exists in one shared location.
- [ ] The shared images are published once and referenced by both repos.
- [ ] `dq-made-easy` keeps only thin adapters around the shared functionality.
- [ ] MaaS can adopt the same shared artifacts without copy-paste.
- [ ] A follow-up cleanup removes the duplicated code paths.

---

## Open Questions

1. Should the shared platform be a separate repository from day one, or should it start as a versioned package area?
2. Is `scripts/seed_delivery_objects.py` the first shared ingestion target, or should `playground_source_bundles` be extracted first because it is smaller?
3. Should the shared platform own only auth primitives, or also the Airflow/JWKS adapter layer?
4. What image names and tags should become the canonical shared contract?

---

## Next Steps

1. Approve the first extraction candidate list.
2. Decide the shared platform home.
3. Split the first extraction into a work item with test coverage.
4. Start with `scripts/seed_delivery_objects.py` unless there is a stronger priority from MaaS.
