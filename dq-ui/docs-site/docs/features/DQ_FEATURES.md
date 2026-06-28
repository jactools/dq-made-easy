# Data Quality Features

- [x] #DQ-1 Enhanced rule validation logic
- [x] #DQ-2 Define join conditions on data objects
- [x] #DQ-3 Define a re-usable filter
- [x] #DQ-3b Define a re-usable join
- [x] #DQ-3c Data Assets
- Planning doc: [DATA_ASSETS_FEATURES.md](/docs/features/DATA_ASSETS_FEATURES/)
- Implementation details: [DQ_3C_DATA_ASSETS_IMPLEMENTATION_DETAILS.md](/docs/implementation-details/DQ_3C_DATA_ASSETS_IMPLEMENTATION_DETAILS/)
- [x] #DQ-4 New rule types or checks
- [x] #DQ-5 Advanced data profiling capabilities
- [x] #DQ-6 Batch rule execution improvements
- [x] #DQ-7 Implement DSL / Integration with Great Expectations
- [x] #DQ-8 Rule test execution with attribute selection and plain-language results
- [x] #DQ-9 Create a CLI that enables listing, running, and exporting DQ run plans
- [x] #DQ-10 Natural-language rule drafting preview for data stewards
- [x] #DQ-11 Continuous data observability and health scorecards
- [x] #DQ-12 Scheduled monitors, anomaly detection, drift detection, and root-cause analysis
- [x] #DQ-13 Incident remediation workflows, ownership, and ticket integration _(partial: incidents API + Zammad + ownership routing done; remediation tracking and history are captured in-app while the lifecycle remains in Zammad)_
- [x] #DQ-14 Data contracts, schema-change governance, and conformance checks
- [x] #DQ-15 Collaboration and reusable policy management
- [x] #DQ-15.1 Surface suggestion, profiling, contract-review, and run-plan replay interactions in the homepage activity feed, scoped to the current workspace
- [x] #DQ-16 AI-assisted authoring and recommendations for quality standards
- [x] #DQ-17 First-class reconciliation and cross-system comparison workflows
- [x] #DQ-18 Lineage and business context across Data Assets and rules

## DQ-1 Enhanced Rule Validation Logic (Completion Scope)

User-facing position:
- Standard feature
- Current rollout navigation: `Rule Quality -> Rule Validation`
- Product role: workspace-level quality control for rules, separate from the core Rules authoring and inventory workspace
- Forward-compatible feature map: `Rules` = authoring and inventory, `Rule Quality` = validation and suggestions, `Governance` = approvals/lifecycle/exceptions, `Operations` = execution/schedules/result aggregation/monitoring
- Current UI note: `Governance` and `Operations` are now first-class navigation sections, so rule-related capabilities no longer sit behind the older interim `Approvals` and `Reports` labels
- Standard-feature rollout plan: [DQ_1_RULE_VALIDATION_STANDARD_FEATURE_IMPLEMENTATION_PLAN.md](/docs/implementation-details/DQ_1_RULE_VALIDATION_STANDARD_FEATURE_IMPLEMENTATION_PLAN/)
- Key rollout references: `DQ1-I-P2-01`, `DQ1-I-P3-01`, `DQ1-I-P4-04`, `DQ1-I-P6-01`, `DQ1-I-AC-01`

Primary user journeys:
- `Rules`: create, edit, version, search, and activate rules without turning the inventory screen into a multi-tool workspace
- `Rule Quality`: validate rules, review suggestions, and run pre-execution quality checks before governance or runtime steps
- `Governance`: review approvals, manage lifecycle states, and handle exceptions or policy-driven rule controls
- `Operations`: review execution activity, schedules, aggregated outcomes, and runtime monitoring signals

Tracked Work Items
- [x] `DQ-1.1` Configurable validation policies (severity, enabled/disabled, scope)
- [x] `DQ-1.2` Batch validation API + aggregate summary reporting
- [x] `DQ-1.3` Cross-rule conflict/inconsistency detection
- [x] `DQ-1.4` Validation run history + exportable reports
- [x] `DQ-1.5` Real-time validation feedback during rule authoring

Acceptance Criteria
- [x] `DQ-1.AC-01` Validation checks are configurable without code changes.
- [x] `DQ-1.AC-02` Users can validate multiple rules in one operation and get aggregated diagnostics.
- [x] `DQ-1.AC-03` Contradictory/duplicate/overlapping rules are flagged with actionable messages.
- [x] `DQ-1.AC-04` Validation outcomes can be reviewed historically and exported.
- [x] `DQ-1.AC-05` Rule editor provides immediate validation feedback before explicit submission.

## DQ-4 New Rule Types / Checks

Goal: Introduce a set of first-class, parameterised rule check-types so rules can be defined through structured parameters rather than requiring a hand-authored expression. Each check-type maps to a well-known data quality concern and auto-generates a compiler-ready expression for the DQ-7 pipeline.

### Motivation

The current rule model accepts a single free-form `expression` string. This is powerful but places the full authoring burden on the user and makes machine-readable rule intent opaque. Typed rule checks solve three problems:

- **Accessibility**: non-technical users can define checks through guided parameter forms.
- **Consistency**: identical intent is always expressed the same way, preventing subtle expression divergence.
- **Discoverability**: check coverage across DAMA dimensions can be reported and audited programmatically.

### Rule Check Type Taxonomy

#### Implemented / Current Executable Check Types

| Done | Id | Check type | DAMA dimension | Example |
|--|---|--|---|--|
| [x] | #RCH-01 | `THRESHOLD` | Completeness | No more than 2% of `customer_email` values are NULL, empty, or a known placeholder value |
| [x] | #RCH-02 | `REGEX` | Accuracy | `customer_email` matches the expected email format |
| [x] | #RCH-03 | `RANGE` | Validity | `interest_rate` must be between 0 and 100 inclusive |
| [x] | #RCH-04 | `ALLOWLIST` | Validity | `order_status` must be one of `PENDING`, `SHIPPED`, `DELIVERED`, or `CANCELLED` |
| [x] | #RCH-05 | `BLOCKLIST` | Validity | `country_code` must not use blocked placeholder values such as `ZZ` or `UNKNOWN` |
| [x] | #RCH-06 | `UNIQUENESS` | Uniqueness | The combination of `customer_id` and `account_id` must be unique within the data object |
| [x] | #RCH-07 | `REFERENTIAL_INTEGRITY` | Consistency | Every `order.customer_id` must exist in the referenced `customers.id` attribute |
| [x] | #RCH-08 | `FRESHNESS` | Timeliness | `last_update_at` must be no more than 1 day old |
| [x] | #RCH-09 | `LAG` | Timeliness | The elapsed time between `trade_time` and `settlement_time` must not exceed 24 hours |
| [x] | #RCH-10 | `FUTURE_DATE` | Timeliness | `transaction_date` cannot be later than the current date |
| [x] | #RCH-11 | `JOIN_CONSISTENCY` | Consistency | Customer risk grade and actuality date must align across joined producer and consumer data objects within contract tolerance |

#### Extended Check Types

| Done | Id | Check type | DAMA dimension | Example |
|--|---|--|---|--|
| [x] | #RCH-12 | `CORRECT` | Accuracy | The closing price of a stock matches the exchange's authoritative market feed |
| [x] | #RCH-13 | `PRESENT` | Completeness | `customer_name` must be populated and cannot be NULL, blank, or a configured default placeholder |
| [x] | #RCH-14 | `RECONCILE` | Consistency | The aggregate cash movement matches the ATM customer transaction amount |
| [x] | #RCH-15 | `PLAUSIBLE` | Validity | `customer_age` must fall within the allowed range for the customer's product type or segment |
| [x] | #RCH-16 | `TRANSFER_MATCH` | Consistency | A transferred file or replicated target dataset must match the source rows or expected payload hash |

Scope notes for these types:
- `CORRECT` is reserved for comparison against an authoritative external or reference source, not for internal referential checks.
- `PRESENT` is implemented as a steward-facing completeness type with optional placeholder-value blocking in addition to NULL and blank checks.
- `RECONCILE` is intended for lightweight cross-system reconciliation without the contract-governed actuality-date semantics of `JOIN_CONSISTENCY`.
- `PLAUSIBLE` is limited in initial scope to contextual validity modes such as `contextual_range` and `conditional_allowlist`; it is not a catch-all for arbitrary business logic.
- `TRANSFER_MATCH` is limited in initial scope to `row_value_match` and `payload_hash_match` semantics.
- Audit logging, lineage completeness, and change-history controls are explicitly out of scope for DQ-4 and belong to governance/audit features rather than rule-check taxonomy.


### Architecture

```
User fills check-type form
        │
        ▼
RuleCheckTypeParams  ──► expression auto-generated ──► DQ-7 compiler
        │
        ▼
stored in rule.checkType / rule.checkTypeParams (new fields)
expression field retained as cache / override
```

- `checkType` and `checkTypeParams` are stored alongside the existing `expression` field.
- When `checkType` is set, the expression is auto-derived at save time; manual override is still allowed.
- If the expression has been manually overridden, `checkType` stays informational only.

### Tracked Work Items

- [x] `DQ-4.1` Define `RuleCheckType` taxonomy: domain entities, backend schema, frontend types, and DB columns ([implementation progress](/docs/implementation-details/DQ_4_NEW_RULE_TYPES_PROGRESS/))
- [x] `DQ-4.2` Threshold / completeness checks (null%, empty%, default-value%)
- [x] `DQ-4.3` Pattern / regex checks (format validation)
- [x] `DQ-4.4` Range checks (numeric min/max)
- [x] `DQ-4.5` Allowlist and blocklist checks
- [x] `DQ-4.6` Uniqueness / duplicate-detection checks
- [x] `DQ-4.7` Referential integrity checks (cross-dataset FK validation)
- [x] `DQ-4.8` Timeliness checks (freshness, lag, future-date)
- [x] `DQ-4.9` UI: structured check-type parameter builder (replaces expression textarea for typed rules)
- [x] `DQ-4.10` Compiler integration: typed parameters auto-generate DQ-7 compiler expressions
- [x] `DQ-4.11` Join consistency check: ensure joined data objects carry equivalent business values and the actuality date is identical or within tolerance governed by the producer-consumer data delivery contract


### Acceptance Criteria

- [x] `DQ-4.AC-01` All implemented current executable check types can be defined without writing a manual expression.
- [x] `DQ-4.AC-02` Each implemented current executable check type generates a deterministic, compiler-valid expression.
- [x] `DQ-4.AC-03` Existing free-form expression rules continue to work unchanged.
- [x] `DQ-4.AC-04` Rule check-type coverage is visible per DAMA dimension in the Operations view.
- [x] `DQ-4.AC-05` Validation errors on check-type parameters produce field-level UI messages.

### Delivery Milestones

- [x] `DQ-4.MS-01` Milestone A (Foundation): `DQ-4.1` — type taxonomy agreed, schema extended
- [x] `DQ-4.MS-02` Milestone B (Core Types): `DQ-4.2` through `DQ-4.5` — completeness, accuracy, validity checks
- [x] `DQ-4.MS-03` Milestone C (Advanced Types): `DQ-4.6` through `DQ-4.8` — uniqueness, referential integrity, timeliness
- [x] `DQ-4.MS-04` Milestone D (UI + Compiler): `DQ-4.9` through `DQ-4.10` — full end-to-end round-trip
- [x] `DQ-4.MS-05` Milestone E (Cross-Object Consistency): `DQ-4.11` — join consistency with actuality-date alignment

---

## DQ-5 Advanced Data Profiling Capabilities

Goal: mature profiling and AI-powered suggestions so the feature uses the same internal app API boundaries as the rest of FastAPI rather than endpoint-local PostgreSQL/SQLAlchemy access.

Status note: DQ-5 is complete. Suggestions profiling, suggestion review, and natural-language draft persistence now flow through repository-backed infrastructure and dependency injection instead of endpoint-local ORM/session handling.

Tracked Work Items
- [x] `DQ-5.1` Define repository-backed domain entities and contracts for suggestions, interactions, profiling requests, and source metadata ([detail](/docs/status/current/DQ-5_ADVANCED_DATA_PROFILING/))
- [x] `DQ-5.2` Move the current suggestions persistence logic into concrete repository implementations
- [x] `DQ-5.3` Refactor suggestions endpoints to depend on injected repositories instead of direct ORM/session access
- [x] `DQ-5.4` Preserve the current HTTP contract while hardening fail-fast behavior and test isolation

Acceptance Criteria
- [x] `DQ-5.AC-01` Suggestions endpoints no longer import SQLAlchemy statements, ORM rows, or session helpers directly.
- [x] `DQ-5.AC-02` Profiling cooldown, suggestion transitions, and interaction audit writes are covered by repository-backed tests.
- [x] `DQ-5.AC-03` The suggestions HTTP contract remains stable during the persistence-boundary refactor.
- [x] `DQ-5.AC-04` Missing persistence prerequisites fail fast with explicit non-success responses.

---

## DQ-7 Executable Rule Transformation (DSL or Great Expectations)

Goal: Transform stored rule expressions into executable checks that can run consistently in `dq-engine`, enabling scheduled execution and reliable runtime results.

Decision Track
- [x] `DQ-7.DC-01` Define execution target approach: internal DSL runtime, Great Expectations integration, or hybrid.
- [x] `DQ-7.DC-02` Document supported expression subset and unsupported constructs.
- [x] `DQ-7.DC-03` Define normalization rules so filter/join expressions compile consistently.

Execution Architecture
- [x] `DQ-7.ARC-01` Build a rule compiler stage: `rule expression -> normalized AST/intermediate model -> executable artifact`.
- [x] `DQ-7.ARC-02` Add adapter layer for Great Expectations expectations when GE mode is used.
- [x] `DQ-7.ARC-03` Add deterministic mapping from rule IDs/versions to executable artifacts.
- [x] `DQ-7.ARC-04` Add validation gate that fails activation when rule cannot be compiled.

Runtime and Observability
- [x] `DQ-7.OB-01` Add execution result schema with pass/fail, failure count, and sample failures.
- [x] `DQ-7.OB-02` Add compile/runtime diagnostics for unsupported functions/operators.
- [x] `DQ-7.OB-03` Add traceability fields linking execution output back to rule version and source expression.
- [x] `DQ-7.OB-04` Add test harness for compilation and execution regression cases.

Acceptance Criteria
- [x] `DQ-7.ACC-01` A rule can be compiled into executable checks before scheduling.
- [x] `DQ-7.ACC-02` Compilation failures produce actionable diagnostics in UI/API.
- [x] `DQ-7.ACC-03` Execution output is version-aware and traceable to source rule expression.
- [x] `DQ-7.ACC-04` Both simple predicates and regex-like validations are executable through the chosen runtime.

Tracked Work Items (Proposed)
- [x] `DQ-7.DT-01` DSL vs Great Expectations architecture decision record ([ADR-011](/docs/architecture/adr/ADR-011-executable-rule-transformation-strategy-dsl-first-with-great-expectations-adapter/))
- [x] `DQ-7.DT-02` Expression syntax guidance and supported-grammar coverage ([DQ-1 Rule Validation User Guide](/docs/user-manuals/DQ-1_RULE_VALIDATION_USER_GUIDE/), [DQ-2 Join Conditions User Guide](/docs/user-manuals/DQ-2_JOIN_CONDITIONS_USER_GUIDE/))
- [x] `DQ-7.DT-03` Rule compiler to intermediate executable model ([implementation progress](/docs/implementation-details/DQ_7_3_RULE_COMPILER_IMPLEMENTATION_PROGRESS/))
- [x] `DQ-7.DT-04` Great Expectations adapter (if GE/hybrid path selected) ([implementation details](/docs/implementation-details/DQ_7_4_GX_SUITE_ORCHESTRATION_IMPLEMENTATION_DETAILS/), [ADR-014](/docs/architecture/adr/ADR-014-gx-suite-registry-pyspark-execution-and-exception-store-separation/))
        Registry, retrieval, PySpark execution, persistence separation, observability, and runtime traceability are in place.
- [x] `DQ-7.DT-05` Compile-time diagnostics surfaced in API/UI
- [x] `DQ-7.DT-06` Execution result contract and traceability fields
- [x] `DQ-7.DT-07` Regression suite for compile and runtime behavior

Status note: DQ-7 is complete. The compiler, validation gate, GX adapter/runtime integration, and traceable execution flow are implemented and covered by tests.

Delivery Milestones
- [x] `DQ-7.MS-01` Milestone A (Decision): `DQ-7.DT-01` to `DQ-7.DT-02` ✅ Complete
- [x] `DQ-7.MS-02` Milestone B (Compiler): `DQ-7.DT-03` to `DQ-7.DT-05`
- [x] `DQ-7.MS-03` Milestone C (Runtime/Quality): `DQ-7.DT-06` to `DQ-7.DT-07`

---

## DQ-8 Rule Test Execution with Attribute Selection and Plain-Language Results

Goal: Allow users to run a rule test against generated data, select which assigned attributes to test against, and receive business-friendly evidence that explains what ran and why records passed or failed.

### Motivation

Rules can be assigned to multiple attributes across one or more data-object versions. Prior to this feature, test runs had no way to scope execution to a specific attribute or version — any test fired against an implied version, making results ambiguous when a rule was reused across several data objects. Additionally, raw technical payloads were not consumable by non-technical users.

### User-Facing Behaviour

**Attribute selection panel (Test Rule modal)**
- [x] `DQ-8.UX-03` When the user opens the *Test Rule* modal, all attributes currently assigned to the rule are listed with checkboxes.
- [x] `DQ-8.UX-04` The user can select one or more attributes. By default all are selected.
- [x] `DQ-8.UX-05` *Select all* and *Clear* convenience buttons are provided.
- [x] `DQ-8.UX-06` If the selected attributes span more than one data-object version the UI blocks the run with a validation message. Each test run must resolve to a single data-object version.
- [x] `DQ-8.UX-07` If no attributes are assigned to the rule the modal shows an informational message and disables the run button.

**Plain-language explainer ("What does this mean?")**
- [x] `DQ-8.UX-08` After a test completes, a toggle button *What does this mean?* appears inside the rule-details business-evidence section.
- [x] `DQ-8.UX-09` Clicking it expands a collapsible panel that explains in plain English.
- [x] `DQ-8.UX-09a` The panel explains how many records were tested and what percentage passed.
- [x] `DQ-8.UX-09b` The panel identifies which data source and data-object version were used.
- [x] `DQ-8.UX-09c` The panel shows the compiled artifact key and quality dimension being checked.
- [x] `DQ-8.UX-09d` The panel lists which attributes were included in the test.
- [x] `DQ-8.UX-09e` The panel includes failure analysis when failures are found.
- [x] `DQ-8.UX-09e-1` Failure analysis first uses explicit `failureReasons` returned by the API when available.
- [x] `DQ-8.UX-09e-2` Failure analysis next uses `diagnostics` messages returned by the API when available.
- [x] `DQ-8.UX-09e-3` Failure analysis can derive null/empty field hotspots across failed rows.
- [x] `DQ-8.UX-09e-4` Failure analysis can include a representative failed row as key/value evidence.
- [x] `DQ-8.UX-09e-5` Failure analysis falls back to a generic message when no per-row detail was returned.

**Test results table (Operations)**
- [x] `DQ-8.UX-01` The test-results table includes an *Attributes* column showing the attribute name(s) under which each test ran.
- [x] `DQ-8.UX-02` When more than two attributes are shown, overflow is condensed to `+N more`; the full list is available as a hover tooltip.

### Technical Details

| Component | Change |
|---|---|
| `TestRuleModal.tsx` | Added `assignedAttributes` prop; checkbox panel; version-uniqueness validation; resolves `versionId` from selection |
| `useRuleActions.ts` | `handleTestRule` accepts `{ sampleCount, versionId, selectedAttributes }`; reads `totalTests`/`passedCount`/`failedCount`/`successRate` from API; guards on `testedCount &lt;= 0`; persists `selectedAttributes` in proofData; auto-closes modal on success |
| `Rules.tsx` | Resolves `versionId` and `dataObjectId` into attribute catalog; computes `activeRuleAssignedAttributes` memo |
| `RuleDetailsModal.tsx` | `testExplanation` memo; `What does this mean?` toggle; collapsible explainer panel with failure analysis |
| `Reports.tsx` | Added Attributes column to the Operations test-results view; reads `proofData.selectedAttributes` from stored proof |
| `testing.py` (FastAPI) | Returns HTTP 400 if `totalTests &lt;= 0` after test run |

### Zero-Row Guard

A rule test that generates zero test records was previously reported as a pass (0 failures ÷ 0 total = 100 % success). This is now blocked at two layers:
- [x] `DQ-8.GUARD-01` Backend: `testing.py` raises `HTTP 400` with message `"No test records were executed"` when `totalTests &lt;= 0`.
- [x] `DQ-8.GUARD-02` Frontend: `useRuleActions.ts` throws a handled error before persisting a proof when `testedCount &lt;= 0`.

### Tracked Work Items

- [x] `DQ-8.1` Attribute selection panel in Test Rule modal
- [x] `DQ-8.2` Version-uniqueness validation for multi-attribute test runs
- [x] `DQ-8.3` Plain-language explainer ("What does this mean?") in rule details
- [x] `DQ-8.4` Failure analysis in plain-language explainer
- [x] `DQ-8.5` Attributes column in test-results table (Operations)
- [x] `DQ-8.6` Zero-row false-pass guard (frontend + backend)
- [x] `DQ-8.7` Modal auto-close after successful test run

---


## DQ-10 Natural-Language Rule Drafting Preview

Status note: DQ-10 is complete. The current-state snapshot now lives in [docs/status/current/DQ-10_NATURAL_LANGUAGE_RULE_DRAFTING_PREVIEW.md](/docs/status/current/DQ-10_NATURAL_LANGUAGE_RULE_DRAFTING_PREVIEW/).

Related details:
- [DQ-10 implementation details](/docs/implementation-details/DQ_10_NATURAL_LANGUAGE_RULE_DRAFTING_IMPLEMENTATION_DETAILS/)

---


## DQ-11 Continuous Data Observability and Health Scorecards

Goal: add a first-class observability surface that continuously evaluates datasets, Data Assets, and execution targets so users can see overall health, trend changes, and quality posture at a glance.

Tracked Work Items
- [x] `DQ-11.1` Define a dataset and Data Asset health scorecard model with configurable dimensions and rollups.
- [x] `DQ-11.2` Build overview dashboards for asset-level and workspace-level observability summaries.
- [x] `DQ-11.3` Add trend charts for quality, freshness, stability, and usage over time.
- [x] `DQ-11.4` Add drill-down views from scorecards into underlying checks, runs, and source assets.

Acceptance Criteria
- [x] `DQ-11.AC-01` Users can view a health scorecard for a Data Asset or dataset.
- [x] `DQ-11.AC-02` Scorecards summarize the current state and historical trend of key observability dimensions.
- [x] `DQ-11.AC-03` Users can drill from a scorecard into the contributing rule runs or monitors.

## DQ-12 Scheduled Monitors, Anomaly Detection, Drift Detection, and Root-Cause Analysis

Goal: provide continuous monitoring so the platform can detect quality regressions, schema drift, volume changes, and anomalous behavior without requiring manual test runs.

See [DQ-12 run plan initiation API and package CLI](/docs/technical/DQ-12_RUN_PLAN_INITIATION_API_AND_CLI/) for the dedicated external-initiation contract.

Current API slice: `GET /rulebuilder/v1/governance/monitor-definitions` returns scheduled monitor definitions for Data Assets and source datasets derived from the live catalog.

Current API slice: `GET /rulebuilder/v1/governance/monitor-anomalies` returns catalog-backed anomaly monitor templates for volume, distribution, null-rate, and freshness changes.

Current API slice: `GET /rulebuilder/v1/governance/monitor-drifts` returns catalog-backed drift-monitor templates for schema, field-level, and behavioral changes.

Current API slice: `GET /rulebuilder/v1/governance/monitor-notification-preferences` returns workspace-scoped monitor notification preferences, and the drift monitor UI exposes a one-click `Subscribe me to notifications` action for accessible workspaces.

Tracked Work Items
- [x] `DQ-12.1` Define scheduled monitor definitions for Data Assets and source datasets.
- [x] `DQ-12.2` Add anomaly-detection monitors for volume, distribution, null-rate, and freshness changes.
- [x] `DQ-12.3` Add drift-detection monitors for schema, field-level, and behavioral changes.
- [x] `DQ-12.4` Add root-cause analysis views that correlate monitor failures to source changes, rule changes, or upstream events.
- [x] `DQ-12.5` Add alert routing and notification preferences for monitor failures.
- [x] `DQ-12.6` Expose an API and package CLI for other applications to initiate a DQ run plan.

Acceptance Criteria
- [x] `DQ-12.AC-01` Users can schedule monitors for a Data Asset or dataset.
- [x] `DQ-12.AC-02` The system detects and reports anomalous or drifting behavior with explicit failure reasons.
- [x] `DQ-12.AC-03` Users can inspect likely causes and correlated changes for a failed monitor.
- [x] `DQ-12.AC-04` External applications can initiate a DQ run plan through the API or package CLI.

## DQ-13 Incident Remediation Workflows, Ownership, and Ticket Integration

Goal: connect failures to actionable operations so teams can assign owners, track remediation, and hand off issues to external ticketing or chat systems.

Tracked Work Items
- [x] `DQ-13.1` Add incident records for failed monitors, rule violations, and high-severity data events.
- [x] `DQ-13.2` Add ownership assignment and escalation rules for incidents.
- [x] `DQ-13.3` Add ticketing and webhook integrations for incident creation and status updates. _(Zammad; technical vs functional distinction)_
- [x] `DQ-13.4` Add remediation status tracking, comments, and resolution history.

Acceptance Criteria
- [x] `DQ-13.AC-01` Users can create and track incidents from data quality failures.
- [x] `DQ-13.AC-02` Incidents can be assigned, escalated, and closed with an auditable history.
- [x] `DQ-13.AC-03` External ticketing or webhook integrations can receive incident payloads.

## DQ-14 Data Contracts, Schema-Change Governance, and Conformance Checks

Implementation plan: [DQ_14_DATA_CONTRACTS_SCHEMA_CHANGE_GOVERNANCE_IMPLEMENTATION_PLAN.md](/docs/implementation-details/DQ_14_DATA_CONTRACTS_SCHEMA_CHANGE_GOVERNANCE_IMPLEMENTATION_PLAN/)

Goal: treat schema and contract changes as explicit governed events so consumers can see breaking changes before they cause downstream failure.

Tracked Work Items
- [x] `DQ-14.1` Add data contract definitions for Data Assets and source datasets.
- [x] `DQ-14.2` Add schema-diff and breaking-change detection for versioned assets.
- [x] `DQ-14.3` Add contract conformance checks for required fields, types, and compatibility rules.
- [x] `DQ-14.4` Add contract-change approval and notification flows for workspace governance.

Acceptance Criteria
- [x] `DQ-14.AC-01` Users can define and view contracts for governed assets.
- [x] `DQ-14.AC-02` Schema changes are classified as compatible or breaking with explicit diagnostics.
- [x] `DQ-14.AC-03` Contract conformance failures are visible before activation or publication.

## DQ-15 Collaboration and Reusable Policy Management

Goal: make data-quality definition creation collaborative so teams can share policies, comments, and review workflows instead of recreating rules manually.

Tracked Work Items
- [x] `DQ-15.1` Add comments and discussion threads on rules, Data Assets, monitors, and incidents. _(rules-page comment editor and monitor run comments now complete the remaining write surfaces; approvals, Data Assets, and incidents were already wired)_
- [x] Approval discussion comments are persisted through the approval audit trail and rendered in the approvals panel.
- [x] Reusable discussion panel components now render approval discussion threads, incident comments, and saved contract review notes across the app.
- [x] Dedicated Discussions hub now aggregates approval, incident, and contract-review threads with search and topic filters.
- [x] Data Assets expose entry-level contract-review comments on the selected asset/version.
- [x] Incidents expose entry-level remediation comments on each incident.
- [x] Rules-page inline comments and monitor-page entry comments now have dedicated write surfaces.
- [x] `DQ-15.2` Add reusable policy templates for common quality standards and monitor definitions. _(Governance policy documents page, policy-library sharing, and workspace-scoped reuse controls added.)_
        - [x] Create the policy document template for reusable quality standards and monitor definitions.
        - [x] Render the policy document from structured template parameters for review and reuse.
        - [x] Add a Governance policy page where documents can be viewed, reviewed, and acknowledged in the UI.
- [x] `DQ-15.3` Add review/approval flows for policy changes and shared standards.
- [x] `DQ-15.4` Add sharing and workspace-scoped reuse controls for policy libraries.

Acceptance Criteria
- [x] `DQ-15.AC-01` Users can collaborate on quality definitions through comments or discussions.
- [x] `DQ-15.AC-02` Policies can be reused across multiple assets or workspaces where permitted.
- [x] `DQ-15.AC-03` Policy changes are reviewable before they become active.

## DQ-16 AI-Assisted Authoring and Recommendations for Quality Standards

Goal: use AI to suggest checks, monitors, and quality policies from asset metadata, history, and observed behavior without replacing explicit user confirmation.

Tracked Work Items
- [x] `DQ-16.1` Add AI-assisted suggestions for rules, monitors, and Data Asset definitions.
- [x] `DQ-16.2` Add recommendation previews that explain why a suggestion was made.
- [x] `DQ-16.3` Add explicit confirm/reject flows before suggested changes are saved.
- [x] `DQ-16.4` Add prompt and suggestion history so teams can review what was proposed.

Acceptance Criteria
- [x] `DQ-16.AC-01` Users can request suggestions for checks, monitors, or policy patterns.
- [x] `DQ-16.AC-02` Suggested content is preview-only until explicitly confirmed.
- [x] `DQ-16.AC-03` The system records suggestion provenance and user decisions.

## DQ-17 First-Class Reconciliation and Cross-System Comparison Workflows

Goal: model reconciliation as a dedicated workflow for comparing source systems, datasets, and delivery outputs instead of treating it only as an isolated rule type.

Tracked Work Items
- [x] `DQ-17.1` Add reconciliation workflows for comparing two or more systems or datasets.
- [x] `DQ-17.2` Add match/mismatch summaries for row counts, aggregates, keys, and payloads.
- [x] `DQ-17.3` Add reconciliation run history and exception tracking. _(Persisted through GX run storage and the reconciliation run history API.)_
- [x] `DQ-17.4` Add reuse of reconciliation definitions across Data Assets and rules. _(User guide: [DQ_17_RECONCILIATION_WORKFLOW_GUIDE.md](/docs/user-manuals/DQ_17_RECONCILIATION_WORKFLOW_GUIDE/))_

Acceptance Criteria
- [x] `DQ-17.AC-01` Users can configure and run reconciliation between selected sources.
- [x] `DQ-17.AC-02` Reconciliation outputs show matched, missing, and mismatched outcomes.
- [x] `DQ-17.AC-03` Reconciliation results can be reviewed historically and reused.

## DQ-18 Lineage and Business Context Across Data Assets and Rules

Goal: attach business context and lineage to Data Assets, rules, and execution results so users can understand impact, provenance, and downstream dependencies.

Tracked Work Items
- [x] `DQ-18.1` Add lineage views that connect Data Assets, source datasets, rules, monitors, and incidents.
- [x] `DQ-18.2` Add business-context fields such as domain, purpose, steward, criticality, and consumers.
- [x] `DQ-18.3` Add impact analysis for changes to Data Assets, contracts, and rules.
- [x] `DQ-18.4` Add lineage-aware navigation in the UI and API responses.

Acceptance Criteria
- [x] `DQ-18.AC-01` Users can trace a Data Asset or rule back to its sources and forward to its dependents.
- [x] `DQ-18.AC-02` Business context is visible alongside technical lineage.
- [x] `DQ-18.AC-03` Impact analysis highlights downstream objects affected by a change.

## DQ-19 Ataccama ONE Parity Gaps

Goal: close feature gaps highlighted by the public Ataccama ONE platform surface, especially business glossary, reference data management, master data management, autonomous AI stewardship, and governed data protection workflows.

Roadmap alignment: `DQ-19.9` is tracked in `WS-10` as the Agentic AI Ecosystem workstream in [docs/status/roadmap/FEATURE_ROADMAP_OVERVIEW.md](/docs/status/roadmap/FEATURE_ROADMAP_OVERVIEW/).

Tracked Work Items
- [x] `DQ-19.1` Business glossary with stewarded terms, hierarchies, synonyms, and rule bindings. Note: this is intentionally OpenMetadata-backed and not Postgres-backed.
- [x] `DQ-19.2` Reference data management for governed code lists, lookup values, and reusable domains.
- [x] `DQ-19.3` Master data management for 360-style entity consolidation, matching, survivorship, and merge resolution.
- [x] `DQ-19.4` Autonomous AI steward for natural-language rule authoring, metadata explanations, and suggested fixes. Persisted in Postgres via the natural-language analysis request rows.
- [x] `DQ-19.5` Automated lineage capture with business-context overlays, classification views, and anomaly annotations. Persisted in Postgres via lineage snapshot rows.
- [x] `DQ-19.6` Data observability triage with issue routing, root-cause drilldown, and remediation actions. _(User guide: [Data Observability Triage Guide](/docs/user-manuals/data-observability-triage-guide/), v0.11.0)_
        - Metadata-only triage view that exposes incident routing, status, and remediation metadata without surfacing source records or failure payloads.
        - Current implementation adheres to the data-protection policy for no raw-data exposure in the triage path.
- [x] `DQ-19.7` Data protection workflows for masking, encryption of privacy sensitive information, consent management, and erasure-rights handling.
        - Advice from `DQ-19.8` classification output that an attribute should be protected through masking or encryption.
        - If the steward or admin accepts the advice, they can choose the masking method or encryption key to use when the current workspace allows it.
        - Governance page analysis that shows which attributes have which classifications and whether they are protected by an approved masking method or encryption key.
        - Current implementation adheres to the policy document for classification-driven advice, explicit masking/encryption selection, and fail-fast policy alignment; retention/disposal is handled by separate platform controls and is out of scope for this slice.
        - Additional protection workflows such as consent management, restriction handling, and erasure-rights handling.
- [x] `DQ-19.8` Governance discovery and classification automation to prioritize sensitive or high-value assets. Persisted in Postgres via governance-discovery snapshots and prioritized from OpenMetadata-backed delivery classifications. Its output feeds `DQ-19.7` protection advice and Governance analysis.
- [ ] `DQ-19.9` MCP-based assistant integration for exposing trusted-data capabilities to external AI tools. This work is tracked in `WS-10`.

---
