# Definition Mappings - AI-Assisted Data Definition Guide

**Time to read:** 5 minutes
**Last updated:** 2026-05-27

## Overview

Use **Definition Mappings** when you want to draft governed business definitions from a selected data object and its catalog attributes, review the draft with AI assistance, and then import the approved result into OpenMetadata.

This guide covers the workflow behind the WS4 acceptance criteria for:

- generating a definition draft from inside Definition Mappings without a separate manual AI step,
- capturing steward revision feedback and board approval,
- validating the generated definitions before approval or import,
- importing approved definitions into OpenMetadata with explicit success or failure reporting.

## Where to find it

1. Open **Data Catalog** in the main navigation.
2. Select **Definition Mappings**.
3. In the page, use the **Data definition task** section to generate or revise a draft.

You can also open Definition Mappings from a data object or attribute in the Data Browser when a direct mapping workflow is already in context.

## Prerequisites

- Role: `Data Steward` or `Admin` to create and import; `Editor` can review and provide feedback; `Viewer` can inspect results.
- You need a selected version and at least one attribute in the draft scope.
- Prepare a short steward note that explains the business meaning, policy constraints, or wording you want in the definition.
- If you plan to import to OpenMetadata, make sure the board review step has been completed and the status is approved.

## Quick Start

1. Open **Definition Mappings**.
2. Select the data object version you want to define.
3. Add one or more catalog attributes to the draft scope, or use **Use all version attributes**.
4. Enter a short **Steward input** and any **Policies and guardrails**.
5. Click **Generate draft**.
6. Review the generated definitions and refine the next draft with **Feedback for next draft** if needed.
7. Set the **Board approval status** and add **Board notes**.
8. Click **Capture board approval**.
9. Once approved, click **Import to OpenMetadata**.

## Step-by-Step

### 1) Choose the scope

The draft scope controls what the AI can use when proposing definitions.

- Click **Add current attribute** to include the attribute you are currently viewing.
- Click **Use all version attributes** when the data object should be reviewed as a whole.
- Remove any attribute from the scope if it is not relevant to the definition you want.

Keep the scope focused. The AI produces better drafts when the input set is small and clearly related.

### 2) Add steward context

Use the text areas to provide the human context the model cannot infer from the catalog alone.

- **Steward input**: describe the business meaning, stewardship goal, or ambiguity that needs resolving.
- **Policies and guardrails**: add one policy per line, such as naming conventions, ISO 11179 requirements, or board constraints.
- **Feedback for next draft**: summarize what needs to change before regenerating.

### 3) Generate the draft

Click **Generate draft** to create the first version of the definition package.

The system may show:

- generated definition names,
- business definitions,
- examples,
- constraints,
- open questions that still need steward review.

Treat these as draft suggestions. Review each field before moving to approval.

If you already generated a draft and want to refine it, the button changes to **Generate revised draft**.

### 4) Review and revise

Check that each generated definition:

- uses the right business name,
- describes the object clearly,
- includes realistic examples,
- reflects the policy notes you supplied,
- does not invent meaning that is not present in the catalog context.

If the draft needs changes, update your steward input or feedback and generate a revised draft.

### 5) Capture board approval

Use **Board approval status** to record the decision:

- `Pending` while the review is still open,
- `Approved` when the board accepts the draft,
- `Rejected` when the board wants the draft reworked.

Add **Board notes** so the decision is auditable and easy to revisit later.

Click **Capture board approval** after the board decision is ready. This step is required before OpenMetadata import.

### 6) Import to OpenMetadata

After approval, click **Import to OpenMetadata**.

The UI reports whether the import succeeded and how many definitions were imported. If you re-run the import after a previous success, the button changes to **Re-sync OpenMetadata**.

This import path is fail-fast: if the backend cannot validate or import the definitions, it shows an error instead of silently guessing or using partial data.

## What the AI does

The AI helps draft governed definitions from the selected attributes plus your steward input.

It can propose:

- definition names,
- short business descriptions,
- example values,
- constraints,
- open questions for review.

The AI is a drafting assistant, not the source of truth. You remain responsible for the final wording, scope, and approval.

## What you must review

Always confirm:

- the definition is about the right business object,
- the wording is clear enough for governance review,
- examples match the source context,
- any constraints are actually enforceable,
- no sensitive data has been copied into the draft,
- the board decision matches the current review status.

## Validation and quality checks

WS4-AC07 requires the generated definitions to be validated for semantic quality, structure, and compliance before approval or import.

In practice, that means checking for:

- a coherent business meaning,
- one definition per concept,
- no duplicate or conflicting terms,
- reasonable examples and constraints,
- alignment with the policies you entered.

If the draft does not pass review, revise the scope or steward input and regenerate it.

## Troubleshooting

- If **Generate draft** is disabled, select a version and at least one attribute first.
- If the draft looks too broad, reduce the scope to fewer attributes.
- If **Capture board approval** is disabled, the task is not yet completed.
- If **Import to OpenMetadata** is disabled, the board review has not been marked approved.
- If the AI service is unavailable, the page shows an error and you can continue with manual drafting; it does not silently substitute approximate output.

## Related cards

- [Autonomous AI Steward Guide](/docs/user-manuals/autonomous-ai-steward-guide/)
- [Governance Terminology Reference Card](/docs/user-manuals/governance-terminology/)
- [Data Asset Lineage Guide](/docs/user-manuals/data-asset-lineage-guide/)

