# Contracts

This folder contains versioned contract packages for API and artifact payloads.

Available contracts:

- [exception-fact](/docs/contracts/exception-fact/): canonical engine-neutral row-level exception fact contract for exception persistence and reason analytics.
- [execution-engine-capabilities](/docs/contracts/execution-engine-capabilities/): engine-neutral capability declarations that gate whether a runtime may participate in row-level exception fact recording.
- [internal-api](/docs/contracts/internal-api/): current generated versioned JSON Schema bundles for the live FastAPI internal API surface.
- [gx-artifact-envelope](/docs/contracts/gx-artifact-envelope/): GX artifact envelope contract used by DQ-7.4.
- [pyspark-native-artifact-envelope](/docs/contracts/pyspark-native-artifact-envelope/): PySpark-native validation artifact contract for engine_type `pyspark_native`.
- [rule-dsl](/docs/contracts/rule-dsl/): canonical semantic rule authoring contract package for DQ-7 `dsl.schema_version = 2.0.0`.
- [test-proof](/docs/contracts/test-proof/): canonical JSON schema for curated UI and API test proof summaries.
- [validation-artifact-envelope](/docs/contracts/validation-artifact-envelope/): runtime-neutral artifact envelope that wraps engine-native GX or Soda payloads for ABS-1 multi-runtime expansion.
- [self-built-pyspark-executor-request](/docs/contracts/self-built-pyspark-executor-request/): grouped-batch handoff contract for self-built PySpark executors above the neutral artifact and grouped-planning seams.
- [test-proof-payload](/docs/contracts/test-proof-payload/): canonical proof submission contract for `POST /api/rulebuilder/v1/rules/&#123;rule_id&#125;/test`.

Rules:

- JSON Schema is the source of truth for payload shape.
- OpenAPI files document the HTTP usage of the same contract.
- Contract payloads use snake_case field names only.
- Contract version changes require a new versioned subdirectory.