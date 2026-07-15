# ADR-028: Post-Quantum Cryptography Must Be Implemented by 2026-12-31

**Status**: Accepted
**Date**: 2026-04-22
**Related**: [ADR-016](./ADR-016-iso27001-logging-and-monitoring-policy-adoption.md), [ADR-027](./ADR-027-internal-service-communication-uses-repository-managed-tls.md), [SEC-2 Post-Quantum Cryptography Readiness](../../docs/features/SEC_2_POST_QUANTUM_READINESS.md)

## Context

The platform still relies primarily on classical cryptographic assumptions across transport security, certificate handling, token signing, secret exchange, and vendor-managed security surfaces.

That is acceptable only as a temporary state. The repository already depends on long-lived trust relationships and security-sensitive workflows that should not remain indefinitely tied to classical-only assumptions when post-quantum standards and hybrid migration paths are now part of forward security planning.

The repository also has a growing split between:

- cryptographic surfaces that are repository-managed or repository-configured,
- cryptographic surfaces that are vendor-managed but still part of the platform risk envelope,
- transport and trust changes already being planned under internal TLS work.

Without a deadline-backed architectural decision, post-quantum work risks staying stuck at “readiness” and “future investigation” without a mandatory delivery point.

## Decision

Adopt a repository-wide mandate that post-quantum cryptography implementation MUST be completed no later than 2026-12-31.

For this ADR, “implemented” means:

1. Repository-managed cryptographic surfaces have an approved and deployed post-quantum or hybrid classical-plus-post-quantum implementation where supported.
2. Repository-configured transport and trust surfaces use the approved post-quantum or hybrid model instead of remaining classical-only by default.
3. Surfaces that cannot meet the target because of vendor or ecosystem limitations are explicitly documented as named exceptions with owners, compensating controls, and removal plans by the same deadline.
4. Validation, operational documentation, and rollout controls exist so the implementation is testable and auditable rather than aspirational.

The deadline is normative:

- No later than 2026-12-31, post-quantum implementation must be part of the repository security baseline.
- Open-ended readiness-only status is not acceptable beyond that date.
- New security work should not introduce choices that block or materially delay this deadline.

The preferred implementation strategy is hybrid first where required for interoperability, standards alignment, or ecosystem compatibility. Pure post-quantum-only deployment is allowed only where compatibility and operational support are explicit.

## Consequences

### Positive

- The repository gains a hard security modernization deadline instead of an indefinite research track.
- Security planning for TLS, certificates, signatures, and trust distribution can converge on one timeline.
- Vendor-managed gaps must be surfaced explicitly instead of being hidden inside generic future work.
- Validation and operational readiness become mandatory parts of delivery rather than follow-up tasks.

### Negative

- The deadline creates delivery pressure across multiple components and third-party dependencies.
- Some services may need hybrid or transitional cryptographic support that increases implementation complexity.
- Vendor limitations may force exception tracking, compensating controls, or staged deployment patterns.
- Security and platform teams must maintain active review of standards and supported runtime/library versions through 2026.

## Implementation Notes

- SEC-2 is the primary planning track for inventory, compatibility policy, adoption sequencing, and governance.
- Execution tasks are tracked in [SEC_2_POST_QUANTUM_IMPLEMENTATION_PLAN.md](../../docs/implementation-details/SEC_2_POST_QUANTUM_IMPLEMENTATION_PLAN.md).
- Named blocked surfaces are tracked in [ARCHITECTURE_DEVIATIONS_AND_EXCEPTIONS.md](../../architecture/ARCHITECTURE_DEVIATIONS_AND_EXCEPTIONS.md).
- ADR-027 internal TLS work should be treated as one of the main execution vehicles for post-quantum transport adoption.
- Post-quantum rollout must remain fail-fast: do not silently downgrade a migrated surface back to classical-only behavior without an explicit documented exception.
- Validation and smoke coverage should be extended as soon as experimental or staged post-quantum paths exist.
- Exception records must name the blocked surface, blocking dependency, owner, compensating control, and target removal date.

## Deadline Control

- By 2026-06-30, the repository must have a complete cryptographic inventory and adoption matrix.
- By 2026-09-30, the repository must have approved target patterns for hybrid or post-quantum implementation on in-scope surfaces.
- By 2026-12-31, the repository security baseline must include implemented post-quantum or hybrid controls for in-scope surfaces, with only explicitly documented exceptions remaining.