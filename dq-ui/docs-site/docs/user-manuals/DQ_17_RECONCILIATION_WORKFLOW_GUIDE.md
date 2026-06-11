# DQ-17 Reconciliation Workflow Guide

This guide explains how reconciliation works in dq-made-easy and how the same definition can be reused across Data Assets and rules.

## What the workflow does

Reconciliation compares two selected datasources or datasets using a canonical `RECONCILE` definition. The definition captures the left and right versions, join keys, and comparison rules so the same contract can be used in the workbench, in saved policy documents, and later in worker-backed execution.

The current implementation stores each run, so users can review history after the browser session ends. A datasource can only take part in one active reconciliation at a time, which prevents overlapping runs from conflicting with each other.

## How to use it

1. Open the Reconciliation Workbench.
2. Choose the left and right datasources.
3. Enter or adjust the reconciliation contract:
   - left and right data object versions
   - join keys
   - comparison rules
4. Run the reconciliation.
5. Review the match, mismatch, and diagnostic output.
6. Open the policy-document or template surfaces when you want to reuse the same definition in another place.

## Reuse flow

The reuse path is built around the existing policy-document library:

- The reconciliation definition is represented as a reusable blueprint template.
- The same template can be previewed as a policy document for both rules and Data Assets.
- Reuse controls keep the definition aligned across workspaces and governed surfaces.

In practice, this means a steward can author one reconciliation contract and then reuse it wherever the same left/right comparison logic is needed.

## Active-run protection

Before a new run is created, the API checks whether either selected datasource is already part of a pending or running reconciliation. If so, the request fails fast with a conflict response and the UI keeps the run disabled until the active run completes.

## Where to look in the UI

- Reconciliation Workbench: run and review reconciliation history.
- Policy Documents: preview reusable reconciliation definitions.
- Template Library: browse the reusable blueprint template.
- Rules: assign reusable joins and related policy assets from the rule workspace.

## Result surfaces

After a run completes, the workbench shows:

- matched rows
- mismatched rows
- rows missing from the left side
- rows missing from the right side
- execution diagnostics and summary metrics

## Notes for stewards

- Reuse the same definition when the comparison contract must stay identical across rules and Data Assets.
- Update the shared blueprint when the business meaning of the comparison changes.
- Keep workspace scope explicit so teams can see where a definition is intended to be reused.