---
title: "generate_secrets.sh --force then --force --reuse-admin; verified admin passwords reused, service passwords rotated."
description: "Human-readable test proof generated from test-results/test-proof/0.11.6/infra/secrets-reuse-admin-2026-07-14.json."
---

# generate_secrets.sh --force then --force --reuse-admin; verified admin passwords reused, service passwords rotated.

This page was generated from [test-results/test-proof/0.11.6/infra/secrets-reuse-admin-2026-07-14.json](../../../../test-results/test-proof/0.11.6/infra/secrets-reuse-admin-2026-07-14.json).

## Summary

generate_secrets.sh --force then --force --reuse-admin; verified admin passwords reused, service passwords rotated.

## Metadata

| Field | Value |
| --- | --- |
| App Version | 0.11.6 |
| Proof Id | secrets-reuse-admin-2026-07-14 |
| Proof Type | infra |
| Feature | stack-scripts |
| Status | passed |
| Executed At Utc | 2026-07-14T12:00:02+00:00 |
| Test File Count | 1 |
| Test Count | 3 |
| Command | generate_secrets.sh --force then --force --reuse-admin; verify admin reused, service rotated |
| Raw Evidence Directory | test-results/evidence/0.11.5/infra/20260714T120002Z-secrets-reuse-admin |

## Test Files

- scripts/supporting/generate_secrets.sh

## Assertions

- Admin passwords are preserved after --reuse-admin rotation
- Service passwords are rotated in a --reuse-admin run
- Non-admin variables remain unchanged across rotations
