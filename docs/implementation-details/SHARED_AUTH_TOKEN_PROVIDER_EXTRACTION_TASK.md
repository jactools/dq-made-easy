# Shared Auth Token Provider Extraction Task

**Status**: Implemented in prototype  
**Date**: 2026-08-03  
**Workstream**: 1 — Inventory and Boundary Definition  
**Focus**: Candidate A — Shared OIDC token-provider foundation

---

## Purpose

This document starts the first concrete extraction task for the shared-platform migration.

The task is to isolate the reusable OIDC token-provider and token URL resolution logic so it can become the first shared auth primitive for `dq-made-easy` and `metadata-as-a-service`.

This task stays in `dq-made-easy` because it describes migration and execution details.

---

## Why this is the first extraction task

The auth token-provider code is:

- small enough to extract safely
- already reused across multiple callers
- easy to verify with unit tests
- a good foundation for later shared ingestion runtime wiring

Starting here gives us a low-risk proof that the shared boundary works.

---

## Current Code Surface

### Core shared candidate

- `dq-utils/src/dq_utils/auth_utils.py`

### Current consumers in `dq-made-easy`

- `dq-engine/dq_plan_execution_api.py`
- `dq-engine/gx_dispatch_config.py`
- `dq-engine/test_data_materialization_worker.py`
- `dq-api/fastapi/app/application/services/openmetadata_definition_importer.py`
- `dq-api/fastapi/app/application/services/registry_definition_resolver.py`
- `dq-api/fastapi/app/application/services/product_spec_resolver.py`
- `dq-api/fastapi/app/application/services/data_contract_resolver.py`

### Existing tests

- `dq-utils/tests/test_auth_utils.py`
- `dq-api/fastapi/tests/application/services/test_registry_definition_resolver.py`
- `dq-api/fastapi/tests/application/services/test_data_contract_resolver.py`

---

## Boundary Target

### Shared platform responsibilities

These are now shared primitives in `platform-foundation/packages/platform-foundation/src/platform_foundation`:

- `StaticTokenProvider`
- `OidcClientCredentialsTokenProvider`
- `AuthConfigError`
- `TokenProvider` protocol
- `TokenBundle`
- `resolve_oidc_token_url`
- `build_token_provider_from_env`
- `build_oidc_token_provider_from_env`

### Consumer responsibilities

These should remain in the product repos:

- app-specific env var names
- app-specific token source selection
- domain-specific auth policy
- route authorization rules
- app-specific tests for each consumer flow

---

## Extraction Plan

### Step 1: Confirm the shared primitive set

Verify that the listed types and helpers are the only reusable pieces needed by both repos.

### Step 2: Freeze the public auth surface

Define the shared API surface that consumers will import.

This should be stable enough that both repos can depend on it without copying logic.

### Step 3: Identify app-specific wrappers

Any code that only maps repo-specific env vars into the shared helpers should stay in the consumer repos.

### Step 4: Decide the packaging location

Place the shared auth primitives in the shared platform home established by `platform-foundation`.

### Step 5: Update consumers

Move consumers to the shared package or shared module path, keeping local wrappers thin.

### Step 6: Retain tests

Keep unit tests for the shared auth primitives and add consumer tests that verify the wrappers still behave correctly.

---

## First Questions to Resolve

1. Should the env-driven helpers stay generic, or should the shared package also expose a higher-level config object?
2. Should `build_token_provider_from_env` be the canonical shared entrypoint, or should consumers use the lower-level providers directly?
3. Which app-specific env var names should be normalized first?
4. Do any consumers need a static-token fallback that should remain outside the shared package?

---

## Acceptance Criteria

- [x] The reusable auth primitives have a single shared ownership target.
- [x] Compatibility wrappers have been removed; consumers import `platform_foundation` directly.
- [x] The shared auth surface is documented and implemented.
- [x] Shared-package and consumer tests identify the expected behavior.
- [x] The next implementation step can proceed without ambiguity.

## Remaining Release Step

The local Docker pypiserver now serves `platform-foundation==0.1.0`. Clean `dq-made-easy` build/install flows still need to receive the env-derived local index URL instead of relying on an editable checkout.

---

## Next Step

Implement the shared JWKS/JWT validator and auth environment contract tracked by Workstream 3.
