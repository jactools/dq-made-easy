# PySpark-Native Artifact Envelope Contract

This directory contains the versioned contract for the PySpark-native artifact envelope introduced as the third engine-native contract for ABS-1 multi-runtime expansion.

Contract structure:

- `v1/schema.json`: canonical machine-readable contract in JSON Schema.
- `v1/example.json`: canonical example payload.
- `v1/example.yaml`: review-friendly rendering of the same example payload.

Contract rules:

- JSON Schema is the source of truth for envelope structure and validation.
- JSON examples must conform to the schema.
- YAML examples are documentation only and must mirror the JSON example.
- This contract defines a PySpark-native validation artifact, not merely an alternate executor for GX.
- The artifact expresses validation logic as PySpark-native checks and row predicates rather than GX suite semantics.
- `engine_target` remains `pyspark`, but `engine_type = pyspark_native` identifies a different engine-native artifact family than `gx` or `soda`.
- Missing source binding, missing traceability identifiers, or unsupported check kinds must fail fast.

Related mapping note:

- [ABS-1 PySpark-native compiler mapping](../../implementation-details/ABS_1_PYSPARK_NATIVE_COMPILER_MAPPING.md)

Versioning rules:

- `artifact_version` versions the envelope contract shape.
- `artifact_revision` versions a specific compiled PySpark-native artifact.
- Changes to envelope structure require a new contract version directory.