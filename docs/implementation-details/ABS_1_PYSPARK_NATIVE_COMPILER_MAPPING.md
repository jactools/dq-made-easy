# ABS-1 PySpark-Native Compiler Mapping

Status: Draft
Last updated: 2026-04-26

## Purpose

This note defines how canonical DQ-7.3 compiler output is translated into the PySpark-native artifact envelope introduced for ABS-1 multi-runtime expansion.

This mapping is intentionally compile-time only. It does not define an external compiler-output handoff contract. The compiler remains the source of truth, and the PySpark-native artifact is a derived engine-native artifact.

## Inputs

Required compiler-side inputs:

- DQ-7.3 intermediate model fields:
  - `artifactKey`
  - `compilerVersion`
  - `target`
  - `rule`
  - `filter`
  - `join`
  - `diagnostics`
  - `compilable`
- Rule/version metadata:
  - `rule_id`
  - `rule_version_id`
- Assignment and resolved execution scope metadata
- Primary-key and business-key metadata when available

Fail-fast preconditions:

- `compilable` must be `true`
- `target` must be `dsl`
- Compiler diagnostics must not contain unresolved error-level entries
- Resolved execution scope must contain at least one `data_object_version_id`

## Envelope Mapping

| Canonical compiler / metadata input | PySpark-native artifact field | Rule |
| --- | --- | --- |
| `artifactKey` | `artifact_id` | Reuse deterministic compiler key or derive a stable engine-specific key from it. |
| Compiler artifact revision / publish version | `artifact_revision` | Start at `1` for the first published PySpark-native artifact revision. |
| Constant | `artifact_version` | Always `v1` for this contract version. |
| Constant | `engine_type` | Always `pyspark_native`. |
| Constant | `engine_target` | Always `pyspark`. |
| Assignment scope metadata | `assignment_scope` | Copy through in snake_case. |
| Resolved execution scope metadata | `resolved_execution_scope` | Copy through in snake_case. |
| `rule.id`, related rule ids | `compiled_from.rule_ids` | Include all contributing rule ids for grouped artifacts. |
| `compilerVersion` | `compiled_from.compiler_version` | Copy through directly. |
| Compiler generation timestamp | `compiled_from.generated_at` | Use compiler artifact generation timestamp. |
| Primary/business key metadata | `execution_hints.*` | Copy when known; fail fast if required primary keys are unavailable for row-level failure output. |
| `rule.id` | `traceability.rule_id` | Required. |
| `rule.versionId` | `traceability.rule_version_id` | Required. |
| `artifactKey` or derived key | `traceability.artifact_id` | Must match envelope `artifact_id`. |
| Published revision | `traceability.artifact_revision` | Must match envelope `artifact_revision`. |
| Single resolved execution target when applicable | `traceability.data_object_version_id` | Use the grouped target for single-object planning; null only when no single target can be expressed. |

## Filter / Predicate Mapping

The compiler filter AST or predicate list is mapped into `pyspark_plan.checks`.

Deterministic mappings for v1:

| Canonical predicate shape | PySpark-native `check_kind` | Mapping |
| --- | --- | --- |
| `IS NOT NULL` on one column | `not_null` | `column_refs = [column]`; `assertion.predicate_sql = "column IS NOT NULL"` |
| `[NOT] IN (...)` on one column | `accepted_values` | Preserve allowed values in `assertion.allowed_values`; keep original predicate in `predicate_sql`. |
| `BETWEEN a AND b` on one column | `range` | Set `min_value`, `max_value`, and original `predicate_sql`. |
| `>=`, `<=`, `>`, `<` that collapse to a single bounded numeric/date range | `range` | Normalize to min/max when both bounds are proven for the same column. |
| `RLIKE` / regex alias on one column | `regex` | Preserve exact regex in `regex_pattern` and original `predicate_sql`. |
| Any supported predicate that cannot be losslessly specialized | `sql_predicate` | Preserve canonical SQL predicate text only. |

Fail-fast rules:

- Mixed-column expressions do not become `range`, `accepted_values`, or `regex` checks unless equivalence is proven.
- Unsupported functions or ambiguous predicate trees must fail the PySpark-native artifact build instead of silently degrading to a looser check.
- `LIKE` stays `sql_predicate` in v1 unless exact pattern equivalence to regex has been formally accepted.

## Logical Composition Mapping

- A top-level canonical filter becomes one or more PySpark-native checks.
- Simple leaf predicates map directly according to the table above.
- Compound `AND` expressions may emit multiple checks when each child predicate can be mapped independently without changing semantics.
- `OR`, nested mixed boolean groups, or `NOT` expressions that cannot be safely decomposed must emit one `sql_predicate` check carrying the normalized canonical predicate SQL.
- If the compiler cannot provide a stable normalized predicate string for such a case, artifact generation must fail fast.

## Join Mapping

- `join = null` maps to `pyspark_plan.execution_shape = single_object` and `input_mode = spark_dataframe`.
- A normalized join definition only maps to `execution_shape = join_pair` when ABS-1 already has a materialized-join handoff for that rule scope.
- The PySpark-native artifact must not instruct the executor to perform source joins directly.
- If a required landing-zone or materialized-join contract is absent, artifact generation must fail fast.

## Failure Output Mapping

- If row-level exception persistence is required, set `failure_output.emit_row_level_failures = true`.
- `failure_reason_template` should use a stable engine-specific code such as `pyspark_native_check_failed`.
- Primary-key projection must be present when row-level failures are emitted.

## Recommended Build Algorithm

1. Validate compiler output preconditions.
2. Resolve scope, primary keys, and grouped execution metadata.
3. Normalize canonical predicates into specialized checks where equivalence is proven.
4. Collapse any unsupported but still executable expression into `sql_predicate` only when semantics remain exact.
5. Fail artifact generation on unsupported or ambiguous mappings.
6. Emit the PySpark-native artifact envelope.
7. Wrap that payload in the neutral validation artifact envelope when publishing it through ABS-1 repositories or executor handoff.

## Current v1 Limits

- The mapping is defined for single-object predicates first.
- Join-pair support depends on the existing materialized-join seam and is not a license to push raw join execution into the custom executor.
- Unsupported compiler constructs must fail artifact creation; there is no implicit fallback from `pyspark_native` to `gx`.

## Related References

- [DQ-7.3 Rule Compiler Implementation Progress](./DQ_7_3_RULE_COMPILER_IMPLEMENTATION_PROGRESS.md)
- [PySpark-native artifact envelope contract](../contracts/pyspark-native-artifact-envelope/README.md)
- [ABS-1 execution abstraction](../features/ABS_1_EXECUTION_ABSTRACTION.md)