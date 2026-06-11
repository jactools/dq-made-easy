# EDR-009 [API]: API Data Contract and Snake Case Naming

**Status**: Accepted
**Date**: 2026-04-20
**Tag**: API

## Context
This repository treats the backend API surface as a stable machine-readable contract, but several implementation paths made that contract easy to erode:

- free-form nested JSON payloads do not get renamed correctly by Pydantic aliasing alone
- request middleware cannot be relied on to rewrite incoming payload shapes safely
- app-level exception handling can accidentally stringify structured error payloads
- resolver-based view models can fail when entity objects are validated without attribute-aware mapping
- GX dispatch and status payloads pass through API, Redis, workers, and persisted status details, so one shape mismatch can break several readers

The result is that backend contract shape must be treated as a deliberate engineering rule, not an incidental serialization outcome.

## Decision
Adopt the following API contract rules:

- Canonical backend request and response JSON field names are snake_case at every API boundary.
- Incoming request bodies are not implicitly rewritten into snake_case by middleware; routes, validators, and repositories must enforce the expected contract directly.
- Outgoing JSON responses must be normalized recursively so nested free-form payloads also remain snake_case.
- Dict and list `HTTPException.detail` payloads must remain structured and machine-readable; they must not be stringified by the application error handler.
- Resolver-based response view models that validate ORM or entity instances must use attribute-aware mapping, typically `from_attributes=True`, unless they explicitly map from a dumped dict instead.
- GX queue handoff payloads and related persisted status payloads must stay snake_case end-to-end, including nested `execution_contract`, queue metadata, handoff payloads, and status details read back by adjacent services.

## Rationale
- Snake_case is the documented backend contract and must be consistent across endpoints, workers, and persisted artifacts.
- Free-form nested dict payloads are exactly where implicit aliasing stops being reliable, so response normalization needs to be explicit.
- Structured error details are required for the UI and other consumers to react to machine-readable error codes and attached payload details.
- Attribute-aware view validation avoids fragile hand-mapping and keeps resolver-based endpoint code predictable.
- GX dispatch payloads are read by several components; contract drift there causes multi-hop breakage rather than a single local failure.

## Scope Boundaries
This decision applies to backend API contracts, application error payloads, resolver/view-model mapping, and API-originated GX dispatch payloads.

It does not by itself define:
- frontend camelCase conventions after the frontend converts backend payloads for UI use
- every internal Python variable naming convention
- schema evolution policy for public APIs across major versions
- non-JSON transport formats outside the API and queue payload surface

## Consequences
**Positive**
- Backend contract shape is explicit and consistent across endpoints and worker handoffs.
- Machine-readable error payloads remain usable by the UI and tests.
- Nested payloads no longer silently drift into mixed casing.
- Resolver-based endpoint code can rely on a clear view-model mapping rule.

**Negative**
- Routes handling free-form payloads must be deliberate about validation and normalization.
- Middleware and exception handling changes need regression coverage because small changes can damage cross-service contract stability.
- Developers cannot rely on aliasing or framework defaults to clean up shape mismatches automatically.

## Implementation Guidance
- Keep backend JSON keys snake_case in API request/response models and in persisted API-owned payloads.
- Use response-side normalization for nested JSON structures that are not fully modeled by strict Pydantic schemas.
- Preserve dict/list `HTTPException.detail` values in app-level exception handlers.
- When validating view models from entity instances, configure the model for attribute-based validation or explicitly map the source object first.
- When GX dispatch payload shape changes, update all adjacent readers that inspect queue payloads, persisted handoff payloads, or queue status metadata.

## Related Artifacts
- `/memories/repo/dq-rulebuilder-fastapi-gx-dispatch-snake-case-end-to-end-note.md`
- `/memories/repo/dq-rulebuilder-fastapi-structured-http-exception-detail-note.md`
- `/memories/repo/dq-rulebuilder-fastapi-view-model-from-attributes-note.md`
- `/memories/repo/dq-rulebuilder-fastapi-api-case-middleware-nested-dicts-note.md`
- `dq-api/fastapi/app/core/errors.py`
- `dq-api/fastapi/app/middleware/api_case_enforcement.py`
- `dq-api/fastapi/app/api/v1/endpoints/gx.py`
