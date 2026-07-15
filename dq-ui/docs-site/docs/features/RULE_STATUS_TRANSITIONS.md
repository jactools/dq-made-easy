# Rule Status Transitions

Status: Done

This document lists the allowed lifecycle transitions for rules, rule lifecycle, and approvals in the FastAPI backend.

The backend source of truth is the governance model at `/api/v1/governance/status-models/rule`, `/api/v1/governance/status-models/rule_lifecycle`, and `/api/v1/governance/status-models/approval`.

## Rule transitions

| From | To | Required scope |
| --- | --- | --- |
| draft | testing | dq:rules:test or dq:rules:write |
| testing | tested | dq:rules:test or dq:rules:write |
| tested | pending-approval | dq:rules:create or dq:rules:write |
| draft | pending-approval | dq:rules:create or dq:rules:write |
| rejected | pending-approval | dq:rules:create or dq:rules:write |
| pending-approval | approved | dq:rules:approve |
| pending-approval | rejected | dq:rules:approve |
| approved | activated | dq:rules:activate |
| activated | deactivated | dq:rules:approve |
| deactivated | removed | dq:rules:delete or dq:rules:write |
| removed | recovered | dq:users:manage |
| recovered | pending-approval | dq:rules:create or dq:rules:write |
| rejected | draft | dq:rules:edit or dq:rules:write |

## Rule lifecycle transitions

| From | To | Required scope |
| --- | --- | --- |
| active | deprecated | dq:rules:write |
| active | superseded | dq:rules:write |
| active | retired | dq:rules:delete or dq:rules:write |
| deprecated | active | dq:rules:write |
| deprecated | superseded | dq:rules:write |
| deprecated | retired | dq:rules:delete or dq:rules:write |
| superseded | retired | dq:rules:delete or dq:rules:write |

## Approval transitions

| From | To | Required scope |
| --- | --- | --- |
| pending | approved | dq:rules:approve |
| pending | rejected | dq:rules:approve |

## Enforcement notes

- The rule status transition matrix is enforced server-side before rules are activated, deactivated, removed, recovered, or updated.
- The rule lifecycle matrix is enforced server-side before `PATCH /api/rulebuilder/v1/rules/&#123;rule_id&#125;/lifecycle` persists `lifecycle_status` changes.
- The approval workflow also validates the matrix before persisting a review decision.
- Rule creation is treated as a bootstrap case and is not represented as a transition from a prior rule status.
- Rules list and detail payloads now expose `lifecycle_status`, and `GET /api/rulebuilder/v1/rules` supports backend-owned filtering via `lifecycle_status`.
- If the backend model changes, update this document and the governance endpoint together so the contract stays aligned.
