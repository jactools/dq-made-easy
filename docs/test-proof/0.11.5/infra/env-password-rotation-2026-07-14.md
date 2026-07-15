---
title: "seed_password_rotation.py --no-admin-rotate; verified admin passwords unchanged, service passwords rotated, non-password vars unchanged."
description: "Human-readable test proof generated from test-results/test-proof/0.11.5/infra/env-password-rotation-2026-07-14.json."
---

# seed_password_rotation.py --no-admin-rotate; verified admin passwords unchanged, service passwords rotated, non-password vars unchanged.

This page was generated from [test-results/test-proof/0.11.5/infra/env-password-rotation-2026-07-14.json](../../../../test-results/test-proof/0.11.5/infra/env-password-rotation-2026-07-14.json).

## Summary

seed_password_rotation.py --no-admin-rotate; verified admin passwords unchanged, service passwords rotated, non-password vars unchanged.

## Metadata

| Field | Value |
| --- | --- |
| App Version | 0.11.5 |
| Proof Id | env-password-rotation-2026-07-14 |
| Proof Type | infra |
| Feature | stack-scripts |
| Status | passed |
| Executed At Utc | 2026-07-14T12:00:03+00:00 |
| Test File Count | 1 |
| Test Count | 6 |
| Command | seed_password_rotation.py --no-admin-rotate; verify admin unchanged, service rotated |
| Raw Evidence Directory | test-results/evidence/0.11.5/infra/20260714T120003Z-env-password-rotation |

## Test Files

- scripts/seeding/seed_password_rotation.py

## Assertions

- Admin passwords are preserved when --no-admin-rotate is used
- Service passwords are rotated in a --no-admin-rotate run
- Non-password environment variables remain unchanged
