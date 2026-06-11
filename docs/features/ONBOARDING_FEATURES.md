# Onboarding Features

## ONB-1: Guided Standard Rule Generation

**Status**: Specified  
**Workstream**: WS9-A04  
**Acceptance criterion**: WS9-AC03 — Onboarding can generate standard starter rules with reviewable output.  
**Implementation plan**: [docs/ONB-1_IMPLEMENTATION_PLAN.md](../ONB-1_IMPLEMENTATION_PLAN.md)

### Overview

When a new data domain, dataset, or data product is brought into the workspace, a data steward or developer needs a fast way to apply standard quality baselines across all attributes without writing rules one-by-one. This feature provides a guided, multi-step flow that:

1. Accepts a scope selection (workspace, data product, dataset, or single data object).
2. Generates rule proposals based on the existing DAMA template library and per-attribute metadata.
3. Presents proposals in a reviewable, bulk-selectable tree so the user can de-select what is not needed.
4. Creates all accepted proposals as draft rules (not active), ready for a single approval pass.

### Scale design requirement

A data product can contain tens of datasets, each with tens of objects, each with hundreds of attributes. A naive flat list of rule proposals is unusable at that scale. The UX must remain navigable whether 10 or 10,000 rules are proposed.

Design principle: **group proposals by template type, not by attribute**. Users review and act on groups. They drill into individual attributes only when needed.

---

### Step 1: Scope selection

The user picks one of four scope levels. Selecting a higher level includes all children automatically; the scope summary shows the count of included objects and attributes before the user proceeds.

| Scope | Includes |
| --- | --- |
| Workspace | All data products → all datasets → all objects → all attributes in the active workspace |
| Data product | All datasets within the selected data product |
| Dataset | All objects within the selected dataset |
| Data object | A single data object version |

The scope selector shows:
- A hierarchical tree picker (workspace → product → dataset → object).
- A live summary: "X objects · Y attributes selected".
- A warning if the scope is very large (> 500 attributes): "This scope will generate a large proposal set. Review using the group filters."

---

### Step 2: Proposal generation

The backend generates rule proposals by matching attributes to templates using metadata signals.

**Matching signals** (in priority order):

| Signal | Templates triggered |
| --- | --- |
| Attribute data type is string or text | NULL Value Check, Empty String Check |
| Attribute is marked required / non-nullable | NULL Value Check (high severity) |
| Attribute name matches `*_date`, `*_at`, `*_time` | NULL Value Check, Freshness Check, Future Date Detection |
| Attribute name matches `*_id`, `*_key`, `*_code` | NULL Value Check, Uniqueness |
| Attribute name matches `email`, `*_email` | NULL Value Check, Regex (email pattern) |
| Attribute name matches `phone`, `*_phone` | NULL Value Check, Regex (phone pattern) |
| Attribute data type is numeric or decimal | NULL Value Check, Range Check |
| Attribute data type is boolean | NULL Value Check |
| Any attribute | NULL Value Check (applied universally as baseline) |

Each proposal captures: template ID, attribute ID, attribute name, data object, dataset, data product, proposed check type, proposed parameters, and proposed severity.

Proposals are returned as a grouped structure, not a flat list:

```
Proposal group: NULL Value Check          [847 attributes proposed]
  └── Dataset: customer_data              [212 attributes]
  │     └── Object: customer_profile      [45 attributes]  
  │           └── customer_id  ✓
  │           └── email        ✓
  │           └── ...
  └── Dataset: transaction_data           [635 attributes]
        └── ...

Proposal group: Uniqueness                [12 attributes proposed]
  └── ...

Proposal group: Regex – Email Pattern     [8 attributes proposed]
  └── ...
```

**Existing-rule deduplication**: if a rule with the same check type and attribute already exists for the object, the proposal is omitted from the default selection (but shown as a de-selected item labelled "already covered").

---

### Step 3: Review and selection (the UX)

The review screen is the central experience. It must remain usable whether 10 or 10,000 proposals are shown.

**Tree structure:**
- Top level: template group row — name, dimension badge, total count, bulk checkbox.
- Second level (expandable): data object row — object name, dataset path, count, bulk checkbox.
- Third level (expandable on demand): individual attribute row — attribute name, proposed check type, severity badge, individual checkbox.

**Bulk controls at each level:**
- Checking a template group row selects all attributes in that group.
- Unchecking a template group row deselects all.
- Checking/unchecking a data object row selects/deselects all attributes in that object within the group.
- Individual attributes can always be toggled independently.

**Filter bar (always visible):**

| Filter | Values |
| --- | --- |
| Dimension | Completeness, Accuracy, Validity, Timeliness, Uniqueness, Consistency |
| Template group | Dropdown of all proposed groups |
| Dataset | Search by name |
| Data type | String, Numeric, Date, Boolean |
| Status | All · Selected · De-selected · Already covered |

**Summary bar (sticky at bottom):**
`X rules selected · Y already have coverage · Z total proposals · [Create X draft rules]`

**Performance**: the tree is virtual-scrolled; only visible rows are rendered. Groups are collapsed by default. Expanding a group loads its children lazily if the group contains more than 50 attributes.

---

### Step 4: Batch draft creation

When the user confirms:

1. The backend creates one draft rule per accepted proposal.
2. All created rules have status `draft` (not active).
3. Rules are named following the pattern: `{Template name} – {attribute name}` (e.g. "NULL Value Check – customer_email").
4. Rules are tagged with `generated:true` and `onboarding_batch:{batch_id}` for traceability.
5. A progress indicator is shown since large scopes may create hundreds of rules.
6. On completion, a summary shows: rules created, skipped (already covered), failed (with reason).

After creation, the user is offered two next steps:
- **Go to Rules** — view all created draft rules in the standard rule list, filtered to the current batch.
- **Submit for approval** — bulk-submit all created drafts to the approval workflow.

---

### API contract (backend responsibilities)

The backend owns:
- `POST /api/rules/v1/onboarding/generate-proposals` — accepts scope, returns grouped proposals.
- `POST /api/rules/v1/onboarding/create-batch` — accepts list of accepted proposal IDs, creates draft rules, returns batch summary.

Proposal generation must:
- Apply existing-rule deduplication server-side.
- Return counts at each level so the UI can render group/object summaries without expanding the tree.
- Fail fast (503 with correlation ID) if the metadata or rules services are unavailable.

---

### Acceptance criteria

- [ ] `ONB-1-AC01` A user can select a workspace, data product, dataset, single data object or a single data object version as the onboarding scope.
- [ ] `ONB-1-AC02` The platform proposes starter rules for each attribute using metadata signals and the DAMA template library.
- [ ] `ONB-1-AC03` Proposals are grouped by template type so the review screen is navigable for scopes with hundreds or thousands of attributes.
- [ ] `ONB-1-AC04` The user can select or de-select proposals at the template group, data object, and individual attribute levels.
- [ ] `ONB-1-AC05` Attributes that already have equivalent rules are shown as "already covered" and excluded from the default selection.
- [ ] `ONB-1-AC06` Accepted proposals are created as draft rules tagged with the onboarding batch ID for traceability.
- [ ] `ONB-1-AC07` The batch creation summary shows rules created, skipped, and failed without requiring the user to inspect each rule individually.
- [ ] `ONB-1-AC08` Created drafts can be bulk-submitted to the approval workflow from the batch summary screen.

