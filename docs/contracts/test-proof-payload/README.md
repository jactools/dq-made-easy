# Test Proof Payload Contract

This contract defines the canonical request payload for submitting a proof to `POST /api/rulebuilder/v1/rules/{rule_id}/test`.

Contract files:

- `v1/schema.json`: JSON Schema for the request body.
- `v1/example.json`: canonical example payload.
- `v1/example.yaml`: review-friendly rendering of the same example payload.
- `v1/openapi.yaml`: OpenAPI 3.1 fragment for the proof submission endpoint.

Contract rules:

- Use snake_case field names only.
- `proof_data` is the canonical proof envelope.
- `proof_data.request_status` and `proof_data.version_id` are required in v1.
- `proof_data` may contain additional domain-specific evidence fields, but callers should keep the canonical fields present when available.
- The API generates `execution_trace` when the proof is stored; external callers do not send it in the request body.

Versioning rules:

- `v1` is the current contract version.
- Changes to the request shape or canonical field meaning require a new version directory.