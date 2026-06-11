# Data Asset Lineage Guide

> **Feature:** DQ-19.5 Automated lineage capture with business-context overlays, classification views, and anomaly annotations
> **Where to find it:** *Data Assets* → open a Data Asset → **Lineage and Impact** section
> **Persistence:** Each lineage refresh is captured as a snapshot in Postgres, so you can revisit the same analysis later.

## What lineage capture does

Lineage is assembled automatically from the live catalog and governance records for the selected Data Asset. The platform traces the asset back to its source Data Objects, source datasets, and data products, then looks forward to the rules, monitor schedules, and incidents that are linked to the same lineage.

The captured lineage snapshot includes:

- Upstream catalog sources
- Downstream rules, monitor schedules, and incidents
- The current business-context overlay for the asset
- A classification view based on business criticality and impact signals
- Anomaly annotations for contract changes, monitor coverage, and incidents

Each lineage build is stored as a snapshot row in Postgres. That means the lineage you review is not just a temporary screen state; it is recorded and can be loaded again from the lineage history.

## Where to find it

1. Open **Data Assets** in the UI.
2. Select the asset you want to inspect.
3. Scroll to the **Lineage and Impact** section.
4. Review the snapshot metadata, the upstream and downstream nodes, and the business-context overlay.

The lineage section is shown directly on the Data Assets page. You do not need to leave the page to inspect the graph relationships or the related governance signals.

## Is it shown as a graph or diagram?

Yes, but in a structured lineage view rather than a free-form diagram editor.

The UI presents lineage as:

- A summary card with capture time and snapshot id
- Separate **Upstream** and **Downstream** sections
- Grouped node cards for objects, datasets, products, rules, monitors, and incidents
- "Open" links that let you jump to the related screen when navigation is available

This makes the lineage easy to scan while still keeping the technical relationships visible. If you are looking for a visual diagram canvas with node dragging and edge drawing, that is not the current experience.

## When to use it

Use lineage when you want to answer questions such as:

- Where did this asset come from?
- Which rules, monitors, or incidents are connected to it?
- Has the contract changed in a way that affects governance?
- What business context should I use when interpreting this asset?

It is especially useful before publishing changes, reviewing a contract update, or checking whether a data asset has downstream impact.

## What the classification means

The classification view helps you understand how sensitive or operationally important the asset appears based on the available signals.

- `public` means no strong impact signal was detected
- `internal` means the asset has some business or operational relevance
- `restricted` means the lineage includes high-risk or incident-heavy signals

The classification is informational. It does not replace a formal access-control policy.

## Troubleshooting

- If the lineage section looks empty, make sure the asset has source-object version links and saved business-context data.
- If no downstream nodes appear, that usually means no rules, monitors, or incidents matched the asset lineage yet.
- If a source link is missing, check that the source object version still exists in the catalog.

## Related cards

- [Data Assets feature plan](../features/DQ_FEATURES.md)
- [Governance Terminology Reference Card](./governance-terminology.md)
- [UI Capability Matrix](./ui-capability-matrix.md)
