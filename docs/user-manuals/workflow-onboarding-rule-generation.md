# Guided Standard Rule Generation

**Role:** Data steward, developer, or analyst onboarding a new data domain, dataset, or data product.
**Time to read:** 8 minutes
**Last updated:** 2026-05-31
**Where to find it:** *Rules* → **Generate starter rules** (or from the data object detail page)

## What it does

Guided rule generation lets you apply standard quality baselines across an entire data product, dataset, or data object in one guided flow, without writing rules one by one.

The platform:
1. Reads the attributes in your selected scope.
2. Proposes starter rules for each attribute based on its data type, name, and metadata.
3. Presents the proposals grouped by rule type so you can review and de-select at any level.
4. Creates all accepted proposals as draft rules ready for an approval pass.

## When to use it

Use this when:
- You are onboarding a new data domain or data product and want a quality baseline quickly.
- A large dataset has been added to the workspace and has no rules yet.
- You want to make sure every attribute has at least a completeness check before the first execution run.

Do not use this to replace manual rule authoring for complex business logic. Starter rules cover standard dimensions (completeness, uniqueness, format, range, timeliness). They are a starting point, not a final rule set.

## Step 1: Select your scope

Choose what to cover:

| Scope | When to use |
| --- | --- |
| **Workspace** | Onboard all data objects in the active workspace at once |
| **Data product** | Cover all datasets within one product |
| **Dataset** | Cover all objects within one dataset |
| **Data object** | Cover a single object version |

Before proceeding you will see a scope summary: "X objects · Y attributes selected." If the scope is large (more than 500 attributes), the platform warns you and advises using the group filters during review.

## Step 2: Review the proposals

The platform proposes starter rules using the existing DAMA template library. Rules are grouped by template type, not by attribute. You do not see a flat list of thousands of individual rows.

**What the review screen looks like:**

```
┌─────────────────────────────────────────────────────────────────────┐
│ ☑ NULL Value Check           Completeness      847 attributes  ▼   │
│   ☑ customer_data :: customer_profile          45 attributes   ▼   │
│       ☑  customer_id       THRESHOLD · High                        │
│       ☑  email             THRESHOLD · High                        │
│       ☐  notes             THRESHOLD · Low  (already covered)      │
│   ☑ transaction_data :: ...                   635 attributes   ▼   │
│                                                                     │
│ ☑ Uniqueness                 Uniqueness        12 attributes   ▼   │
│ ☑ Regex – Email Pattern      Accuracy           8 attributes   ▼   │
│ ☑ Range Check – Amount       Validity           4 attributes   ▼   │
└─────────────────────────────────────────────────────────────────────┘

  Summary bar: 856 rules selected · 9 already have coverage · 1 failed match
  [Create 856 draft rules]
```

Groups are collapsed by default. Expand a group to see objects. Expand an object to see individual attributes.

## Step 3: Select and de-select

You can act at three levels:

- **Template group level**: check or uncheck the group row to select or de-select all attributes in that template at once. This is the fastest way to exclude a whole rule type (for example, if you do not want Freshness checks in this dataset).
- **Data object level**: check or uncheck the object row to select or de-select all attributes in that object for the current template.
- **Attribute level**: toggle individual attributes for precise control.

**Attributes already covered** (shown with "already covered" label) are de-selected by default. These are attributes that already have an equivalent active rule of the same check type. You can select them manually if you want a second rule, but in most cases you will leave them de-selected.

**Filter bar** (always visible above the tree):
- Dimension (Completeness, Accuracy, Validity, Timeliness, Uniqueness, Consistency)
- Template group
- Dataset name (search)
- Data type (String, Numeric, Date, Boolean)
- Status (All · Selected · De-selected · Already covered)

Use the filters to focus on a specific data type or dimension before deciding whether to keep or remove a group of proposals.

## Step 4: Create draft rules

When you are satisfied with the selection, click **Create X draft rules**.

What happens:
- The platform creates one draft rule per accepted proposal.
- All rules start in **draft** status — they will not execute until approved and activated.
- Each rule is named `{Template name} – {attribute name}` (e.g. "NULL Value Check – customer_email").
- Each rule is tagged with the batch ID for traceability.
- A progress indicator shows while the batch is being created.

On completion you see a batch summary:

| Outcome | Meaning |
| --- | --- |
| Created | Draft rule created successfully |
| Skipped | Attribute already had an equivalent rule |
| Failed | Rule could not be created; see the error reason |

## Step 5: Next steps after creation

From the batch summary you have two options:

- **Go to Rules** — opens the rule list filtered to this batch so you can inspect each draft, edit any parameters, or remove rules you change your mind about.
- **Submit for approval** — bulk-submits all created drafts to the approval workflow so a governance reviewer can approve the entire baseline at once.

> If you have hundreds of rules in the batch, **Submit for approval** is the recommended path. A single approval review covers the entire baseline rather than requiring per-rule approvals.

## What the platform proposes for each attribute type

| Attribute signal | Proposed starter rules |
| --- | --- |
| Any attribute | NULL Value Check |
| String or text | NULL Value Check, Empty String Check |
| Required / non-nullable | NULL Value Check (High severity) |
| Name matches `*_date`, `*_at`, `*_time` | NULL Value Check, Freshness Check, Future Date Detection |
| Name matches `*_id`, `*_key`, `*_code` | NULL Value Check, Uniqueness |
| Name matches `email`, `*_email` | NULL Value Check, Regex (email format) |
| Name matches `phone`, `*_phone` | NULL Value Check, Regex (phone format) |
| Numeric or decimal | NULL Value Check, Range Check |

## Troubleshooting

- If a group shows zero attributes after filtering, check whether the filter is too narrow or whether all attributes in that group are already covered.
- If the scope summary shows fewer attributes than expected, confirm the data object version is registered in the workspace catalog.
- If batch creation reports failures, check the rule name conflict column — a rule with the same name may already exist. Edit the name before resubmitting.
- Draft rules created in this flow can be deleted individually from the Rules list if you decide a proposal is not needed after review.

## Related guides

- [Developer Workflow Guide](./workflow-developer.md) — rule authoring and the git-first workflow
- [Data Steward Workflow Guide](./workflow-data-steward.md) — approvals and lifecycle management
- [DQ-1 Rule Validation User Guide](./DQ-1_RULE_VALIDATION_USER_GUIDE.md) — understanding rule check types
- [User Manuals index](./README.md)
