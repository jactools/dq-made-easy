# EDR-001 [META]: Engineering Decision Records Scope and Usage

**Status**: Accepted
**Date**: 2026-04-19
**Tag**: META

## Context
This repository has accumulated many important engineering decisions outside the ADR set. Some were captured in standalone markdown files, some in implementation notes, and some only in repository memory notes. Those sources are useful during active work, but they are not a stable or easily discoverable system of record.

The existing ADR set under `architecture/adr/` should remain the home for architecture-level and platform-level decisions. However, many decisions made during implementation and operations are narrower in scope: validation tooling behavior, observability conventions, runtime execution choices, repository-specific workflows, or other engineering constraints that are important but do not need to be elevated to full ADR status.

## Decision
Adopt **Engineering Decision Records (EDRs)** under `docs/engineering-decisions/` for repository-scoped engineering decisions.

Use EDRs for stable technical decisions such as:
- Validation and test-runner behavior
- Runtime and worker-operation conventions
- Observability and monitoring implementation choices
- Repository-specific integration constraints
- Documentation, tooling, and developer workflow conventions

Use ADRs for broader architecture and platform decisions such as:
- Primary execution architecture
- API/platform technology choices
- Long-lived system boundaries and cross-cutting design rules

Repository memory notes, one-off implementation summaries, and ad hoc markdown files are input material for future EDRs, not the authoritative final record.

## Rationale
- Creates a durable, searchable decision trail for important repo-scoped technical choices.
- Preserves the ADR series for higher-level architectural decisions instead of diluting it.
- Gives implementation teams a lightweight format for documenting decisions that matter operationally.
- Reduces the chance that decisions remain trapped in transient notes or chat memory.

## Scope Boundaries
EDRs are intended for accepted or actively proposed repository-scoped engineering decisions.

EDRs are not intended to replace:
- ADRs for architecture-level decisions
- Feature trackers for delivery status
- Implementation-details documents for step-by-step build notes
- Repository memory notes for short-lived or working-context observations

## Consequences
**Positive**
- More technical decisions become explicit, linkable, and reviewable.
- Important repo-scoped conventions can be documented without forcing them into ADR scope.
- Existing implementation notes and memory entries can be backfilled gradually into a durable format.

**Negative**
- Introduces another documentation surface that must be maintained.
- Requires editorial judgment to distinguish ADR-worthy decisions from EDR-worthy ones.
- Backfilling older decisions will take time and may happen incrementally.

## Implementation Guidance
- Store EDRs in `docs/engineering-decisions/`.
- Name files `EDR-XXX-short-kebab-title.md`.
- Use the template in `docs/engineering-decisions/EDR_TEMPLATE.md`.
- Prefer one EDR per durable decision rather than bundling unrelated topics together.
- When a decision is superseded, keep the old EDR and record the replacement in a newer EDR.
- When a stable decision currently exists only in a memory note or ad hoc markdown file, promote it into an EDR and link the source material.

## Related Artifacts
- `architecture/adr/`
- `docs/implementation-details/`
- `docs/features/`
- `docs/engineering-decisions/EDR_TEMPLATE.md`
