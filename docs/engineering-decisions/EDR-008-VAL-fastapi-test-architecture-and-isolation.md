# EDR-008 [VAL]: FastAPI Test Architecture and Isolation

**Status**: Accepted
**Date**: 2026-04-19
**Tag**: VAL

## Context
FastAPI API tests in this repository run in a mixed environment: the global test harness can expose database-backed state and shared singleton dependencies, while many endpoint tests expect deterministic in-memory repositories and explicitly seeded fixture data.

That mismatch caused a recurring class of failures where the endpoint logic was correct, but tests failed because state leaked across modules or because the wrong repository implementation was used for the test's intent.

Observed failure modes included:
- database-backed configuration leaking into tests that expected in-memory defaults
- per-request repository recreation breaking multi-step workflows inside a single test
- shared in-memory singleton repositories retaining state across modules
- tests assuming worker-side completion or seeded runtime artifacts that are not present in API-only test execution

## Decision
Adopt the following FastAPI API test isolation rules:

- Tests that assert deterministic endpoint behavior must explicitly override repository dependencies to the intended in-memory or test-local implementation instead of relying on ambient global test configuration.
- When an endpoint test exercises a multi-step flow, it must use one shared in-memory repository instance per test via dependency overrides rather than constructing a fresh repository on every request.
- Shared singleton repositories in application dependency modules must be reset or replaced when tests mutate their state.
- API tests must not assume background workers run implicitly; if completed worker-side state is required, the test must simulate or seed that state explicitly.
- Tests that need fail-fast behavior for missing infrastructure must force that behavior explicitly, for example by monkeypatching the infrastructure lookup or error path, instead of depending on ambient environment configuration.

## Rationale
- The repository contains both in-memory and database-backed test paths; endpoint tests need to state which one they are validating.
- Shared dependency singletons are convenient in app code but unsafe in tests unless isolation is explicit.
- Reusing one repository instance per test preserves realistic multi-step behavior while still keeping tests isolated from the rest of the suite.
- Explicit worker-state simulation keeps API tests focused on API behavior instead of accidentally depending on external async processes.
- Fail-fast infrastructure assertions are more stable when the test triggers them deliberately instead of inheriting whatever environment the suite happened to set.

## Scope Boundaries
This decision applies to FastAPI endpoint and API-integration tests in this repository.

It does not by itself define:
- every fixture implementation detail in `tests/conftest.py`
- database integration test strategy for end-to-end or smoke environments
- frontend test architecture
- worker or background-job validation coverage outside API tests

## Consequences
**Positive**
- API tests become deterministic and less sensitive to suite ordering.
- Repository implementation choice is explicit in each test cluster.
- Multi-step endpoint workflows are validated against stable per-test state.
- Fail-fast behavior is tested directly instead of being masked by ambient environment leaks.

**Negative**
- Test modules must do more setup work instead of relying on shared defaults.
- Dependency override lists can be verbose for endpoints that touch several repositories.
- Test authors need to understand when to reuse one repository instance versus replacing a singleton.

## Implementation Guidance
- Override app dependencies through `app.dependency_overrides` for endpoint tests that need in-memory determinism.
- Reuse one repository instance per test for create-update-approve-validate style flows.
- Reset or replace shared singleton repositories such as app-config repositories before asserting default-driven behavior.
- Seed or simulate worker-completed state explicitly in API tests that inspect completed profiling or validation outcomes.
- Monkeypatch explicit fail-fast helpers when a test needs to verify 4xx or 5xx behavior caused by missing infrastructure.

## Related Artifacts
- `/memories/repo/dq-rulebuilder-fastapi-api-test-isolation-tail-clusters-note.md`
- `/memories/repo/dq-rulebuilder-fastapi-app-config-test-isolation-note.md`
- `/memories/repo/dq-rulebuilder-fastapi-auth-endpoint-test-isolation-note.md`
- `/memories/repo/dq-rulebuilder-fastapi-rules-endpoint-test-isolation-note.md`
- `dq-api/fastapi/tests/conftest.py`
- `dq-api/fastapi/tests/api/test_auth_endpoints.py`
- `dq-api/fastapi/tests/api/test_rules_endpoint.py`
- `dq-api/fastapi/tests/api/test_rule_versions_endpoint.py`