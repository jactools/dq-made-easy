# DQ-5 Advanced Data Profiling and Suggestions API Boundary

Status: Done

Goal: strengthen advanced profiling and AI-powered suggestions by moving the suggestions feature onto the internal app API pattern used elsewhere in FastAPI, so the endpoint no longer depends directly on PostgreSQL/SQLAlchemy details.

Current status: the suggestions workflow now uses repository-backed persistence, dependency injection, and repository-backed tests for profiling requests, suggestions, and natural-language draft handling.

## Why this exists

The profiling-and-suggestions flow is a good candidate for stronger persistence abstraction because it is still implemented with direct ORM/session access in the endpoint layer. This makes PostgreSQL harder to replace cleanly and makes the feature harder to test in isolation than other domains that already use repository interfaces and dependency injection.

This track does not change the user-facing suggestions workflow. It changes the backend boundary so profiling requests, suggestion review, and suggestion state transitions are executed through an internal app API contract instead of endpoint-local SQLAlchemy logic.

## Scope

### In scope

- Define domain entities for suggestions, suggestion interactions, profiling requests, and source metadata
- Add a `SuggestionsRepository` protocol and concrete implementations
- Move suggestion persistence and audit logic into infrastructure repositories
- Wire the suggestions endpoints through dependency injection in the same style as other FastAPI domains
- Preserve the existing HTTP contract for the suggestions endpoints unless a deliberate schema change is approved
- Add repository-level and endpoint-level tests that verify fail-fast behavior and status transitions

### Out of scope

- Converting suggestions into a separate HTTP microservice
- Changing the preview-feature UX or rule-creation flow from accepted/applied suggestions
- Adding silent fallback behavior when persistence or profiling prerequisites are unavailable

## User-facing outcome

Users keep the same profiling and suggestions workflow, but the backend boundary becomes consistent with the rest of the application. That makes the suggestions feature easier to test, easier to evolve, and less tightly coupled to PostgreSQL.

## Tracked Work Items

- [x] `DQ-5.1` Define domain entities and a `SuggestionsRepository` protocol for suggestions, interactions, profiling requests, and source metadata
- [x] `DQ-5.2` Implement `PostgresSuggestionsRepository` by moving the current endpoint helper logic into infrastructure
- [x] `DQ-5.3` Add `InMemorySuggestionsRepository` for test isolation and parity with other repository-backed domains
- [x] `DQ-5.4` Update dependency wiring so suggestions endpoints resolve repositories through the internal app API pattern
- [x] `DQ-5.5` Refactor suggestions endpoints to remove direct SQLAlchemy, ORM-row, and session imports
- [x] `DQ-5.6` Add tests for profiling cooldown, suggestion status transitions, interaction audit writes, and metrics-clearing behavior
- [x] `DQ-5.7` Confirm the generated internal API contract remains stable unless an intentional HTTP schema change is introduced

## Acceptance Criteria

- [x] Suggestions endpoints do not import SQLAlchemy statements, ORM rows, or `session_scope` directly
- [x] Profiling requests and suggestion actions execute through a repository boundary with explicit fail-fast errors on missing persistence prerequisites
- [x] The existing suggestions HTTP request/response shapes remain stable during the decoupling refactor
- [x] Repository-backed tests cover cooldown enforcement, user resolution, status transitions, and interaction audit history
- [x] The feature remains compatible with the existing preview-feature workflow for request profiling, review suggestions, accept, apply, and dismiss actions

## Related References

- [DQ feature rollup](/docs/features/DQ_FEATURES/)
- [Legacy feature summary](/docs/features/)
- [Internal API contracts](../../contracts/internal-api)