# Contracts

This folder contains versioned contract packages for API and artifact payloads.

Available contracts:

- [exception-fact](exception-fact/README.md): canonical engine-neutral row-level exception fact contract for exception persistence and reason analytics.
- [execution-engine-capabilities](execution-engine-capabilities/README.md): engine-neutral capability declarations that gate whether a runtime may participate in row-level exception fact recording.
- [internal-api](internal-api/README.md): current generated versioned JSON Schema bundles for the live FastAPI internal API surface.
- [gx-artifact-envelope](gx-artifact-envelope/README.md): GX artifact envelope contract used by DQ-7.4.
- [pyspark-native-artifact-envelope](pyspark-native-artifact-envelope/README.md): PySpark-native validation artifact contract for engine_type `pyspark_native`.
- [rule-dsl](rule-dsl/README.md): canonical semantic rule authoring contract package for DQ-7 `dsl.schema_version = 2.0.0`.
- [test-proof](test-proof/README.md): canonical JSON schema for curated UI and API test proof summaries.
- [validation-artifact-envelope](validation-artifact-envelope/README.md): runtime-neutral artifact envelope that wraps engine-native GX or Soda payloads for ABS-1 multi-runtime expansion.
- [self-built-pyspark-executor-request](self-built-pyspark-executor-request/README.md): grouped-batch handoff contract for self-built PySpark executors above the neutral artifact and grouped-planning seams.
- [test-proof-payload](test-proof-payload/README.md): canonical proof submission contract for `POST /api/rulebuilder/v1/rules/{rule_id}/test`.

Rules:

- JSON Schema is the source of truth for payload shape.
- OpenAPI files document the HTTP usage of the same contract.
- Contract payloads use snake_case field names only.
- Contract version changes require a new versioned subdirectory.