# Data Observability Triage Guide

> **Feature:** DQ-19.6 Data observability triage with issue routing, root-cause drilldown, and remediation actions
> **Available from:** v0.11.0
> **Where to find it:** *Operations* → **Incidents**
> **Data protection note:** This view is metadata-only. It helps you coordinate incident response without exposing source records, row values, or failure payloads.

## What it does

The triage view helps you manage incidents created from rule failures, runtime problems, or other workspace-scoped operational issues. It gives you a fast way to understand what needs attention, who is working on it, and whether the issue is moving toward resolution.

You can use it to:

- See how many incidents are open, in progress, and resolved for the current workspace.
- Review the incident title, kind, severity, workspace, scope, assignment, and tracking ticket.
- Check whether an incident has comments or a resolution history.
- Coordinate follow-up work without opening raw data or payload-level details.

## When to use it

Use the incident triage view when you need to:

- Prioritize the next incident to work on.
- Assign or reassign work to the correct owner.
- Confirm whether an issue has already been acknowledged or resolved.
- Track an external ticket that is being handled outside the platform.

If you need to inspect actual records, row values, or source payloads, use the approved source-system or data-access workflow for that data. This triage view is intentionally not a data preview screen.

## How to use it

1. Open **Operations** in the application.
2. Select **Incidents**.
3. Make sure the correct workspace is selected.
4. Review the summary cards at the top of the page.
5. Open the incident cards that need attention.
6. Read the incident metadata:
   - incident kind
   - severity and status
   - workspace and scope
   - assignment and ticket number
   - update time
7. Use the comments and history counts to see whether the issue is already being worked on.
8. Follow up in the appropriate workflow if the incident needs remediation.

## What success looks like

You should be able to answer these questions quickly:

- Is this incident open, active, or resolved?
- Who owns it right now?
- Is there a ticket or discussion already attached?
- Do I need to escalate or can I continue work in another part of the platform?

## What you will not see

This page does not show:

- raw source rows
- sample data
- failure payload bodies
- record-level output from the affected data object

That restriction is intentional and aligns with the data-protection policy.

## Troubleshooting

- If the page says no workspace is selected, choose an active workspace first.
- If the page shows no incidents, there may simply be nothing recorded for that workspace yet.
- If an incident is missing the details you expected, remember that this view only shows metadata and workflow context.

## Related cards

- [Data Asset Lineage Guide](./data-asset-lineage-guide.md)
- [Governance Terminology Reference Card](./governance-terminology.md)
- [User Manuals index](./README.md)