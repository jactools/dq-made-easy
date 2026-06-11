# EDR-040 [API]: JSON Schema Required for API Payload Contracts

**Status**: Accepted
**Date**: 2026-04-20
**Tag**: API

## Context
This repository treats API payload shape as a durable contract, but that contract becomes unreliable when any of the following are allowed:

- an endpoint accepts a JSON payload without a corresponding machine-readable schema
- request validation depends only on handwritten guards or implicit framework behavior
- mixed-case field names appear in schemas or payloads and drift away from the documented backend contract

Those failure modes create silent contract erosion. Clients cannot reliably generate or validate payloads, backend validation becomes inconsistent across endpoints, and casing drift propagates into tests, workers, and UI conversion layers.

The repository already treats snake_case as the canonical backend API JSON shape and follows a fail-fast policy for required contract surfaces. JSON Schema now needs to be an explicit engineering requirement rather than an optional publishing artifact.

## Decision
Adopt the following repository-wide API contract rules for JSON request payloads:

- Every API operation that accepts a JSON request payload MUST have a corresponding JSON Schema.
- The schema MUST exist as a published repository artifact and be discoverable from the internal API contract family.
- The API MUST validate the received payload against the corresponding JSON Schema before business logic continues.
- If the required JSON Schema is missing, the API MUST fail closed and return an explicit server error rather than accepting the payload without schema validation.
- JSON Schema property names for backend API payloads MUST use snake_case only.
- Snake_case enforcement for JSON request bodies is provided by the JSON Schema contract itself; the API does not need a separate request-body casing verification step beyond schema validation.

## Rationale
- A missing schema means the contract is undefined in machine-readable form, so accepting payloads anyway would violate the repository's fail-fast policy.
- Runtime schema validation makes the published contract enforceable instead of informational only.
- Requiring snake_case inside the schema itself prevents a split-brain contract where docs say one thing and runtime payloads permit another.
- Central schema validation reduces duplicated per-endpoint guard logic and makes contract drift visible immediately.
- Using the schema as the casing authority avoids duplicate API-side validation rules that can diverge from the contract artifact.

## Scope Boundaries
This decision applies to backend API operations that accept JSON request payloads and to the JSON Schemas that define those payloads.

This decision does not by itself define:
- OpenAPI as the only contract publication format
- frontend internal state naming after the UI converts backend payloads
- non-JSON request formats such as multipart or binary upload surfaces
- response-body runtime validation policy beyond the requirement that published backend contract fields remain snake_case

## Consequences
**Positive**
- Every JSON request payload has an explicit contract artifact.
- Runtime behavior matches the published contract instead of relying on documentation alone.
- Missing-schema situations fail fast instead of silently accepting unvalidated payloads.
- Snake_case remains the only canonical backend payload shape across schema, runtime, tests, and generated docs.
- The schema artifact becomes the single enforcement source for request-body field naming.

**Negative**
- New JSON-body endpoints must not ship until their schema is published and wired into validation.
- Contract generation and runtime validation become part of the delivery path for body-carrying endpoints.
- Existing endpoints with loose payload handling may require refactoring to align with the schema-first rule.

## Implementation Guidance
- Publish JSON Schemas under the internal API contract family in `docs/contracts/internal-api/`.
- Treat the generated contract bundle as the source of truth for request payload schema lookup.
- Validate request bodies before endpoint business logic and return structured machine-readable errors for invalid JSON, unsupported media type, missing schema, or schema mismatch.
- Fail closed when an operation expects schema-backed validation but no matching schema contract can be resolved.
- Keep schema property names, required-field names, and example payload keys in snake_case only.
- Do not add a separate request-body casing validator when JSON Schema validation already enforces the contract.
- Do not add middleware or compatibility layers that silently rewrite camelCase request bodies into snake_case.

## Related Artifacts
- `docs/contracts/internal-api/README.md`
- `docs/contracts/internal-api/aggregate/v1/operations.json`
- `dq-utils/src/dq_utils/internal_api_contracts.py`
- `dq-api/fastapi/app/middleware/internal_api_contract_validation.py`
- `dq-api/fastapi/scripts/contracts/export_docs_contracts.py`
- `.github/copilot-instructions.md`
- `docs/engineering-decisions/EDR-009-API-api-data-contract-and-snake-case-naming.md`