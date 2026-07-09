# DQ-10 Natural-Language Rule Drafting - Implementation Details

This note records the DQ-10 implementation backlog and completion status.

For the current-state snapshot, see [DQ-10 Natural-Language Rule Drafting Preview](../features/current/DQ-10_NATURAL_LANGUAGE_RULE_DRAFTING_PREVIEW.md).

## Problem Statement

The platform has typed rule checks and a Suggestions lifecycle, but it does not yet have a steward-facing plain-language entry point that can preview likely attribute matches, surface parent context, and create a typed draft only after explicit confirmation.

What is needed is a preview flow that:

- accepts a short natural-language request from the current workspace
- infers a constrained typed check
- ranks candidate attributes with parent context and match reasons
- requires explicit steward confirmation before creating a draft
- creates a typed rule draft in the existing Suggestions lifecycle
- fails fast when inference, metadata, or authorization checks are unavailable

## Proposed Model Split

- The preview request is the user intent boundary.
- The candidate ranking result is the preview artifact.
- The steward-confirmed selection is the draft boundary.
- The Suggestions item is the durable workflow record.
- The generated DQ DSL 2.0.0 draft remains the canonical rule shape.

## Current Scope

The first implementation slice should stay deliberately narrow:

- support only the constrained typed checks already listed in the feature plan
- reuse the existing Suggestions area rather than creating a separate workflow
- keep the UI simple and form-based rather than chatbot-shaped
- require explicit confirmation for all selected attributes
- preserve the current workspace as the draft destination
- fail closed on ambiguity instead of guessing

## Numbered Backlog

1. [x] (DQ10-IMP-01) Define the canonical preview request and response contract.
   - Accept a plain-language prompt, search scope, and optional current-context anchor.
   - Return the inferred check type, extracted terms, candidate attributes, and confidence data.
   - Keep the response shape stable and snake_case at the API boundary.

   Complete: the preview route now uses dedicated request and response schema views in `app/api/v1/schemas/natural_language_rule_drafting_view.py`, and the API returns the typed response model instead of an ad hoc dict.

2. [x] (DQ10-IMP-02) Implement the preview inference service.
   - Map steward prompts to the constrained typed check set.
   - Fail fast when the prompt cannot be classified into the supported set.
   - Surface an explicit non-success outcome when inference is unavailable or ambiguous.

   Complete: the preview inference and target-term resolution now live in `app/application/services/natural_language_rule_drafting.py`, and the suggestions endpoints delegate to that service.

3. [x] (DQ10-IMP-03) Implement candidate attribute retrieval and ranking.
   - Search attributes within the selected scope.
   - Include parent-path context, workspace id, and match reasons for each candidate.
   - Rank candidates deterministically so the preview is reviewable.

   Complete: candidate retrieval and ranking now flow through `build_ranked_preview_candidate_attributes()` in `app/application/services/natural_language_rule_drafting.py`, with direct service tests covering scope filtering and deterministic ordering.

4. [x] (DQ10-IMP-04) Enforce authorization-aware search scope resolution.
   - Support current, workspace, and cross-workspace search modes only where the user is allowed to use them.
   - Prevent broader search scopes from being shown when the user lacks access.
   - Keep the resulting draft anchored to the current workspace.

   Complete: `resolve_authorized_preview_search_scope()` now enforces workspace membership and cross-workspace authorization before the preview flow resolves candidates, and the preview draft remains anchored to the current workspace.

5. [x] (DQ10-IMP-05) Build the draft generation bridge into Suggestions.
   - Convert the steward-confirmed preview into a typed rule draft.
   - Persist the draft through the existing Suggestions lifecycle.
   - Preserve selected attributes and the parent context snapshot on the saved item.

   Complete: `build_natural_language_rule_draft_suggestion_payload()` now converts a validated preview into the persisted Suggestions payload, including `selected_attributes`, `selected_attribute_ids`, and `parent_context_snapshot`.

6. [x] (DQ10-IMP-06) Add the preview UI inside the existing Suggestions area.
   - Provide a simple describe/preview/confirm/save flow.
   - Render ranked candidates with checkboxes, badges, and summary state.
   - Keep the layout aligned with the existing app-owned UI primitives.

   Complete: the reusable `NaturalLanguageRuleDraftPreview` component now renders directly inside the Suggestions page, so the draft flow sits alongside the existing suggestions and profiling workflow.

7. [x] (DQ10-IMP-07) Add fail-fast validation for preview inputs.
   - Reject blank prompts, unsupported check types, and missing search anchors.
   - Reject invalid scope selections and ambiguous multi-object selections.
   - Return explicit errors for missing metadata dependencies.

   Complete: preview requests now reject blank prompts and missing workspaces up front, preview generation fails fast when catalog metadata is unavailable, and draft creation rejects selections that span multiple data object versions.

8. [x] (DQ10-IMP-08) Add API and UI tests for the preview flow.
   - Verify contract shape, ranking behavior, and confirmation requirements.
   - Verify scope restrictions and current-workspace draft creation.
   - Verify ambiguity and dependency failures are surfaced explicitly.

   Complete: focused FastAPI tests cover the preview contract, ranking behavior, confirmation requirements, scope restrictions, missing metadata, blank prompts, and cross-object draft rejection, while the UI component tests cover the steward-facing blank-prompt guard, preview failure messaging, and cross-workspace scope visibility.

9. [x] (DQ10-IMP-09) Add rollout and operator notes.
   - Document the supported check subset and the preview-only behavior.
   - Document the model shortlist and the fail-fast behavior.
   - Record the entry point and validation expectations for maintainers.

   Complete: operator-facing rollout guidance now lives in [docs/technical/DQ_10_NATURAL_LANGUAGE_RULE_DRAFTING_ROLLOUT_AND_OPERATOR_NOTES.md](../technical/DQ_10_NATURAL_LANGUAGE_RULE_DRAFTING_ROLLOUT_AND_OPERATOR_NOTES.md), covering the supported check subset, model shortlist, fail-fast behavior, rollout steps, validation commands, and troubleshooting notes.

## Acceptance Criteria

- A steward can enter a short plain-language request and receive a structured preview.
- The preview returns ranked candidate attributes with parent context and reasons.
- The steward must explicitly confirm the final attributes before a draft is created.
- The saved draft enters the existing Suggestions lifecycle in the current workspace.
- Unsupported prompts, ambiguous matches, and missing dependencies fail fast.

## Related References

- [DQ-10 current-state snapshot](../features/current/DQ-10_NATURAL_LANGUAGE_RULE_DRAFTING_PREVIEW.md)
- [DQ-10 in the feature catalog](../features/DQ_FEATURES.md)
- [Suggestions workflow](../features/DQ_FEATURES.md)
