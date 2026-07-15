# ADR-020: Shared Runtime Domain Validation Wheel

**Status**: Proposed
**Date**: 2026-04-17
**Related**: [ADR-017](./ADR-017-canonical-snake_case-api-fields.md), [ADR-019](./ADR-019-platform-business-keys-and-stable-identity-surfaces.md)

## Context

dq-rulebuilder currently enforces allowed values in several different ways:

- `Literal[...]` annotations in FastAPI schemas
- ad hoc `set` membership checks in endpoint code
- one-off `ValueError` and `HTTPException` guards in service logic

Those approaches work locally, but they duplicate contract knowledge across API modules and make it difficult to version or audit allowed-value changes independently from the services that consume them.

The platform needs a shared runtime validator that can be published as a wheel, versioned separately, and imported consistently by every API service.

## Decision

Adopt a dedicated Python package, `dq-domain-validation`, as the shared runtime domain-validation layer for dq-made-easy APIs.

The package will:

- store allowed-value sets as versioned package data, not embedded enums inside each API
- expose pure validation helpers for runtime use
- expose Pydantic-compatible types so request and response models can keep using FastAPI validation
- fail fast when a requested value is not part of the registered domain contract

API services should use this package instead of defining new `Enum`, `Literal`, or ad hoc allowlist checks for values that represent shared domain rules.

## Consequences

### Positive

- Allowed-value changes become versioned and reviewable in one place.
- APIs share the same validation semantics and error shape.
- Request models stay declarative while runtime rules stay centralized.
- The package can be released independently of API code when shared contracts change.

### Negative

- The build and deployment pipeline now needs to install an additional wheel.
- Contract changes require a package release, not just an API patch.
- Some API schemas will need migration work to replace existing literals and ad hoc checks.

## Implementation Guidance

- Keep the package small, pure, and dependency-light.
- Store allowed values as package data so changes are diffable and auditable.
- Use Pydantic adapters for request/response models and plain helper functions for service logic.
- Do not move API-specific business logic into the shared package.
- Prefer shared aliases over repeated inline literals when a value set is reused across services.
- Preserve fail-fast behavior when a value is missing or not allowed.

## Related Artifacts

- [dq-domain-validation/README.md](../../dq-domain-validation/README.md)
- [BUSINESS_KEYS.md](../../docs/features/BUSINESS_KEYS.md)
- [ABS_3_DELIVERY_LINKED_RULE_EXECUTION_IMPLEMENTATION_DETAILS.md](../../docs/implementation-details/ABS_3_DELIVERY_LINKED_RULE_EXECUTION_IMPLEMENTATION_DETAILS.md)