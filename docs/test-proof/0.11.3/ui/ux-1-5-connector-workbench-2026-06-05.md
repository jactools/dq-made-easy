---
title: "The connector workbench renders the backend-owned setup, validation, discovery, and sync flow, and the sidebar now exposes the canonical Administration > Connectors entry point."
description: "Human-readable test proof generated from test-results/test-proof/0.11.3/ui/ux-1-5-connector-workbench-2026-06-05.json."
---

# The connector workbench renders the backend-owned setup, validation, discovery, and sync flow, and the sidebar now exposes the canonical Administration &gt; Connectors entry point.

This page was generated from [test-results/test-proof/0.11.3/ui/ux-1-5-connector-workbench-2026-06-05.json](../../../../test-results/test-proof/0.11.3/ui/ux-1-5-connector-workbench-2026-06-05.json).

## Summary

The connector workbench renders the backend-owned setup, validation, discovery, and sync flow, and the sidebar now exposes the canonical Administration &gt; Connectors entry point.

## Metadata

| Field | Value |
| --- | --- |
| App Version | 0.11.3 |
| Proof Id | ux-1-5-connector-workbench-2026-06-05 |
| Proof Type | ui |
| Feature | UX-1.5 |
| Status | passed |
| Executed At Utc | 2026-06-05T23:51:23Z |
| Test File Count | 2 |
| Test Count | 10 |
| Command | scripts/run_test_evidence.sh ui --label ux-1-5-secret-access -- src/components/ConnectorWorkbench.test.tsx src/components/Sidebar.test.tsx |
| Raw Evidence Directory | test-results/evidence/0.11.3/ui/20260605T235122Z-ux-1-5-secret-access |

## Test Files

- dq-ui/src/components/ConnectorWorkbench.test.tsx
- dq-ui/src/components/Sidebar.test.tsx

## Assertions

- The connector workbench loads the connector sync status model, renders provider-specific setup controls, and supports test, discovery, and sync actions against the backend routes.
- The sidebar exposes the canonical Administration &gt; Connectors entry point and maps the administration parent item to that workbench by default.

## Proof Data

```json
{
  "app_version": "0.11.3",
  "ui_command": "scripts/run_test_evidence.sh ui --label ux-1-5-secret-access -- src/components/ConnectorWorkbench.test.tsx src/components/Sidebar.test.tsx",
  "ui_evidence_directory": "test-results/evidence/0.11.3/ui/20260605T235122Z-ux-1-5-secret-access",
  "ui_tests": 10,
  "shared_primitives": [
    "AppBadge",
    "AppEmptyState",
    "AppInput",
    "AppPageHeader",
    "AppPageShell",
    "AppPanel",
    "AppSelect",
    "AppTabs",
    "AppTextarea"
  ]
}
```
