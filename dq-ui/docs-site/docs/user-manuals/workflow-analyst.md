# Analyst Workflow Guide

**Role:** Data analyst or domain user who uses the platform to discover data quality signals, explore results, and understand rule health without authoring or governing rules.
**Time to read:** 8 minutes
**Last updated:** 2026-05-31

## Responsibilities in scope

- Discovering data quality health for datasets, domains, and data products.
- Exploring rule execution results and failure signals.
- Navigating from a failing quality signal to its owning rule and history.
- Reading business term definitions and catalog metadata.

## Core workflows

### 1. Find the health of a data product or dataset

1. Open **Dashboard** from the main navigation.
2. Select your workspace.
3. Review the quality summary cards: quality score, top failing rules, top degraded datasets, and SLA status.
4. Drill into a dataset or data product to see its rule execution history.

### 2. Explore rule execution results

1. Open **Operations** → **Monitoring**.
2. Use the filters to narrow by dataset, domain, severity, or timeframe.
3. Select a result row to see execution metadata, check type, and outcome summary.
4. Navigate to the owning rule from the result detail.

> You will not see raw source rows or sample data values. Results are metadata-only.

### 3. Navigate from a quality signal to the owning rule

1. From a failing result, open the rule link in the result detail.
2. Review the rule definition, severity, check type, and execution target.
3. Check the version history to see whether a recent rule change preceded the failure.
4. See the assigned owner or domain to find the right person to contact.

### 4. Review quality history for a rule or dataset

1. Open **Operations** → **Quality History**.
2. Select the dataset, rule, domain, or data product you want to review.
3. Use the time range selector to compare recent runs against a baseline period.
4. Look for degradation events or drift markers in the trend view.

### 5. Look up a business term definition

1. Open **Data Catalog** → **Business Terms**.
2. Search for the term by name, domain, or related dataset.
3. Read the canonical English definition, domain scope, primary owner, and policy linkage.
4. Use the source references to locate the policy document that governs the term.

## What you will not see

- Raw source records or row-level data values.
- Rule source code internals (check the rule definition card for the configured check type and parameters).
- Unpublished drafts in the definition workflow.

## Troubleshooting

- If a dataset shows no quality history, it may not yet have an active rule execution target or run plan.
- If a rule is not visible under your workspace, check that you are viewing the correct workspace scope.
- If you cannot find a business term, it may still be in draft or board-review state and not yet published.

## Related guides

- [Data Observability Triage Guide](/docs/user-manuals/data-observability-triage-guide/)
- [Data Asset Lineage Guide](/docs/user-manuals/data-asset-lineage-guide/)
- [Governance Terminology Reference Card](/docs/user-manuals/governance-terminology/)
- [User Manuals index](/docs/user-manuals/)
