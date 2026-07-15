# DQ-10 Natural-Language Rule Drafting Rollout and Operator Notes

This note records the rollout and operator expectations for the DQ-10 natural-language rule drafting preview.

## Audience

- Operators running the dq-rulebuilder stack
- Maintainers verifying the preview flow in local or staged environments

## What Is Enabled

- A steward-facing preview flow inside the existing Suggestions area
- Plain-language requests that infer a constrained typed check
- Ranked candidate attributes with parent-path context and match reasons
- Explicit steward confirmation before a draft suggestion is created
- A fail-fast preview contract for blank prompts, missing metadata, unsupported checks, and unauthorized scopes

## Supported Check Subset

The preview flow only supports:

- `UNIQUENESS`
- `PRESENT`
- `REGEX`
- `RANGE`
- `ALLOWLIST`
- `FRESHNESS`

Requests outside that subset must fail fast with an explicit error response.

## Entry Points

- UI: the `NaturalLanguageRuleDraftPreview` component inside the Suggestions page
- Preview API: `POST /api/data-catalog/v1/suggestions/natural-language-rule-previews`
- Draft creation API: `POST /api/data-catalog/v1/suggestions/natural-language-rule-previews/create-suggestion`

The preview always targets the current workspace for the resulting draft suggestion, even when the candidate search scope is broader.

## Model Shortlist

Use a small local instruction-tuned model for dq-llm tryouts:

- `Llama 3.1 8B Instruct` is the default recommendation
- `Qwen2.5 7B Instruct` is the alternate benchmark
- `Qwen2.5 14B Instruct` is only appropriate when the latency tradeoff is acceptable

Avoid larger models unless the operator has explicitly accepted the memory and latency cost.

## Rollout Guidance

1. Confirm the API and UI images were rebuilt with the release line that includes the DQ-10 preview changes.
2. Verify the `dq-llm` container is healthy before enabling the LLM analysis provider in the UI.
3. Confirm Redis is available if the LLM path is expected to queue draft requests.
4. Ensure the authenticated user has access to the current workspace before testing cross-workspace search behavior.
5. Keep the preview-only flow visible in Suggestions, and do not treat it as a direct rule activation path.

## Validation Expectations

Use the following checks to verify the rollout:

```bash
cd dq-ui
npm test -- --run src/components/NaturalLanguageRuleDraft.test.tsx
```

```bash
cd dq-api/fastapi
/Users/jacbeekers/gitrepos/dq-rulebuilder/venv/bin/python -m pytest tests/application/services/test_natural_language_rule_drafting.py tests/api/test_suggestions_endpoints.py -q --no-cov
```

Expected outcomes:

- blank prompts are rejected before preview generation runs
- missing metadata fails fast with an explicit preview error
- unsupported scopes or unauthorized cross-workspace requests return explicit 4xx responses
- draft creation rejects selected attributes that do not belong to the same data object version
- the UI shows preview failures instead of silently falling back

## Operator Notes

- Use the current workspace as the canonical destination for the saved suggestion.
- Treat `all_across_workspaces` as an authorization-sensitive search mode, not as a guaranteed default.
- If `dq-llm` or Redis is unavailable, the LLM-backed path must fail fast rather than substituting a local fallback.
- The preview feature is intentionally reviewable and should remain preview-only until steward confirmation.

## Troubleshooting

- If the preview button returns a blank prompt error, confirm the steward entered a non-empty prompt.
- If the preview returns a missing-metadata error, verify the catalog repository and its backing data are available.
- If the LLM path fails, check `dq-llm` health, Redis reachability, and the preview request status endpoint.
- If cross-workspace options do not appear, confirm the user has access to more than one workspace and that the active session includes that scope.

## References

- [DQ-10 current-state snapshot](../features/current/DQ-10_NATURAL_LANGUAGE_RULE_DRAFTING_PREVIEW.md)
- [DQ-10 implementation details](../implementation-details/DQ_10_NATURAL_LANGUAGE_RULE_DRAFTING_IMPLEMENTATION_DETAILS.md)
- [Technical documentation index](./README.md)