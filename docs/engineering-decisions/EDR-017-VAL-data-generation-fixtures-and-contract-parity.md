# EDR-017 [VAL]: Data-Generation Fixtures and Contract Parity

**Status**: Accepted
**Date**: 2026-04-20
**Tag**: VAL

## Context
Test-data generation and proof-submission flows in this repository originally drifted across several representations: local simulation in UI-oriented flows, ad hoc in-memory fixtures in Python modules, and endpoint tests that bypassed the real queue lifecycle or used payload shapes that no longer matched the documented contract.

Recent work established a more stable pattern:

- generated test data should flow through one backend-owned queued request model
- in-memory repository seed datasets should come from one central generator module rather than duplicated hand-built fixtures
- CSV-backed fixtures should remain the source of truth for shared suggestions/mock data
- proof payload examples and tests must stay aligned with the published snake_case contract

These are durable test and validation rules, not just implementation cleanup.

## Decision
Adopt the following fixture and contract-parity rules:

- Generated test-data and mock-preview flows should use the unified backend queue/request lifecycle rather than local-only simulation paths.
- API and endpoint tests that exercise generated-data flows directly must stub the queued request helpers and provide fake repository behavior that reflects the proof lifecycle, including creation and update of persisted proof state.
- In-memory repository seed datasets must be centralized in the shared in-memory test-data generator module and consumed through generator accessors rather than duplicated across repositories.
- Shared suggestions fixtures must be CSV-backed and fail fast when the CSV source is missing; fallback payloads embedded directly in Python fixture modules are not the source of truth.
- CSV fixture fields that contain JSON must use CSV-safe escaping rules so the shared loader can parse them deterministically.
- Canonical proof submission examples and tests must follow the published snake_case contract, including `proof_data` as the proof envelope and repository-owned fields such as generated execution traces being omitted from request payloads.

## Rationale
- One queued backend path keeps generated-data behavior consistent across API, profiling-worker, and preview/test flows.
- Endpoint tests are more realistic when they model the same proof-state lifecycle that production code persists.
- Centralized in-memory seed generation reduces drift between repositories and improves full-suite consistency.
- CSV-backed shared fixtures are easier to audit and keep aligned than fallback payloads hidden in Python modules.
- Contract parity prevents documentation, examples, and tests from quietly drifting away from the actual backend request shape.

## Scope Boundaries
This decision applies to generated test-data request flows, shared in-memory seed datasets, shared CSV-backed fixtures, and published proof payload contract examples/tests.

It does not by itself define:
- every worker implementation detail behind test-data generation
- all test isolation rules across the repository
- UI behavior outside the requirement that previews use the backend-owned request/status model
- future proof contract versions beyond the currently published contract surface

## Consequences
**Positive**
- Generated-data tests and preview flows stay closer to real backend behavior.
- Shared in-memory fixtures become easier to maintain and reason about.
- Suggestions and similar shared fixtures fail early when the true source data is missing or malformed.
- Contract examples and tests remain aligned with the documented proof payload shape.

**Negative**
- Direct endpoint tests become more explicit because they must stub queue/proof lifecycle helpers correctly.
- Fixture maintenance shifts effort into central generators and CSV sources instead of quick local shortcuts.
- Contract changes require coordinated updates across docs, tests, loaders, and fake repositories.

## Implementation Guidance
- Route generated test-data requests through the repository's Redis-backed queue model and expose status through the backend request/status endpoints.
- When unit or endpoint tests call generated-data flows directly, stub queue helpers and implement proof persistence methods on fake testing repositories.
- Keep central in-memory seed data in the shared generator module and have repository test doubles pull from that source.
- Store shared suggestions fixture data in CSV and validate JSON-in-CSV fields using proper doubled-quote escaping.
- Keep request payload examples and tests snake_case only and omit repository-generated response fields from incoming proof submission payloads.

## Related Artifacts
- `/memories/repo/dq-rulebuilder-fastapi-unified-queued-test-data-generation-note.md`
- `/memories/repo/dq-rulebuilder-fastapi-api67-seed-generator-note.md`
- `/memories/repo/dq-rulebuilder-fastapi-suggestions-fixture-csv-json-note.md`
- `/memories/repo/dq-rulebuilder-fastapi-test-proof-payload-contract-note.md`
- `dq-api/fastapi/app/infrastructure/repositories/in_memory_test_data.py`
- `dq-api/fastapi/tests/api/test_testing_endpoint_helpers_focus.py`
- `dq-profiling/python/test_data_jobs.py`
- `docs/contracts/test-proof-payload/v1/`