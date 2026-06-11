# DQ-7 DSL Rollout Policy

> **Status:** [~] Active rollout policy
> **Audience:** operators and maintainers
> **Scope:** DQ7-DSL-022 rollout controls only

## Purpose

This document records the rollout policy for DQ7 DSL 2.0.0. It is intentionally separate from user-facing capability guidance and UI discovery cards.

## What it does

- Uses the app-config flag `featureRuleDslV2` as the explicit opt-in control for `2.0.0` payloads.
- Keeps the rollout decision in backend/admin configuration, not in the user manuals.
- Lets the backend reject mixed contracts and unsupported compatibility shapes before persistence or execution.
- Keeps the user-manual cards focused on supported shapes, examples, and discovery flow.

## What it does not do

- It does not describe engine capabilities.
- It does not tell users which backend to pick.
- It does not turn the UI capability matrix into a rollout mechanism.
- It does not add fallback behavior for disabled or mixed DQ DSL payloads.

## Operational control

- Enable the rollout gate only when the environment is ready for canonical `2.0.0` ingestion.
- Leave the gate disabled when the environment must continue to reject `2.0.0` at the mutation boundary.
- Use the admin app-config surface to manage the flag; do not expose it through the user-manual cards.

## Related implementation

- Backend gate: [dq-api/fastapi/app/application/use_cases/rule_mutation.py](../../dq-api/fastapi/app/application/use_cases/rule_mutation.py)
- Admin config surface: [dq-ui/src/components/ApplicationSettings.tsx](../../dq-ui/src/components/ApplicationSettings.tsx)
- Rollout plan item: [DQ_7_ENGINE_INDEPENDENT_DSL_IMPLEMENTATION_PLAN.md](DQ_7_ENGINE_INDEPENDENT_DSL_IMPLEMENTATION_PLAN.md)
