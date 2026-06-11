# EDR-043 [VAL]: Environment-Dependent Smoke Tests Belong in Scripts

**Status**: Accepted
**Date**: 2026-04-21
**Tag**: VAL

## Context
This repository has accumulated two different kinds of "smoke" coverage:

- deterministic in-process checks that can run safely inside the normal pytest suite
- environment-dependent checks that require live auth, Kong, a real database, seeded runtime data, or a running GX/materialization path

Those two categories have different operational constraints, but they were not consistently separated in the test tree. In practice this created recurring problems:

- pytest smoke modules under `dq-api/fastapi/tests/` started exercising login flows, system state mutations, live GX execution, and seeded database/runtime behavior
- those tests were sensitive to ambient environment configuration, suite ordering, and shared app state instead of behaving like deterministic repository tests
- the repository already had a dedicated operational home for live smoke coverage under `scripts/smoke*.sh`, which made the pytest duplicates both confusing and harder to maintain

The result was an unclear boundary between repository test coverage and operational smoke verification.

## Decision
Adopt the following repository rule for smoke coverage:

- Smoke checks that depend on live auth, Kong, Keycloak, a real database, seeded runtime data, or live GX/materialization execution MUST live under `scripts/smoke*.sh` or an equivalent repository script entrypoint.
- Pytest tests under `tests/` MUST remain deterministic and in-process by default; they MUST NOT be the home for environment-dependent smoke coverage.
- If a smoke-style pytest check is kept under `tests/`, it must only assert repository-local behavior that can run without external service orchestration beyond the normal test harness.
- When an existing pytest smoke test is discovered to depend on live infrastructure, it should be removed, relocated to the shell smoke layer, or reduced to an in-process deterministic check.

## Rationale
- Environment-dependent smoke checks are operational verification, not ordinary repository unit or API test coverage.
- The repository already has shell smoke entrypoints that are better suited for real gateways, seeded users, live tokens, and running worker flows.
- Keeping pytest smoke coverage deterministic reduces suite-order sensitivity and avoids hidden dependencies on external services.
- One clear home for live smoke checks makes it easier to understand how to validate a real deployed or locally orchestrated stack.

## Scope Boundaries
This decision applies to repository smoke-check placement and ownership.

It does cover:
- FastAPI smoke checks that hit live auth, Kong, a real database, or live GX/materialization execution
- the boundary between `tests/` and `scripts/smoke*.sh`
- repository review guidance for future smoke additions

It does not cover:
- whether a given shell smoke script should target local, compose, or remote environments
- broader end-to-end test strategy outside smoke placement
- deterministic pytest coverage that happens to use the word "smoke" but stays fully in-process

## Consequences
**Positive**
- The pytest suite stays focused on deterministic repository-local behavior.
- Live-stack verification has one obvious home under `scripts/smoke*.sh`.
- Reviewers can reject misplaced environment-dependent smoke tests as a policy violation instead of debating them case by case.
- Failures in smoke scripts are easier to interpret as stack/runtime problems rather than pytest isolation issues.

**Negative**
- Some smoke assertions may need to move out of familiar pytest workflows into shell-driven validation.
- Contributors must decide earlier whether a new smoke check is a repository test or an operational script.
- A few live smoke checks may need script maintenance rather than quick pytest additions.

## Implementation Guidance
- Keep `tests/` smoke coverage limited to deterministic in-process checks such as request-shape guards or repository-local endpoint behavior.
- Put live login, gateway redirect, live token minting, seeded-database assertions, and real GX/materialization run checks into `scripts/smoke*.sh`.
- When a pytest smoke test requires environment setup instructions, external URLs, seeded identities, or long-running services, treat that as a strong signal it belongs in a script instead.
- Document the split clearly in local README files so future contributors do not recreate duplicate smoke layers.

## Related Artifacts
- `docs/engineering-decisions/EDR-008-VAL-fastapi-test-architecture-and-isolation.md`
- `dq-api/fastapi/tests/smoke/README.md`
- `dq-api/fastapi/tests/smoke/test_manual_override_smoke.py`
- `scripts/smoke_test_auth_kong.sh`
- `scripts/smoke_test_api.sh`
- `scripts/smoke_adhoc_rule_execution.sh`
- `/memories/repo/dq-rulebuilder-fastapi-smoke-tests-shell-owned-note.md`
