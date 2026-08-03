# Shared Ingestion and SSO Platform Design

**Status**: Draft
**Date**: 2026-08-03
**Owner**: dq-made-easy / MaaS platform alignment
**Related systems**: `dq-made-easy`, `metadata-as-a-service`
**Related decision**: [ADR-036 Shared Ingestion and SSO Platform Boundary and Image Ownership](../../architecture/adr/ADR-036-shared-ingestion-and-sso-platform-boundary-and-image-ownership.md)
**Related implementation plan**: [Shared Ingestion and SSO Platform Implementation Plan](../implementation-details/SHARED_INGESTION_AND_SSO_PLATFORM_IMPLEMENTATION_PLAN.md)
**Related checklist**: [Shared Ingestion and SSO Platform Repo Migration Checklist](../implementation-details/SHARED_INGESTION_AND_SSO_PLATFORM_REPO_MIGRATION_CHECKLIST.md)

---

## 1. Purpose

This document defines the target design for sharing two cross-cutting capabilities between `dq-made-easy` and `metadata-as-a-service` (MaaS):

1. **Real data ingestion workloads** for verification and demo purposes.
2. **SSO / OIDC integration** so both products can authenticate against the same identity provider and share the same auth patterns.

The key requirement is to **avoid copy-paste** between the repositories and to keep **containers/images in one place** rather than duplicating them in both projects.

---

## 2. Problem Statement

Today the two repositories have overlapping needs:

- `dq-made-easy` already contains real ingestion flows that can be used for DQ validation.
- MaaS needs real ingestion workloads for verification and future operational scenarios.
- `dq-made-easy` already has SSO integration.
- MaaS needs SSO integration, but that work is still planned.
- Both systems would benefit from the same base container images, service wiring, and local-dev orchestration.

Duplicating this functionality would create:

- duplicate maintenance effort
- inconsistent auth behavior
- drift in ingestion behavior across repos
- duplicate Dockerfiles and image build logic
- higher risk of fixing one repo while leaving the other outdated

---

## 3. Design Goals

1. **Single source of truth** for shared ingestion logic and shared SSO logic.
2. **Single source of truth** for reusable container images.
3. **Thin repository adapters** in each application repo.
4. **Versioned consumption** so each repo can adopt shared changes deliberately.
5. **Low-friction local development** and CI usage.
6. **Clear ownership boundaries** between shared platform code and app-specific code.

---

## 4. Non-Goals

This design does **not** aim to:

- merge `dq-made-easy` and MaaS into one repository
- move all app logic into shared modules
- redesign the DQ or metadata domains
- standardize every service in both repos immediately
- replace app-specific UI, business rules, or persistence layers

The shared platform should cover only the reusable foundation pieces.

---

## 5. Proposed Approach

### 5.1 Create a shared platform boundary

Extract shared capabilities into a dedicated shared platform area, ideally a separate repository or clearly versioned package set.

The shared platform owns:

- real ingestion implementations
- ingestion test harnesses and reusable fixtures
- SSO / OIDC helpers
- shared Docker images
- shared startup scripts for reusable services
- common environment contracts

Each application repo owns:

- app-specific orchestration
- domain-specific validation
- app-specific endpoints and UI flows
- repository-specific configuration
- app-specific composition of the shared building blocks

### 5.2 Use versioned artifacts

Both repos consume the shared platform through versioned artifacts:

- language packages for reusable code
- Docker images for reusable runtime services
- compose snippets or overlays for local stacks

This keeps changes explicit and reviewable.

### 5.3 Centralize image building

Build shared images in one place only.

Recommended model:

- one CI pipeline builds shared base images and service images
- images are pushed to a registry under a shared namespace
- both `dq-made-easy` and MaaS reference the same image tags
- app repos do not duplicate Dockerfiles for the shared services

---

## 6. Architecture Overview

### 6.1 Layered structure

The target structure is:

1. **Shared Platform**
   - reusable ingestion engines/connectors
   - auth/SSO integration helpers
   - shared containers
   - shared fixtures and test data

2. **Application Adapters**
   - thin integration layer in each repo
   - app-specific configuration and wiring
   - repo-specific route registration, CLI entrypoints, or job definitions

3. **Application Domain**
   - DQ behavior in `dq-made-easy`
   - metadata behavior in MaaS

### 6.2 Responsibility split

| Concern | Shared platform | dq-made-easy | MaaS |
|---|---:|---:|---:|
| Real data ingestion code | Yes | No | No |
| Ingestion orchestration wiring | Partial | Yes | Yes |
| SSO/OIDC helpers | Yes | No | No |
| App-specific login routes | No | Yes | Yes |
| Shared Docker images | Yes | No | No |
| App-specific containers | No | Yes | Yes |
| Test fixtures for shared scenarios | Yes | Limited | Limited |
| Domain validation | No | Yes | Yes |

---

## 7. Shared Ingestion Design

### 7.1 Ingestion responsibilities

The shared ingestion layer should contain only reusable mechanics:

- source connectors
- schema extraction helpers
- transform/load utilities
- standard retry/error handling
- validation hooks that are generic enough to reuse
- fixture-backed real data feeds for verification

The application repositories should provide:

- which ingestions are enabled
- which targets they load into
- domain rules that interpret the ingested data
- environment-specific credentials and endpoints

### 7.2 Ingestion packaging

Preferred packaging options:

- Python package for ingestion jobs and helpers
- shared CLI entrypoints for local execution and CI
- container image(s) for runtime execution

The shared package should be importable from both repos without vendoring or copying code.

### 7.3 Ingestion test strategy

The shared platform should include:

- unit tests for ingestion transforms and connectors
- contract tests for source/target payloads
- integration tests for containerized execution
- reusable sample datasets for verification

Each app repo may add its own tests around the integration boundary, but not duplicate the shared implementation tests.

---

## 8. Shared SSO Design

### 8.1 Shared SSO responsibilities

The shared auth layer should contain:

- OIDC configuration helpers
- token validation primitives
- claims-to-role mapping helpers
- common callback/session utilities
- standardized logout and refresh handling where appropriate

### 8.2 App-specific auth behavior

Each app still owns:

- authorization policy
- role-based route protection
- app-specific identity mapping rules if they differ
- UI state or session behavior tied to app semantics

### 8.3 Auth deployment model

Both repos should use the same identity-provider integration pattern:

- same issuer or trusted issuer set
- same JWKS validation approach
- same environment variable contract where possible
- same containerized auth-sidecars or helper services if needed

---

## 9. Container and Image Strategy

### 9.1 Single image ownership

The shared platform is the canonical owner of reusable images.

This includes images for:

- ingestion execution
- shared auth support services, if any
- common test harness containers
- any reusable data-loading utilities

### 9.2 Consumer behavior

`dq-made-easy` and MaaS should:

- reference shared image tags from the registry
- avoid rebuilding identical images locally unless explicitly needed for development
- use app-specific override files only for app-specific differences

### 9.3 Tagging and release discipline

Images should be versioned so consumers can pin stable releases.

Example pattern:

- `shared-ingestion:1.2.0`
- `shared-auth:1.2.0`
- `shared-test-data:1.2.0`

Each repo can then decide when to upgrade.

---

## 10. Recommended Repository Boundary

### 10.1 Shared platform repository

A dedicated shared repository is the recommended design if these capabilities will continue to grow.

That repository would own:

- ingestion source code
- SSO helpers
- Dockerfiles and image build pipeline
- reusable compose fragments
- reusable fixtures and test data

### 10.2 Application repositories

`dq-made-easy` and MaaS would each contain only:

- app-specific glue code
- references to shared packages/images
- environment composition for their own stack
- business logic and UX specific to the product

This gives each repo a small, explicit dependency on the shared platform.

---

## 11. Migration Plan

### Phase 1 — Inventory

- Identify all current ingestion-related code in `dq-made-easy`.
- Identify current or planned auth/SSO code in `dq-made-easy`.
- Mark what is reusable vs app-specific.

### Phase 2 — Extract shared ingestion code

- Move reusable ingestion logic into the shared platform.
- Keep app-specific orchestration in `dq-made-easy`.
- Add versioned package consumption.

### Phase 3 — Extract shared SSO code

- Move common auth/OIDC helpers into the shared platform.
- Keep app-specific authorization rules in each app.
- Standardize environment contract where possible.

### Phase 4 — Centralize images

- Build shared containers from the shared platform only.
- Update both repos to consume registry-published image tags.
- Remove duplicate Dockerfiles and build scripts.

### Phase 5 — Clean up duplicates

- Delete copied code paths from each app repo.
- Keep only adapters and app-specific wrappers.
- Document the final dependency graph.

---

## 12. Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Shared repo becomes too broad | Harder ownership | Keep the shared boundary narrow and reusable only |
| Version drift between repos | Inconsistent behavior | Pin versions and upgrade deliberately |
| Auth assumptions differ between apps | Integration friction | Keep auth helpers low-level and app policy separate |
| Image registry dependency breaks local dev | Slower setup | Provide a local override path for development-only builds |
| Shared ingestion becomes app-specific over time | Shared code erosion | Enforce clear boundary reviews before extraction |

---

## 13. Decision Summary

The recommended design is to **extract real ingestion and SSO functionality into a shared platform layer**, with `dq-made-easy` and MaaS consuming it as thin clients.

The shared platform should also own the reusable container images so they are built and published once, not duplicated across repositories.

This gives the teams:

- one implementation of shared capabilities
- one image source of truth
- lower maintenance cost
- clearer separation of concerns
- easier future rollout of MaaS SSO and verification ingestions

---

## 14. Open Questions

1. Should the shared platform be a new repository or an existing repository split into a shared package area?
2. Which ingestion jobs are truly reusable versus product-specific?
3. Should the shared platform publish Python packages, container images, or both on day one?
4. What identity provider assumptions are common to both apps?
5. Which build pipeline should become the canonical image publisher?

---

## 15. Next Steps

1. Confirm the shared boundary and repository ownership model.
2. Inventory existing ingestion and SSO code in `dq-made-easy`.
3. Identify the first reusable ingestion candidate to extract.
4. Define the shared image naming/tagging scheme.
5. Draft the corresponding extraction plan once the design is approved.
