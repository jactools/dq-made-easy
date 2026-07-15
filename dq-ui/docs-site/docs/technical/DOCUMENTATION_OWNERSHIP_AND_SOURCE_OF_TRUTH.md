# Documentation Ownership And Source-Of-Truth Boundaries

Purpose: define one canonical ownership model and one source-of-truth boundary model for feature, current-state, technical, and user documentation.

Status: active policy for documentation updates.

## Audience And Entry Points

| Audience | Primary need | Canonical entry point |
| --- | --- | --- |
| Product, planning, and delivery coordination | Planned scope, acceptance criteria, and sequencing | `docs/features/` and `docs/features/roadmap/` |
| Operators and maintainers | Runtime operations, deployment, troubleshooting, and reliability controls | `docs/technical/`, `docs/runbooks/`, and `docs/engineering-decisions/` |
| Developers and integrators | Contracts, implementation boundaries, and architecture intent | `docs/contracts/`, `docs/technical/`, and `architecture/` |
| End users (analysts, approvers, stewards, admins) | Task-oriented product workflows | `docs/user-manuals/` |
| Leadership and status consumers | What is implemented vs what remains | `docs/features/current/` and `docs/features/roadmap/` |

## Canonical Boundaries

| Documentation family | Source-of-truth scope | Must not be used as source-of-truth for | Primary owner |
| --- | --- | --- | --- |
| `docs/features/` | Planned work definition: goals, backlog decomposition, acceptance criteria, and sequencing | Claims that work is implemented and released unless mirrored in current-state docs | Product owner + feature lead |
| `docs/features/roadmap/` | Cross-workstream future-state prioritization and implementation tracking (`WS*`, `AC*`) | Detailed implementation instructions or operator runbooks | Product/program management |
| `docs/features/current/` | Implemented and validated state snapshots | Future planning or unreleased commitments | Engineering management + owning team |
| `docs/technical/` | Canonical technical behavior, contracts-in-practice, and operational architecture guidance | User workflow walkthroughs and product onboarding copy | Technical owner for the subsystem |
| `docs/runbooks/` | Operational execution procedures and incident handling | Feature planning or UX guidance | Operations/on-call owner |
| `docs/engineering-decisions/` and `architecture/` | Decision rationale, constraints, and architecture governance | Daily operator steps or marketing/user workflow material | Architecture owner / maintainers |
| `docs/user-manuals/` | End-user task flows and role-focused usage guidance | Internal implementation details and planning backlogs | UX/product documentation owner |
| `docs/contracts/` | Versioned request/response and artifact contract definitions | Narrative architecture or workflow instruction | API/contract owner |

## Conflict Resolution Order

When documentation appears inconsistent, resolve in this order and then update lagging docs:

1. Versioned contracts and enforced runtime behavior (`docs/contracts/`, running API behavior).
2. Engineering decisions and architecture decisions (`docs/engineering-decisions/`, `architecture/`).
3. Technical and runbook docs (`docs/technical/`, `docs/runbooks/`).
4. Current-state status snapshots (`docs/features/current/`).
5. Feature and roadmap planning docs (`docs/features/`, `docs/features/roadmap/`).
6. User manuals (which should reflect implemented behavior only).

Notes:

- If runtime behavior and docs disagree, runtime plus contract enforcement is authoritative until docs are corrected.
- Feature and roadmap docs are planning authority, not implementation authority.

## Documentation Ownership Model

Each documentation update must identify one owner role and one review role:

| Change type | Required owner | Required reviewer |
| --- | --- | --- |
| New or changed feature planning scope | Feature lead | Product owner |
| New or changed production behavior | Owning engineer | Technical owner |
| New or changed deployment/operations procedure | Operations owner | Service owner |
| New or changed end-user flow | UX or product documentation owner | Feature owner |
| New or changed contract surface | API/contract owner | Consumer owner |

## Required Update Triggers

Update the relevant documentation family in the same change when any of the following occurs:

- A new endpoint, payload contract, or compatibility policy change is introduced.
- A startup, deployment, auth, security, or observability procedure changes.
- A user-visible workflow changes.
- A roadmap item is implemented and moved from planned to delivered.

## Minimal Release-Time Documentation Checklist

1. Current-state status updated if behavior is now implemented.
2. Roadmap/feature item status updated if planned scope changed.
3. Technical or runbook docs updated for operator-impacting changes.
4. User-manual content updated for user-facing workflow changes.

## WS-9 Coverage

This document implements `WS9-A01` by establishing explicit ownership and source-of-truth boundaries across feature, current-state, technical, and user documentation families.