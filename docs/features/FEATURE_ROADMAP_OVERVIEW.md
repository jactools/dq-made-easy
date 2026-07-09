# dq-made-easy Actionable Feature Roadmap Overview

Status: Planned

This is the single canonical roadmap document for product and platform work that is still planned or partially open.

Use this document to answer four questions:

1. Which platform and feature areas still have meaningful remaining work?
2. Which workstreams should be delivered first?
3. Which acceptance criteria make each workstream releasable?
4. Which detailed markdown files hold the supporting backlog and implementation context?

Completed work is tracked separately in [../MANAGEMENT_FEATURE_SUMMARY.md](../MANAGEMENT_FEATURE_SUMMARY.md) and in the current-state documents under [../README.md](../README.md).

## Goal

Evolve dq-made-easy from a strong rule engine into a governed, observable, scalable data-quality platform with proactive monitoring, business-facing workflows, enterprise integration patterns, and controlled frontend portability.

## Baseline

dq-made-easy already has meaningful foundations in place:

- A working rule engine and real execution path are implemented.
- Execution monitoring metrics and dashboard semantics exist.
- Rule lifecycle transitions, approvals, and versioning exist.
- Business metadata integration and governance drift workflows exist.
- Operational UI surfaces for rules, governance, catalog, monitoring, and notifications exist.
- Natural-language rule drafting and data-definition task foundations exist.
- Theme selection, semantic-token groundwork, and an initial app-shell frontend portability slice exist.

The remaining gap is not building the product from zero. The remaining gap is turning the existing engine and workflow surfaces into a complete platform.

## Source-Of-Truth Rules

- This file is the canonical single-document summary of remaining planned work.
- Detailed feature docs under [../../features/README.md](../../features/README.md) hold deeper backlog, acceptance criteria, and sequencing notes.
- Current-state and technical docs hold completed or implemented surfaces.
- Older ADRs or notes that mention `planned_features.md` or the platform gap closure plan should be interpreted as referring to this file.
- Completed work should not remain in the future-work queue.

## Status Legend

| Status | Meaning |
| --- | --- |
| `Open` | The track is still largely future work. |
| `Partial` | A meaningful implementation base exists, but important scope remains unfinished. |
| `Mostly complete` | The track is substantially delivered and only bounded follow-on work remains. |

## Progress States

Use these states for workstream and epic tracking:

| State | Meaning |
| --- | --- |
| `not_started` | No active discovery or delivery work has begun. |
| `discovery` | Problem framing, requirements, and dependency mapping are in progress. |
| `design_in_progress` | Delivery design, contracts, and solution boundaries are being finalized. |
| `implementation_in_progress` | Code, configuration, or operational rollout work is actively being delivered. |
| `validation_in_progress` | The slice is implemented and is going through tests, demos, or operator validation. |
| `released` | Acceptance criteria are met and a real validation path exists for users or operators. |

Each work item should only move to `released` when the relevant acceptance criteria are satisfied and a user-facing or operator-facing validation path exists.

## Not Remaining Roadmap Work

These areas are implemented and should not be treated as open roadmap items here:

- `DQ-7` executable rule transformation is complete and now belongs to current-state and technical references, not the future-work queue.
- `DQ-10` natural-language rule drafting preview is complete and tracked in current-state docs.
- `API-5` business metadata integration is complete.
- `API-7` real DQ rule execution is complete.
- `WF-3` rule versioning and rollback is complete.
- `WS1-A05` alert-routing policies for Teams, Slack, email, and PagerDuty are complete, with secret app-config connectivity values managed in the admin settings seam.
- `WS1-A06` workspace health summaries are complete, with historical quality score, top regressions, top failing rules, and active incidents surfaced through the dashboard and API contract.
- `WS1-A07` incident correlation inputs are complete, with source correlation metadata flowing through incident creation, support payloads, and the incidents dashboard.
- `UX-1` to `UX-4` user experience cohesion work is complete and now belongs to current-state documentation, not the future-work queue.
- `WF-5` environment contract is mostly complete and should be treated as a dependency for validation and workflow work, not a greenfield workstream.

## Target Platform Blueprint

The target architecture is a composable DQ platform built from explicit layers instead of a single monolith.

| Layer | Role | Primary roadmap coverage |
| --- | --- | --- |
| OpenMetadata control plane | Dataset metadata, ownership, domain mapping, lineage, business definitions, DQ result history, and quality rollups. | `WS-4`, `WS-5` |
| DQ control and integration layer | Rule taxonomy, registry, orchestration, result mapping, control-plane publication, and pipeline triggers. | `WS-3`, `WS-5` |
| dq-made-easy RuleBuilder execution engine | Focused rule execution and structured result generation. | `WS-6` |
| Observability layer | Time-series history, trend analysis, SLOs, drift, anomaly detection, and alerting. | `WS-1` |
| Visualization layer | Business-facing dashboards, failure exploration, steward workflows, and operational views. | `WS-2`, `WS-7` |
| Pipeline integration layer | Validation in ingestion, transform, publish, and orchestrated flows such as Airflow, ADF, or Fabric. | `WS-5` |
| Agentic integration layer | Agent-ready DQ APIs, MCP server resources, autonomous DQ agents, and governed platform integrations. | `WS-10` |
| CI/CD integration layer | Shift-left checks, PR gates, sample validation, and fail-fast validation templates. | `WS-5` |

The design keeps dq-made-easy focused on execution as one player in a broader metadata foundation, OpenMetadata focused on metadata/control-plane context, observability focused on monitoring, and the DQ control layer responsible for orchestration, standardization, and publication.

## Architectural Principles

- Reuse existing FastAPI, dq-ui, execution monitoring, metadata integration, and governance seams instead of building duplicate side systems.
- Prefer backend-owned contracts for filtering, aggregation, lifecycle enforcement, audit, and summaries.
- Treat observability, lineage, metadata, and governance as first-class platform seams, not UI-only features.
- Avoid compatibility-heavy fallback layers; evolve canonical contracts directly.
- Keep dq-made-easy composable so major components can be replaced later without redesigning the whole product.

## Workstream Summary

| Workstream | Status | Current foundation | Target outcome | Wave |
| --- | --- | --- | --- | --- |
| `WS-1` Observability Platform | Done | Execution monitoring taxonomy, dashboard semantics, observability triage guide. | Historical DQ outcomes, trends, drift, anomaly detection, SLA/SLOs, and alerting. | Wave 1 |
| `WS-2` UX and Visualization | Partial | Existing dashboard, governance, monitoring, operations, rules UI, and completed UX-1 to UX-4 cohesion work. | Business-facing health dashboards, result explorer, metadata-safe drilldown, and steward guidance. | Wave 1 |
| `WS-3` Governance and Lifecycle | Partial | Rule status transitions, approvals, versioning basics, and audit surfaces. | Rule registry, explicit ownership, deprecation lifecycle, governance inboxes, and reusable rule packs. | Wave 1 |
| `WS-4` Metadata and Semantic Automation | Partial | API-5 metadata integration, OpenMetadata-backed business terms, governance drift, and data-definition task foundation. | Metadata-aware execution, tag selectors, metadata-driven suggestions, business definitions, domain ownership, lineage impact analysis, an ontology and knowledge-graph foundation across domains built on open standards and open-source software, and a federated metadata registry that can exchange governed local metadata packages across parties. | Wave 2 |
| `WS-5` Control, Delivery, CI/CD, and Integrations | Open | Existing API surface, execution engine, workers, scripts, and environment contract foundations. | Git-first registry, orchestration hooks, connector strategy, CI/CD templates, pipeline-native validation, and contract enforcement. | Wave 1/Wave 2 |
| `WS-6` Scale and Advanced Validation | Open | GX runtime, abstraction seam, grouped planning, and monitoring foundations. | Spark-native execution, incremental validation, pushdown, streaming support, and richer rule families. | Wave 3 |
| `WS-7` Frontend Portability | Partial | Theme selection, semantic-token baseline, and app-shell token migration. | App-owned primitives, vendor adapter boundary, feature-page decoupling, and portability guardrails. | Wave 1/Wave 2 |
| `WS-8` Security, Compliance, and Auditability | Open | Auth, scopes, governance/audit surfaces, observability policy docs, and security plans. | Stronger RBAC, immutable audit, PII-aware controls, compliance reporting, encryption, TLS, and controlled egress. | Wave 2 |
| `WS-9` Documentation and Onboarding | Partial | Current docs, feature docs, and user manuals. | Clear docs ownership, workflow coverage, publishing decision, and onboarding generation for standard rules. | Wave 2 |
| `WS-10` Agentic AI Ecosystem | Partial | Agentic assistant foundations, metadata, observability, and existing FastAPI surface. | Agent-ready APIs, MCP server resources, autonomous DQ agents, external agent platform integrations, and governed, explainable agent actions. | Wave 2 |

## Capability Mapping

| Missing capability | Roadmap response |
| --- | --- |
| Observability | `WS-1` result history, trend APIs, drift, anomaly detection, SLA/SLOs, and alerting. |
| UI and visualization | `WS-2` business-facing dashboards, result exploration, and metadata-safe drilldown. |
| Governance | `WS-3` rule registry, ownership, lifecycle, audit, and stewardship views. |
| Metadata integration | `WS-4` OpenMetadata control-plane usage, lineage, tags, business definitions, ontology and knowledge-graph foundations, federated metadata registry packages, distributed push/pull collection services, and data-product rollups. |
| Pipeline integration | `WS-5` orchestration hooks, pipeline-native validation, and connector patterns. |
| CI/CD | `WS-5` official GitHub Actions and Azure DevOps templates with fail-fast contracts. |
| Scalability | `WS-6` Spark-native execution, incremental validation, SQL pushdown, and streaming seam. |
| Advanced checks | `WS-6` cross-dataset, freshness, distribution, outlier, entropy, and anomaly rule families. |
| Root-cause analysis | `WS-1`, `WS-4`, and `WS-6` incident correlation, lineage-aware analysis, and remediation recommendations. |
| Agentic AI interoperability | `WS-10` agent-ready APIs, MCP server, autonomous agents, and governed platform integrations. |
| Frontend portability | `WS-7` app-owned tokens, primitives, adapter boundary, and replacement pilot. |

## Actionable Backlog And Acceptance Criteria

Use this section as the implementation tracking layer for the roadmap. Each checkbox has a stable unique identifier so it can be referenced in standups, tickets, and status reports.

### WS-1 Observability Platform

Implementation checklist:

- [x] `WS1-A01` Define a canonical DQ result event contract for run outcome, dataset, domain, rule, severity, score dimensions, and correlation metadata.
- [x] `WS1-A02` Persist time-series DQ outcomes so trend analysis is possible by rule, dataset, domain, and data product.
- [x] `WS1-A03` Add degradation and drift detectors for schema changes, null-rate shifts, distribution changes, and volume anomalies.
- [x] `WS1-A04` Add SLA and SLO configuration for freshness, completeness, validity, incident rate, and critical rule pass rates.
- [x] `WS1-A07` Add incident correlation inputs that can later support guided root-cause suggestions.

Acceptance checklist:

- [x] `WS1-AC01` A user can view quality history over time for a dataset, rule, domain, and data product.
- [x] `WS1-AC02` A user can see degradation or drift events without manually comparing raw runs.
- [x] `WS1-AC03` SLA or SLO breaches generate explicit incident or alert events.
- [x] `WS1-AC04` Alert policies support at least one chat target and one email target in the first release.
- [x] `WS1-AC05` The platform can distinguish current failures from worsening trends.

### WS-2 UX And Visualization

Implementation checklist:

- [x] `WS2-A01` Add DQ health dashboards for dataset, domain, and data product views.
- [x] `WS2-A02` Add result exploration pages with backend-owned filtering by dataset, owner, domain, severity, status, and timeframe. No actual data may appear.
- [x] `WS2-A03` Add failure drilldown with metadata-only context, not raw data preview.
- [x] `WS2-A04` Add steward-friendly summary cards and guided navigation into owning workflows.
- [x] `WS2-A05` Add executive and operational dashboard views for quality score, top failing rules, top degraded datasets, and SLA status.

Acceptance checklist:

- [x] `WS2-AC01` A non-technical user can find the current health of a data product without using API tools.
- [x] `WS2-AC02` A user can navigate from a failing quality signal to its owning rule, owner, and recent history.
- [x] `WS2-AC03` Dashboard summaries are API-driven and do not compute business filtering only in the UI.
- [x] `WS2-AC04` Drilldown views remain metadata-safe and do not expose restricted data values.

### WS-3 Governance And Lifecycle

Implementation checklist:

- [x] `WS3-A01` Define the central rule registry contract and rule discovery model.
- [x] `WS3-A02` Add explicit rule ownership fields for data steward, domain owner, and technical owner.
- [x] `WS3-A03` Add lifecycle states for active, deprecated, superseded, and retired rules.
- [x] `WS3-A04` Add governance inboxes for approval, reassignment, and deprecation review.
- [x] `WS3-A05` Strengthen change history and rule audit records for create, edit, approve, reject, activate, deactivate, deprecate, supersede, and retire actions.
- [x] `WS3-A06` Add parameterized rule templates, inheritance rules, and domain rule packs.

Acceptance checklist:

- [x] `WS3-AC01` Every governed rule has an owner and discoverable lifecycle status.
- [x] `WS3-AC02` Rules can be searched and filtered by owner, domain, lifecycle state, severity, and execution target.
- [x] `WS3-AC03` Approval and deprecation actions are recorded with actor, timestamp, and rationale.
- [x] `WS3-AC04` Reusable rule templates reduce duplicated rule definitions across domains.

### WS-4 Metadata And Semantic Automation

Implementation checklist:

- [x] `WS4-A01` Extend metadata ingestion to include dataset-to-domain mapping, lineage references, tags, business definitions, and ownership.
- [x] `WS4-A02` Add tag-based execution selectors such as PII, finance, or domain-specific tags.
- [x] `WS4-A03` Add metadata-driven rule suggestions from schema, tags, glossary terms, profiling signals, and historical incidents.
- [x] `WS4-A04` Add lineage-aware impact analysis for failing datasets and upstream dependency correlation.
- [x] `WS4-A05` Add product and domain quality rollups based on metadata ownership and topology.
- [x] `WS4-A06` Add a platform-owned data-definition task flow that generates BCBS 239-ready glossary drafts from metadata, policy input, steward feedback, and data-definition board decisions.
- [x] `WS4-A07` Add automatic OpenMetadata import and approval-state propagation for generated data-definition contracts after board approval.
- [x] `WS4-A08` Ensure all generated business term definitions and approval workflows comply with the "Guidelines for Definitions of Business Terms" v1.0, including canonical English definitions, one entry per concept, clear homonym disambiguation, source references, primary domain, definition owner, and policy document linkage.
- [x] `WS4-A09` Add exception-analysis session orchestration so a steward can keep the rule, source, and base execution scope fixed while the backend keeps enqueueing the next slice until uncovered exception space is exhausted or a budget is hit.
- [x] `WS4-A10` Add backend slice-batch planning from a partition strategy so slice generation uses reason_code, failure_class, record_identifier_type, date or partition buckets, and hash stripes instead of manual filter entry.
- [x] `WS4-A11` Persist every slice pack and manifest to AIStor while keeping only the session summary, slice metadata, and object-storage pointers in the database.
- [x] `WS4-A12` Add a single-command steward workflow with progress, estimated remaining volume, and cost impact so the UI can track analysis without loading raw exception rows into the browser.
- [x] `WS4-A13` Add adaptive slice sizing, hard execution budgets for concurrency, storage, and time, resume support for interrupted sessions, and a summary-first mode before full archive materialization.
- [x] `WS4-A14` Add a domain ontology and knowledge-graph foundation that can connect the dots within and across domains using open standards and open-source software, with dq-made-easy contributing execution signals and quality outcomes as one player in the broader metadata foundation.
- [x] `WS4-A21` Define the canonical ontology scope, entity vocabulary, relation vocabulary, and open-standard alignment for the knowledge-graph model.
- [x] `WS4-A22` Model domains, datasets, data products, rules, validation suites, validation plans, and DQ outcomes as graph-connected nodes and edges. Also include Time Point and Event, and an Organizational Hierarchy.
- [x] `WS4-A23` Add graph persistence and projection from existing metadata, governance, and execution seams without making dq-made-easy the sole system of record.
- [x] `WS4-A24` Expose graph query and traversal read APIs for cross-domain navigation, lineage-style lookup, and impact discovery.
- [x] `WS4-A15` Add a Federated Metadata Registry that packages governed metadata structures for local creation and maintenance by other parties, while providing push and pull services to collect distributed metadata back into the broader foundation.
- [x] `WS4-A18` Persist federated metadata package snapshots and exchange history so push and pull submissions are durably recorded and auditable.
- [x] `WS4-A19` Register external parties that participate in federated metadata exchange, including their workspace or tenant identity and governing metadata scope.
- [x] `WS4-A20` Track which external parties are subscribed to, can push, or can pull each governed metadata structure and metadata item in the federated registry.
- [x] `WS4-A16` Add an ODCS-based contract for data assets with DQ Validation Suites/Plans and store the ODCS contracts in a Data Contract/Specs Registry. Enable external parties to send/consume ODCS contracts.
- [x] `WS4-A17` Add an ODCS-based contract for data products and use the Open Data Product Specifications (ODPS) for Data Product specifics; store the ODPS-based Data Product specs and ODCS contracts in a Data Contract/Specs Registry
	- Status: lookup, registry-read, lifecycle write, stewardship workflow, and bulk migration-import slices are implemented and validated. The backend read model, OpenMetadata-backed resolver, single-item lookup endpoint, paginated registry list endpoint with backend-owned filters, `POST` and `PUT` lifecycle endpoints, canonical `POST /api/data-catalog/v1/product-specs/import` with dry-run and create/update reporting, stewardship/reporting routes (`GET /api/data-catalog/v1/product-specs/summary`, `POST /api/data-catalog/v1/product-specs/{product_spec_id}/stewardship-actions`), focused resolver/API tests, downstream consumer compatibility coverage in `dq-api/fastapi/tests/api/test_product_specs_consumer_compatibility.py`, committed ODCS demo contract, committed ODPS product-spec manifest, and live OpenMetadata seeding plus HTTP walkthrough are in place for `ps.retail_banking_customer_360`.
	- Follow-on scope: expand compatibility validation further as additional downstream consumers are added.

Acceptance checklist:

- [x] `WS4-AC01` A dataset can be linked to a domain, owner, and business definitions in the platform.
- [x] `WS4-AC02` Rules can be executed based on metadata tags rather than only manual selection.
- [x] `WS4-AC03` The platform can explain which upstream or related entities are likely impacted by a DQ issue.
- [x] `WS4-AC04` Suggested rules use metadata context rather than generic templates only.
- [x] `WS4-AC05` A steward can select a data object with or without one or more catalog attributes, generate a definition draft, submit revision feedback, and capture a board decision without calling dq-llm directly.
- [x] `WS4-AC06` Approved data-definition drafts can be imported into OpenMetadata through a canonical backend workflow with explicit success or failure reporting.
- [x] `WS4-AC07` Generated and approved business term definitions are validated for semantic quality, structure, and compliance before approval or import.
- [x] `WS4-AC08` A steward can run repeatable analysis slices for the same rule and source scope, retrieve each slice's exception results and details from the stored analysis pack, and continue the session until uncovered exception space is exhausted or the budget is hit.
- [x] `WS4-AC09` Slice batches are generated from a documented partition strategy and do not rely on manual entry of hundreds of filters.
- [x] `WS4-AC10` Every analysis slice stores its pack and manifest in object storage while the database stores only the session summary, slice metadata, and storage pointers.
- [x] `WS4-AC11` A steward can start analysis from a single command and see progress, estimated remaining volume, and cost impact without loading raw exception rows into the browser.
- [x] `WS4-AC12` Analysis sessions support adaptive slice sizing, execution budgets, resumable continuation, and a summary-first mode before full archive materialization.
- [x] `WS4-AC13` Domain-level ontologies and knowledge graphs can connect business concepts, datasets, domains, and DQ outcomes across the metadata foundation without treating dq-made-easy as the sole system of record.
- [x] `WS4-AC14` Federated metadata packages can be distributed to other parties for local metadata creation and maintenance, and the platform can collect distributed metadata through both push and pull services.
- [x] `WS4-AC15` Federated metadata package snapshots and exchange history are durably recorded and can be audited after push or pull activity.
- [x] `WS4-AC16` External parties participating in federated metadata exchange are registered with their governing scope and identity.
- [x] `WS4-AC17` The platform can report which external parties are subscribed to, can push, or can pull each governed metadata structure and metadata item.
- [x] `WS4-AC18` The ontology and knowledge-graph model has a documented canonical scope, entity set, relation set, and open-standard alignment.
- [x] `WS4-AC19` Domains, datasets, data products, rules, validation suites, validation plans, and DQ outcomes can be represented and connected in the graph.
- [x] `WS4-AC20` Existing metadata, governance, and execution seams can project their signals into the graph without moving ownership away from the source systems.
- [x] `WS4-AC21` Users and backend consumers can query cross-domain relationships and impact paths through canonical backend contracts.

### WS-5 Control, Delivery, CI/CD, And Integrations

Implementation checklist:

- [x] `WS5-A01` Define the Git-first rule registry layout and deployment workflow.
- [x] `WS5-A02` Define the shared rule taxonomy for type, severity, domain, owner, SLA scope, and execution target.
- [x] `WS5-A03` Add the control-layer mapping from RuleBuilder results to metadata, observability, and control-plane contracts.
- [x] `WS5-A04` Add orchestration hooks for schedule, pipeline-run, and data-arrival triggers.
- [x] `WS5-A05` Publish GitHub Actions and Azure DevOps templates for validation and fail-fast enforcement.
- [x] `WS5-A06` Add first-party integration patterns for one orchestrator path such as Airflow, ADF, or Fabric.
- [ ] `WS5-A07` Define connector strategy and plugin contracts for warehouses and pipeline systems.
- [ ] `WS5-A08` Complete `API-1` to `API-4` connector, webhook, rate-limit, and advanced-auth work.
- [ ] `WS5-A09` Complete `API-6` namespace cleanup so authenticated session/profile reads are outside `/admin/v1`.
- [x] `WS5-A10` Add external orchestration support so external DAGs can trigger runs and fail fast on API or run failure.

Acceptance checklist:

- [ ] `WS5-AC02` CI can fail when sample-data validation or contract thresholds regress.
- [x] `WS5-AC03` Pipelines can trigger DQ validation without custom per-team orchestration logic.
- [x] `WS5-AC04` Rule execution outputs are translated into canonical control-plane and observability events.
- [x] `WS5-AC05` First-party integration paths fail fast when required APIs or services are unavailable.

### WS-6 Scale And Advanced Validation

Implementation checklist:

- [x] `WS6-A01` Add Spark-native execution support through the abstraction seam.
- [x] `WS6-A02` Add incremental validation that can target only new partitions or changed slices.
- [x] `WS6-A03` Add SQL pushdown planning where engine capabilities support it.
- [x] `WS6-A04` Define optional streaming or micro-batch validation support.
- [x] `WS6-A05` Add advanced rule types for cross-dataset integrity, freshness, distribution, outlier, entropy, probabilistic, seasonality, and anomaly checks.
- [x] `WS6-A06` Add performance monitoring for execution path, planner choice, runtime cost, and data scanned.

Acceptance checklist:

- [x] `WS6-AC01` Large datasets can be validated without forcing full rescans for every run.
- [x] `WS6-AC02` The platform supports at least one distributed execution path beyond the current baseline executor.
- [x] `WS6-AC03` Advanced rule types are first-class contracts, not one-off custom scripts.
- [x] `WS6-AC04` Execution plans can select incremental or pushdown strategies where supported.

### WS-7 Frontend Portability

Implementation checklist:

- [x] `WS7-A01` Continue semantic-token migration beyond the completed app-shell slice so feature CSS describes app semantics rather than vendor semantics.
- [x] `WS7-A02` Define and adopt app-owned primitives such as `AppButton`, `AppSelect`, `AppInput`, `AppTextarea`, `AppModal`, `AppBanner`, `AppTabs`, `AppTable`, `AppIcon` and any other component/style used.
- [x] `WS7-A03` Move direct vendor UI knowledge behind one shared adapter boundary.
- [x] `WS7-A04` Remove direct vendor imports and raw vendor element usage from feature pages and shared workflow screens.
- [x] `WS7-A05` Add guardrails against new feature-level vendor coupling.
- [x] `WS7-A06` Prove replacement with one representative pilot page running through app-owned primitives.
- [x] `WS7-A07` Place all icons behind app icon names so changing to a different icon provider is possible.

Acceptance checklist:

- [x] `WS7-AC01` Feature pages consume app-owned primitives rather than direct vendor components.
- [x] `WS7-AC02` Feature CSS uses app-owned semantic tokens rather than vendor-shaped tokens.
- [x] `WS7-AC03` One representative page can run through a replacement primitive implementation with bounded adapter-level changes.

### WS-8 Security, Compliance, And Auditability

Implementation checklist:

- [x] `WS8-A01` Add immutable audit-history support for governed changes.
- [x] `WS8-A02` Add audit compliance reporting views for rule, data-definition, validation, and approval history.
- [x] `WS8-A03` Add PII-aware masking policies for validation, drilldown, evidence, and incident workflows.
- [x] `WS8-A04` Harden RBAC for governance, observability, metadata, and approval workflows.
	- Status: User updates are role/workspace based, direct permission payloads are rejected, and the admin user-management surface now assigns workspace roles through the canonical role catalog.
- [ ] `WS8-A05` Complete internal TLS, post-quantum readiness, synthetic/evidence bucket separation, controlled egress, and encryption-at-rest/key segregation planning.

Acceptance checklist:

- [ ] `WS8-AC01` Compliance users can trace rule and definition changes end to end.
- [ ] `WS8-AC02` Restricted data values are not exposed in metadata-safe workflows.
- [ ] `WS8-AC03` Security controls are enforceable through canonical platform contracts.

### WS-9 Documentation And Onboarding

Implementation checklist:

- [x] `WS9-A01` Define docs ownership and source-of-truth boundaries across feature, current-state, technical, and user documentation.
	- Status: Canonical policy published in `docs/technical/DOCUMENTATION_OWNERSHIP_AND_SOURCE_OF_TRUTH.md` with audience entry points, family boundaries, ownership model, update triggers, and conflict-resolution precedence.
- [x] `WS9-A02` Expand workflow coverage for operators, data stewards, analysts, admins, and developers.
	- Status: Role-based workflow guides published in `docs/user-manuals/`: [workflow-operator.md](../../user-manuals/workflow-operator.md), [workflow-data-steward.md](../../user-manuals/workflow-data-steward.md), [workflow-analyst.md](../../user-manuals/workflow-analyst.md), [workflow-admin.md](../../user-manuals/workflow-admin.md), [workflow-developer.md](../../user-manuals/workflow-developer.md). Index updated with a role-based entry section.
- [x] `WS9-A03` Decide whether to keep or migrate the current docs publishing model.
	- Status: Decision formalised in [EDR-046-META-docs-publishing-model-keep-docusaurus-baked-into-ui.md](../../engineering-decisions/EDR-046-META-docs-publishing-model-keep-docusaurus-baked-into-ui.md). Current Docusaurus model retained; independent docs build step identified as a follow-on improvement.
- [x] `WS9-A04` Add guided generation of standard rules for selected data objects.
	- Status: ONB-1 feature specified in [`docs/features/ONBOARDING_FEATURES.md`](../../features/ONBOARDING_FEATURES.md) with scope selection model, metadata-driven proposal algorithm, progressive-disclosure review tree, bulk select/de-select UX, and batch draft creation flow. User workflow guide published in [`docs/user-manuals/workflow-onboarding-rule-generation.md`](../../user-manuals/workflow-onboarding-rule-generation.md).

Acceptance checklist:

- [x] `WS9-AC01` Users can find current workflow docs without reading implementation notes.
- [x] `WS9-AC02` Operators can validate deployment, smoke-test, and troubleshooting flows.
- [x] `WS9-AC03` Onboarding can generate standard starter rules with reviewable output.

### WS-10 Agentic AI Ecosystem

Implementation checklist:

- [x] `WS10-A01` Expose agent-ready REST APIs for DQ rule execution, anomaly results, and metadata lookup with canonical snake_case request and response contracts and published OpenAPI specifications.
- [x] `WS10-A02` Publish an MCP server that exposes DQ dashboards, rule libraries, lineage graphs, and governed tools such as `validate_dataset`, `get_anomalies`, and `trigger_remediation`.
- [x] `WS10-A03` Define autonomous DQ agent workflows for a data steward, lineage explorer, and remediation bot, including event triggers, permissions, and escalation rules.
- [x] `WS10-A04` Integrate with external agent platforms such as Mistral AI, Microsoft Copilot, GitHub Copilot, Slack, Airflow, and Dagster through explicit integration contracts and operator-owned webhooks or jobs. Only Mistral and Microsoft Copilot are on the initial allow-list, seeded through dq-db/mock-data csv/json files.
- [x] `WS10-A05` Expose governance and observability context for agent decisions, including lineage, business context, SLA thresholds, explanation payloads, and remediation audit trails.

Acceptance checklist:

- [x] `WS10-AC01` Agents can discover active rules, anomaly summaries, and metadata context through canonical backend APIs.
- [x] `WS10-AC02` An MCP client can request DQ resources and invoke governed tools without requiring UI-only workflows.
- [x] `WS10-AC03` At least one autonomous DQ agent workflow can detect an issue, explain the lineage or context, and propose or trigger a remediation path.
- [ ] `WS10-AC04` External agent platforms can consume DQ alerts and trigger DQ checks through documented integration contracts (on test/prod)
- [x] `WS10-AC05` Agent actions are explainable, governance-aware, and auditable with lineage, business context, and SLA metadata.

## Epic-Level Checkpoints

Use these checkpoints to track implementation progress at the epic level.

### OBS-1 To OBS-6

- [ ] `OBS-C01` Result history storage is implemented.
- [ ] `OBS-C02` Trend APIs are implemented.
- [ ] `OBS-C03` Drift and anomaly detection is implemented.
- [ ] `OBS-C04` SLA and SLO policies are persisted and evaluated.
- [ ] `OBS-C05` Alert routing is integrated and validated.

### GOV-1 To GOV-8

- [ ] `GOV-C01` Rule registry contract is implemented.
- [ ] `GOV-C02` Ownership model is enforced.
- [ ] `GOV-C03` Lifecycle and deprecation model is implemented.
- [ ] `GOV-C04` Audit trail is queryable.
- [ ] `GOV-C05` Templates, inheritance, and rule packs are available.

### META-1 To META-4

- [ ] `META-C01` Lineage and metadata model is integrated.
- [ ] `META-C02` Tag-based selection is implemented.
- [x] `META-C03` Metadata-driven suggestions are available.
- [ ] `META-C04` Column-level definitions are visible in authoring and triage flows.

### CICD-1 To CICD-4 And INT-1 To INT-5

- [x] `CICD-C01` GitHub Actions template exists.
- [x] `CICD-C02` Azure DevOps template exists.
- [ ] `CICD-C03` Contract-enforcement gate is implemented.
- [x] `INT-C01` At least one orchestrator integration is implemented.
- [ ] `INT-C02` At least one warehouse integration path is implemented.

### SCALE-1 To SCALE-4 And RULE-ADV-1 To RULE-ADV-4

- [ ] `SCALE-C01` Distributed execution path is implemented.
- [ ] `SCALE-C02` Incremental validation path is implemented.
- [ ] `SCALE-C03` Pushdown planning path is implemented.
- [x] `RULEADV-C01` Advanced rule families are exposed as supported contracts.

### RCA-1 To RCA-4

- [ ] `RCA-C01` Incident correlation model exists.
- [ ] `RCA-C02` Lineage-aware dependency analysis exists.
- [ ] `RCA-C03` Root-cause suggestions are surfaced in triage UX.
- [ ] `RCA-C04` Remediation recommendation hooks are available.

### AGENT-1 To AGENT-5

- [ ] `AGENT-C01` Agent-ready DQ APIs expose rules, anomalies, and metadata through canonical contracts.
- [ ] `AGENT-C02` MCP server resources and tools are available to compliant clients.
- [ ] `AGENT-C03` At least one autonomous steward or remediation workflow is operational.
- [ ] `AGENT-C04` At least one external agent platform integration is validated end to end.
- [ ] `AGENT-C05` Governance and observability context is returned with each agent-relevant action.

## Success Measures

- Data-quality incidents can be detected proactively from trends, drift, anomalies, and SLO breaches.
- Business and governance users can manage rules and investigate failures without raw engineering workflows.
- Rules are owned, versioned, approved, discoverable, and auditable.
- Metadata drives execution, suggestions, definitions, and impact analysis.
- New data domains can onboard with metadata, templates, connectors, and pipeline patterns instead of custom glue.
- Large datasets and advanced rule types can execute without forcing every check through the current smallest-runtime path.
- Feature pages can move across UI libraries through app-owned primitives and tokens instead of page-by-page rewrites.
- Agents and external orchestrators can consume governed DQ signals through canonical APIs and MCP without bypassing platform controls.

## Dependencies And Reuse

This plan should explicitly build on these existing repository foundations:

- [API_5_METADATA_INTEGRATION.md](../API_5_METADATA_INTEGRATION.md)
- [API_7_REAL_DQ_RULE_EXECUTION.md](../API_7_REAL_DQ_RULE_EXECUTION.md)
- [RULE_STATUS_TRANSITIONS.md](../RULE_STATUS_TRANSITIONS.md)
- [EXECUTION_MONITORING_METRIC_TAXONOMY.md](../../technical/EXECUTION_MONITORING_METRIC_TAXONOMY.md)
- [MANAGEMENT_FEATURE_SUMMARY.md](../MANAGEMENT_FEATURE_SUMMARY.md)
- [Frontend UI portability](../../features/FRONTEND_UI_PORTABILITY_FEATURES.md)

The implementation principle is simple: extend the existing platform seams, do not create a second platform beside them.

## Quick Links

- [Feature doc index](../../features/README.md)
- [Data Quality features](../../features/DQ_FEATURES.md)
- [Integration and API features](../../features/API_FEATURES.md)
- [Frontend UI portability](../../features/FRONTEND_UI_PORTABILITY_FEATURES.md)
- [Workflow enhancements](../../features/WORKFLOW_FEATURES.md)
- [WF-5 dedicated environment contract](../../features/WF_5_DEDICATED_ENVIRONMENT_CONTRACT.md)
- [Security features](../../features/SEC_FEATURES.md)
- [Analytics and reporting](../../features/ANALYTICS_REPORTING_FEATURES.md)
- [Documentation improvements](../../features/DOCUMENTATION_FEATURES.md)
- [Onboarding](../../features/ONBOARDING_FEATURES.md)
- [Agentic AI ecosystem capabilities](../../features/AGENTIC_AI_ECOSYSTEM_FEATURES.md)
- [Current-state summary](../MANAGEMENT_FEATURE_SUMMARY.md)
- [Management future work summary](./MANAGEMENT_FUTURE_WORK_SUMMARY.md)
