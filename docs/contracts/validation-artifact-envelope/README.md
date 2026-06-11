# Validation Artifact Envelope Contract

This directory contains the versioned contract for the runtime-neutral Validation Artifact Envelope introduced for ABS-1.MR-01.

Contract structure:

- `v1/schema.json`: canonical machine-readable contract in JSON Schema.
- `v1/example.json`: canonical example payload.
- `v1/example.yaml`: review-friendly rendering of the same example payload.

Contract rules:

- JSON Schema is the source of truth for envelope structure and validation.
- JSON examples must conform to the schema.
- YAML examples are documentation only and must mirror the JSON example.
- `engine_artifact.payload` remains engine-native on purpose. For GX, that nested payload can preserve the current GX envelope shape without lossy normalization while the outer envelope stays runtime-neutral.
- `engine_type = pyspark_native` is now supported when the nested payload conforms to the PySpark-native artifact envelope contract.

Versioning rules:

- `artifact_contract_version` versions the neutral envelope contract shape.
- `validation_artifact_version` versions a specific compiled validation artifact.
- Engine-specific payload versioning stays inside `engine_artifact.artifact_schema_version`.
- Changes to neutral envelope structure require a new contract version directory.