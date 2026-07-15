---
title: "Test stack.sh help output, argument parsing, child script existence. 19 tests passed."
description: "Human-readable test proof generated from test-results/test-proof/0.11.6/infra/stack-orchestrator-2026-07-14.json."
---

# Test stack.sh help output, argument parsing, child script existence. 19 tests passed.

This page was generated from [test-results/test-proof/0.11.6/infra/stack-orchestrator-2026-07-14.json](../../../../test-results/test-proof/0.11.6/infra/stack-orchestrator-2026-07-14.json).

## Summary

Test stack.sh help output, argument parsing, child script existence. 19 tests passed.

## Metadata

| Field | Value |
| --- | --- |
| App Version | 0.11.6 |
| Proof Id | stack-orchestrator-2026-07-14 |
| Proof Type | infra |
| Feature | stack-scripts |
| Status | passed |
| Executed At Utc | 2026-07-14T12:00:05+00:00 |
| Test File Count | 6 |
| Test Count | 19 |
| Command | test stack.sh help output, argument parsing, child script existence |
| Raw Evidence Directory | test-results/evidence/0.11.5/infra/20260714T120005Z-stack-orchestrator |

## Test Files

- scripts/stack.sh
- scripts/stack_start.sh
- scripts/stack_stop.sh
- scripts/stack_destroy.sh
- scripts/stack_restart.sh
- scripts/stack_seed.sh

## Assertions

- Help output lists all subcommands with descriptions
- Argument validation rejects invalid subcommands
- All referenced child scripts exist and are executable
- Argument parsing correctly routes to child scripts
