---
title: "The revamped Audit Trail page renders rule, data-definition, validation, and approval history from the canonical backend seams, and keeps audit reporting on the dedicated audit surface instead of extending compliance."
description: "Human-readable test proof generated from test-results/test-proof/0.11.3/ui/ws8-a02-audit-trail-2026-06-05.json."
---

# The revamped Audit Trail page renders rule, data-definition, validation, and approval history from the canonical backend seams, and keeps audit reporting on the dedicated audit surface instead of extending compliance.

This page was generated from [test-results/test-proof/0.11.3/ui/ws8-a02-audit-trail-2026-06-05.json](../../../../test-results/test-proof/0.11.3/ui/ws8-a02-audit-trail-2026-06-05.json).

## Summary

The revamped Audit Trail page renders rule, data-definition, validation, and approval history from the canonical backend seams, and keeps audit reporting on the dedicated audit surface instead of extending compliance.

## Metadata

| Field | Value |
| --- | --- |
| App Version | 0.11.3 |
| Proof Id | ws8-a02-audit-trail-2026-06-05 |
| Proof Type | ui |
| Feature | WS8-A02 |
| Status | passed |
| Executed At Utc | 2026-06-05T22:06:10Z |
| Test File Count | 1 |
| Test Count | 1 |
| Command | scripts/run_test_evidence.sh ui --label ws8-a02-audit-trail -- src/components/AuditTrail.test.tsx --reporter=dot --no-isolate --no-file-parallelism --maxWorkers=1 --minWorkers=1 --pool=forks |
| Raw Evidence Directory | test-results/evidence/0.11.3/ui/20260605T220610Z-ws8-a02-audit-trail |

## Test Files

- dq-ui/src/components/AuditTrail.test.tsx

## Assertions

- The Audit Trail page renders the canonical rule, data-definition, validation, and approval history sections.
- The page fetches the expected history endpoints for rule status, data-definition requests, validation runs, and approvals.

## Proof Data

```json
{
  "app_version": "0.11.3",
  "ui_command": "scripts/run_test_evidence.sh ui --label ws8-a02-audit-trail -- src/components/AuditTrail.test.tsx --reporter=dot --no-isolate --no-file-parallelism --maxWorkers=1 --minWorkers=1 --pool=forks",
  "ui_evidence_directory": "test-results/evidence/0.11.3/ui/20260605T220610Z-ws8-a02-audit-trail",
  "ui_tests": 1,
  "shared_primitives": [
    "AppTabs",
    "AppButton",
    "AppSelect",
    "AppIcon"
  ]
}
```
