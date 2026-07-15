# DQ-6 Batch Rule Execution Improvements

Status: Done

Goal: improve grouped rule test execution so batch requests are created, run, and tracked through the same repository-backed FastAPI boundary used by the rest of the application.

Current status: batch test requests now persist execution state, correlation metadata, proof linkage, and failure details through the testing repository and FastAPI workflows API. The user-facing API supports creating grouped requests, running an existing request, and reading the persisted result.

## Why this exists

Rule testing already had a repository-backed test flow for single-rule execution, but grouped request execution needed a clearer contract for request lifecycle tracking. This track keeps batch execution behavior explicit so request state, completion metadata, and runtime failures are all stored consistently instead of being handled ad hoc at the endpoint layer.

## Scope

### In scope

- Create batch test requests for one or more rules
- Run a batch test request through the repository-backed execution path
- Persist `pending`, `running`, `completed`, and `failed` state transitions
- Store execution correlation metadata and proof linkage on success
- Store failure metadata when the executor raises at runtime
- Expose the current request state through the FastAPI testing endpoints

### Out of scope

- Replacing the existing rule test execution model with a new scheduler
- Adding silent fallback behavior when rule execution or persistence fails
- Changing the test proof contract beyond the persisted batch execution metadata

## User-facing outcome

Users can queue a grouped batch of rule test requests, run each request, and see whether the request completed or failed with persisted metadata. The API returns the execution context when available, and the stored request record keeps the final status, proof reference, and execution correlation details for later review.

## Tracked Work Items

- [x] `DQ-6.1` Define the batch test request lifecycle in the testing repository contract
- [x] `DQ-6.2` Persist batch request state transitions and execution correlation metadata
- [x] `DQ-6.3` Wire the FastAPI testing workflows API to run existing batch requests through the repository boundary
- [x] `DQ-6.4` Return scheduler handoff and execution context details in the run response
- [x] `DQ-6.5` Capture runtime failures in the stored request payload instead of dropping them
- [x] `DQ-6.6` Cover the grouped request flow with API and repository tests

## Acceptance Criteria

- [x] Batch test requests can be created and run through the FastAPI testing endpoints
- [x] Successful runs persist a proof reference and execution correlation metadata
- [x] Failed runs persist explicit error metadata and a terminal failed status
- [x] The batch run response includes the execution context when a request exists
- [x] Repository and API tests cover the pending, completed, and failed paths

## Related References

- [DQ feature rollup](../features/DQ_FEATURES.md)
- [Testing endpoints](../../dq-api/fastapi/app/api/v1/endpoints/testing.py)
- [Testing workflows API](../../dq-api/fastapi/app/api/v1/testing_workflows_api.py)
- [Testing repository contract](../../dq-api/fastapi/app/domain/interfaces/v1/testing_repository.py)
- [Batch request API tests](../../dq-api/fastapi/tests/api/test_testing_endpoint.py)
- [Batch request repository tests](../../dq-api/fastapi/tests/infrastructure/unit/repositories/postgres/test_testing_repository.py)