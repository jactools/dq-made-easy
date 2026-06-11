# Agent Workflow Examples and Templates

> **Feature:** DOC-1.11 Agent workflow examples and templates
> **Audience:** analysts, data stewards, and developers using the dq-llm agent harness
> **Use it with:** Suggestions, Connector Workbench, and Data Asset Studio

## Purpose

This guide gives you ready-to-copy agent prompts and practical workflow patterns for the dq-llm assistant surfaces already available in the UI. It is meant to reduce time-to-first-answer and make the assistant easier to reuse across connector setup, rule drafting, and metadata review.

## Common workflow patterns

### 1. Connector onboarding

Use this when you need fast, reviewable guidance before validating, discovering, or syncing a connector.

Example prompt:

> Help me configure this connector for the current workspace. Explain the required fields, recommend safe secret handling, and outline the validation steps I should run before a discovery or sync operation.

Best when:
- you are setting up a new provider
- you want a quick checklist before running connector actions
- you need a non-destructive explanation of the current configuration

### 2. Rule drafting

Use this when you want to turn plain language into a precise rule suggestion.

Example prompt:

> Turn this natural-language requirement into a testable data quality rule. Suggest candidate attributes, explain the expected condition, and provide a safe validation plan before I save a draft suggestion.

Best when:
- you are authoring a new quality rule from a business statement
- you want a structured suggestion before the rule is persisted
- you need to validate attribute match quality first

### 3. Metadata and governance review

Use this when you are reviewing data assets, lineage, or governance context before publication or handoff.

Example prompt:

> Review the current metadata and lineage for this asset. Identify the most important governance gaps, protection checks, and missing context that should be resolved before I save or publish this asset.

Best when:
- you are preparing an asset for downstream consumption
- you want a plain-language summary of metadata quality
- you need support for stewardship and contract review

## Copy-ready prompt templates

| Scenario | Prompt template | Expected value |
| --- | --- | --- |
| Connector setup | Help me configure this connector for the current workspace. Explain the required fields, the safest secret-handling approach, and the validation steps I should run before syncing. | A concise checklist and configuration guidance |
| Rule authoring | Turn this requirement into a precise, testable data quality rule. Suggest candidate attributes, the primary condition, and a safe validation plan. | A draft-ready recommendation with context |
| Metadata review | Review this metadata record and its lineage. Highlight missing governance context, protection concerns, and the top next actions to improve quality. | A review summary and prioritised fixes |
| Policy check | Explain whether this asset is ready for consumer use. Call out gaps in ownership, purpose, glossary context, and protection readiness. | An explainable readiness assessment |

## Suggested prompt structure

For the best responses, keep prompts in this order:

1. State the task clearly.
2. Name the target surface or asset.
3. Ask for the output format you want.
4. Add the quality bar you care about.

Example:

> Review this data asset for governance readiness. Highlight the top three gaps, suggest the safest next actions, and explain why each one matters for downstream consumers.

## Workflow checklist

Before you run a prompt, ask:

- What outcome do I want from the agent?
- Which UI surface is the best match for this question?
- What context must be included to avoid vague guidance?
- What would make the answer actionable for my next step?

## Operational notes

- Treat the agent response as an assistant, not an automatic authority.
- Review any recommendation that affects secrets, rules, contracts, or production operations.
- Use specific prompts so the model can act on the current workspace or connector context instead of guessing.

## Summary

These workflow examples and prompt templates are designed to help you get reliable, reviewable assistance from the agent harness in the existing UI flows. Use the most specific prompt possible, and keep the output focused on the next action you need to take.
