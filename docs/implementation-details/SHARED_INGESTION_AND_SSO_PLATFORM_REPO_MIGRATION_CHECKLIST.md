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

### Candidate 1: File-to-object-storage real-data ingestion

**Source file**

- `scripts/stage_local_csv_to_s3_parquet.py`

**Why this is the first candidate**

- It is the only identified production path that ingests caller-supplied row data.
- It transforms CSV data to Parquet and uploads it to S3-compatible storage.
- Its transport and transformation mechanics can be separated from DQ join-pair naming and catalog resolution.

**What should move to the shared platform**

- explicit source-file validation
- CSV-to-Parquet transformation
- reusable S3-compatible client configuration
- bucket/prefix writes and checksums
- typed ingestion result with row/file counts

**What should stay in `dq-made-easy`**

- join-pair case/role/version naming
- DQ catalog and delivery resolution
- DQ-specific destination policy and wrapper CLI

---

### Candidate 2: Delivery object synthetic verification generation

**Source files**

- `scripts/seed_delivery_objects.py`
- related `dq-db/mock-data` delivery and schema CSVs

This is a valuable second candidate, but it generates synthetic data rather than ingesting real source rows. Share the schema-driven multi-format generation and upload mechanics; keep DQ seed catalogs and delivery semantics in DQ.

The playground source bundle flow is not a real-data candidate: it stores JSON metadata records containing URLs and licenses, not the referenced datasets.

---

### Candidate 3: Shared OIDC token-provider foundation

**Source files**

- `platform-foundation/packages/platform-foundation/src/platform_foundation`

**Status**: Extracted for DQ; MaaS adoption remains.

The package now owns token providers, retry/caching behavior, token URL resolution, and env-driven factories. DQ imports it directly without a compatibility shim.

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

- [x] Confirm the shared platform home: `platform-foundation` with packages under `packages/`.
- [x] Classify each ingestion/auth file as shared, adapter, or app-specific.
- [x] Identify all Dockerfiles and image build paths that would be duplicated across repos.
- [ ] Record the exact env var contract that the shared platform will own.

### Phase 2: Extract the first ingestion candidate

- [ ] Extract the generic file-to-object-storage kernel from `stage_local_csv_to_s3_parquet.py`.
- [ ] Move CSV-to-Parquet and S3 upload helpers into the shared platform.
- [ ] Keep DQ join-pair/catalog behavior in a thin DQ entrypoint.
- [ ] Add shared-package tests with one explicit real CSV fixture.
- [ ] Prove both DQ and MaaS can consume the same ingestion result contract.

### Phase 3: Extract the first auth candidate

- [x] Extract token-provider primitives to `platform_foundation` and migrate DQ consumers directly.
- [ ] Extract fail-closed JWKS/JWT validation from the Airflow-proven mechanics.
- [x] Keep app-specific role mapping and authorization policy in each consuming application.
- [ ] Add tests proving both apps can use the same auth env contract.

### Phase 4: Centralize images

- [x] Create one canonical build pipeline for the shared ingestion/auth images.
- [x] Publish images with versioned tags in one registry namespace.
- [x] Update `dq-made-easy` to consume those tags instead of rebuilding duplicate images.
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

1. Extract the **file-to-object-storage real-data ingestion kernel**.
2. Extract **fail-closed JWKS/JWT validation**.
3. Define the shared auth environment contract and adopt it in MaaS.
4. Add **delivery object synthetic multi-format generation**.
5. Build the shared ingestion runner image.
6. Revisit connector providers after comparing the MaaS connector contract.

---

## Acceptance Criteria

- [ ] The first reusable ingestion path has a shared home outside `dq-made-easy`.
- [x] The first reusable auth foundation exists in one shared location.
- [ ] The shared images are published once and referenced by both repos.
- [ ] `dq-made-easy` keeps only thin adapters around the shared functionality.
- [ ] MaaS can adopt the same shared artifacts without copy-paste.
- [ ] A follow-up cleanup removes the duplicated code paths.

---

## Open Questions

1. What exact auth environment names become the shared contract?
2. Should password-grant support remain in the shared package after all browser and service flows migrate?
3. Which registry namespace and tags should own the ingestion, Keycloak, and trust-bundle images?
4. Which MaaS real CSV dataset should prove the first shared ingestion vertical slice?

---

## Next Steps

1. Create the file-to-object-storage extraction task with module boundaries and test fixtures.
2. Define and implement the provider-neutral JWKS/JWT validator.
3. Define the shared auth env contract.
4. Wire clean DQ installs through the local pypiserver.
