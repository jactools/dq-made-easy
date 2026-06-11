# Autonomous AI Steward Guide

> **Feature:** DQ-19.4 Autonomous AI steward
> **Where to find it:** *Suggestions* → *Natural language rule previews* → choose **Autonomous AI Steward**
> **Persistence:** Each steward request is saved in Postgres and appears in the request history list.

## What the Autonomous AI steward does

The Autonomous AI steward helps you understand governed metadata and improve it without leaving the Suggestions workflow. It reads the target metadata, explains what is present, highlights gaps, and suggests practical fixes.

Use it when you want a quick, reviewable answer to questions such as:

- What does this data object version contain?
- Which metadata fields are missing or incomplete?
- How can I improve this glossary term before publishing it?
- What should I fix first to make an asset easier to govern and explain?

The steward is designed for explainability, not automatic approval. It gives you a clear summary and suggested next steps, but you still decide whether to apply the changes.

## Best scenarios

### 1. Reviewing a data object version before handoff

Use the steward when you need a quick governance check on a specific data object version. This is useful when you are preparing an asset for a downstream team or confirming whether the object has the metadata needed for publication.

Typical prompts:

- Explain this data object version and list the most important fixes.
- What is missing from this version before I hand it off?
- Show me the steward summary for this object version.

The steward can help you spot issues such as:

- Missing storage location or storage format
- Missing or weak key definitions
- Unmapped attributes that should be tied to glossary terms
- Gaps in the object, dataset, or product context

### 2. Improving glossary terms

Use the steward when you want to clean up glossary content or prepare a term for wider use. It can explain the term, point out missing business definitions, and suggest governance improvements.

Typical prompts:

- Explain this glossary term and suggest fixes.
- What should I add before publishing this term?
- Review this term for stewardship gaps.

The steward is especially useful when you want to check for:

- Missing or vague business definitions
- Missing owner or steward assignment
- Missing synonyms
- Hierarchy issues, such as a term that should sit under a parent definition

### 3. Checking whether metadata is ready for consumers

Use the steward if you are trying to decide whether a metadata record is clear enough for analysts, data producers, or downstream teams.

Typical prompts:

- Is this metadata ready for consumers?
- What would a steward ask me to fix here?
- Give me a plain-English explanation of this asset.

This is a good fit when the question is not about rule logic itself, but about whether the asset is understandable and governed.

### 4. Preparing metadata for rule authoring

Use the steward before writing or reviewing a rule if you want to make sure the target metadata is in good shape first.

Typical prompts:

- Explain the target asset before I write a rule.
- What metadata problems could affect rule authoring?
- Which fields should I review before creating a rule?

This is useful when the rule depends on a clean object version, a clear glossary term, or both.

## How to use it

1. Open **Suggestions** in the UI.
2. Select the natural-language steward flow.
3. Choose the target type:
   - `data_object_version` for a specific object version
   - `glossary_term` for a glossary definition
4. Enter a short prompt that describes what you want reviewed.
5. Submit the request and review the returned summary, explanation, and suggested fixes.
6. Check the request history if you want to revisit past steward analyses.

## What you get back

The steward response usually includes:

- A short metadata summary
- A plain-English explanation of the target
- Suggested fixes
- Structured metadata facts that can be reused in the UI or audits

The request is also persisted, so you can revisit the same analysis later from the request history instead of rerunning the prompt.

## When not to use it

Do not use the steward when you need:

- A final approval decision
- Automatic editing of catalog records
- A runtime rule execution result
- A substitute for missing source data

If the underlying metadata target cannot be resolved, the steward fails fast and returns an error instead of guessing.

## Example prompts

- Explain this data object version and suggest the top three fixes.
- Review this glossary term for missing stewardship details.
- Tell me whether this asset is ready for consumer use.
- Summarize the current metadata state for this object version.

## Practical tips

- Keep the prompt short and specific.
- Use the steward for a single target at a time.
- Start with a data object version when you want technical context, then switch to a glossary term if you need business meaning.
- Review the suggested fixes before moving on to rule authoring or publishing.
