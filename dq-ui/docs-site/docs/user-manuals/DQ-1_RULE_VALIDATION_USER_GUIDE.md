# Rule Validation — User Guide

> **Feature:** DQ-1 Enhanced Rule Validation Logic  
> **Available from:** v0.6.1  
> **Availability:** Standard feature  
> **Where to find it:** *Rule Quality* → *Rule Validation* in the main navigation.  
> **Rollout tracking:** [DQ-1 Rule Validation Standard Feature Implementation Plan](/docs/implementation-details/DQ_1_RULE_VALIDATION_STANDARD_FEATURE_IMPLEMENTATION_PLAN/) — especially `DQ1-I-P2-01`, `DQ1-I-P3-01`, `DQ1-I-P6-01`, and `DQ1-I-AC-01`

---

## Overview

The **Rule Validation** feature lets you check the quality of your rules before they are
activated or scheduled. You can validate one rule or hundreds at once, and the system
tells you exactly what is wrong and why — without you having to run a live test against
real data.

Rule Validation is intentionally separate from the main Rules workspace. The Rules area
stays focused on authoring, editing, and managing rule inventory, while Rule Validation
provides a dedicated quality-control view for batch checks, cross-rule diagnostics, and
validation run history.

Related follow-on capabilities now appear under the dedicated **Governance** and **Operations** navigation areas, so users can move from rule quality checks into approval, lifecycle, exception, monitoring, and aggregation flows without overloading the Rules workspace.

The related standard-feature rollout is tracked in the DQ-1 implementation plan. For the
navigation and availability changes described in this guide, the main tracking items are
`DQ1-I-P2-01`, `DQ1-I-P3-01`, `DQ1-I-P6-01`, and `DQ1-I-AC-01`.

Use Rule Validation when you want to:

- Confirm that a rule's filter expression is correctly written
- Find duplicate or contradictory rules before they cause confusion in results
- Get a quick health check across all rules in your workspace
- Keep a history of past validation checks for audit or review purposes

## Supported Expression Syntax Basics

Rule Validation checks the dq-made-easy filter-expression syntax, not full SQL.

Use these common building blocks in rule expressions:

| Construct | Examples |
|---|---|
| Comparison | `age >= 18`, `status = 'active'`, `score != 0` |
| Null checks | `email IS NULL`, `email IS NOT NULL` |
| Set membership | `country IN ('NL', 'BE')`, `status NOT IN ('inactive', 'deleted')` |
| Ranges | `amount BETWEEN 10 AND 100`, `amount NOT BETWEEN 0 AND 5` |
| Pattern matching | `name LIKE 'A%'`, `code RLIKE '^INV-[0-9]+$'` |
| Boolean logic | `status = 'active' AND age >= 18`, `(country = 'NL' OR country = 'BE') AND email IS NOT NULL` |

Keep these limits in mind:

- Do not use SQL statements such as `SELECT`, `FROM`, or `WHERE`.
- Do not use comments or semicolons.
- Make sure parentheses and quotes are balanced.
- Use Rule Validation to catch unsupported keywords, malformed syntax, and contradictory predicates before activation.

If your rule depends on relationships across datasets, use the join-definition flow described in the [DQ-2 Join Conditions User Guide](/docs/user-manuals/DQ-2_JOIN_CONDITIONS_USER_GUIDE/) rather than trying to express cross-dataset joins inside one free-text filter expression.

---

## Getting Started

### Open the Rule Validation Panel

1. Log in and select your workspace.
2. Open **Rule Quality** in the main navigation.
3. Click **Rule Validation**.
4. The panel loads automatically showing all rules in your workspace.

You can also open Rule Validation directly from the Rules workspace using the per-rule **Open in Rule Validation** action or the bulk-selection **Rule Validation** action.

The Rules inventory also shows the latest validation state directly on each rule card and, when available, the most recent validation date so you can decide quickly whether to open the broader Rule Validation workspace.

---

## Selecting and Validating Rules

### Choose Which Rules to Validate

The **Select Rules** section lists every rule in your workspace. Each row shows the rule
name, current version, and internal ID.

Use the search field to quickly filter by:

- Rule name
- Rule ID
- Version label (for example `v3`)

| Action | How |
|---|---|
| Select individual rules | Click the checkbox next to each rule |
| Select all currently visible rules | Click **Select visible** |
| Clear your selection | Click **Clear** |

### Run Validation

Click the **Validate** button:

- If rules are selected, only those selected rules are validated.
- If no rules are selected, **all currently visible (filtered) rules** are validated.

Validation usually completes within a few seconds. A spinning indicator is shown while
it runs.

---

## Understanding the Results

After validation completes, a **Results** section appears beneath the rule list.

### Summary Bar

At the top of the results you will see coloured pills summarising the outcome:

| Pill | Meaning |
|---|---|
| **N rules** | Total number of rules that were validated |
| **N valid** | Rules with no errors |
| **N invalid** | Rules that have at least one error |
| **N errors** | Total number of error-level issues found |
| **N warnings** | Total number of warning-level issues found |

### Per-Rule Rows

Each rule appears as a row with a green tick (valid) or red cross (invalid).

Click a row to expand it and see the individual diagnostics for that rule.

Each diagnostic shows:

- **Severity** — error (red), warning (amber), or info (blue)
- **Check ID** — a short code identifying the specific check that raised the issue (e.g. `DQ1_EMPTY_EXPRESSION`)
- **Message** — a plain-English description of the problem
- **Location** — where in the expression the issue was found, if applicable
- **Compiled expression** — the normalised form of the expression, shown when compilation succeeds

### What each Check ID means

| Check ID | Severity | What it means |
|---|---|---|
| `DQ1_EMPTY_EXPRESSION` | Error | The rule's filter expression is blank. Add an expression before activating. |
| `DQ1_EXPRESSION_SYNTAX` | Error | The expression could not be parsed. Check for mismatched brackets, missing operators, or typos. |
| `DQ1_UNSUPPORTED_KEYWORD` | Error | The expression contains a SQL keyword (such as `SELECT` or `FROM`) that is not allowed here. Use the DQ expression syntax instead. |
| `DQ1_MISSING_ALIAS` | Warning | The expression references an alias (e.g. `t.column`) that has no mapping defined. Add the alias mapping or correct the expression. |
| `DQ1_JOIN_VALIDATION` | Warning | The rule's join definition has a structural issue. Review the join conditions. |
| `DQ1_DUPLICATE_EXPRESSION` | Warning | Another rule in the workspace uses an identical filter expression. Consider merging the rules or confirming this is intentional. |
| `DQ1_DUPLICATE_NAME` | Warning | Another rule in the workspace has the same name (ignoring upper/lower case). Rename one of them to avoid confusion. |
| `DQ1_CONTRADICTORY_PREDICATES` | Warning | Two conditions on the same field are logically contradictory (e.g. `age > 50 AND age < 10`). Review the predicates. |

### Cross-Rule Conflicts

If two or more of the validated rules conflict with each other, a **Cross-Rule Conflicts**
section appears below the per-rule rows.

Each conflict entry shows:

- The **conflict type** (e.g. *Duplicate expression*, *Contradictory predicates*)
- A **message** explaining which rules are involved and why they conflict

Conflicts are warnings — they do not block activation — but they are worth reviewing to
make sure your rules produce the results you expect.

---

## Exporting Results

The Rule Validation panel focuses on actionable on-screen diagnostics and run history.
For exports, use the **Validation Run History** CSV download per run.

---

## Validation Run History

Every time you click **Validate**, the system saves a record of that run. The
**Validation Run History** section shows the last 10 runs for your workspace.

Each row shows the run ID, date, total rules checked, how many were valid, and the run
status.

### View Run Details

Click any history row to expand it and see the per-rule outcomes for that saved run,
including the rule version captured at run time.

### Export a Past Run as CSV

In any history row, click the download icon to download that run's results as a CSV file.
The CSV lists one rule per row with its valid/invalid status, error count, and warning
count — suitable for import into a spreadsheet or reporting tool.

### Refresh the History List

Click **Refresh** at the top-right of the history section to reload the latest runs.

---

## Frequently Asked Questions

**Do I need to fix all warnings before activating a rule?**  
No. Warnings are advisory. Only errors prevent a rule from being compiled successfully.
However, it is good practice to review warnings — duplicate names and contradictory
predicates can cause unexpected results when rules are executed at scale.

**Can I validate rules from different workspaces at once?**  
No. The Rule Validation panel operates on the workspace you are currently logged into.
Switch your workspace and re-open the panel to validate rules in another workspace.

**How many rules can I validate in one run?**  
Up to 100 rules per run. If your workspace has more than 100 rules, use the checkboxes
to validate them in batches.

**Is validation the same as running a test?**  
No. Validation checks the *structure and logic* of a rule's expression without touching
any data. A test run (available from the Rules page) executes the rule against actual
data and returns pass/fail counts for real records.

**Why is Rule Validation separate from the Rules page?**  
Rule Validation is a workspace-level quality-control feature. It supports batch checks,
cross-rule conflict detection, and saved run history across many rules at once. Keeping
it separate helps the Rules page stay focused on authoring and day-to-day rule management.

**Why does a valid rule still show warnings?**  
Warnings indicate potential issues that do not prevent compilation. Common examples are
a duplicate expression shared with another rule, or an alias that is referenced but not
yet mapped. The rule can still be activated, but reviewing the warnings is recommended.

---

## Tips

- **Validate after every significant edit.** Run a quick validation whenever you change an expression to catch syntax errors before they reach activation.
- **Use filtering + "Select visible" for focused checks.** This is the fastest way to validate a large ruleset in targeted batches.
- **Run a workspace health check with no manual selection.** With no selected rows, Validate runs against all currently visible rules.
- **Keep run-history CSV exports for audit.** If your organisation requires review evidence, download CSV from Validation Run History for each relevant run.
