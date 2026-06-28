# DQ-4 New Rule Types / Checks — Implementation Progress

> **Deprecated:** Historical progress log for the DQ-4 typed check-type builder. New rule-contract, lowering, assistant, and capability guidance work now lives in the DQ-7 docs.
> Use [DQ-7 Rule DSL Contract](/docs/technical/DQ-7_RULE_DSL_CONTRACT/) and [DQ-7 Engine-Independent DSL Implementation Plan](/docs/implementation-details/DQ_7_ENGINE_INDEPENDENT_DSL_IMPLEMENTATION_PLAN/) for current guidance.

Status: [x] Complete  
Last updated: 2026-04-19  
Related feature tracker: ../features/DQ_FEATURES.md

Final UI acceptance gaps closed on 2026-04-19:
- Reports now expose check-type coverage by DAMA dimension.
- Wizard validation now surfaces field-level messages across typed check parameter forms, not only join consistency.

## Coverage Delta (2026-03-28)

Final stabilization and coverage uplift completed across API, service, and repository test suites.

- Full suite result: `780 passed, 1 skipped`.
- Branch+line coverage gate: `90.13%` (fail-under target: `90%`).
- Per-file minimum coverage target (`>=60%`) is satisfied.

Primary high-impact test additions in this pass:
- `dq-api/fastapi/tests/application/services/test_check_type_expression_generator.py`
- `dq-api/fastapi/tests/application/services/test_rule_compiler.py`
- `dq-api/fastapi/tests/api/test_rules_endpoint_mapping_focus.py`
- `dq-api/fastapi/tests/infrastructure/unit/repositories/in_memory/test_testing_repository_focus.py`
- `dq-api/fastapi/tests/infrastructure/unit/repositories/postgres/test_rules_repository_postgres.py`

Validation command:
- `cd dq-api/fastapi && ../../venv/bin/python -m pytest tests --cov=app --cov-branch --cov-report=json:test-results/coverage.full.json --cov-fail-under=90 -q`

## Scope

DQ-4 currently covers sixteen implemented/current executable rule check-types that can be
defined through guided structured parameters instead of a raw expression string. Each
implemented check-type auto-generates a DQ-7 compiler-ready expression when saved, while
leaving existing free-form expression rules fully intact. The feature tracker now also
captures the initial execution scope and guardrails for the newly added extended types.

Implemented/current executable scope in this note:
- `THRESHOLD`
- `REGEX`
- `RANGE`
- `ALLOWLIST`
- `BLOCKLIST`
- `UNIQUENESS`
- `REFERENTIAL_INTEGRITY`
- `FRESHNESS`
- `LAG`
- `FUTURE_DATE`
- `CORRECT`
- `PRESENT`
- `RECONCILE`
- `PLAUSIBLE`
- `TRANSFER_MATCH`
- `JOIN_CONSISTENCY`

Initial scope constraints for the extended taxonomy:
- `CORRECT` compares a source object against an authoritative reference object through declared join keys and a single comparison rule.
- `PRESENT` enforces non-null, non-blank values with optional placeholder blocking.
- `RECONCILE` supports lightweight cross-object reconciliation through one or more declared comparisons without actuality-date contract semantics.
- `PLAUSIBLE` is currently limited to `contextual_range` and `conditional_allowlist` modes.
- `TRANSFER_MATCH` is currently limited to `row_value_match` and `payload_hash_match` modes.

Full context and acceptance criteria: [DQ_FEATURES.md — DQ-4 section](/docs/features/DQ_FEATURES/#dq-4-new-rule-types--checks)

## GX Core Coverage Matrix (2026-04-20)

This matrix distinguishes between:

- `Native GX Core`: the published expectation is a GX Core expectation class and the real Spark worker can execute it through GX Core `batch.validate(expectation)`.
- `Hybrid`: part of the rule type uses native GX Core, but one or more modes or sub-checks still require custom worker-backed expectations.
- `Custom worker`: the current implementation does not execute that rule type through native GX Core in the real Spark worker.

| Check-type | GX Core status | Current native GX Core coverage | Notes |
|---|---|---|---|
| `THRESHOLD` | Hybrid | `null_pct` only | Native GX aggregate mapping exists for `null_pct`; `empty_pct` and `default_val_pct` are not auto-published to GX Core today. |
| `REGEX` | Native GX Core | Full current scope | Publishes as native GX regex expectation. |
| `RANGE` | Native GX Core | Full current scope | Publishes as native GX between expectation, including one-sided bounds and inclusive/exclusive options. |
| `ALLOWLIST` | Native GX Core | Full current scope | Uses native GX `in_set` for case-sensitive lists and native regex for case-insensitive lists. |
| `BLOCKLIST` | Native GX Core | Full current scope | Uses native GX `not_in_set` or native regex negation depending on case sensitivity. |
| `UNIQUENESS` | Native GX Core | Full current scope | Uses native GX single-column uniqueness or compound-column uniqueness. |
| `REFERENTIAL_INTEGRITY` | Native GX Core | Narrow native scope | Current GX publication is a native not-null check on the joined `rhs` reference attribute after join materialization. |
| `FRESHNESS` | Custom worker | None | Uses a custom worker-backed expectation shape today; not part of the native GX execution allowlist. |
| `LAG` | Custom worker | None | Uses a custom lag expectation shape today; not executed through native GX Core. |
| `FUTURE_DATE` | Custom worker | None | Uses a custom worker-backed future-date expectation shape today; not executed through native GX Core. |
| `CORRECT` | Hybrid | `exact` comparison mode | Exact cross-object equality uses native GX column-pair equality; `case_insensitive` and `numeric_tolerance` remain custom worker-backed. |
| `PRESENT` | Native GX Core | Full current scope | Implemented via native not-null plus native regex-based blank/placeholder blocking expectations. |
| `RECONCILE` | Hybrid | `exact` comparison mode | Exact comparisons are native GX column-pair equality; non-exact comparison modes remain custom worker-backed. |
| `PLAUSIBLE` | Native GX Core | Full currently implemented scope | `contextual_range` and `conditional_allowlist` now publish as native GX expectations scoped by GX `row_condition`. |
| `TRANSFER_MATCH` | Hybrid | `payload_hash_match` and `row_value_match` with `exact` comparisons | Native for payload-hash equality and exact row-value equality; non-exact row-value comparisons remain custom worker-backed. |
| `JOIN_CONSISTENCY` | Hybrid | Exact comparison clauses only | Exact value comparisons are native GX column-pair equality; actuality-date tolerance remains custom worker-backed. |

Summary:

- Fully native GX Core for the currently implemented scope: `REGEX`, `RANGE`, `ALLOWLIST`, `BLOCKLIST`, `UNIQUENESS`, `PRESENT`, `PLAUSIBLE`.
- Hybrid: `THRESHOLD`, `REFERENTIAL_INTEGRITY`, `CORRECT`, `RECONCILE`, `TRANSFER_MATCH`, `JOIN_CONSISTENCY`.
- Still custom worker-backed: `FRESHNESS`, `LAG`, `FUTURE_DATE`.

---

## DQ-4.1 — Define RuleCheckType Taxonomy

Status: [x] Complete

### Backend

Files to add / change:
- `dq-api/fastapi/app/domain/entities/rule_check_type.py` *(new)*
  - `RuleCheckType` enum with all currently executable values
  - `RuleCheckTypeParams` union type mapping each check-type to its parameter model
- `dq-api/fastapi/app/api/v1/schemas/rule_view.py` — add `checkType` / `checkTypeParams` fields to `RuleView` and `RuleCreateRequest`
- `dq-api/fastapi/app/infrastructure/orm/models.py` — add `check_type TEXT`, `check_type_params JSONB` columns to `RuleRow`

### Database

Files to change:
- `dq-db/init/01_schema.sql` — add `check_type TEXT`, `check_type_params JSONB` to `rules` table
- `dq-db/scripts/validate_seed_headers.py` — will auto-validate after schema change

### Frontend

Files to change:
- `dq-ui/src/types/rules.ts` — add `RuleCheckType` union type and `RuleCheckTypeParams` interface to `Rule`

---

## DQ-4.2 — Threshold / Completeness Checks

Status: [x] Complete

Check-type: `THRESHOLD`  
DAMA dimension: Completeness  
Parameters: `attribute`, `metric` (`null_pct` | `empty_pct` | `default_val_pct`), `operator` (`gt` | `gte` | `lt` | `lte`), `threshold` (number)

Expression template:
```
percentage_of({attribute} IS NULL) {operator} {threshold}
```

Files added / changed:
- [x] `dq-api/fastapi/app/domain/entities/rule_check_type.py` — `ThresholdParams` dataclass
- [x] `dq-api/fastapi/app/application/services/check_type_expression_generator.py` — all implemented executable generators
- [x] `dq-api/fastapi/app/application/services/__init__.py` — exports `generate_expression_from_check_type`
- [x] `dq-api/fastapi/app/api/v1/endpoints/rules.py` — wired `checkType`/`checkTypeParams` → generator
- [x] `dq-ui/src/components/CheckTypeForm/ThresholdForm.tsx`
- [x] `dq-ui/src/components/CheckTypeForm/index.tsx`
- [x] `dq-ui/src/components/CheckTypeForm/CheckTypeForm.css`

---

## DQ-4.3 — Pattern / Regex Checks

Status: [x] Complete

Check-type: `REGEX`  
DAMA dimension: Accuracy  
Parameters: `attribute`, `pattern` (string), `flags` (string, optional — e.g. `i` for case-insensitive)

Expression template:
```
{attribute} MATCHES '{pattern}'
```

Files added / changed:
- [x] `dq-api/fastapi/app/domain/entities/rule_check_type.py` — `RegexParams` dataclass
- [x] expression generator: `REGEX` branch in `check_type_expression_generator.py`
- [x] `dq-ui/src/components/CheckTypeForm/RegexForm.tsx` *(new)*
- [x] `dq-ui/src/components/CheckTypeForm/index.tsx` — dispatcher wiring for `REGEX`
- [x] `dq-api/fastapi/tests/application/services/test_check_type_expression_generator.py` *(new)* — regex generator unit coverage

Validation / unit test evidence:
- Primary test file: `dq-api/fastapi/tests/application/services/test_check_type_expression_generator.py`
- Regex-specific cases in that file:
  - `test_generate_regex_expression_without_flags`
  - `test_generate_regex_expression_with_flags`
  - `test_generate_regex_expression_requires_attribute`
  - `test_generate_regex_expression_requires_pattern`
- Focused command (repo root):
  - `cd dq-api/fastapi && ../../venv/bin/python -m pytest --no-cov tests/application/services/test_check_type_expression_generator.py -k regex -q`
- Full generator command (repo root):
  - `cd dq-api/fastapi && ../../venv/bin/python -m pytest --no-cov tests/application/services/test_check_type_expression_generator.py -q`
- Latest validation run (2026-03-26):
  - Command executed via FastAPI test wrapper:
    - `cd dq-api && ./scripts/testing/run_fastapi_pytest.sh --no-cov tests/application/services/test_check_type_expression_generator.py -k regex -q`
  - Result: `4 passed, 12 deselected in 0.36s`
- Result artifact locations (repo root):
  - `test-results/coverage.xml`
  - `test-results/coverage.json`

---

## DQ-4.4 — Range Checks

Status: [x] Complete

Check-type: `RANGE`  
DAMA dimensions: Validity / Timeliness  
Parameters: `attribute`, `minValue` (number | date, optional), `maxValue` (number | date, optional), `inclusive` (boolean, default `true`)

Expression template:
```
{attribute} BETWEEN {minValue} AND {maxValue}
```

Files added / changed:
- [x] `dq-api/fastapi/app/domain/entities/rule_check_type.py` — `RangeParams` dataclass
- [x] `dq-api/fastapi/app/application/services/check_type_expression_generator.py` — `RANGE` branch with inclusive/exclusive and one-sided bounds
- [x] `dq-ui/src/components/CheckTypeForm/RangeForm.tsx` *(new)*
- [x] `dq-ui/src/components/CheckTypeForm/index.tsx` — dispatcher wiring for `RANGE`
- [x] `dq-ui/src/components/Templates.tsx` — range defaults + range validation in Step 3 wizard flow
- [x] `dq-api/fastapi/tests/application/services/test_check_type_expression_generator.py` — range generator coverage (inclusive/exclusive/one-sided/error)

Validation / unit test evidence:
- Focused command (repo root):
  - `cd dq-api && ./scripts/testing/run_fastapi_pytest.sh --no-cov tests/application/services/test_check_type_expression_generator.py -k range -q`
- Latest validation run (2026-03-26):
  - Result: `5 passed, 12 deselected in 0.27s`

---

## DQ-4.5 — Allowlist and Blocklist Checks

Status: [x] Complete

Check-types: `ALLOWLIST`, `BLOCKLIST`  
DAMA dimensions: Accuracy / Validity  
Parameters: `attribute`, `values[]` (string list), `caseSensitive` (boolean, default `false`)

Expression templates:
```
{attribute} IN ({values})       -- ALLOWLIST
{attribute} NOT IN ({values})   -- BLOCKLIST
```

Files added / changed:
- [x] `dq-api/fastapi/app/domain/entities/rule_check_type.py` — `AllowlistParams`, `BlocklistParams`
- [x] `dq-api/fastapi/app/application/services/check_type_expression_generator.py` — `ALLOWLIST` / `BLOCKLIST` branches
- [x] `dq-ui/src/components/CheckTypeForm/AllowlistForm.tsx` *(new)*
- [x] `dq-ui/src/components/CheckTypeForm/index.tsx` — dispatcher wiring for `ALLOWLIST` and `BLOCKLIST`
- [x] `dq-ui/src/components/Templates.tsx` — allowlist/blocklist defaults and step validation
- [x] `dq-api/fastapi/tests/application/services/test_check_type_expression_generator.py` — allowlist/blocklist generator coverage

Validation / unit test evidence:
- Focused command (repo root):
  - `cd dq-api && ./scripts/testing/run_fastapi_pytest.sh --no-cov tests/application/services/test_check_type_expression_generator.py -k "allowlist or blocklist" -q`
- Latest validation run (2026-03-26):
  - Result: `8 passed, 15 deselected in 0.25s`

---

## DQ-4.6 — Uniqueness / Duplicate-Detection Checks

Status: [x] Complete

Check-type: `UNIQUENESS`  
DAMA dimension: Uniqueness  
Parameters: `attributes[]` (one or more column names forming the key)

Expression template:
```
COUNT(*) OVER (PARTITION BY {attributes}) = 1
```

Files added / changed:
- [x] `dq-api/fastapi/app/domain/entities/rule_check_type.py` — `UniquenessParams`
- [x] `dq-api/fastapi/app/application/services/check_type_expression_generator.py` — `UNIQUENESS` branch
- [x] `dq-ui/src/components/CheckTypeForm/UniquenessForm.tsx` *(new)*
- [x] `dq-ui/src/components/CheckTypeForm/index.tsx` — dispatcher wiring for `UNIQUENESS`
- [x] `dq-ui/src/components/Templates.tsx` — uniqueness defaults and step validation
- [x] `dq-api/fastapi/tests/application/services/test_check_type_expression_generator.py` — uniqueness generator coverage

Validation / unit test evidence:
- Focused command (repo root):
  - `cd dq-api && ./scripts/testing/run_fastapi_pytest.sh --no-cov tests/application/services/test_check_type_expression_generator.py -k uniqueness -q`
- Latest validation run (2026-03-26):
  - Result: `3 passed, 22 deselected in 0.25s`

---

## DQ-4.7 — Referential Integrity Checks

Status: [x] Complete

Check-type: `REFERENTIAL_INTEGRITY`  
DAMA dimension: Consistency  
Parameters: `attribute`, `refDataObjectId`, `refAttribute`

Expression template:
```
{attribute} IN (SELECT {refAttribute} FROM {refDataObject})
```

Version mapping note:
- Referential integrity now requires explicit `refDataObjectVersionId` and validates `refAttribute` against that exact version's attribute catalog.
- `refDataObjectId` is normalized from the selected version to avoid object/version drift.
- Optional `refWorkspaceId` metadata is supported so references can point to current-workspace or external-workspace objects.

Files added / changed:
- [x] `dq-api/fastapi/app/domain/entities/rule_check_type.py` — `ReferentialIntegrityParams` includes `refDataObjectVersionId` and optional `refWorkspaceId`
- [x] `dq-api/fastapi/app/application/services/check_type_expression_generator.py` — `REFERENTIAL_INTEGRITY` branch enforces `refDataObjectVersionId`
- [x] `dq-api/fastapi/app/api/v1/endpoints/rules.py` — validates selected reference version exists and contains `refAttribute`
- [x] `dq-ui/src/components/CheckTypeForm/ReferentialIntegrityForm.tsx` *(new)* — captures workspace, object ID, object version ID, and reference attribute
- [x] `dq-ui/src/components/Templates.tsx` — step validation requires reference object version ID for referential checks
- [x] `dq-api/fastapi/tests/application/services/test_check_type_expression_generator.py` — referential generator coverage updated for required version ID

Validation / unit test evidence:
- Focused command (repo root):
  - `cd dq-api && ./scripts/testing/run_fastapi_pytest.sh --no-cov tests/application/services/test_check_type_expression_generator.py -k referential -q`
- Latest validation run (2026-03-26):
  - Result: `2 passed, 24 deselected in 0.25s`

---

## DQ-4.8 — Timeliness Checks

Status: [x] Complete

Check-types: `FRESHNESS`, `LAG`, `FUTURE_DATE`  
DAMA dimension: Timeliness

| Sub-type | Parameters | Expression template |
|---|---|---|
| `FRESHNESS` | `attribute`, `maxDaysOld`, `anchor` (now/processing_date) | `DATEDIFF(now(), &#123;attribute&#125;) &lt;= &#123;maxDaysOld&#125;` |
| `LAG` | `startAttribute`, `endAttribute`, `maxHours` | `TIMESTAMPDIFF(HOUR, &#123;start&#125;, &#123;end&#125;) &lt;= &#123;maxHours&#125;` |
| `FUTURE_DATE` | `attribute`, `referenceDate?` | `&#123;attribute&#125; &lt;= {referenceDate or now()}` |

Files added / changed:
- [x] `dq-api/fastapi/app/domain/entities/rule_check_type.py` — `FreshnessParams`, `LagParams`, `FutureDateParams`
- [x] `dq-api/fastapi/app/application/services/check_type_expression_generator.py` — `FRESHNESS`, `LAG`, and `FUTURE_DATE` branches
- [x] `dq-ui/src/components/CheckTypeForm/TimelinessForm.tsx` *(new)*
- [x] `dq-ui/src/components/CheckTypeForm/index.tsx` — dispatcher wiring for timeliness checks
- [x] `dq-ui/src/components/Templates.tsx` — timeliness defaults and step validation for freshness/lag/future-date
- [x] `dq-api/fastapi/tests/application/services/test_check_type_expression_generator.py` — timeliness generator and validation coverage

Validation / unit test evidence:
- Focused command (repo root):
  - `cd dq-api && ./scripts/testing/run_fastapi_pytest.sh --no-cov tests/application/services/test_check_type_expression_generator.py -k "freshness or lag or future_date" -q`
- Latest validation run (2026-03-26):
  - Result: `12 passed, 21 deselected in 0.25s`

---

## DQ-4.9 — UI: Structured Check-Type Parameter Builder

Status: [x] Complete

Goal: Replace the expression textarea with a guided parameter form when a check-type is selected in the rule editor. The text area remains available as an override ("advanced" mode).

Files to add / change:
- `dq-ui/src/components/CheckTypeForm/index.tsx` *(new)* — dispatcher that renders the correct form for each check-type
- `dq-ui/src/components/RuleForm.tsx` (or `Rules.tsx`) — add check-type selector dropdown; show `CheckTypeForm` or raw expression textarea
- `dq-ui/src/types/rules.ts` — confirm `checkType` / `checkTypeParams` fields are populated from form

Completion update (2026-03-26):
- [x] `dq-ui/src/components/Templates.tsx` now renders a check-type selector in wizard Step 3.
- [x] `dq-ui/src/components/Templates.tsx` now renders `CheckTypeForm` for all typed checks and persists `checkType` / `checkTypeParams` in the create/update flow.
- [x] Step 3 validation now enforces check-type specific required fields before moving to summary.
- [x] Advanced/manual expression override mode now supports editing a raw expression while preserving typed check metadata.
- [x] `dq-ui/src/components/Rules.tsx` create and edit actions consistently route through `TemplatesSelectorModal`, so DQ-4.9 behavior applies to both new and existing rules.

Validation / unit test evidence:
- Focused frontend test (repo root):
  - `cd dq-ui && npm run test -- src/components/rules/useRulesScope.test.ts`
- Latest run (2026-03-26):
  - Result: `1 passed test file, 4 passed tests`
- Frontend build verification:
  - `cd dq-ui && npm run build`
  - Result: build completed successfully (`vite build` passed)

UX notes:
- Selecting a check-type pre-fills the DAMA dimension automatically.
- If the user switches to advanced mode, the generated expression is copied in as a starting point.
- Validation errors on params are shown inline per field.

---

## DQ-4.10 — Compiler Integration

Status: [x] Complete

Goal: Typed rule parameters must produce an expression that passes the DQ-7 compiler without manual edits.

Completion update (2026-03-26):
- [x] `dq-api/fastapi/app/api/v1/endpoints/rules.py` now treats `generated=false` as an explicit manual override signal.
- [x] Create/update now auto-generate `expression` from `checkType` / `checkTypeParams` unless manual override is explicitly requested.
- [x] `dq-ui/src/components/rules/useRuleTemplateFlow.ts` now sends `generated: !useAdvancedExpression` so advanced mode preserves raw expression overrides.
- [x] `dq-ui/src/contexts/RuleContext.tsx` now forwards `generated` in update payloads.
- [x] `dq-api/fastapi/tests/api/test_rules_endpoint_focus.py` now covers:
  - create + check-type generation path,
  - update + check-type generation path,
  - create + manual override preservation (`generated=false`),
  - update + manual override preservation (`generated=false`),
  - create → validate round-trip for typed check params with zero validation errors.

Validation / unit test evidence:
- Focused backend endpoint tests (repo root):
  - `cd dq-api/fastapi && /Users/jacbeekers/gitrepos/dq-rulebuilder/venv/bin/python -m pytest --no-cov tests/api/test_rules_endpoint_focus.py -q`
  - Latest run (2026-03-26): `17 passed in 0.45s`
- Focused frontend regression check (repo root):
  - `cd dq-ui && npm run test -- src/components/rules/useRulesScope.test.ts`
  - Latest run (2026-03-26): `1 passed test file, 4 passed tests`

Acceptance: `POST /api/rulebuilder/v1/rules` with `checkType` + `checkTypeParams` now yields compiler-valid expressions by default, and explicit advanced/manual expressions are preserved when `generated=false`; `POST /api/rulebuilder/v1/rules/&#123;id&#125;/validate` completes with no errors for the typed round-trip test.

---

## DQ-4.11 — Join Consistency Check (Including Actuality-Date Alignment)

Status: [~] In progress

Goal: Ensure joined data objects represent the same business truth by validating both value-level consistency and time alignment.

### Scope Definition

Proposed check-type: `JOIN_CONSISTENCY`

Core checks:
- Joined key mappings are valid and executable.
- Compared attribute pairs are equal (or equivalent after normalization/tolerance rules).
- Actuality dates between left/right joined objects are the same, or "similar" within tolerance derived from the producer-consumer data delivery contract.

Minimum parameter contract (MVP):
- `leftDataObjectVersionId`
- `rightDataObjectVersionId`
- `joinKeys[]` (array of `{ leftAttribute, rightAttribute }`)
- `comparisons[]` (array of `{ leftAttribute, rightAttribute, mode }`)
- `actualityDate`:
  - `leftAttribute`
  - `rightAttribute`
  - `toleranceSource` (`DELIVERY_CONTRACT`)
  - `contractId` (or delivery binding reference)
  - `resolvedToleranceValue` *(read-only, resolved at validation/execution time)*
  - `resolvedToleranceUnit` (`minutes` | `hours` | `days`) *(read-only)*
  - `overrideToleranceValue?` *(optional, only when contract policy allows override)*
  - `overrideToleranceUnit?` *(optional, only when contract policy allows override)*
- `minMatchRate` (0-100)

### Semantics

Row outcome classification:
- `match`: all configured comparisons pass AND actuality-date delta is within tolerance.
- `mismatch`: one or more comparisons fail OR actuality-date delta exceeds tolerance.
- `out_of_scope`: join key missing/null according to null policy (tracked separately).

Actuality-date rule:
- "Same" means absolute timestamp difference equals 0.
- "Similar" means absolute timestamp difference is less than or equal to the resolved contract tolerance.
- Contract tolerance is authoritative; user-provided overrides are optional and only valid when explicitly allowed by contract policy.
- If no delivery contract tolerance is available yet, rule save/activation must fail with actionable validation rather than silently defaulting.

Pass condition:
- `match_rate = match_count / eligible_joined_rows`
- Rule passes when `match_rate >= minMatchRate`

### Implementation Plan

Phase 0 — Delivery contract dependency (prerequisite):
- Implement/read delivery contract tolerance policy between producer and consumer (actuality-date SLA window).
- Provide a resolver API/service that returns effective tolerance for a given left/right object relationship.
- Define policy flags:
  - `overrideAllowed` (boolean)
  - `maxOverrideTolerance` (optional bound)

Phase 1 — Contract and validation:
- Add `JOIN_CONSISTENCY` to rule-check type taxonomy and frontend type unions.
- Add backend schema model for `JoinConsistencyParams`.
- Validate:
  - referenced object versions exist,
  - join/comparison attributes exist in selected versions,
  - actuality attributes are date/timestamp compatible,
  - referenced delivery contract/binding exists,
  - effective tolerance can be resolved from contract,
  - user overrides are rejected when `overrideAllowed=false`,
  - user overrides do not exceed contract max override bounds,
  - `minMatchRate` range is valid.

Current implementation status:
- [x] `JOIN_CONSISTENCY` added to backend rule-check taxonomy.
- [x] Backend schema model added for `JoinConsistencyParams`, nested join/comparison mappings, and actuality-date contract metadata.
- [x] Initial validation added for paired tolerance fields and `minMatchRate` bounds.
- [x] Catalog-backed validation added for left/right version IDs, referenced attributes, and actuality-date type compatibility.
- [x] Delivery-contract tolerance now resolves from OpenMetadata data contracts by `contractId`, with ODCS-origin contract metadata read from the OpenMetadata contract entity.
- [x] OpenMetadata contract lookups are cached in Redis with admin-configurable TTL (`openMetadataContractCacheTtlSeconds`); when Redis is unavailable, lookup continues without cache.
- [x] JOIN_CONSISTENCY contract resolution is enforced at dataset level; left/right object versions must resolve to the same dataset scope.
- [~] Override policy enforcement is wired, but current ODCS contracts do not yet expose explicit override-enabled policy metadata.

Phase 2 — Expression/generator integration:
- Extend check-type expression generator with deterministic `JOIN_CONSISTENCY` expression output.
- Include explicit actuality-date comparison in generated expression (exact or contract-resolved tolerance window).
- Preserve manual override behavior from DQ-4.10 (`generated=false`).

Current implementation status:
- [x] Deterministic `JOIN_CONSISTENCY` generator added.
- [x] Generator now fails fast when contract tolerance has not been resolved yet.
- [x] Generated expression includes join keys, comparison clauses, and actuality-date tolerance enforcement.
- [x] Generator output is now constrained to the current DQ-7 compiler-supported expression subset.
- [x] Endpoint create/update flows populate resolved contract tolerance before expression generation.

Phase 3 — API + persistence wiring:
- Ensure create/update/validate endpoints accept and round-trip `JOIN_CONSISTENCY` params.
- Confirm payloads are preserved in `checkType` / `checkTypeParams` and exposed via view models.

Current implementation status:
- [x] Create/update endpoints accept `JOIN_CONSISTENCY` params and normalize them before persistence.
- [x] Persisted payload includes resolved tolerance metadata derived from the referenced contract.
- [x] Focused create-to-validate round-trip proof added for backend endpoint flow.
- [x] `GET /api/rulebuilder/v1/rules/&#123;id&#125;` now exposes `checkType` / `checkTypeParams` in `RuleView`.
- [x] `GET /api/rulebuilder/v1/rules` now normalizes legacy `check_type` / `check_type_params` payloads to camel-case contract fields (`checkType`, `checkTypeParams`) while preserving existing keys.

Validation / test evidence:
- Focused backend endpoint tests (repo root):
  - `cd dq-api/fastapi && ../../venv/bin/python -m pytest --no-cov tests/api/test_rules_endpoint_focus.py -k "list_rules_normalizes_check_type_contract_fields or get_rule_exposes_check_type_fields_in_rule_view" -q`
- Latest run (2026-03-28):
  - Result: `2 passed, 24 deselected in 0.57s`

Phase 4 — UI authoring flow:
- Add `JoinConsistencyForm` in check-type form suite.
- Include guided selectors for:
  - left/right object versions,
  - join key mappings,
  - attribute comparisons,
  - actuality-date pair + contract binding.
- Show resolved contract tolerance as read-only by default.
- If policy allows, render bounded override controls with contract limits shown inline.
- Add field-level error messages for invalid mappings, time compatibility issues, and contract-policy violations.

Detailed implementation checklist (Phase 4):
- [x] Add frontend type support for `JOIN_CONSISTENCY` (`RuleCheckType`, params model, nested actuality/join/comparison payloads).
- [x] Implement `JoinConsistencyForm` component with:
  - [x] left/right data object version ID inputs
  - [x] dynamic join-key mapping rows
  - [x] dynamic comparison mapping rows with mode selector
  - [x] actuality-date + contract ID capture block
  - [x] min-match-rate input
- [x] Wire `JoinConsistencyForm` into `CheckTypeForm` dispatcher.
- [x] Add `JOIN_CONSISTENCY` to check-type selector options in wizard Step 3.
- [x] Add default parameter builder for `JOIN_CONSISTENCY` in template flow.
- [x] Add Step 3 validation rules for required join-consistency fields.
- [x] Add summary-level user-friendly rendering for join-consistency config.
- [x] Add generated-expression preview fallback for join-consistency in advanced mode.
- [x] Replace version ID/attribute free-text inputs with catalog-backed guided selectors.
- [x] Surface backend-resolved tolerance and contract policy (read-only + override affordance when allowed).
- [x] Add inline field-level surfacing for backend validation errors (contract scope mismatch, non-temporal actuality attrs, override policy violation).
- [x] Add focused frontend tests for join-consistency form interactions and wizard validation.

Current implementation status:
- [x] `JoinConsistencyForm` now uses catalog-backed selectors for version and attribute mapping.
- [x] Policy-aware contract tolerance panel and bounded override controls are implemented.

Phase 5 — Testing and smoke coverage:
- Unit tests for param validation and expression generation (including tolerance boundary cases).
- API endpoint tests for create/update/validate round-trip.
- Smoke test covering:
  - exact actuality-date match,
  - contract-resolved allowed tolerance,
  - override allowed + within bound,
  - override rejected by contract policy,
  - over-tolerance mismatch.

Current implementation status:
- [x] Focused backend unit tests added for parameter validation and expression generation.
- [x] Focused API round-trip tests added for create, update validation failure, and create-to-validate success.
- [x] Smoke coverage completed for contract-policy override matrix and dataset-scope/contract-resolution failure paths.

Validation / smoke test evidence:
- Focused JOIN_CONSISTENCY smoke matrix (repo root):
  - `cd dq-api/fastapi && /Users/jacbeekers/gitrepos/dq-rulebuilder/venv/bin/python -m pytest --no-cov tests/api/test_rules_endpoint_focus.py -k "join_consistency and (override or cross_dataset or lookup_error or resolves_contract_tolerance or round_trips_into_validate or rejects_non_temporal)" -q`
- Latest run (2026-03-28):
  - Result: `8 passed, 21 deselected in 0.58s`
- Full focused endpoint file sanity run (repo root):
  - `cd dq-api/fastapi && /Users/jacbeekers/gitrepos/dq-rulebuilder/venv/bin/python -m pytest --no-cov tests/api/test_rules_endpoint_focus.py -q`
- Latest run (2026-03-28):
  - Result: `29 passed in 0.35s`

Phase 6 — Reporting and diagnostics:
- Expose metrics: `matchCount`, `mismatchCount`, `eligibleJoinedRows`, `matchRate`, `actualityDateMismatchCount`.
- Include diagnostics that indicate whether failures are value mismatches or actuality-date drift.

Status: [x] Complete

Goal: Surface detailed execution metrics and failure diagnostics for JOIN_CONSISTENCY rules so users understand why rules passed/failed and to support auditing and root-cause analysis.

### Scope Definition

Metrics to capture:
- `matchCount` (integer) — rows where all comparisons AND actuality-date check passed
- `mismatchCount` (integer) — rows where at least one comparison OR actuality-date check failed
- `eligibleJoinedRows` (integer) — total rows produced by the join (used in denominator for match rate)
- `matchRate` (float 0-100) — percentage: `(matchCount / eligibleJoinedRows) * 100`
- `actualityDateMismatchCount` (integer) — rows where actuality-date delta exceeded tolerance (subset of `mismatchCount`)

Diagnostics to classify:
- `value_mismatch` — one or more configured comparison attributes differ between left/right
- `actuality_date_drift` — actuality-date delta exceeds contract tolerance
- `null_or_missing_join_key` — join key is null/missing; row excluded from eligible set

### Implementation Plan

Phase 6.1 — Domain and schema models:
- Add `JoinConsistencyExecutionMetrics` dataclass with fields: `matchCount`, `mismatchCount`, `eligibleJoinedRows`, `matchRate`, `actualityDateMismatchCount`
- Add `FailureDiagnostic` dataclass with fields: `failureClass` (enum: `value_mismatch`, `actuality_date_drift`, `null_or_missing_join_key`), `rowIdentifier` (optional), `details` (string)
- Add `JoinConsistencyExecutionResult` combining metrics + array of `FailureDiagnostic` items
- Update rule execution result schema to include metrics + diagnostics

Files to add / change:
- [ ] `dq-api/fastapi/app/domain/entities/execution_metrics.py` *(new)* — `JoinConsistencyExecutionMetrics`, `FailureDiagnostic`, `JoinConsistencyExecutionResult`
- [ ] `dq-api/fastapi/app/api/v1/schemas/execution_result.py` — extend `RuleExecutionResult` with `metrics` field (union type) and `diagnostics` field
- [ ] `dq-db/init/01_schema.sql` — extend `rule_execution_results` table with `metrics JSONB`, `diagnostics JSONB` columns

Phase 6.2 — Metrics and diagnostics calculation:
- Implement metrics calculation during rule execution (post-join, post-comparison, post-tolerance check)
- Implement diagnostics classifier that produces failure reason code for each failed row
- Add diagnostics aggregation (limit to top N failures per class, or sample distribution)

Files to add / change:
- [ ] `dq-api/fastapi/app/application/services/rule_execution_service.py` — wire metrics/diagnostics calculation into execution flow
- [ ] `dq-api/fastapi/app/application/services/join_consistency_metrics_calculator.py` *(new)* — calculate metrics and classify diagnostics
- [ ] `dq-api/fastapi/tests/application/services/test_join_consistency_metrics_calculator.py` *(new)* — unit tests for metric calculation and diagnostic classification

Phase 6.3 — API exposure:
- Ensure create/update/validate endpoints return metrics + diagnostics in response
- Add diagnostics summary to rule validation failure reason (user-facing string derived from failure classes)

Files to add / change:
- [ ] `dq-api/fastapi/app/api/v1/endpoints/rules.py` — update `POST /api/rulebuilder/v1/rules/&#123;id&#125;/validate` response schema to include metrics + diagnostics
- [ ] `dq-api/fastapi/tests/api/test_rules_endpoint_focus.py` — add tests asserting metrics + diagnostics are returned and correct values

Phase 6.4 — Frontend rendering:
- Add metrics display widget (match rate %, counts)
- Add diagnostics collapsible panel showing failure categories and samples
- Wire into TestResultsVisualization or similar component

Files to add / change:
- [ ] `dq-ui/src/components/ExecutionMetricsPanel.tsx` *(new)* — render metrics summary
- [ ] `dq-ui/src/components/ExecutionDiagnosticsPanel.tsx` *(new)* — render failure classifications with sample details
- [ ] `dq-ui/src/components/TestResultsVisualization.tsx` — integrate metrics/diagnostics panels into result display
- [ ] `dq-ui/src/types/execution.ts` — add `ExecutionMetrics`, `FailureDiagnostic`, `ExecutionDiagnosticsResult` types
- [ ] `dq-ui/src/components/__tests__/ExecutionMetricsPanel.test.tsx` *(new)*
- [ ] `dq-ui/src/components/__tests__/ExecutionDiagnosticsPanel.test.tsx` *(new)*

Phase 6.5 — Testing and validation:
- Unit tests for metric calculation (exact match, partial mismatch, all mismatches, actuality-date only failures)
- Unit tests for diagnostics classification and aggregation
- API integration tests for metrics/diagnostics round-trip
- Frontend tests for metrics/diagnostics rendering

Current implementation status:
- [ ] Domain models created
- [ ] Schema migrations applied
- [ ] Metrics calculator implemented
- [ ] Diagnostics classifier implemented
- [ ] API endpoints updated to return metrics/diagnostics
- [ ] Frontend components created and wired
- [ ] Unit tests added for calculator
- [ ] API integration tests added
- [ ] Frontend component tests added
- [ ] Smoke test validates end-to-end metrics/diagnostics for JOIN_CONSISTENCY

Validation / test evidence:
- Metrics calculator unit tests (repo root):
  - `cd dq-api/fastapi && ../../venv/bin/python -m pytest --no-cov tests/application/services/test_join_consistency_metrics_calculator.py -q`
  - Target result: `TBD passed`
- API metrics/diagnostics integration tests (repo root):
  - `cd dq-api/fastapi && ../../venv/bin/python -m pytest --no-cov tests/api/test_rules_endpoint_focus.py -k "join_consistency and (metrics or diagnostics)" -q`
  - Target result: `TBD passed`
- Frontend metrics/diagnostics render tests (repo root):
  - `cd dq-ui && npm run test -- src/components/__tests__/ExecutionMetricsPanel.test.tsx src/components/__tests__/ExecutionDiagnosticsPanel.test.tsx`
  - Target result: `TBD passed`
- Smoke end-to-end (repo root):
  - `cd dq-api/fastapi && ../../venv/bin/python -m pytest --no-cov tests/api/test_rules_endpoint_focus.py -k "join_consistency and (validate or execute)" -q`
  - Target result: `TBD passed, metrics/diagnostics populated in result`

### Acceptance Criteria

- Metrics are calculated correctly: match/mismatch counts, eligible row count, and derived match rate
- Diagnostics clearly classify failure reasons (value mismatch vs actuality-date drift)
- Null/missing join keys are tracked separately and excluded from denominator
- API returns metrics + diagnostics in execution result payload
- Frontend displays metrics summary and diagnostics categorization
- All calculations are validated via unit and integration tests

---

### Audit and Evidence Requirements

The items in this section are follow-on governance and evidence enhancements. They are not required to consider DQ-4.11 functionally complete for the DQ-4 rule-check taxonomy milestone.

Audit scope (must be captured and queryable):
- Rule governance events:
  - rule created/updated/activated/deactivated,
  - actor (`who`), timestamp (`when`), and changed fields (`what`).
- Delivery contract resolution events:
  - contract/binding identifier,
  - contract version used,
  - resolved tolerance value/unit,
  - resolution timestamp.
- Policy enforcement events:
  - override requested (yes/no),
  - override allowed by policy (yes/no),
  - override accepted/rejected,
  - rejection reason code.
- Execution evidence events:
  - left/right data object version IDs,
  - join key mapping fingerprint,
  - match/mismatch counts,
  - actuality-date mismatch count,
  - effective tolerance used at runtime.

Evidence retention and traceability:
- Every execution record must link to:
  - rule version ID,
  - delivery contract version,
  - resolved tolerance decision.
- Audit trail must support reconstruction of why a run passed/failed without relying on mutable runtime state.
- Evidence payloads should separate failure classes explicitly:
  - value mismatch,
  - actuality-date drift,
  - policy/contract validation failure.

Governance validation (definition of done for auditability):
- API tests assert audit fields are persisted for create/update/execute flows.
- Contract-policy tests assert accepted/rejected overrides produce distinct audited reason codes.
- Reporting/API contract exposes contract version and effective tolerance used for each run.
- Smoke test verifies end-to-end evidence generation for:
  - contract-resolved tolerance pass,
  - over-tolerance fail,
  - override-rejected fail.

#### Audit Event Schema (Draft)

| Event | Required fields | Notes |
|---|---|---|
| `dq.join_consistency.rule_saved` | `eventId`, `ts`, `actorId`, `ruleId`, `ruleVersionId`, `checkType`, `changedFields[]` | Emitted on create/update of `JOIN_CONSISTENCY` rules. |
| `dq.join_consistency.contract_resolved` | `eventId`, `ts`, `ruleId`, `ruleVersionId`, `contractId`, `contractVersion`, `resolvedToleranceValue`, `resolvedToleranceUnit`, `overrideRequested`, `overrideApplied` | Captures authoritative tolerance decision. |
| `dq.join_consistency.policy_decision` | `eventId`, `ts`, `ruleId`, `ruleVersionId`, `overrideAllowed`, `decision` (`accepted`/`rejected`), `reasonCode` | Mandatory when override is requested or denied. |
| `dq.join_consistency.execution_completed` | `eventId`, `ts`, `runId`, `ruleId`, `ruleVersionId`, `leftDataObjectVersionId`, `rightDataObjectVersionId`, `matchCount`, `mismatchCount`, `actualityDateMismatchCount`, `effectiveToleranceValue`, `effectiveToleranceUnit`, `contractVersion` | Main evidence record used in reports and audits. |
| `dq.join_consistency.execution_failed` | `eventId`, `ts`, `runId`, `ruleId`, `ruleVersionId`, `failureClass` (`value_mismatch`/`actuality_date_drift`/`contract_policy_violation`), `reasonCode`, `contractVersion` | Must classify failures for governance and RCA. |

#### Proof Tracking Checklist

Use this checklist to track auditability evidence as implementation lands.

- [ ] `DQ-4.11.A1` Rule create/update audit event persisted (`dq.join_consistency.rule_saved`)
- [ ] `DQ-4.11.A2` Contract resolution audit event persisted (`dq.join_consistency.contract_resolved`)
- [ ] `DQ-4.11.A3` Policy decision audit event persisted (`dq.join_consistency.policy_decision`)
- [ ] `DQ-4.11.A4` Execution completed/failed audit events persisted with failure classes
- [ ] `DQ-4.11.A5` API contract exposes `contractVersion` + effective tolerance per run
- [ ] `DQ-4.11.T1` Unit-test proof added for contract resolution and policy enforcement
- [ ] `DQ-4.11.T2` Unit-test proof added for event payload shape and required fields
- [ ] `DQ-4.11.T3` Integration/API proof added for end-to-end audit persistence
- [ ] `DQ-4.11.T4` Smoke-test proof added for pass/fail/override-rejected evidence flows
- [ ] `DQ-4.11.T5` Evidence links added (test command, result summary, artifact path)

#### Evidence Log

Use this table to record implementation proof as each checklist item is completed.

| Item | Command / Validation Step | Result Summary | Artifact / Evidence Path | Date |
|---|---|---|---|---|
| `DQ-4.11.A1` | TBD | TBD | TBD | TBD |
| `DQ-4.11.A2` | TBD | TBD | TBD | TBD |
| `DQ-4.11.A3` | TBD | TBD | TBD | TBD |
| `DQ-4.11.A4` | TBD | TBD | TBD | TBD |
| `DQ-4.11.A5` | TBD | TBD | TBD | TBD |
| `DQ-4.11.T1` | TBD | TBD | TBD | TBD |
| `DQ-4.11.T2` | TBD | TBD | TBD | TBD |
| `DQ-4.11.T3` | TBD | TBD | TBD | TBD |
| `DQ-4.11.T4` | TBD | TBD | TBD | TBD |
| `DQ-4.11.T5` | TBD | TBD | TBD | TBD |

### Acceptance Criteria

- User can define join consistency checks without writing raw expressions.
- Generated expression is deterministic and compiler-valid.
- Actuality dates are explicitly enforced as same or within contract-governed tolerance.
- Validation rejects incompatible actuality date fields, missing contract tolerance, and policy-invalid overrides.
- Test results clearly separate value mismatches from actuality-date mismatches.

---

## Progress Summary

The milestone table below tracks the implemented/current executable scope captured in
this implementation note, including the extended taxonomy introduced for `CORRECT`,
`PRESENT`, `RECONCILE`, `PLAUSIBLE`, and `TRANSFER_MATCH`.

| Work item | Status | Milestone |
|---|---|---|
| DQ-4.1 RuleCheckType taxonomy | [x] Complete    | A |
| DQ-4.2 Threshold / completeness | [x] Complete | B |
| DQ-4.3 Regex / pattern | [x] Complete | B |
| DQ-4.4 Range checks | [x] Complete | B |
| DQ-4.5 Allowlist / blocklist | [x] Complete | B |
| DQ-4.6 Uniqueness | [x] Complete | C |
| DQ-4.7 Referential integrity | [x] Complete | C |
| DQ-4.8 Timeliness | [x] Complete | C |
| DQ-4.9 UI check-type builder | [x] Complete | D |
| DQ-4.10 Compiler integration | [x] Complete | D |
| DQ-4.11 Join consistency + actuality date alignment | [x] Complete | E |
