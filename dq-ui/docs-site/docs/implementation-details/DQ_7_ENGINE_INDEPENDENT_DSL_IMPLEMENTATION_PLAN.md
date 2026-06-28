# DQ-7 Engine-Independent DSL Implementation Plan

> **Status:** [~] In progress
> **Current phase:** canonical contract definition and exact runtime lowering
> **Next step:** move from the backend capability registry to fail-fast lowering validation.

Related feature note: [../features/DQ-7_RULE_DSL_CONTRACT.md](/docs/technical/DQ-7_RULE_DSL_CONTRACT/)

## Goal

Implement a canonical DQ DSL that describes data quality checks independently from Great Expectations, SodaCL, SQL, or any single runtime, while still lowering fail-fast to supported execution backends.

## Principles

- Canonical user intent first, engine syntax second.
- No silent fallback semantics.
- Lowering must preserve meaning or fail fast.
- SQL is an execution target, not the DSL.
- Evidence and operational intent are part of the rule contract, not just runtime side effects.

## Uniquely numbered implementation list

1. [x] `DQ7-DSL-001` Freeze the canonical construct-family list for `dsl.schema_version = 2.0.0`.
    Status: complete.
    Deliverable: approved list of semantic rule kinds:
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

2. [x] `DQ7-DSL-002` Define the top-level `2.0.0` API schema.
    Status: complete.
   Deliverable: OpenAPI and JSON Schema contract for `dsl.rule.kind`, `scope`, `measure`, `expectation`, `evidence`, and `operations`.

3. [x] `DQ7-DSL-003` Define the canonical scope vocabulary.
    Status: complete.
    Deliverable: typed schema for dataset scope, row filter scope, join scope, grouping scope, time-window scope, and cross-source comparison scope.
    Canonical scope vocabulary:
    - `dataset`
    - `row_filter`
    - `join`
    - `grouping`
    - `time_window`
    - `comparison`

4. [x] `DQ7-DSL-004` Define the canonical metric vocabulary.
    Status: complete.
   Deliverable: typed schema and registry for metrics such as `row_count`, `missing_percent`, `duplicate_count`, `distinct_count`, `avg`, `sum`, and `freshness_age`.
    Canonical metric vocabulary:
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

5. [x] `DQ7-DSL-005` Define the canonical expectation vocabulary.
    Status: complete.
   Deliverable: typed schema for threshold, equality, set-membership, schema-contract, and baseline-driven expectation clauses.
    Canonical expectation vocabulary:
    - `threshold`
    - `equality`
    - `set_membership`
    - `schema_contract`
    - `baseline`

6. [x] `DQ7-DSL-006` Define the canonical evidence vocabulary.
    Status: complete.
   Deliverable: schema for summary-only results, failed-row sampling, row identifiers, generated SQL capture, and compiled artifact capture.
    Canonical evidence vocabulary:
    - `failed_rows`
    - `emit_compiled_artifact`
    - `emit_generated_sql`

7. [x] `DQ7-DSL-007` Define the canonical operations vocabulary.
    Status: complete.
    Deliverable: schema for severity, preferred engines, and fail-if-not-native policy in the current executable contract; ownership and alert intent remain future extensions.
    Canonical operations vocabulary:
    - `severity`
    - `preferred_engines`
    - `fail_if_not_native`

    Auxiliary capability families that travel through the same canonical contract but are not rule kinds:
    - `failed_rows_evidence_policy`
    - `operational_metadata`

8. [x] `DQ7-DSL-008` Introduce a typed semantic IR package in the backend.
    Status: complete.
   Deliverable: runtime-safe IR classes or models that normalize `2.0.0` payloads before lowering.

9. [ ] `DQ7-DSL-009` Build a `1.0.0` to IR adapter.
   Deliverable: compatibility adapter that maps current `filter_expression` and `check_type` payloads into the new IR without changing current callers immediately.

10. [x] `DQ7-DSL-010` Build a `2.0.0` to IR adapter.
    Status: complete.
    Deliverable: direct mapper from the canonical semantic payload to the IR.

11. [x] `DQ7-DSL-011` Define the backend capability registry.
    Status: complete.
    Deliverable: machine-readable capability matrix covering GX, SodaCL, SQL, PySpark-native, and custom-worker targets by construct family and subset.

12. [x] `DQ7-DSL-012` Enforce fail-fast lowering validation.
    Status: complete.
    Deliverable: compiler step that rejects rules when the chosen target engine cannot preserve semantics, prevents persistence of runnable backend fields for that target, and never falls back to a different backend.

13. [x] `DQ7-DSL-013` Implement the GX lowerer.
    Status: complete.
    Deliverable: lowering pipeline from IR to GX expectation suites or GX-compatible artifacts, with explicit native versus partial support rules.

14. [~] `DQ7-DSL-014` Implement the SodaCL lowerer.
    Deliverable: lowering pipeline from IR to SodaCL checks, including schema, freshness, failed rows, and metric-oriented constructs where supported.
    Status: partial. A minimal SodaCL lowering seam now exists for simple metric, schema, and freshness cases; the rule write path validates SodaCL-preferred rules and activation now auto-publishes SodaCL artifacts for the supported subset. Unsupported scope families still fail fast.

15. [ ] `DQ7-DSL-015` Implement the SQL lowerer.
    Deliverable: lowering pipeline from IR to parameterized SQL artifacts for metric, reconciliation, referential-integrity, schema-introspection, and custom-query assertions.

16. [ ] `DQ7-DSL-016` Implement the custom-worker lowering seam.
    Deliverable: explicit artifact contract for rules that cannot be represented faithfully in GX, SodaCL, or SQL alone.

17. [x] `DQ7-DSL-017` Add schema-assertion execution support.
    Status: complete.
    Deliverable: end-to-end support for required columns, forbidden columns, type checks, and column-count checks.

18. [x] `DQ7-DSL-018` Add first-class aggregate-metric execution support.
    Status: complete
    Deliverable: end-to-end support for aggregate checks without forcing them through row-predicate syntax.

|Id|Aggregate rule family|	UI today |API / lowering today | GX execution today|
|--| --|--|--|--|
|UI-AGG-01|row_count|Yes |Yes |Yes|
|UI-AGG-02|quantile|Yes |Yes |Yes|
|UI-AGG-03|null_pct, the UI name for missing-rate completeness | Yes|Yes|Yes|
|UI-AGG-04|min, max, avg, sum, stddev, distinct_count | Yes |Yes|Yes|
|UI-AGG-05|missing_count, duplicate_count, duplicate_percent | Yes | Yes, but only bounded zero-threshold semantics: the API lowering can represent these checks only when the allowed deviation is exactly zero and the rule is interpreted as a bounded absence/duplication guard, not as a general threshold, percentile, ratio, or baseline comparison. | Yes, but only that same bounded zero-threshold semantics: GX can execute these checks only as exact zero-tolerance constraints, and must fail fast if a caller tries to express broader tolerance or non-zero threshold behavior. |

19. [~] `DQ7-DSL-019` Add first-class evidence policy execution support.
    Deliverable: execution path that honors summary-only, sample failed rows, and audit-artifact requirements consistently across backends.
    .1 [x] for GX
    .2 [x] for SodaCL
    .3 [ ] for SQL
    .4 [ ] for custom-worker

20. [~] `DQ7-DSL-020` Add compiler and lowering contract tests.
    Deliverable: test suite that asserts one canonical rule payload either lowers consistently across GX, SodaCL, and SQL or fails fast with a machine-readable unsupported reason.
    .1 [x] for GX
    .2 [x] for SodaCL
    .3 [ ] for SQL
    .4 [ ] for custom-worker
    .5 [x] mixed GX/Soda execution-plan catalog responses remain unified.
    .6 [x] validation wrapper added at `scripts/validate_mixed_engine_execution_plan.sh` and now runs the host-local live DB mixed-plan regression.
    .7 [x] CSV-backed mixed plan test reads `dq-db/mock-data` seed rows.
    .8 [x] Validation Plans page renders plan-scoped recent runs from the execution-monitoring API.

21. [x] `DQ7-DSL-021` Add engine-capability guidance.
    Deliverable: user-facing docs for supported and unsupported backend capabilities, sample `2.0.0` payloads, and any `1.0.0` mock-data examples needed for internal reference. Migration guidance is deferred until there is a real user-facing `1.0.0` adoption path.
    .1 [x] Short docs in user-manuals as the source of truth.
    .2 [x] A UI capability matrix or small wizard for guided discovery.
    .3 [x] AI assistance only as a read-only helper, not as the contract owner.
        .3.1 [x] Add a read-only assistant panel in the rule wizard that can explain supported capabilities and surface example payloads.
        .3.2 [x] Back the assistant with a read-only backend suggestions endpoint derived from the canonical capability registry and guidance docs.
        .3.3 [x] Block all create, update, and persist actions from AI output; validation and persistence remain with the backend gate.
        .3.4 [x] Add tests proving the assistant cannot mutate contracts and fails fast if the suggestions service is unavailable.
        .3.5 [x] Scope assistant support rows to implemented runtimes only; current user-facing assistant guidance reports GX support and omits planned SodaCL, SQL, PySpark, and custom-worker targets.

22. [x] `DQ7-DSL-022` Add rollout controls and compatibility gates.
    Deliverable: explicit version gate at ingestion or lowering time so repo-controlled callers can opt into `2.0.0` incrementally, with fail-fast rejection of mixed or unsupported semantics.
    .1 [x] Add an explicit opt-in gate for `2.0.0` payloads.
    .2 [x] Reject mixed-version or unsupported compatibility paths before persistence or execution.
    .3 [x] Add tests that prove opted-in `2.0.0` paths work and non-opted-in paths fail fast.
    .4 [x] Keep rollout policy separate from the 021 guidance docs and UI discovery cards. Documented in [DQ_7_DSL_ROLLOUT_POLICY.md](/docs/implementation-details/DQ_7_DSL_ROLLOUT_POLICY/) and exposed only through the admin app-config surface.

## Recommended implementation order

### Phase A: Canonical contract definition

- `DQ7-DSL-001`
- `DQ7-DSL-002`
- `DQ7-DSL-003`
- `DQ7-DSL-004`
- `DQ7-DSL-005`
- `DQ7-DSL-006`
- `DQ7-DSL-007`

### Phase B: Compiler normalization

- `DQ7-DSL-008`
- `DQ7-DSL-009`
- `DQ7-DSL-010`
- `DQ7-DSL-011`
- `DQ7-DSL-012`

### Phase C: Backend lowerers

- `DQ7-DSL-013`
- `DQ7-DSL-014`
- `DQ7-DSL-015`
- `DQ7-DSL-016`

### Phase D: Missing construct families

- `DQ7-DSL-017`
- `DQ7-DSL-018`
- `DQ7-DSL-019`

### Phase E: Verification and rollout

- `DQ7-DSL-020`
- `DQ7-DSL-021`
- `DQ7-DSL-022`

## Acceptance criteria

- A canonical `2.0.0` rule payload can represent deterministic constructs currently spread across our DSL, GX, and SodaCL.
- The compiler emits a typed IR before selecting a backend.
- Each backend lowerer declares native, partial, SQL-assisted, or unsupported support explicitly.
- Unsupported semantics fail fast before execution.
- Contract tests prove semantic preservation or explicit rejection.
- Repo-controlled callers can migrate from `1.0.0` without silent compatibility shims.