# GX Capability Guidance

**Time to read:** 4 minutes
**Last updated:** 2026-05-03

## Purpose
This card explains the actual GX capability map for DQ Made Easy rules and how to tell whether a rule will lower cleanly or fail fast.

## How to read capability status

| Status | Meaning |
| --- | --- |
| `native` | The backend can represent the rule directly. |
| `partial` | Only the listed subsets are supported. Anything outside the subset fails fast. |
| `no` | The backend does not support the construct family. |

## Actual GX capability overview

| Construct family | GX support | Supported subsets | Compiler behavior |
| --- | --- | --- | --- |
| `row_assertion` | `native` | `row_filter`, `row_predicate`, `threshold_percent`, `failed_rows` | Prefer native predicate lowering and preserve row scope and evidence policy. |
| `metric_threshold` | `native` | `row_count`, `missing_count`, `missing_percent`, `duplicate_count`, `duplicate_percent`, `distinct_count`, `min`, `max`, `avg`, `sum`, `stddev`, `quantile`, `freshness_age`, `match_percent` | Treat this as the main cross-engine deterministic construct. |
| `metric_comparison` | `partial` | `grouped_comparison`, `cross_source_comparison` | Prefer SQL for broadest fidelity when comparing grouped or cross-source metrics. |
| `schema_assertion` | `partial` | `required_columns_present`, `forbidden_columns_absent`, `column_types_match`, `column_count_between`, `column_order_matches` | Prefer native schema checks where the table shape can be expressed directly; lower required, forbidden, count, order, and type clauses explicitly. |
| `reference_assertion` | `partial` | `comparison_scope`, `single_join_key`, `ref_data_object_id`, `ref_data_object_version_id` | Prefer SQL for portable existence checks across sources. |
| `reconciliation_assertion` | `partial` | `cross_source_comparison`, `matched_rows`, `unmatched_rows` | Default to SQL or custom runtime plans for reconciliation semantics. |
| `freshness_assertion` | `partial` | `freshness_age`, `duration_iso8601_days`, `anchor_now` | Normalize time units and anchoring rules in the IR before lowering. |
| `distribution_assertion` | `native` | `distribution_metrics`, `quantile`, `histogram` | Prefer native statistical support; use SQL or custom runtime when portable semantics require it. |
| `anomaly_assertion` | `partial` | `history_window`, `baseline_strategy`, `anomaly_score` | Require a history-aware engine or custom worker; fail fast for SQL-only targets. |
| `custom_query_assertion` | `partial` | `sql_query` | Lower query-comparison assertions only when both SQL queries and the comparison data source name are provided. |
| `failed_rows_evidence_policy` | `partial` | `summary_only`, `sample`, `all_with_limit`, `include_row_identifier`, `include_primary_key`, `emit_compiled_artifact`, `emit_generated_sql` | Treat evidence emission as a separate concern from assertion semantics. |
| `operational_metadata` | `native` | `severity`, `preferred_engines`, `fail_if_not_native` | Preserve operational metadata even when the target ignores some fields. |

## What this means for authors

1. Pick GX only when the capability registry marks the construct family or subset as supported.
2. If the status is `partial`, stay inside the supported subset or change the rule shape.
3. If the status is `no`, the rule must fail fast and the authoring path should explain why.

## Engine type usage

`engine_type` declares which runtime family a rule is expected to run against. The practical cases are:

- `gx`:
  - The default RuleBuilder runtime for GX artifacts.
  - Used for standard GX validation suites, especially when the rule is expressed in the GX artifact model and the target engine is not explicitly `pyspark_native`.
  - Good for row assertions, metric thresholds, distribution assertions, and the existing rule execution path.

- `pyspark_native`:
  - Used when the rule is compiled for Spark-native execution and the engine capability supports SQL pushdown or streaming/micro-batch shapes.
  - Chosen when `preferred_engines` or execution hints explicitly prefer `pyspark_native`, or when the run plan/execution contract engineTarget is `pyspark_native`.
  - Best for large datasets, distributed workloads, and cases where Spark can push down predicate/filter logic instead of materializing full source sets.

- `soda`:
  - Used when a rule is authored as SodaCL checks or the backend chooses the Soda runtime.
  - Intended for single-object validation shapes that match Soda's supported check families.
  - Not typically used for join_pair or multi-source pushdown workloads.

- `sql`:
  - Used when the rule is naturally expressed as a SQL query and the execution target can run SQL directly.
  - This path is for SQL-native validation and is not the default for GX artifact compilation.

- `custom_worker`:
  - Used when a rule requires a custom execution engine or domain-specific worker.
  - Appropriate when no ordinary runtime such as GX, Spark, or Soda can express the rule semantics.

### When to expect `pyspark_native` instead of `gx`

- The rule has an execution hint or preferred engine pointing at `pyspark_native`.
- The execution contract is written for streaming or micro-batch validation.
- The target workload is large enough that Spark-native pushdown or scalable execution is needed.
- The engine capability registry marks the path as supporting SQL pushdown and the rule is in a supported subset.

### When `gx` remains the safer default

- The rule is otherwise a normal GX suite and you want the behavior of the existing GX runtime.
- The rule uses families such as row assertions, metric thresholds, or evidence policies that are already well-supported by GX.
- You do not need Spark-specific distributed execution, streaming, or SQL pushdown.

## Practical GX reading

- GX is strongest for row assertions, metric thresholds, distribution assertions, and operational metadata.
- GX is partial for cross-source, reference, reconciliation, freshness, anomaly, and evidence-policy flows.
- If the authoring intent needs broad cross-source fidelity, SQL is usually the safer target.

## Example payload

Use this shape as a reference when you want a GX-friendly rule with evidence capture:

- `schema_version`: `2.0.0`
- `rule.kind`: `metric_threshold`
- `rule.scope.dataset.data_object_id`: `do-customer`
- `rule.measure.metric`: `row_count`
- `rule.expectation.operator`: `gte`
- `rule.expectation.value`: `1000`
- `rule.expectation.unit`: `count`
- `rule.evidence.failed_rows.mode`: `sample`
- `rule.evidence.failed_rows.limit`: `25`
- `rule.operations.preferred_engines`: `gx`

## Internal note

Some internal mock-data examples may still use `1.0.0` payloads for reference, but new authoring guidance should prefer `2.0.0`.

## Related cards

- [Engine Capability Guidance](/docs/user-manuals/engine-capability-guidance/)
- [Governance Terminology Reference Card](/docs/user-manuals/governance-terminology/)
- [UI Capability Matrix](/docs/user-manuals/ui-capability-matrix/)