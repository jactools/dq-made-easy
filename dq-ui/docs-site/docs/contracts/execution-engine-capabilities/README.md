# Execution Engine Capabilities Contract

This directory contains the versioned contract for engine-neutral execution capability declarations used to gate row-level exception fact recording.

Contract structure:

- `v1/schema.json`: canonical machine-readable contract in JSON Schema.
- `v1/example.json`: canonical example payload.
- `v1/example.yaml`: review-friendly rendering of the same example payload.

Contract rules:

- JSON Schema is the source of truth for execution engine capability declarations.
- JSON examples must conform to the schema.
- YAML examples are documentation only and must mirror the JSON example.
- Contract payloads use snake_case field names only.
- Capability declarations are runtime-neutral and must use canonical `engine_type` values.
- When `row_level_exception_facts_supported = false`, required exception-fact flows must fail fast; they must not degrade to aggregate-only success.
- When `normalized_reason_codes_supported = false` or `record_identifier_resolution_supported = false`, the engine must not be treated as capable for required exception-fact recording.

Versioning rules:

- `execution_engine_capabilities_contract_version` versions the capability declaration contract shape.
- Changes to declaration structure require a new contract version directory.