# Frontend UI Portability and Theming Abstraction

Goal: decouple feature pages from vendor-specific components and tokens so the frontend can use app-owned primitives, semantic themes, and a controlled replacement path for the underlying UI library without page-by-page rewrites.

Current overlap assessment as of 2026-05-29:

- The app already supports user-facing theme selection such as light, dark, and auto mode.
- The frontend already has a shared semantic token baseline in [../dq-ui/src/themes.css](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/themes.css).
- Shared wrappers and reusable UI components already exist, but the feature surface still contains direct vendor assumptions.
- The missing scope is not a theme switcher or a new design-system picker for end users; the missing scope is one app-owned UI API above vendor components and one app-owned styling model above vendor tokens.
- This track is about codebase portability and controlled theming, not runtime user selection between multiple UI libraries.

## Phase 1: Define the App-Owned UI Surface

- Standardize app-owned primitives such as `AppButton`, `AppSelect`, `AppInput`, `AppTextarea`, `AppModal`, `AppBanner`, `AppTabs`, `AppTable`, and `AppIcon`.
- Move feature code toward app-owned naming so shared wrappers are treated as product primitives instead of vendor details.
- Define the allowed primitive surface for feature pages and document it as the canonical UI contract.

## Phase 2: Create One Vendor Adapter Boundary

- Define the one shared layer that is allowed to import vendor UI packages directly.
- Move direct vendor UI imports and raw vendor-shaped usage behind that boundary.
- Normalize shared props and behavior so feature pages do not depend on vendor-specific event shapes, disabled handling, loading semantics, or validation quirks.

## Phase 3: Move Styling to App Semantics

- Keep [../../dq-ui/src/themes.css](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/themes.css) as the canonical semantic-token source.
- Continue replacing vendor-shaped token usage in feature CSS with app-owned tokens for surfaces, borders, text, hover, selection, and status states.
- Remove page-local theme branches where shared semantic tokens should express the state instead.

## Phase 4: Enforce the Boundary

- Add a lightweight CI or grep-based guard against new direct vendor imports in feature code.
- Treat new vendor-specific feature-page usage as architecture debt rather than normal product work.
- Use review guidance that keeps feature pages dependent on repository-owned primitives instead of vendor contracts.

## Phase 5: Prove Portability With a Pilot

- Pick one non-critical page and migrate it fully onto app-owned primitives and app-owned tokens.
- Implement a small alternative primitive set behind the adapter boundary for a limited pilot.
- Verify that the page still works without feature-level redesign, proving that the portability work is concentrated in the adapter and token layers.

## Acceptance Criteria

- Feature pages consume app-owned primitives rather than direct vendor components.
- Vendor UI imports are limited to one shared adapter boundary.
- Theme styling is expressed primarily through app-owned semantic tokens rather than vendor-shaped tokens.
- Existing light, dark, and auto theming continues to work while the abstraction is introduced.
- At least one representative page can switch to an alternative primitive implementation with bounded adapter-level changes.

## Tracked Work Items (Current Status)

- [x] `UI-PORT-1` Theme and semantic-token foundation
- [x] `UI-PORT-2` App-owned primitive surface
- [x] `UI-PORT-3` Single vendor adapter boundary
- [x] `UI-PORT-4` Feature-page decoupling
- [x] `UI-PORT-5` Guardrails and pilot replacement
	- Add enforcement checks and prove the architecture by migrating one representative page through app-owned primitives.
- [x] `UI-PORT-6` Page decoupling

## UI-PORT-7 CSS Structure Consolidation Plan

Goal: reduce repeated page-local CSS by moving recurring layout, panel, stack, toolbar, label, badge, empty-state, and list-row patterns into app-owned primitives and a small shared styling layer while keeping feature-specific composition in feature CSS.

Baseline evidence as of 2026-05-29:

- `dq-ui/src` contains 73 source CSS files and roughly 30,662 CSS lines.
- The largest consolidation hotspots are `App.css`, `Suggestions.css`, `Approvals.css`, `DataBrowser.css`, `Reports.css`, `AccessRequestsDashboard.css`, `Settings.css`, `Documentation.css`, and `Rules.css`.
- Repeated declarations are concentrated in flex layouts, card surfaces, borders, radius values, semantic text colors, toolbar rows, label text, and chip/badge styling.
- Common blocks such as `display: flex; flex-direction: column; gap: 8px`, `gap: 12px`, and `gap: 16px` appear across many unrelated page stylesheets.
- Recent malformed CSS warnings in `DefinitionMappingsPage.css`, `Documentation.css`, and `DriftAlert.css` show that source-level CSS guardrails are needed before more consolidation work proceeds.

Implementation sequence:

- [x] `UI-PORT-7A` Add a source CSS syntax guard.
	- Parse every `dq-ui/src/**/*.css` file with PostCSS or the existing Vite CSS parser in a focused test or validation script.
	- Fail fast on malformed CSS instead of relying on production builds to surface minifier warnings.
	- Store curated proof under `test-results/test-proof/ui/` when the guard is validated through the repository test-evidence workflow.
	- Completed slice: [../../dq-ui/src/cssSyntaxGuard.test.ts](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/cssSyntaxGuard.test.ts) parses every source CSS file with PostCSS and reports all malformed files in one focused Vitest failure; [../../dq-ui/package.json](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/package.json) declares PostCSS as an explicit dev dependency for the guard.

- [x] `UI-PORT-7B` Define shared layout and pattern CSS.
	- Add a small shared styling layer for app-owned patterns such as page shell, page header, content region, panel, stack, toolbar, action row, metadata label, status chip, empty state, and list row.
	- Keep `themes.css` as the semantic-token source of truth and use tokens such as `--app-page-bg`, `--app-surface-primary`, `--app-border-subtle`, `--app-hover-bg`, and `--app-selected-bg`.
	- Prefer semantic pattern classes over broad one-off utility proliferation.
	- Completed slice: [../../dq-ui/src/styles/appPatterns.css](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/styles/appPatterns.css) defines shared page, panel, stack, toolbar, action-row, metadata, status-chip, empty-state, and list-row patterns on app-owned tokens; [../../dq-ui/src/styles/appPatterns.test.ts](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/styles/appPatterns.test.ts) guards the canonical selector set and root import order.

- [x] `UI-PORT-7C` Add missing primitive contracts where CSS alone is not enough.
	- Extend `dq-ui/src/components/app-primitives/` only for repeated UI concepts with behavior or accessibility semantics, such as `AppPageShell`, `AppPageHeader`, `AppPanel`, `AppStack`, `AppToolbar`, `AppBadge`, `AppEmptyState`, and `AppListRow`.
	- Export new primitives through the canonical `app-primitives` barrel.
	- Add primitive-surface guard coverage so feature code continues to import app-owned primitives through the approved surface.
	- Completed slice: [../../dq-ui/src/components/app-primitives/AppPageShell.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/app-primitives/AppPageShell.tsx), [../../dq-ui/src/components/app-primitives/AppPageHeader.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/app-primitives/AppPageHeader.tsx), [../../dq-ui/src/components/app-primitives/AppPanel.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/app-primitives/AppPanel.tsx), [../../dq-ui/src/components/app-primitives/AppStack.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/app-primitives/AppStack.tsx), [../../dq-ui/src/components/app-primitives/AppToolbar.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/app-primitives/AppToolbar.tsx), [../../dq-ui/src/components/app-primitives/AppBadge.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/app-primitives/AppBadge.tsx), [../../dq-ui/src/components/app-primitives/AppEmptyState.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/app-primitives/AppEmptyState.tsx), and [../../dq-ui/src/components/app-primitives/AppListRow.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/app-primitives/AppListRow.tsx) add the shared page/surface primitive contracts; [../../dq-ui/src/components/app-primitives/appSharedSurface.test.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/app-primitives/appSharedSurface.test.tsx) and [../../dq-ui/src/components/app-primitives/appPrimitiveSurface.test.ts](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/app-primitives/appPrimitiveSurface.test.ts) guard the new exports and semantics.

- [x] `UI-PORT-7D` Pilot the consolidation on one contained page.
	- Start with `DefinitionMappingsPage` or `Reports` because both expose repeated panel/header/toolbar/list patterns without requiring a broad app-shell rewrite.
	- Replace local page shell, panel, stack, toolbar, badge, and empty-state CSS with shared patterns or primitives.
	- Keep page-specific selectors only for feature-specific layout, data visualization, or workflow-specific composition.
	- Completed slice: [../../dq-ui/src/components/DefinitionMappingsPage.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/DefinitionMappingsPage.tsx) now uses [../../dq-ui/src/components/app-primitives/AppPageShell.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/app-primitives/AppPageShell.tsx), [../../dq-ui/src/components/app-primitives/AppPageHeader.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/app-primitives/AppPageHeader.tsx), [../../dq-ui/src/components/app-primitives/AppPanel.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/app-primitives/AppPanel.tsx), [../../dq-ui/src/components/app-primitives/AppStack.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/app-primitives/AppStack.tsx), [../../dq-ui/src/components/app-primitives/AppToolbar.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/app-primitives/AppToolbar.tsx), [../../dq-ui/src/components/app-primitives/AppBadge.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/app-primitives/AppBadge.tsx), and [../../dq-ui/src/components/app-primitives/AppEmptyState.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/app-primitives/AppEmptyState.tsx) for the page shell, hero, tab strip, section panels, status chips, and major empty states; [../../dq-ui/src/components/DefinitionMappingsNavigation.test.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/DefinitionMappingsNavigation.test.tsx) still passes the page navigation flow with the new structure.

- [x] `UI-PORT-7E` Consolidate settings and administration shells.
	- Move repeated `settings-*` and `admin-*` structural classes toward shared page, panel, form, action-row, and list-row patterns.
	- Update `Settings`, `RoleManagement`, `UserManagement`, `ApplicationSettings`, `GxSuitesAdmin`, `GxRunPlansAdmin`, and `ValidationPlans` in small slices.
	- Avoid adding compatibility aliases for old class names in new code; update repo-owned callers to the canonical pattern names.
	- Completed slice: [../../dq-ui/src/components/AdminPageHeader.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/AdminPageHeader.tsx) now delegates to [../../dq-ui/src/components/app-primitives/AppPageHeader.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/app-primitives/AppPageHeader.tsx), [../../dq-ui/src/components/Settings.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/Settings.tsx) now uses [../../dq-ui/src/components/app-primitives/AppPageShell.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/app-primitives/AppPageShell.tsx) and the shared header primitive, and [../../dq-ui/src/components/RoleManagement.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/RoleManagement.tsx), [../../dq-ui/src/components/ApplicationSettings.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/ApplicationSettings.tsx), [../../dq-ui/src/components/GxSuitesAdmin.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/GxSuitesAdmin.tsx), [../../dq-ui/src/components/GxRunPlansAdmin.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/GxRunPlansAdmin.tsx), [../../dq-ui/src/components/ValidationPlans.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/ValidationPlans.tsx), and [../../dq-ui/src/components/UserManagement.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/UserManagement.tsx) now render within the shared page shell.

- [x] `UI-PORT-7F` Apply the shared patterns to the largest operational views.
	- Prioritize `Suggestions`, `Approvals`, `DataBrowser`, `Reports`, `AccessRequestsDashboard`, `Rules`, and `features/features.css` after the pilot proves the shared pattern API.
	- Remove repeated local definitions only when the shared pattern preserves the page behavior and visual hierarchy.
	- Keep feature-specific density, grid, visualization, and workflow states local when they are not repeated across pages.
	- Completed slice: [../../dq-ui/src/components/Reports.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/Reports.tsx) now uses [../../dq-ui/src/components/app-primitives/AppPageShell.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/app-primitives/AppPageShell.tsx) and [../../dq-ui/src/components/app-primitives/AppPageHeader.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/app-primitives/AppPageHeader.tsx) for the Operations shell and tabbed hero, with a focused Reports shell test in [../../dq-ui/src/components/Reports.test.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/Reports.test.tsx) and evidence recorded in the repository test-proof artifacts.
	- Completed slice: [../../dq-ui/src/components/Approvals.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/Approvals.tsx) now uses [../../dq-ui/src/components/app-primitives/AppPageShell.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/app-primitives/AppPageShell.tsx) and [../../dq-ui/src/components/app-primitives/AppPageHeader.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/app-primitives/AppPageHeader.tsx) for the governance shell and view tabs, with a focused Approvals shell test in [../../dq-ui/src/components/Approvals.test.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/Approvals.test.tsx) and evidence recorded in the repository test-proof artifacts.
	- Completed slice: [../../dq-ui/src/components/Suggestions.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/Suggestions.tsx) now uses [../../dq-ui/src/components/app-primitives/AppPageShell.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/app-primitives/AppPageShell.tsx) and [../../dq-ui/src/components/app-primitives/AppPageHeader.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/app-primitives/AppPageHeader.tsx) for the suggestions shell, with a focused Suggestions shell test in [../../dq-ui/src/components/Suggestions.test.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/Suggestions.test.tsx) and evidence recorded in the repository test-proof artifacts.
	- Completed slice: [../../dq-ui/src/components/DataBrowser.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/DataBrowser.tsx) now uses [../../dq-ui/src/components/app-primitives/AppPageShell.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/app-primitives/AppPageShell.tsx) and [../../dq-ui/src/components/app-primitives/AppPageHeader.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/app-primitives/AppPageHeader.tsx) for the data browser shell and workspace filter hero, with a focused DataBrowser shell test in [../../dq-ui/src/components/DataBrowser.test.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/DataBrowser.test.tsx) and evidence recorded in the repository test-proof artifacts.
	- Completed slice: [../../dq-ui/src/components/rules/RulesHeader.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/rules/RulesHeader.tsx) now uses [../../dq-ui/src/components/app-primitives/AppPageHeader.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/app-primitives/AppPageHeader.tsx) for the rules header chrome, and [../../dq-ui/src/components/Rules.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/Rules.tsx) now renders inside [../../dq-ui/src/components/app-primitives/AppPageShell.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/app-primitives/AppPageShell.tsx), with [../../dq-ui/src/components/rules/RulesHeader.test.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/rules/RulesHeader.test.tsx) still covering the scope selector and filter toggle behavior and evidence recorded in the repository test-proof artifacts.
	- Completed slice: [../../dq-ui/src/components/AccessRequestsDashboard.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/AccessRequestsDashboard.tsx) now uses [../../dq-ui/src/components/app-primitives/AppPageShell.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/app-primitives/AppPageShell.tsx) and [../../dq-ui/src/components/app-primitives/AppPageHeader.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/app-primitives/AppPageHeader.tsx) for both access-request and governance overview shells, with [../../dq-ui/src/components/AccessRequestsDashboard.test.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/AccessRequestsDashboard.test.tsx) still covering the request and review flows and evidence recorded in the repository test-proof artifacts.
	- Completed slice: feature-folder operational screens now use [../../dq-ui/src/components/app-primitives/AppPageShell.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/app-primitives/AppPageShell.tsx) and [../../dq-ui/src/components/app-primitives/AppPageHeader.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/app-primitives/AppPageHeader.tsx) for the shared feature chrome in [../../dq-ui/src/components/features/RuleValidation.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/features/RuleValidation.tsx), [../../dq-ui/src/components/features/RuleExecutionMonitoring.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/features/RuleExecutionMonitoring.tsx), [../../dq-ui/src/components/features/RuleResultAggregation.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/features/RuleResultAggregation.tsx), [../../dq-ui/src/components/features/RuleSuggestions.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/features/RuleSuggestions.tsx), and [../../dq-ui/src/components/features/RuleLifecycleManagement.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/features/RuleLifecycleManagement.tsx), with shared feature header styling aligned in [../../dq-ui/src/components/features/features.css](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/features/features.css) and evidence recorded in the repository test-proof artifacts.

- [x] `UI-PORT-7G` Add duplication regression reporting.
	- Added `dq-ui/src/styles/cssDuplicationReport.ts` to scan source CSS, count repeated declaration blocks above a threshold, and format a review report.
	- Added `dq-ui/src/styles/cssDuplicationReport.test.ts` to prove the grouping logic on synthetic CSS and print the report for the real `dq-ui/src` tree.
	- Recorded the curated proof in the repository test-proof artifacts.
	- Marked UI-PORT-7G complete in the canonical roadmap and docs-site mirror.

- [x] `UI-PORT-7H` Apply the shared patterns to the remaining views.
	- Completed slice: [../../dq-ui/src/components/TemplateLibrary.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/TemplateLibrary.tsx) now uses [../../dq-ui/src/components/app-primitives/AppPageShell.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/app-primitives/AppPageShell.tsx), [../../dq-ui/src/components/app-primitives/AppPageHeader.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/app-primitives/AppPageHeader.tsx), [../../dq-ui/src/components/app-primitives/AppPanel.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/app-primitives/AppPanel.tsx), and [../../dq-ui/src/components/app-primitives/AppEmptyState.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/app-primitives/AppEmptyState.tsx) for the template library shell, filter rail, empty state, preview card, and footer, with [../../dq-ui/src/components/TemplateLibrary.test.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/TemplateLibrary.test.tsx) and evidence recorded in the repository test-proof artifacts.
	- Completed slice: [../../dq-ui/src/components/VersionInfoModal.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/VersionInfoModal.tsx) now uses [../../dq-ui/src/components/app-primitives/AppModal.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/app-primitives/AppModal.tsx), [../../dq-ui/src/components/app-primitives/AppBanner.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/app-primitives/AppBanner.tsx), [../../dq-ui/src/components/app-primitives/AppPanel.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/app-primitives/AppPanel.tsx), and [../../dq-ui/src/components/app-primitives/AppStack.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/app-primitives/AppStack.tsx) for the loading state, error state, and version sections, with [../../dq-ui/src/components/VersionInfoModal.test.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/VersionInfoModal.test.tsx) and evidence recorded in the repository test-proof artifacts.
	- Completed slice: [../../dq-ui/src/components/JoinConditionsModal.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/JoinConditionsModal.tsx) now uses [../../dq-ui/src/components/app-primitives/AppModal.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/app-primitives/AppModal.tsx), [../../dq-ui/src/components/app-primitives/AppPanel.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/app-primitives/AppPanel.tsx), [../../dq-ui/src/components/app-primitives/AppStack.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/app-primitives/AppStack.tsx), and [../../dq-ui/src/components/app-primitives/AppBanner.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/app-primitives/AppBanner.tsx) for the join editor shell, join-definition cards, preview card, and callout surfaces, with [../../dq-ui/src/components/JoinConditionsModal.test.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/JoinConditionsModal.test.tsx) and evidence recorded in the repository test-proof artifacts.
	- Completed slice: [../../dq-ui/src/components/ValidationDiagnosticsModal.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/ValidationDiagnosticsModal.tsx) now uses [../../dq-ui/src/components/app-primitives/AppModal.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/app-primitives/AppModal.tsx), [../../dq-ui/src/components/app-primitives/AppBanner.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/app-primitives/AppBanner.tsx), [../../dq-ui/src/components/app-primitives/AppPanel.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/app-primitives/AppPanel.tsx), and [../../dq-ui/src/components/app-primitives/AppStack.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/app-primitives/AppStack.tsx) for the validation status, compiled expression, compiler metadata, and diagnostics sections, with [../../dq-ui/src/components/ValidationDiagnosticsModal.test.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/ValidationDiagnosticsModal.test.tsx) and evidence recorded in the repository test-proof artifacts.
	- Completed slice: [../../dq-ui/src/components/AuthModal.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/AuthModal.tsx) now uses [../../dq-ui/src/components/app-primitives/AppModal.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/app-primitives/AppModal.tsx) and [../../dq-ui/src/components/app-primitives/AppButton.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/app-primitives/AppButton.tsx) for the login selector, admin form, workspace selector, and logout actions, with [../../dq-ui/src/components/AuthModal.test.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/AuthModal.test.tsx) and evidence recorded in the repository test-proof artifacts.
	- Completed slice: [../../dq-ui/src/components/RuleDetailsModal.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/RuleDetailsModal.tsx) now uses [../../dq-ui/src/components/app-primitives/AppModal.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/app-primitives/AppModal.tsx) and [../../dq-ui/src/components/app-primitives/AppButton.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/app-primitives/AppButton.tsx) for the details shell and footer actions, with [../../dq-ui/src/components/RuleDetailsModal.test.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/RuleDetailsModal.test.tsx) and evidence recorded in the repository test-proof artifacts.
	- Completed slice: [../../dq-ui/src/components/TestRuleModal.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/TestRuleModal.tsx) now uses [../../dq-ui/src/components/app-primitives/AppModal.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/app-primitives/AppModal.tsx) and [../../dq-ui/src/components/app-primitives/AppButton.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/app-primitives/AppButton.tsx) for the test configuration and result footer actions, with [../../dq-ui/src/components/TestRuleModal.contract.test.ts](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/TestRuleModal.contract.test.ts) and evidence recorded in the repository test-proof artifacts.
	- Completed slice: [../../dq-ui/src/components/GxSuiteScopePickerModal.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/GxSuiteScopePickerModal.tsx) now uses [../../dq-ui/src/components/app-primitives/AppModal.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/app-primitives/AppModal.tsx), [../../dq-ui/src/components/app-primitives/AppButton.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/app-primitives/AppButton.tsx), and [../../dq-ui/src/components/app-primitives/AppStack.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/app-primitives/AppStack.tsx) for the scope picker shell and footer actions, with [../../dq-ui/src/components/GxSuiteScopePickerModal.test.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/GxSuiteScopePickerModal.test.tsx) and evidence recorded in the repository test-proof artifacts.
	- Completed slice: [../../dq-ui/src/components/TemplateAttributeCatalogPickerModal.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/TemplateAttributeCatalogPickerModal.tsx) now uses [../../dq-ui/src/components/app-primitives/AppModal.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/app-primitives/AppModal.tsx), [../../dq-ui/src/components/app-primitives/AppButton.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/app-primitives/AppButton.tsx), and [../../dq-ui/src/components/app-primitives/AppStack.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/app-primitives/AppStack.tsx) for the catalog picker shell and footer actions, with [../../dq-ui/src/components/TemplateAttributeCatalogPickerModal.test.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/TemplateAttributeCatalogPickerModal.test.tsx) and evidence recorded in the repository test-proof artifacts.
	- Completed slice: [../../dq-ui/src/components/Suggestions.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/Suggestions.tsx) now uses [../../dq-ui/src/components/app-primitives/AppPageShell.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/app-primitives/AppPageShell.tsx), [../../dq-ui/src/components/app-primitives/AppPageHeader.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/app-primitives/AppPageHeader.tsx), [../../dq-ui/src/components/app-primitives/AppButton.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/app-primitives/AppButton.tsx), [../../dq-ui/src/components/app-primitives/AppSelect.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/app-primitives/AppSelect.tsx), and [../../dq-ui/src/components/app-primitives/AppIcon.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/app-primitives/AppIcon.tsx) for the assistant shell, profiling controls, and suggestion actions, with [../../dq-ui/src/components/Suggestions.test.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/Suggestions.test.tsx) and evidence recorded in the repository test-proof artifacts.
	- Completed slice: [../../dq-ui/src/components/IconGallery.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/IconGallery.tsx), [../../dq-ui/src/components/HierarchyTree.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/HierarchyTree.tsx), and [../../dq-ui/src/components/NotificationCenter.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/NotificationCenter.tsx) now use app-owned page, input, button, and icon primitives for the remaining helper-view shell and action wiring, with [../../dq-ui/src/components/IconGallery.contract.test.ts](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/IconGallery.contract.test.ts), [../../dq-ui/src/components/HierarchyTree.contract.test.ts](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/HierarchyTree.contract.test.ts), [../../dq-ui/src/components/NotificationCenter.contract.test.ts](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/NotificationCenter.contract.test.ts), and evidence recorded in the repository test-proof artifacts.

Acceptance criteria:

- Source CSS syntax is validated by an automated guard.
- Shared layout and surface patterns exist above page stylesheets and below semantic tokens.
- New shared primitives are exported through `app-primitives` and covered by primitive-surface tests when they are introduced.
- The pilot page removes duplicated page-local layout/card/toolbar/chip CSS without visual or behavioral regression.
- Settings and administration pages stop relying on broad page-local structural classes as their shared layout contract.
- Largest operational views reduce repeated panel, stack, toolbar, badge, empty-state, and list-row CSS while preserving page-specific styling where it is genuinely unique.
- The Vite build remains free of CSS minifier warnings, and UI test evidence is captured for each migration slice.

Non-goals:

- Do not rewrite the full styling system in one pass.
- Do not replace semantic tokens with generic utility classes.
- Do not move feature-specific workflow layout into global CSS unless at least two independent pages use the same pattern.
- Do not introduce legacy class aliases or compatibility layers for repo-owned callers.

## Page Migration Sequence

WS7-A06 proved the replacement path on a pilot page. The remaining page migration should happen in this order so the highest-traffic shared surfaces move first and the smaller dialogs can follow the stabilized primitive contract.

1. Shared browser and settings shells:
	- [dq-ui/src/components/DataBrowser.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/DataBrowser.tsx)
	- [dq-ui/src/components/Settings.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/Settings.tsx)
	- [dq-ui/src/components/TemplateLibrary.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/TemplateLibrary.tsx)
	- [dq-ui/src/components/Templates.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/Templates.tsx)

2. High-use operational and stewardship views:
	- [dq-ui/src/components/Reports.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/Reports.tsx)
	- [dq-ui/src/components/HealthScorecards.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/HealthScorecards.tsx)
	- [dq-ui/src/components/RuleVersionDetails.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/RuleVersionDetails.tsx)
	- [dq-ui/src/components/VersionInfoModal.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/VersionInfoModal.tsx)

3. Shared selection and catalog dialogs:
	- [dq-ui/src/components/GxSuiteScopePickerModal.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/GxSuiteScopePickerModal.tsx)
	- [dq-ui/src/components/TemplateAttributeCatalogPickerModal.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/TemplateAttributeCatalogPickerModal.tsx)
	- [dq-ui/src/components/JoinConditionsModal.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/JoinConditionsModal.tsx)
	- [dq-ui/src/components/ReusableFiltersModal.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/ReusableFiltersModal.tsx)
	- [dq-ui/src/components/ReusableJoinsModal.tsx](https://github.com/jactools/dq-rulebuilder/blob/main/dq-ui/src/components/ReusableJoinsModal.tsx)

The sequencing above assumes the current app-owned primitives remain the canonical contract and that raw vendor-specific icon strings stay behind the existing adapter or inventory seams.

## Already Covered Elsewhere

- User-facing theme selection and persistence.
- Existing shared wrappers and reusable UI helpers.

## Remaining Platform Gap

The missing scope is not basic theming capability. The missing scope is a stable frontend architecture where product screens depend on repository-owned primitives and semantic tokens instead of directly depending on vendor contracts and vendor-shaped styling.