# Exception Fact Contract

This directory contains the versioned canonical contract for the engine-neutral Exception Fact used to persist row-level failed-record evidence across GX, Soda, and future execution engines.

The runtime code mirrors this contract through the executable exception record entity in dq-api/fastapi, but this package is the source of truth for the contract shape.

Contract structure:

- `v1/schema.json`: canonical machine-readable contract in JSON Schema.
- `v1/example.json`: canonical example payload.
- `v1/example.yaml`: review-friendly rendering of the same example payload.

Contract rules:

- JSON Schema is the source of truth for exception fact structure and validation.
- JSON examples must conform to the schema.
- YAML examples are documentation only and must mirror the JSON example.
- Contract payloads use snake_case field names only.
- The contract is runtime-neutral; engine-specific details belong in `engine_metadata` and must not replace canonical fields.
- `record_reference.identifier_type` is the canonical indicator for whether the record was identified by primary key or business key.
- `failure.reason_code` must be stable enough for cross-run analytics; `failure.reason_text` is the point-in-time human-readable snapshot.

Canonical family decisions:

- Public family name is `exception-fact`; public APIs stay under `/rulebuilder/v1/exceptions/...`.
- Raw immutable source of truth is the exception archive in object storage; relational persistence is the query-optimized projection store for raw-fact APIs and summaries.
- `record_reference.identifier_value` remains plaintext inside authorized raw-fact storage and raw-fact APIs only; aggregate exports and observability must not expose it.
- `record_reference.identifier_hash` is the canonical deterministic companion identifier and should use `sha256:<64 lowercase hex>` when present.
- Engine-native artifacts and expectation details belong in `engine_metadata` or `ops_metadata`, not in the canonical contract vocabulary.

Reason taxonomy decisions:

- `failure.reason_code` is the cross-engine analytics key and should use the controlled family prefixes below. Example: `completeness_not_null_violation`.
- `completeness_*`: missing required data, nullability, or blank-value failures.
- `uniqueness_*`: duplicate keys or duplicate combinations.
- `validity_*`: invalid format, invalid type, or invalid domain-value failures.
- `consistency_*`: mismatched values across related fields or datasets.
- `referential_integrity_*`: missing parent or broken foreign-reference failures.
- `range_*`: numeric, temporal, or rule-threshold boundary violations.
- `freshness_*`: stale or overdue data failures.
- `volume_*`: row-count or cardinality threshold breaches.
- `custom_*`: approved domain-specific failures that do not fit the shared families.
- Engine-native values such as GX expectation types remain useful, but they are supporting metadata rather than the long-term canonical analytics key.

Versioning rules:

- `exception_fact_contract_version` versions the exception fact contract shape.
- `validation_artifact_version` versions the neutral validation artifact that produced the failure.
- `native_artifact_version` is engine-native and remains optional because not every runtime exposes the same native artifact semantics.
- Changes to exception fact structure require a new contract version directory.

Related decision record:

- `ADR-034`: engine-neutral exception-fact family naming, storage authority, identifier handling, and reason taxonomy.