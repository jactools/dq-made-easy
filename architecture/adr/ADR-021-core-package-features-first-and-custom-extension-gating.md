# ADR-021: Core Package Features First and Custom Extension Gating

**Status**: Accepted
**Date**: 2026-04-20
**Related**: [ADR-011](./ADR-011-executable-rule-transformation-strategy-dsl-first-with-great-expectations-adapter.md), [ADR-014](./ADR-014-gx-suite-registry-pyspark-execution-and-exception-store-separation.md)

## Context

dq-rulebuilder increasingly depends on mature external platforms and libraries such as Great Expectations. Those packages already provide well-defined execution semantics, validation behavior, and interoperability contracts.

At the same time, the platform also has:

- a canonical DQ DSL and compiler pipeline,
- runtime-specific adapters such as the GX adapter,
- custom worker-backed expectations and execution helpers for unsupported semantics.

Without an explicit policy, it is too easy to introduce custom extensions where a package core feature already exists, or where the same outcome could be expressed in the DSL and then lowered through the canonical compiler/adaptation path. That creates avoidable semantic drift, extra maintenance cost, and weaker portability.

The platform needs a clear decision rule for when custom extensions are allowed.

## Decision

Adopt a **core-package-features-first policy** for external runtime packages and libraries.

For packages such as Great Expectations:

1. If required functionality exists as a stable package core feature, the implementation must use that core feature instead of adding a custom extension or parallel reimplementation.
2. If the required behavior can be expressed through the platform DSL and lowered through the canonical compiler or adapter path, that route must be preferred over a package-specific custom extension.
3. A custom extension is allowed only when both of the following are true:
   - the functionality does not exist as a suitable core feature in the package, and
   - the functionality cannot be covered by the DSL and its canonical lowering path without losing required semantics.

For GX specifically, this means:

- prefer GX Core expectation classes, row conditions, and supported execution APIs first,
- prefer DSL-to-GX lowering when a rule can be represented canonically,
- add custom worker-backed expectations only for genuine GX Core gaps that the DSL also cannot cover directly.

## Consequences

### Positive

- Runtime behavior stays closer to the semantics and guarantees of the upstream package.
- The platform reduces duplicate logic and semantic drift between native and custom implementations.
- Interoperability improves because suites and artifacts stay closer to standard package contracts.
- Future upgrades are easier because fewer custom surfaces shadow upstream capabilities.

### Negative

- Some implementations may require extra design work to discover and exploit package core features before writing custom code.
- Teams must maintain an explicit compatibility matrix and evidence when claiming that a core feature does not exist.
- Some custom code paths will need periodic review and possible retirement as upstream packages evolve.

## Implementation Guidance

- During design or PR review, document the decision path explicitly:
  - core package feature available and used,
  - or DSL lowering used,
  - or custom extension required with evidence for why the first two options are insufficient.
- Treat custom extensions as exception paths, not the default implementation strategy.
- When a custom extension is introduced, include:
  - the missing core-package capability,
  - the reason DSL coverage is insufficient,
  - tests proving required behavior,
  - a note in the relevant compatibility matrix or implementation progress document.
- Revisit existing custom extensions when upstream package releases add matching core functionality.
- Fail fast rather than silently downgrading from a core feature to a custom approximation when exact semantics are required.

## Related Artifacts

- [DQ_4_NEW_RULE_TYPES_PROGRESS.md](../../docs/implementation-details/DQ_4_NEW_RULE_TYPES_PROGRESS.md)
- [DQ-1_RULE_VALIDATION_USER_GUIDE.md](../../docs/user-manuals/DQ-1_RULE_VALIDATION_USER_GUIDE.md)
- [DQ-2_JOIN_CONDITIONS_USER_GUIDE.md](../../docs/user-manuals/DQ-2_JOIN_CONDITIONS_USER_GUIDE.md)
- [ADR-011](./ADR-011-executable-rule-transformation-strategy-dsl-first-with-great-expectations-adapter.md)
- [ADR-014](./ADR-014-gx-suite-registry-pyspark-execution-and-exception-store-separation.md)