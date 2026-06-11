# Architecture Documentation

This directory contains repository-level architecture artifacts and is part of the source set that the public Docusaurus build copies into the site-local docs tree.

## Purpose

Use this directory for Architecture Decision Records (ADRs) and other cross-cutting architecture guidance that applies to the whole workspace.

## Contents

- `adr/`: canonical home for numbered ADR source files (`ADR-001`, `ADR-002`, ...).
- `ARCHITECTURAL_DECISIONS.md`: ADR index and register for the `adr/` directory.
- `ARCHITECTURE_DEVIATIONS_AND_EXCEPTIONS.md`: numbered register for approved, time-bounded architecture deviations and exceptions.
- `deviations/`: one file per numbered architecture deviation or exception (`ARCH-EXC-0001`, `ARCH-EXC-0002`, ...).

## Boundary

- `architecture/adr/` is the source of truth for ADRs.
- `docs/engineering-decisions/` is the separate EDR tree for repository-scoped engineering decisions.

## ADR Conventions

- Keep ADR numbering monotonic and never reuse numbers.
- Use this structure per ADR section:
  - `Status`
  - `Date`
  - `Context`
  - `Decision`
  - `Consequences`
- Update links in docs when adding or renaming ADR files.
- Keep decisions concise and implementation-oriented.

## Related Directory

- `dq-architecture/` contains high-level system architecture overview material (`info.md`).
- `architecture/` contains formal decisions and decision history.

## Consumption Notes

- Docusaurus consumes this tree through the public docs build pipeline.
- Keep numbered ADRs and deviation records here rather than editing the generated site tree directly.
