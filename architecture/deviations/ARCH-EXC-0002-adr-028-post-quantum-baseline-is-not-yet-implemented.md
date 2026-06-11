# ARCH-EXC-0002: ADR-028 Post-Quantum Baseline Is Not Yet Implemented

**Status**: Approved
**Category**: post-quantum
**Owner**: Platform Security
**First recorded**: 2026-04-22
**Last reviewed**: 2026-04-22
**Next review date**: 2026-05-15
**Target closure date**: 2026-12-31
**Risk level**: critical
**Impact level**: high
**Governing baseline**: [ADR-028 Post-Quantum Cryptography Must Be Implemented by 2026-12-31](../adr/ADR-028-post-quantum-cryptography-must-be-implemented-by-2026-12-31.md), [SEC-2 Post-Quantum Cryptography Readiness](../../docs/features/SEC_2_POST_QUANTUM_READINESS.md), [ADR-029 EU Financial C=3 Security Baseline Mandate](../adr/ADR-029-eu-financial-c3-security-baseline-mandate.md), [DQ-SEC-EU-C3-001](../../docs/technical/EU_FINANCIAL_C3_SECURITY_REQUIREMENTS.md)

## Affected Surface

Repository-managed cryptographic baseline across transport, certificates, trust distribution, and security-sensitive runtime paths.

## Summary

The repository has accepted a hard post-quantum deadline, but no repository-managed hybrid or post-quantum implementation baseline is in place yet.

## Rationale

SEC-2 planning and ADR-028 were only just established, and the repository currently lacks implemented hybrid or PQ-capable transport, trust, or validation paths.

## Risk Details

Without an explicit tracked deviation, ADR-028 could exist only as policy text while delivery remains classical-only through most of 2026, creating deadline, compliance, and security modernization risk.

## Impact Details

The gap affects certificate tooling, transport migration planning, runtime validation, release-readiness controls, and exception governance across multiple services.

## Compensating Controls

[SEC_2_POST_QUANTUM_IMPLEMENTATION_PLAN.md](../../docs/implementation-details/SEC_2_POST_QUANTUM_IMPLEMENTATION_PLAN.md) now defines dated workstreams and gates, and the architecture deviation register makes deadline risk explicit instead of leaving it implicit.

## Validation and Evidence

- [create_certs.sh](../../scripts/create_certs.sh) currently provisions local certificates with `mkcert` and `openssl` for local development.
- The repository contains no implemented or documented hybrid/PQ runtime path yet.
- [SEC_2_POST_QUANTUM_IMPLEMENTATION_PLAN.md](../../docs/implementation-details/SEC_2_POST_QUANTUM_IMPLEMENTATION_PLAN.md) was added because the implementation baseline is still missing.

## Exit Criteria

The SEC-2 implementation gates are met, at least one repository-managed secure path is validated against the approved target pattern, and any remaining blocked surfaces are narrowed to explicit approved exceptions only.