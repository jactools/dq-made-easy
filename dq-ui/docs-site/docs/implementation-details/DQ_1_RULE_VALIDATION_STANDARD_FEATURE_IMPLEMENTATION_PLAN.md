# DQ-1 Rule Validation Standard Feature Implementation Plan

Status: [x] Complete
Last updated: 2026-04-27
Owner: Product + UI + API

Related documents:
- [Management feature summary](/docs/features/current/MANAGEMENT_FEATURE_SUMMARY/)
- [DQ-1 Rule Validation User Guide](/docs/user-manuals/DQ-1_RULE_VALIDATION_USER_GUIDE/)
- [DQ-1 Enhanced Rule Validation Logic — Implementation Progress](https://github.com/jactools/dq-rulebuilder/blob/main/DQ_1_ENHANCED_RULE_VALIDATION_PROGRESS.md)
- [API-7 Real DQ Rule Execution](/docs/features/current/API_7_REAL_DQ_RULE_EXECUTION/)

## Goal

Promote Rule Validation from a preview feature to a standard product capability without turning the Rules area into a large, overloaded workspace.

The target product structure is:

| Product area | Primary responsibility | Included capabilities |
|---|---|---|
| Rules | Authoring and inventory | create, edit, version, search, ownership, activation entry points |
| Rule Quality | Pre-execution quality control | rule validation, rule suggestions, future rule quality checks |
| Governance | Controlled state and policy workflows | approvals, lifecycle management, exceptions |
| Operations | Runtime execution and outcomes | scheduling, execution, result aggregation, monitoring |

For catalog drift specifically, the intended split is:

- `Governance` owns the summary and policy signal: approvals impact, counts of rules with drift, critical drift visibility, and governance-level escalation.
- `Rule Quality` owns the working surface: affected-rule inspection, field-level drift details, previous-versus-current comparisons, and revalidation actions.
- `Operations` remains out of the drift-review flow unless runtime monitoring later needs to surface downstream execution impact.

## Scope

In scope:

- [x] (DQ1-I-S-01) Promote Rule Validation to standard availability.
- [x] (DQ1-I-S-02) Keep Rule Validation out of the main Rule Management page as a full embedded workspace.
- [x] (DQ1-I-S-03) Add strong entry points from Rules into Rule Validation.
- [x] (DQ1-I-S-04) Define the forward-compatible navigation model for upcoming rule-related features.
- [x] (DQ1-I-S-05) Update product copy and documentation to remove preview positioning for Rule Validation.

Out of scope:

- [ ] (DQ1-I-OOS-01) Rebuild all rule-related pages in one release.
- [ ] (DQ1-I-OOS-02) Fully implement Rule Lifecycle Management, Rule Result Aggregation, or Rule Execution Monitoring as part of this plan.
- [ ] (DQ1-I-OOS-03) Merge operational monitoring into the Rule Validation screen.

## Product Decisions

- [x] (DQ1-I-D-01) Adopt Rule Quality as the canonical grouping for Rule Validation and future rule-assistance capabilities.
- [x] (DQ1-I-D-02) Keep Rules focused on authoring, rule inventory, versioning, and direct rule actions.
- [x] (DQ1-I-D-03) Treat Rule Validation as a workspace-level quality control surface, not as an inline-only authoring helper.
- [x] (DQ1-I-D-04) Keep Lifecycle Management aligned with Governance rather than Rule Quality.
- [x] (DQ1-I-D-05) Keep Execution, Scheduling, Result Aggregation, and Monitoring aligned with Operations rather than Rules.
- [x] (DQ1-I-D-06) Keep Rule Suggestions adjacent to Rule Validation because both help users improve rules before runtime.
- [x] (DQ1-I-D-07) Split catalog drift between Governance and Rule Quality: Governance shows drift summary and control impact, while Rule Quality hosts affected-rule review and revalidation.

## Implementation Phases

### Phase 1: Confirm Information Architecture

- [x] (DQ1-I-P1-01) Confirm the top-level label `Rule Quality` as the standard navigation name.
- [x] (DQ1-I-P1-02) Confirm Rule Validation as the first standard page inside Rule Quality.
- [x] (DQ1-I-P1-03) Confirm Rule Suggestions as the next Rule Quality capability when it graduates from preview.
- [x] (DQ1-I-P1-04) Confirm Rule Lifecycle Management belongs under Governance, not Rule Quality.
- [x] (DQ1-I-P1-05) Confirm Rule Result Aggregation and Rule Execution Monitoring belong under Operations.
- [x] (DQ1-I-P1-06) Document the target user journeys for authoring, quality review, governance review, and runtime monitoring.

### Phase 2: Promote Rule Validation Out of Preview

- [x] (DQ1-I-P2-01) Change Rule Validation lifecycle state from `preview` to `live` in the feature lifecycle configuration.
- [x] (DQ1-I-P2-02) Remove preview-only positioning and labels from Rule Validation UI copy.
- [x] (DQ1-I-P2-03) Stop requiring preview opt-in for users who already have Rule Validation access.
- [x] (DQ1-I-P2-04) Preserve scope and role checks so the feature remains permission-controlled.
- [x] (DQ1-I-P2-05) Keep unfinished features in preview instead of promoting the whole feature group at once.

### Phase 3: Restructure Navigation

- [x] (DQ1-I-P3-01) Add a dedicated `Rule Quality` navigation entry or navigation group.
- [x] (DQ1-I-P3-02) Do not use a dedicated `Preview Features` sidebar area; preview-stage capabilities should appear in their intended navigation area from the start.
- [x] (DQ1-I-P3-03) Avoid embedding the full Rule Validation workspace inside the main Rules page.
- [x] (DQ1-I-P3-04) Ensure collapsed-sidebar behavior still routes to a sensible Rule Quality default page.
- [x] (DQ1-I-P3-05) Keep the navigation model stable enough to absorb future standard features without another major rework.

### Phase 4: Add Cross-Entry Points From Rules

- [x] (DQ1-I-P4-01) Add a `Validate rule` action on individual rule rows or rule detail views.
- [x] (DQ1-I-P4-02) Add a `Validate selected` action for multi-select rule workflows.
- [x] (DQ1-I-P4-03) Show latest validation status or last validation timestamp in rule inventory where useful.
- [x] (DQ1-I-P4-04) Add a direct deep link from Rules to the Rule Validation page with preselected rule context when feasible.
- [x] (DQ1-I-P4-05) Keep rule authoring fast by sending users to Rule Validation only when they need the broader diagnostics and history workspace.

### Phase 5: Clarify Future Feature Placement

- [x] (DQ1-I-P5-01) Define Rule Quality as the home for Rule Validation and Rule Suggestions.
- [x] (DQ1-I-P5-02) Define Governance as the home for Rule Lifecycle Management, approvals, and exception workflows.
- [x] (DQ1-I-P5-03) Define Operations as the home for execution, schedules, result aggregation, and monitoring.
- [x] (DQ1-I-P5-04) Publish a simple feature map so users understand where each future capability will live.
- [x] (DQ1-I-P5-05) Ensure page names reflect user intent rather than internal implementation boundaries.
- [x] (DQ1-I-P5-06) Place catalog drift remediation under Rule Quality, while keeping governance-level drift summary in Governance.

### Phase 6: Update Documentation and Product Copy

- [x] (DQ1-I-P6-01) Update the Rule Validation user guide to remove preview language and describe the standard availability model.
- [x] (DQ1-I-P6-02) Update in-app help text, onboarding copy, and navigation labels to match the new structure.
- [x] (DQ1-I-P6-03) Add release-note language explaining why Rule Validation is separate from Rules.
- [x] (DQ1-I-P6-04) Document the distinction between Rules, Rule Quality, Governance, and Operations.
- [x] (DQ1-I-P6-05) Update screenshots, walkthroughs, and demo scripts if the navigation changes.

### Phase 7: Verify and Roll Out

- [x] (DQ1-I-P7-01) Validate that existing Rule Validation workflows still work for authorized users after promotion.
- [x] (DQ1-I-P7-02) Validate that Rule Validation history, batch execution, and CSV export remain unchanged functionally.
- [x] (DQ1-I-P7-03) Validate that telemetry still distinguishes Rules navigation from Rule Quality navigation.
- [x] (DQ1-I-P7-04) Validate that no preview-only gating accidentally hides the live Rule Validation page.
- [x] (DQ1-I-P7-05) Validate that unfinished preview features remain clearly separated from standard features.

## Acceptance Criteria

- [x] (DQ1-I-AC-01) Rule Validation is accessible as a standard feature without preview opt-in.
- [x] (DQ1-I-AC-02) The main Rules page remains focused on authoring and inventory rather than becoming a multi-tool workspace.
- [x] (DQ1-I-AC-03) Users can reach Rule Validation directly from navigation and from rule-level actions.
- [x] (DQ1-I-AC-04) The information architecture clearly separates Rule Quality, Governance, and Operations concerns.
- [x] (DQ1-I-AC-05) Future rule-related capabilities can be added without forcing everything into one oversized Rule Management page.
- [x] (DQ1-I-AC-06) Documentation and UI copy consistently describe Rule Validation as a standard capability.

## Suggested Delivery Order

- [x] (DQ1-I-DO-01) Finalize the information architecture and naming decision.
- [x] (DQ1-I-DO-02) Promote Rule Validation to live state and remove preview framing.
- [x] (DQ1-I-DO-03) Introduce the dedicated Rule Quality navigation surface.
- [x] (DQ1-I-DO-04) Add Rules-to-Validation entry points.
- [x] (DQ1-I-DO-05) Update documentation, release notes, and walkthroughs.
- [x] (DQ1-I-DO-06) Roll out remaining rule-related features into Rule Quality, Governance, or Operations based on the target model.