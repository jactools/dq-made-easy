# DQ-10 Natural-Language Rule Drafting Preview

Status: Done

Goal: allow data stewards to describe a desired check in plain language, review ranked candidate attributes with parent context, and create a typed rule draft only after explicit confirmation.

Current status: the preview flow is implemented inside the existing Suggestions area, supports the constrained typed-check subset, resolves authorization-aware search scopes, persists confirmed drafts through the Suggestions lifecycle, and fails fast on ambiguity or missing metadata.

## Scope

### In scope

- preview-only UI flow inside Suggestions
- plain-language requests for UNIQUENESS, PRESENT, REGEX, RANGE, ALLOWLIST, and FRESHNESS
- ranked candidate attributes with parent-path context and match reasons
- authorization-aware search scopes and current-workspace draft creation
- explicit steward confirmation before save
- fail-fast handling when inference, metadata, or authorization checks are unavailable

### Out of scope

- direct activation of rules from natural language without steward confirmation
- free-form chatbot conversations or open-ended assistant UI
- support for unsupported check types
- silent fallback guessing when inference is ambiguous or unavailable

## Tracked Work Items

- [x] `DQ10-IMP-01` Define the canonical preview request and response contract
- [x] `DQ10-IMP-02` Implement the preview inference service
- [x] `DQ10-IMP-03` Implement candidate attribute retrieval and ranking
- [x] `DQ10-IMP-04` Enforce authorization-aware search scope resolution
- [x] `DQ10-IMP-05` Build the draft generation bridge into Suggestions
- [x] `DQ10-IMP-06` Add the preview UI inside the existing Suggestions area
- [x] `DQ10-IMP-07` Add fail-fast validation for preview inputs
- [x] `DQ10-IMP-08` Add API and UI tests for the preview flow
- [x] `DQ10-IMP-09` Add rollout and operator notes

## Acceptance Criteria

- A steward can enter a short plain-language request and receive a structured preview.
- The preview returns ranked candidate attributes with parent context and reasons.
- The steward must explicitly confirm the final attributes before a draft is created.
- The saved draft enters the existing Suggestions lifecycle in the current workspace.
- Unsupported prompts, ambiguous matches, and missing dependencies fail fast.

## Related References

- [DQ feature rollup](/docs/features/DQ_FEATURES/)
- [DQ-10 implementation details](/docs/implementation-details/DQ_10_NATURAL_LANGUAGE_RULE_DRAFTING_IMPLEMENTATION_DETAILS/)
- [DQ-10 rollout and operator notes](/docs/technical/DQ_10_NATURAL_LANGUAGE_RULE_DRAFTING_ROLLOUT_AND_OPERATOR_NOTES/)