# ADR-029: EU Financial C=3 Security Baseline Mandate

**Status**: Accepted  
**Date**: 2026-04-22  
**Related**: [ADR-016](./ADR-016-iso27001-logging-and-monitoring-policy-adoption.md), [ADR-027](./ADR-027-internal-service-communication-uses-repository-managed-tls.md), [ADR-028](./ADR-028-post-quantum-cryptography-must-be-implemented-by-2026-12-31.md), [Requirement](../../docs/technical/EU_FINANCIAL_C3_SECURITY_REQUIREMENTS.md)

## Context

dq-rulebuilder is being treated as a `C=3` application in a financial-institution context.

That classification raises the engineering security bar above a generic internal application baseline. The repository already has targeted security and observability decisions, but it does not yet have a single engineering baseline that explicitly states what a `C=3` financial-sector deployment must implement and demonstrate.

For EU-regulated financial institutions, security expectations are shaped by multiple overlapping sources, especially:

- DORA-style operational resilience and ICT risk-management expectations,
- NIS2-style cyber-risk governance expectations where applicable,
- supervisory expectations for access control, resilience, incident evidence, change management, third-party risk, and security monitoring.

The repository needs an explicit engineering mandate so those expectations are treated as implementation requirements instead of general background context.

## Decision

Adopt [EU_FINANCIAL_C3_SECURITY_REQUIREMENTS.md](../../docs/technical/EU_FINANCIAL_C3_SECURITY_REQUIREMENTS.md) as the mandatory engineering security baseline for dq-rulebuilder whenever it is handled as a `C=3` application for an EU financial-institution context.

For this ADR:

1. `C=3` is treated as a high-criticality application classification provided by product, security, or governance stakeholders.
2. The requirement document is normative for repository engineering decisions, implementation planning, release readiness, and exception handling.
3. Deviations from this baseline MUST be recorded in [ARCHITECTURE_DEVIATIONS_AND_EXCEPTIONS.md](../ARCHITECTURE_DEVIATIONS_AND_EXCEPTIONS.md) with owner, risk, impact, review date, and closure target.
4. Existing security ADRs and policies remain in force and are part of the baseline where referenced by the requirement document.
5. This ADR establishes an engineering baseline and does not replace formal legal, regulatory, or compliance interpretation by the institution.

## Consequences

### Positive

- Security expectations for a high-criticality financial-sector deployment become explicit and reviewable.
- Release readiness can enforce a consistent C=3 baseline instead of relying on ad hoc judgment.
- Architecture deviations become easier to justify, track, and close because the governing baseline is clear.
- Existing ADRs for logging, internal TLS, and post-quantum planning are tied into one higher-level compliance-driven requirement.

### Negative

- The repository gains additional governance overhead and evidence requirements.
- More changes will require explicit security review, exception handling, or compensating controls.
- Some current defaults may be out of baseline and will need remediation or formal deviation records.

## Implementation Notes

- The requirement document is the primary normative control list for engineering teams.
- Execution tasks and evidence tracking are captured in [EU_FINANCIAL_C3_SECURITY_IMPLEMENTATION_CHECKLIST.md](../../docs/technical/EU_FINANCIAL_C3_SECURITY_IMPLEMENTATION_CHECKLIST.md).
- Release readiness should include an explicit compliance check against the requirement ID.
- Architecture deviations remain the only approved route for temporary non-compliance.
- Related policies such as ISO 27001-aligned logging and monitoring continue to apply as referenced controls, not alternatives.