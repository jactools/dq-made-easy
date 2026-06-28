# Rule DSL Contract

This directory contains the versioned contract package for the canonical rule authoring DSL.

Contract structure:

- `2.0.0/schema.json`: canonical machine-readable contract in JSON Schema.
- `2.0.0/example.json`: canonical example payload.
- `2.0.0/example.yaml`: review-friendly rendering of the same example payload.
- `2.0.0/openapi.yaml`: OpenAPI 3.1 fragment showing how the same request contract is used by the rule write endpoints.
- `2.0.0/seed-templates/`: JSON Schema files and JSON seed templates for the DQ7 migration plan.

Contract rules:

- JSON Schema is the source of truth for request shape.
- OpenAPI documents the HTTP usage of the same request contract.
- Contract payloads use snake_case field names only.
- The contract package version mirrors `dsl.schema_version` for this DSL family.
- The semantic compiler model is language-neutral. TypeScript may be generated from the schema for UI use, but it is not the source of truth.

Versioning rules:

- `2.0.0` is the first semantic, engine-independent rule DSL contract package.
- Changes to field meaning, required properties, or enum semantics require a new version directory.