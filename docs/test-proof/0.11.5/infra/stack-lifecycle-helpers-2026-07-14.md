---
title: "Source stack_lifecycle.sh; tested is_admin_password_var, _derive_env_suffix, _get_project_prefix, STATEFUL_VOLUME_NAMES. 24 tests passed."
description: "Human-readable test proof generated from test-results/test-proof/0.11.5/infra/stack-lifecycle-helpers-2026-07-14.json."
---

# Source stack_lifecycle.sh; tested is_admin_password_var, _derive_env_suffix, _get_project_prefix, STATEFUL_VOLUME_NAMES. 24 tests passed.

This page was generated from [test-results/test-proof/0.11.5/infra/stack-lifecycle-helpers-2026-07-14.json](../../../../test-results/test-proof/0.11.5/infra/stack-lifecycle-helpers-2026-07-14.json).

## Summary

Source stack_lifecycle.sh; tested is_admin_password_var, _derive_env_suffix, _get_project_prefix, STATEFUL_VOLUME_NAMES. 24 tests passed.

## Metadata

| Field | Value |
| --- | --- |
| App Version | 0.11.5 |
| Proof Id | stack-lifecycle-helpers-2026-07-14 |
| Proof Type | infra |
| Feature | stack-scripts |
| Status | passed |
| Executed At Utc | 2026-07-14T12:00:04+00:00 |
| Test File Count | 1 |
| Test Count | 24 |
| Command | source stack_lifecycle.sh; test is_admin_password_var, _derive_env_suffix, _get_project_prefix, STATEFUL_VOLUME_NAMES |
| Raw Evidence Directory | test-results/evidence/0.11.5/infra/20260714T120004Z-stack-lifecycle-helpers |

## Test Files

- scripts/supporting/stack_lifecycle.sh

## Assertions

- is_admin_password_var classifies admin variables correctly
- _derive_env_suffix produces correct suffixes for dev/test/prod
- _get_project_prefix derives correct prefix from compose files
- STATEFUL_VOLUME_NAMES lists all expected stateful volumes
