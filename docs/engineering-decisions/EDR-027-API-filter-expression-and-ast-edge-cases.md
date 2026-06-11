# EDR-027 [API]: Filter-Expression and AST Edge-Case Rules

**Status**: Accepted
**Date**: 2026-04-20
**Tag**: API

## Context
Rule compilation and filter validation both depend on expression parsing behaving sensibly at the edges. Small parser mistakes caused valid expressions to be rejected or produced noisy warnings for boolean predicates that should be accepted.

## Decision
- Validate logical-operator placement with token boundaries rather than naive string-prefix checks.
- Accept bare boolean predicates in the AST/compiler path by normalizing them to explicit truth evaluation.
- Preserve regression coverage for common edge cases that previously failed, such as identifiers with operator-like prefixes and boolean function predicates.

## Rationale
- Token-boundary checks avoid false positives on valid identifiers.
- Bare boolean predicates are a legitimate expression form and should not be treated as parser anomalies.
- These parser fixes are small but high impact because they affect rule authoring and compilation reliability.

## Scope Boundaries
This decision covers selected parser and AST edge cases.

It does not by itself define:
- the full expression grammar
- parser optimization or caching strategy
- general compiler architecture

## Consequences
**Positive**
- Valid filter expressions are less likely to be rejected incorrectly.
- Compiler behavior is more predictable for boolean predicate expressions.

**Negative**
- Parser changes still require targeted regression tests to prevent new edge-case drift.

## Implementation Guidance
- Use token-aware logical-operator validation.
- Normalize bare boolean predicates to explicit truth semantics.
- Keep focused parser/compiler regression tests for known edge cases.

## Related Artifacts
- `/memories/repo/dq-rulebuilder-fastapi-filter-expression-prefix-or-edge-note.md`
- `/memories/repo/dq-rulebuilder-fastapi-ast-bare-boolean-predicate-note.md`
