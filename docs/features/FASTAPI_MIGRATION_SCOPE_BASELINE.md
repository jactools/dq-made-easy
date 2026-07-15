# FastAPI Migration Scope Baseline

Date: 2026-03-29
Owner: API migration stream
Status: Done

## Purpose

This document freezes the migration scope from archived NestJS controllers to FastAPI v1 endpoints and stores the implementation to-do list.

## Ground Rules

- No fallback logic. Missing APIs must fail fast and clearly.
- API payload contract is snake_case only.
- One canonical attribute per meaning.

## Source Of Truth

Legacy controller inventory:
- dq-api/server-archive/app.controller.ts
- dq-api/server-archive/data-contracts.controller.ts
- dq-api/server-archive/governance.controller.ts
- dq-api/server-archive/health.controller.ts
- dq-api/server-archive/rule-versions.controller.ts
- dq-api/server-archive/suggestions.controller.ts

FastAPI v1 router composition:
- dq-api/fastapi/app/api/v1/router.py

FastAPI endpoint modules:
- dq-api/fastapi/app/api/v1/endpoints/*.py

## Baseline Findings

### Fully migrated domains

- Rules core and versioning routes
- Approvals routes
- Workspaces routes
- Data catalog routes
- App config routes
- Admin and me routes
- Auth routes
- Governance drift and revalidation routes
- Batch testing and test proofs routes

### Partially migrated domains

- Suggestions:
  - Present: GET /suggestions/metrics
  - Missing: suggestions list, data sources, request profiling, accept, dismiss, apply, profiling request status, metrics clear

- Reusable assets:
  - Present: list, create, delete for reusable filters and reusable joins
  - Missing: get by id and update by id for reusable filters and reusable joins

- Health compatibility:
  - Present: health, readiness, ready, and live

### Not migrated domains

- Data contracts:
  - Missing full route set for data-contracts listing, single contract retrieval, and quality-rules extraction

### Additional parity gap

- Rules:
  - Delete parity implemented with soft-delete and admin recovery lifecycle

## Stored To-Do

- [x] Finalize migration scope baseline
- [x] Migrate Suggestions endpoints first
- [x] Add Data Contracts endpoints
- [x] Close reusable asset parity
- [x] Add missing rules delete route
- [x] Add health alias parity routes
- [x] Add contract and auth tests
- [x] Update docs and version manifest

## Acceptance Criteria For Task 1

- Legacy controller surface inventoried
- FastAPI v1 route surface inventoried
- Gaps categorized into fully migrated, partial, and missing
- To-do list persisted in repository
- Priority order defined for implementation

## Implementation Priority

1. Suggestions endpoints
2. Data contracts endpoints
3. Reusable asset get/update parity
4. Rules delete parity
5. Health alias parity
6. Contract and auth tests
7. Documentation and version manifest updates
