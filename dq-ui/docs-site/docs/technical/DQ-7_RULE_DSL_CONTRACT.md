# DQ-7 Rule DSL Contract

> **Status:** Current technical reference
> **Scope:** Canonical rule authoring contract and live backend behavior

This document describes the DQ-7 rule DSL as it is implemented today. It is a technical contract reference, not a remaining feature-plan backlog.

The authoritative 2.0.0 contract artifacts live in [../contracts/rule-dsl/2.0.0/schema.json](https://github.com/jactools/dq-rulebuilder/blob/main/docs/contracts/rule-dsl/2.0.0/schema.json), [../contracts/rule-dsl/2.0.0/openapi.yaml](https://github.com/jactools/dq-rulebuilder/blob/main/docs/contracts/rule-dsl/2.0.0/openapi.yaml), [../contracts/rule-dsl/2.0.0/example.json](https://github.com/jactools/dq-rulebuilder/blob/main/docs/contracts/rule-dsl/2.0.0/example.json), and [../contracts/rule-dsl/2.0.0/example.yaml](https://github.com/jactools/dq-rulebuilder/blob/main/docs/contracts/rule-dsl/2.0.0/example.yaml).

## Contract summary

- Rule write requests carry a nested `dsl` object.
- The live write API accepts `dsl.schema_version` `1.0.0` and `2.0.0` on `POST /api/rulebuilder/v1/rules` and `PUT /api/rulebuilder/v1/rules/&#123;rule_id&#125;`.
- `1.0.0` remains the broad execution-compatibility contract built around `dsl.source.kind`.
- `2.0.0` is the canonical semantic contract built around `dsl.rule.kind`, `scope`, `measure`, `expectation`, `evidence`, and `operations`.
- `2.0.0` ingestion is feature-gated behind `feature_rule_dsl_v2`.
- The backend fails fast on unsupported schema versions, mixed contract shapes, invalid predicates, non-compilable payloads, unsupported target engines, and unsupported 2.0.0 lowerings.
- The backend persists the canonical DSL document in `rules.dsl` and `rule_versions.dsl`.
- The current rule-mutation write path is narrower than the full capability registry. The registry and dedicated lowerers describe broader support surfaces than the live `POST` and `PUT` mutation flow currently exposes.

## Live schema versions

- `1.0.0`: executable compatibility contract centered on `filter_expression` and `check_type`.
- `2.0.0`: semantic contract centered on `rule.kind`, `scope`, `measure`, `expectation`, `evidence`, and `operations`.

The live backend also carries canonical reusable-asset references on the 2.0.0 rule model through `reusable_join_id` and `reusable_filter_ids`.

## Frozen 2.0.0 vocabularies

The 2.0.0 vocabularies are implemented in the JSON Schema, OpenAPI fragment, Pydantic request model, semantic IR model, and backend capability registry.

### Construct families

- `row_assertion`
- `metric_threshold`
- `metric_comparison`
- `schema_assertion`
- `reference_assertion`
- `reconciliation_assertion`
- `freshness_assertion`
- `distribution_assertion`
- `anomaly_assertion`
- `custom_query_assertion`

### Scope vocabulary

- `dataset`
- `row_filter`
- `join`
- `grouping`
- `time_window`
- `comparison`

### Metric vocabulary

- `row_count`
- `missing_count`
- `missing_percent`
- `duplicate_count`
- `duplicate_percent`
- `distinct_count`
- `min`
- `max`
- `avg`
- `sum`
- `stddev`
- `quantile`
- `freshness_age`
- `match_percent`

### Expectation vocabulary

- `threshold`
- `equality`
- `set_membership`
- `schema_contract`
- `baseline`

### Evidence vocabulary

- `failed_rows`
- `emit_compiled_artifact`
- `emit_generated_sql`

### Operations vocabulary

- `severity`
- `preferred_engines`
- `fail_if_not_native`

## Live write-path behavior

For `POST /api/rulebuilder/v1/rules` and `PUT /api/rulebuilder/v1/rules/&#123;rule_id&#125;`, the backend currently performs these steps:

1. Validate the outer request contract.
2. Read `dsl.schema_version` and reject mixed 1.0.0 and 2.0.0 shapes.
3. For `2.0.0`, require `feature_rule_dsl_v2` to be enabled.
4. Normalize the DSL into the canonical request model and semantic IR.
5. For 1.0.0, normalize source details, compile the final predicate, and reject non-compilable payloads.
6. For 2.0.0, select the first preferred engine and reject anything outside the live mutation targets `gx` and `sodacl`.
7. Enforce capability-registry preservation rules, including `fail_if_not_native`.
8. Run lowerer-specific fail-fast checks where the live path already has them.
9. Persist the canonical DSL document and any derived runtime compatibility fields.

The persistence model stays DSL-first:

- Canonical DSL is stored in `rules.dsl` and `rule_versions.dsl`.
- Legacy execution fields remain persisted only when the current write pipeline can still derive them safely:
  - `expression`
  - `check_type`
  - `check_type_params`
  - join and alias metadata

## Current 2.0.0 write support

The live 2.0.0 write surface has three distinct states.

### 1. Supported and lowered into current runtime compatibility fields

These shapes are accepted and produce legacy executable fields for the current runtime:

- `metric_threshold` with `measure.metric = row_count` and dataset scope. Row-filter scope is allowed only for this bounded row-count path.
- `metric_threshold` with `measure.metric = missing_percent`, one subject column, dataset scope, and percent thresholds.
- `metric_threshold` with `measure.metric = missing_count`, one subject column, dataset scope, and only `operator = lte`, `value = 0`, `unit = count`.
- `metric_threshold` with `measure.metric = duplicate_count`, one or more subject columns, dataset scope, and only `operator = lte`, `value = 0`, `unit = count`.
- `metric_threshold` with `measure.metric = duplicate_percent`, one or more subject columns, dataset scope, and only `operator = lte`, `value = 0`, `unit = percent` or no explicit unit.
- `row_assertion` with `measure.type = row_predicate`, `predicate.language = dq_predicate`, and a `100%` success threshold (`operator = gte`, `value = 100`, `unit = percent` or omitted).
- `freshness_assertion` with `measure.metric = freshness_age`, one subject column, dataset scope, and whole-day ISO-8601 durations such as `P3D`.
- `reference_assertion` with comparison scope, exactly one join key, `measure.metric = match_percent`, one subject column matching the left join key, and only a `100%` threshold.

### 2. Accepted and persisted canonically, but not converted into legacy runtime fields

These shapes are accepted by the live mutation flow, validated against the semantic contract, and persisted with canonical DSL only. They currently leave `expression`, `check_type`, and `check_type_params` empty in the mutation payload:

- `metric_threshold` aggregate metrics with supported numeric or count thresholds for `distinct_count`, `min`, `max`, `avg`, `sum`, and `stddev`.
- `custom_query_assertion` on the bounded GX comparison-query path.

This is implemented behavior today. It is broader than the legacy runtime-field lowering path, but narrower than the full contract vocabulary.

### 3. Present in the canonical contract or capability registry, but not supported by the live mutation write path

These shapes currently fail fast in the live rule write flow:

- `schema_assertion`
- `metric_comparison`
- `reconciliation_assertion`
- `distribution_assertion`
- `anomaly_assertion`
- broader `reference_assertion` shapes outside the single-join-key, 100% match path
- broader `freshness_assertion` shapes outside the bounded day-duration path
- broader `row_assertion` shapes outside the bounded `dq_predicate` plus 100% path
- unsupported scope features such as `join`, `grouping`, `time_window`, and most `comparison` usage outside the bounded reference path
- target engines other than `gx` and `sodacl` in the live mutation path

## Capability registry versus live write support

The capability registry is broader than the live rule mutation path.

- The registry models `gx`, `sodacl`, `sql`, `pyspark_native`, and `custom_worker` targets.
- The live `POST` and `PUT` mutation flow currently accepts only `gx` and `sodacl` as target engines.
- The registry is used for fail-fast preservation checks, but registry entries do not by themselves mean the current rule write path can execute or persist every shape.

Two dedicated lowerer surfaces already exist outside the narrow mutation path:

- The GX lowerer can build bounded expectations for `row_assertion`, `metric_threshold`, `freshness_assertion`, `reference_assertion`, `schema_assertion`, and `custom_query_assertion`.
- The SodaCL lowerer can build bounded checks and artifact envelopes for `metric_threshold`, `schema_assertion`, and `freshness_assertion`.

That distinction matters because the contract, capability registry, and lowerer packages are ahead of the legacy rule-mutation compatibility layer.

## Assistant and preview behavior

The read-only DQ-7 assistant endpoint is intentionally narrower than the capability registry.

- `GET /api/rulebuilder/v1/suggestions/dq7-dsl-assistant` currently renders implemented support rows for GX only.
- The assistant does not currently render SodaCL, SQL, PySpark-native, or custom-worker support rows, even though the registry and lowerer packages already contain broader metadata.

This is implemented behavior today and should not be confused with the broader registry surface.

## Fail-fast error boundaries

The live implementation returns explicit machine-readable failures for the main contract boundaries:

- `403 rule_dsl_v2_not_enabled` when 2.0.0 writes are not enabled.
- `503 rule_dsl_v2_gate_unavailable` when the 2.0.0 gate repository is unavailable.
- `400 mixed_rule_dsl_contract` when a payload mixes 1.0.0 and 2.0.0 fields.
- `400 invalid_rule_dsl` when the normalized DSL is not compilable.
- `422 rule_dsl_lowering_unsupported` when semantic validation succeeds but the live write path cannot preserve the requested 2.0.0 shape.

## Related references

- Contract package: [../contracts/rule-dsl/README.md](/docs/contracts/rule-dsl/)
- Engine-independent implementation plan: [../implementation-details/DQ_7_ENGINE_INDEPENDENT_DSL_IMPLEMENTATION_PLAN.md](/docs/implementation-details/DQ_7_ENGINE_INDEPENDENT_DSL_IMPLEMENTATION_PLAN/)
- Rule compiler progress: [../implementation-details/DQ_7_3_RULE_COMPILER_IMPLEMENTATION_PROGRESS.md](/docs/implementation-details/DQ_7_3_RULE_COMPILER_IMPLEMENTATION_PROGRESS/)
- GX capability guidance: [../user-manuals/gx-capability-guidance.md](/docs/user-manuals/gx-capability-guidance/)