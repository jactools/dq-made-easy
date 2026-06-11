# GX Artifact Envelope Contract

This directory contains the versioned contract for the GX Artifact Envelope used by DQ-7.4.

Contract structure:

- `v1/schema.json`: canonical machine-readable contract in JSON Schema.
- `v1/example.json`: canonical example payload.
- `v1/example.yaml`: review-friendly rendering of the same example payload.

Contract rules:

- JSON Schema is the source of truth for envelope structure and validation.
- JSON examples must conform to the schema.
- YAML examples are documentation only and must mirror the JSON example.
- Runtime-generated GX artifacts are stored in the registry database and are not version-controlled in Git.

Versioning rules:

- `artifactVersion` versions the envelope contract shape.
- `suiteVersion` versions a specific compiled GX suite artifact.
- Changes to envelope structure require a new contract version directory.