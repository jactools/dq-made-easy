# Self-Built PySpark Executor Request Contract

This directory contains the versioned request contract for ABS-1.MR-04.

Purpose:

- define the platform-to-executor handoff for a self-built PySpark execution path
- keep the handoff above the runtime-neutral validation artifact seam and the grouped-planning seam
- let a custom executor consume resolved batch inputs without coupling it to the current GX worker queue payload

Contract structure:

- `v1/schema.json`: canonical machine-readable request contract in JSON Schema
- `v1/example.json`: canonical example request payload
- `v1/example.yaml`: review-friendly rendering of the same example payload
- `v1/example_pyspark_native.json`: grouped-batch example carrying a `pyspark_native` artifact item
- `v1/example_pyspark_native.yaml`: review-friendly rendering of the same `pyspark_native` example

Contract rules:

- JSON Schema is the source of truth for request structure.
- JSON examples must conform to the schema.
- YAML examples are documentation only and must mirror the JSON example.
- `executor_kind` identifies the execution implementation path and does not replace `engine_type`.
- `engine_type` identifies the validation-engine semantics of each artifact item. A self-built PySpark executor can still run `engine_type = gx` items; it is simply an alternative executor for the same GX artifact semantics.
- `validation_artifact` is embedded as a runtime-neutral envelope payload; the executor must not assume an implicit lookup against platform storage.
- The platform resolves grouped execution and source binding before handoff; missing bindings or unsupported source shapes must fail fast.
- No silent fallback to the platform-owned GX executor is allowed when the self-built executor cannot satisfy the request.

Field intent:

- Use `engine_type` for what the artifact means: today `gx`, `pyspark_native`, and later potentially `soda` or another engine-native artifact type.
- Use `executor_kind` for how the artifact is executed: in this contract `self_built_pyspark`.
- That means a valid MR-04 request is expected to look like `executor_kind = self_built_pyspark` plus `engine_type = gx` for each item when the custom executor is running GX-derived artifacts.
- That same request shape can now also carry `engine_type = pyspark_native` items, because the PySpark-native artifact envelope is now defined as its own engine-native contract.

Current v1 scope:

- The v1 request carries grouped batches backed by the runtime-neutral validation artifact envelope.
- The v1 request supports `engine_type = gx` when custom PySpark is acting as an alternative executor for GX artifacts, and `engine_type = pyspark_native` when the artifact itself is PySpark-native.
- Direct canonical compiler-output handoff is intentionally deferred until the compiler artifact has its own versioned contract package.

Related mapping note:

- [ABS-1 PySpark-native compiler mapping](/docs/implementation-details/ABS_1_PYSPARK_NATIVE_COMPILER_MAPPING/)

Versioning rules:

- `executor_contract_version` versions the self-built PySpark request shape.
- Expanding the request to carry direct canonical compiler output requires either a new version directory or a separately versioned compiler-artifact contract package.
- Breaking changes to grouped batch semantics, source-binding shape, or embedded artifact requirements require a new version directory.