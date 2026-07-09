# DQ-7 Mock-Data DSL 2.0.0 Migration Plan

> **Status:** [x] Complete
> **Current phase:** release versioning complete
> **Next step:** none.
>
> **Validation note:** the live GX validation slice now passes against the rebuilt and reseeded stack.
>
> **Validation blocker:** none currently observed in the supported two-case smoke slice.

Related contract: [DQ-7 Rule DSL Contract](/docs/technical/DQ-7_RULE_DSL_CONTRACT/)
Current-state references:
- [DQ-7 Executable Rule Transformation](/docs/features/DQ-7_EXECUTABLE_RULE_TRANSFORMATION/)
Related rollout policy: [DQ-7 DSL Rollout Policy](/docs/implementation-details/DQ_7_DSL_ROLLOUT_POLICY/)
Related implementation plan: [DQ-7 Engine-Independent DSL Implementation Plan](/docs/implementation-details/DQ_7_ENGINE_INDEPENDENT_DSL_IMPLEMENTATION_PLAN/)

## Goal

Move repo-owned mock-data seeds onto the canonical DQ DSL `2.0.0` contract while keeping GX lowering honest:

- canonical seed payloads must use `dsl.schema_version: 2.0.0`
- unsupported GX semantics must fail fast instead of being disguised as native support
- legacy `check_type`, `check_type_params`, and `filter_expression` seed shapes should be retired from canonical seed sources after backfill
- reusable filter and reusable join references must become first-class `2.0.0` capabilities instead of compatibility-only metadata

## Principles

- Canonical contract first, runtime compatibility second.
- No silent fallback semantics.
- If GX cannot preserve the semantic intent, keep the seed canonical and mark the GX path partial or unsupported.
- Repo-owned seed sources should not continue to publish legacy DSL shapes once the canonical seed exists.

## Migration buckets

| Bucket | Seed shape | Action |
| --- | --- | --- |
| GX-native rewrite | simple row, metric, regex, range, allowlist, blocklist, uniqueness, and basic completeness shapes | Rewrite directly to `2.0.0` and keep GX lowering native where the contract already supports it |
| GX-partial rewrite | freshness, referential integrity, schema assertions, cross-object comparisons, and evidence-policy shapes | Rewrite to `2.0.0`, preserve the canonical intent, and mark GX lowering partial where required |
| Canonical but non-GX-faithful | expression-only aggregate comparisons and other custom query semantics | Rewrite to `2.0.0` using the explicit semantic family that best preserves intent, and fail fast on GX when no faithful lowering exists |
| Reusable-asset promotion | reusable filters and reusable joins | Promote reusable-asset references into the canonical `2.0.0` DSL contract and lower them explicitly in each engine |

## Uniquely numbered migration list

1. [x] `DQ7-SEED-001` Inventory every rule-bearing mock-data seed and classify its semantic family.
   - [x] Enumerate all repo-owned seed sources that still carry rule content.
   - [x] Tag each seed as GX-native, GX-partial, or canonical-only.
   - [x] Identify all remaining legacy `check_type`, `check_type_params`, and `filter_expression` payloads.
   - [x] Inventory reusable-filter and reusable-join seed assets and decide whether they are canonical DSL 2.0.0 capabilities or separate compatibility-only helpers.
   - [x] Final inventory: `dq-db/mock-data/rules.csv`, `dq-db/mock-data/rule_versions.csv`, `dq-db/mock-data/reusable_filters.csv`, `dq-db/mock-data/reusable_joins.csv`, and `dq-db/mock-data/rule_reusable_filters.csv` are the repo-owned mock-data sources carrying rule content; the validation-data fixtures remain the canonical test corpus.
   - [x] Final classification: the canonical mock-data set is GX-native, GX-partial, or canonical-only by semantic family, and reusable joins/filters are canonical `2.0.0` rule capabilities via `reusable_join_id` and `reusable_filter_ids`.

2. [x] `DQ7-SEED-002` Define the canonical `2.0.0` seed templates for each semantic family.
   - [x] Template catalog scaffolded in [../contracts/rule-dsl/2.0.0/seed-templates/catalog.json](https://github.com/jactools/dq-rulebuilder/blob/main/docs/contracts/rule-dsl/2.0.0/seed-templates/catalog.json).
   - [x] Freeze the shared canonical envelope for `dsl.schema_version`, `rule.kind`, `scope`, `measure`, `expectation`, `evidence`, and `operations`.
   - [x] Create seed templates for `row_assertion`.
   - [x] Create seed templates for `metric_threshold`.
   - [x] Create seed templates for `metric_comparison` where cross-metric comparisons are required.
   - [x] Create seed templates for `schema_assertion`.
   - [x] Create seed templates for `reference_assertion`.
   - [x] Create seed templates for `reconciliation_assertion`.
   - [x] Create seed templates for `freshness_assertion`.
   - [x] Create seed templates for `distribution_assertion`.
   - [x] Create seed templates for `anomaly_assertion`.
   - [x] Create seed templates for `custom_query_assertion` where expression-only semantics must be preserved.
   - [x] Record the GX support label for each template as native, partial, or canonical-only.

3. [x] `DQ7-SEED-003` Rewrite GX-native mock-data seeds to canonical `2.0.0`.
   - [x] Canonical GX-native subset generated in [../../validation-data/validate_rule_lifecycle_gx_native_cases_2_0_0.json](https://github.com/jactools/dq-rulebuilder/blob/main/validation-data/validate_rule_lifecycle_gx_native_cases_2_0_0.json).
   - [x] Convert direct row-predicate seeds to `row_assertion`.
   - [x] Convert aggregate and completeness seeds to `metric_threshold`.
   - [x] Convert composite uniqueness seeds to the canonical uniqueness-preserving `2.0.0` shape.
   - [x] Remove legacy DSL fields from the rewritten seed payloads.

4. [x] `DQ7-SEED-004` Rewrite GX-partial seeds to canonical `2.0.0` with explicit fidelity labels.
   - [x] Canonical GX-partial subset generated in [../../validation-data/validate_rule_lifecycle_gx_partial_cases_2_0_0.json](https://github.com/jactools/dq-rulebuilder/blob/main/validation-data/validate_rule_lifecycle_gx_partial_cases_2_0_0.json).
   - [x] Convert freshness and timeliness seeds to `freshness_assertion`.
   - [x] Convert referential integrity and cross-object comparison seeds to `reference_assertion` or `reconciliation_assertion`.
   - [x] Convert schema-related seed cases to `schema_assertion`.
   - [x] Preserve evidence and operational intent in the canonical payload instead of in ad-hoc seed metadata.
   - [x] No schema-specific GX-partial source cases were present in the supported fixture; the partial rewrite focused on freshness, reference, and reconciliation shapes.

5. [x] `DQ7-SEED-005` Convert expression-only seed cases into explicit semantic contract shapes.
   - [x] Canonical expression-only subset generated in [../../validation-data/validate_rule_lifecycle_gx_expression_only_cases_2_0_0.json](https://github.com/jactools/dq-rulebuilder/blob/main/validation-data/validate_rule_lifecycle_gx_expression_only_cases_2_0_0.json).
   - [x] The expression-only rewrite scope is the four plausibility-style custom-query cases remaining after the partial rewrite.
   - [x] Rewrite dynamic aggregate comparisons to the closest canonical metric or custom query contract.
   - [x] Rewrite custom SQL-like predicates to `custom_query_assertion` or `row_assertion` only when the semantics remain faithful.
   - [x] Reject any attempt to keep these cases as legacy free-form seed fragments.

6. [x] `DQ7-SEED-006` Rebuild validation fixtures from the canonical `2.0.0` seeds.
   - [x] Regenerate `validation-data` cases from the rewritten seed set in [../../validation-data/validate_rule_lifecycle_gx_rebuilt_cases_2_0_0.json](https://github.com/jactools/dq-rulebuilder/blob/main/validation-data/validate_rule_lifecycle_gx_rebuilt_cases_2_0_0.json).
   - [x] Regenerate GX registry and suite snapshot data that depends on the migrated seeds.
   - [x] Keep snake_case contract fields only in the regenerated fixtures.
   - [x] Normalize the suite names in [../../dq-db/mock-data/gx-suite-registry.csv](https://github.com/jactools/dq-rulebuilder/blob/main/dq-db/mock-data/gx-suite-registry.csv) and [../../dq-db/mock-data/validation-artifact-registry.csv](https://github.com/jactools/dq-rulebuilder/blob/main/dq-db/mock-data/validation-artifact-registry.csv) to the canonical versionless suite identifiers.

7. [x] `DQ7-SEED-007` Add fail-fast tests for the supported and unsupported GX paths.
   - [x] Prove the GX-native `2.0.0` seeds lower successfully.
   - [x] Prove partial shapes lower only within the supported subset.
   - [x] Prove unsupported shapes fail with a machine-readable lowering reason.
   - [x] Added regression coverage in [../../dq-api/fastapi/tests/application/use_cases/test_rule_mutation_use_cases.py](https://github.com/jactools/dq-rulebuilder/blob/main/dq-api/fastapi/tests/application/use_cases/test_rule_mutation_use_cases.py) for a canonical supported case and an explicit unsupported GX lowering path.

8. [x] `DQ7-SEED-008` Remove legacy DSL fields from canonical seed sources.
   - [x] Retire `check_type` from rewritten canonical seed records.
   - [x] Retire `check_type_params` from rewritten canonical seed records.
   - [x] Retire `filter_expression` from rewritten canonical seed records.
   - [x] Keep any remaining legacy shapes only in explicitly named compatibility fixtures, if they are still needed for tests.

9. [x] `DQ7-SEED-009` Validate the reseed and smoke-test flow after migration.
   - [x] Run the seed and validation scripts that exercise the mock-data path.
   - [x] Confirm the new canonical seeds do not introduce silent backend fallbacks.
   - [x] Confirm the smoke path still fails fast for shapes that GX cannot faithfully preserve.
   - [x] The supported two-case GX lifecycle slice now passes after the reseed and backend contract fixes.

10. [x] `DQ7-SEED-010` Promote reusable filters and reusable joins into the canonical DSL `2.0.0` contract.
   - [x] Define canonical reusable-filter and reusable-join reference shapes in the DSL contract.
   - [x] Update engine lowerers to resolve reusable assets from canonical DSL payloads instead of treating them as sidecar metadata.
   - [x] Add fail-fast coverage for unsupported reusable-asset lowering paths.
   - [x] Backfill seed templates and fixtures so reusable assets are emitted through the canonical contract once the engine support lands.

## Acceptance criteria

- All repo-owned mock-data seeds that represent rules are stored as canonical `2.0.0` payloads.
- The canonical seed set makes the GX support boundary explicit instead of assuming every rule is native.
- Legacy seed contracts are removed from canonical mock-data sources after backfill.
- Reusable filters and reusable joins are modeled as canonical `2.0.0` capabilities rather than compatibility-only metadata.
- Validation data and smoke tests continue to fail fast where GX cannot preserve semantics.