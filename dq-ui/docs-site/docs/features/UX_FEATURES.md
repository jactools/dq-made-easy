# User Experience Features

This backlog should stay anchored to the existing UI instead of turning into a generic "make the UX better" list. The product already has dashboard cards, scoped search/filter patterns, and some bulk-selection flows. The remaining work is to make those surfaces more consistent, more role-aware, and more explicit where backend capabilities already exist but are not surfaced well in the UI.

Scope guardrails:

- Build on the existing dashboard, rules, execution-monitoring, data-browser, and test-data-materialization surfaces instead of adding parallel navigation paths.
- Keep UX work metadata-first and policy-aligned. Summary views may expose counts, statuses, and delivery locations, but must not expose raw protected source data.
- Prefer consistent interaction patterns across screens over one-off bespoke controls.

- [x] #UX-1 Expand the existing dashboard into role-aware operational entry points
	- Current implementation base: the dashboard now exposes role-focused entry sections for rule authors, approvers, and workspace/operations users based on the user's currently selected role, not every role assigned in the workspace. The cards for failed validation runs, pending governance actions, profiling activity, and catalog drift are backed by existing platform APIs and navigate to existing owning workflows. Those cards hand off filter presets into the owning rules, approvals, and execution-monitoring screens so the destination opens in the relevant workflow state instead of as a generic landing view. It also shows a workspace-aware secondary summary strip so users can see which governance, monitoring, drift, and rule-authoring areas need attention without opening each owning screen first.
	- [x] `UX-1.1` Extend the current dashboard card model with tiles that point to concrete workflows already in the product, such as failed validation runs, pending governance actions, profiling activity, and catalog drift.
	- [x] `UX-1.2` Add workspace-aware secondary summaries so users can see what needs attention without opening rules, approvals, or monitoring pages one by one.
	- [x] `UX-1.3` Make dashboard cards consistently navigable to their owning screens and pre-applied filter states rather than acting as static counters.
	- [x] `UX-1.4` Distinguish role-focused entry points for rule authors, approvers, and workspace admins instead of showing every metric to every user.
	- [x] `UX-1.AC-01` A user can move from the landing dashboard to the relevant filtered workflow in one click.
	- [x] `UX-1.AC-02` New dashboard cards must reuse existing platform signals rather than introduce a second summary model.
	- Proof: `test-results/test-proof/ui/ux-1-dashboard-api-driven-navigation-2026-05-26.json` records the passing UI proof run and points to the generated command evidence bundle.

- [x] #UX-2 Unify filtering and search across list-heavy screens
	- [x] `UX-2.1` Standardize search behavior across rules, catalog/data-browser, reusable filters, and attribute-selection modals so tokenization, thresholding, and empty-state behavior feel consistent.
	- [x] `UX-2.2` Add richer composable filters where the UI already has list state, especially status, owner, workspace, attached asset, and last-updated style filters for rule and monitoring views.
	- [x] `UX-2.3` Persist or deep-link important filter state for high-frequency workflows so users do not lose context when navigating between dashboard, rules, and monitoring.
	- [x] `UX-2.4` Make filter scope explicit in the UI copy so users can tell whether they are filtering the current workspace, current page, or the broader catalog.
	- [x] `UX-2.AC-01` Users should not have to relearn search semantics between major screens.
	- [x] `UX-2.AC-02` The UI must clearly communicate when a search threshold, workspace scope, or server-backed filter limits visible results.
	- Proof: `test-results/test-proof/ui/ux-2-api-driven-filtering-search-2026-05-25.json` records the passing UI/API proof for shared tokenized search behavior, deep-linked Rules filters, server-backed reusable-filter search, and explicit scope/threshold copy.

- [x] #UX-3 Strengthen existing bulk-action flows instead of adding generic mass-editing
	- [x] `UX-3.1` Build on the existing rules bulk-selection toolbar with clearer eligibility states, mixed-selection messaging, and outcome feedback for approve, activate, and rule-validation actions.
	- [x] `UX-3.2` Reuse the select-all / clear-all interaction pattern already present in attribute assignment and similar selection-heavy modals.
	- [x] `UX-3.3` Add fail-closed validation and result summaries for partial-success scenarios so users can see which selected items were processed and which were rejected.
	- [x] `UX-3.4` Ensure bulk actions remain scoped to actions the backend already supports canonically; do not add broad client-side compatibility logic or silent fallback behavior.
	- [x] `UX-3.AC-01` Users can tell before submission which selected items are actionable and why others are blocked.
	- [x] `UX-3.AC-02` Bulk results report processed, skipped, and failed items explicitly rather than collapsing into a generic success message.
	- Proof: `test-results/test-proof/ui/ux-3-bulk-action-hardening-2026-05-26.json` records the passing UI proof for eligibility counts, fail-closed no-target handling, and explicit processed/skipped/failed summaries.

- [x] #UX-4 Surface the aggregate delivery summary for multi-target materialization requests in the UI
	- [x] `UX-4.1` Show the backend-provided aggregate delivery summary for test-data materialization requests, including target count, delivery count, total row count, output formats, and delivery locations.
	- [x] `UX-4.2` Update the ad-hoc execution and related monitoring views so multi-target materialization no longer looks like a single-output flow.
	- [x] `UX-4.3` Present per-target delivery outcomes alongside the aggregate summary when the request spans multiple data object versions.
	- [x] `UX-4.4` Keep the summary metadata-only and link users to the owning delivery/inventory surfaces rather than exposing protected dataset contents directly.
	- [x] `UX-4.AC-01` A multi-target materialization request shows an aggregate summary instead of only a single output URI.
	- [x] `UX-4.AC-02` Users can tell whether output was newly materialized or reused, and for how many targets.
	- Proof: `test-results/test-proof/ui/ux-4-materialization-monitoring-2026-05-26.json` records the passing UI proof for multi-target ad-hoc dispatch metadata and execution-monitoring delivery summaries.

Recommended sequencing:

1. `UX-4` first, because the backend already emits the aggregate delivery summary and the UI gap is well-defined.
2. `UX-3` next, because bulk actions already exist in the rules flow and need hardening more than invention.
3. `UX-2` after that, because search and filter behavior already exists across multiple screens but is inconsistent.
4. `UX-1` last, because dashboard expansion is valuable, but it should be informed by the navigation and workflow pain points clarified by the earlier items.
