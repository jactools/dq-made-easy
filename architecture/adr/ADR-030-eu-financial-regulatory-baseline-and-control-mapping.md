# ADR-030: EU Financial Regulatory Baseline and Control Mapping

**Status**: Accepted  
**Date**: 2026-04-22  
**Related**: [ADR-018](./ADR-018-iso-11179-based-data-definition-framework-for-bcbs-239-and-mifid-ii.md), [ADR-029](./ADR-029-eu-financial-c3-security-baseline-mandate.md), [EU Financial C=3 Security Requirements](../../docs/technical/EU_FINANCIAL_C3_SECURITY_REQUIREMENTS.md), [EU Financial Regulatory Control Mapping](../../docs/technical/EU_FINANCIAL_REGULATORY_CONTROL_MAPPING.md), [ISO 11179 Data Definition Framework](../../docs/technical/ISO_11179_DATA_DEFINITION_FRAMEWORK.md), [Log Retention and Disposal Policy](../../docs/technical/LOG_RETENTION_AND_DISPOSAL_POLICY.md), [Log Integrity and Access Control Policy](../../docs/technical/LOG_INTEGRITY_AND_ACCESS_CONTROL.md)

## Context

dq-rulebuilder is being positioned for financial-sector use cases where architecture, controls, and evidence must support regulated data, reporting, governance, privacy, and resilience expectations.

The repository already contains targeted decisions and policies for parts of that problem:

- [ADR-018](./ADR-018-iso-11179-based-data-definition-framework-for-bcbs-239-and-mifid-ii.md) covers governed data definitions and explicitly supports BCBS 239 and MiFID II-style traceability and auditability.
- [ADR-029](./ADR-029-eu-financial-c3-security-baseline-mandate.md) establishes a security baseline for `C=3` financial-institution handling.
- Logging, retention, access-control, and internal transport decisions already exist in narrower artifacts.

What is still missing is one architecture-level statement that makes the relevant regulatory baseline explicit and defines how the repository should treat that baseline in architecture work.

For this repository, the relevant regulatory and supervisory reference set includes:

- BCBS 239 for risk-data aggregation, traceability, governance, and evidence,
- GDPR for personal-data protection, retention, disposal, and access discipline,
- CRR for controlled, traceable, and reviewable prudential-reporting data dependencies,
- MiFID II for record-keeping, controlled data semantics, and auditability,
- EMIR for trade/reporting data lineage, timeliness, and evidentiary traceability,
- DORA for ICT risk management, resilience, incident readiness, third-party risk, and operational control.

These sources do not all impose the same type of obligation on the repository itself, and some obligations remain institution-specific. The architecture still needs to treat them as a governing baseline for design, evidence, and deviation handling rather than as optional background reading.

## Decision

Adopt the above financial regulatory and supervisory set as the explicit repository architecture baseline for regulated financial-sector use cases.

For this ADR:

1. The repository MUST treat BCBS 239, GDPR, CRR, MiFID II, EMIR, and DORA as named governing reference domains when architecture decisions materially affect regulated data, personal data, reporting data, audit evidence, resilience, or security control surfaces.
2. Architecture work MUST map affected decisions, requirements, and implementation artifacts to one or more of the following control areas:
   - governed data definitions and lineage,
   - data accuracy, completeness, and traceability,
   - personal-data protection and retention,
   - access control and privileged access,
   - cryptography and secure transport,
   - audit logging, evidence retention, and record-keeping,
   - resilience, incident readiness, and third-party dependency risk.
3. Where the repository introduces or changes a cross-cutting control in one of those areas, the governing ADR, requirement, feature, implementation plan, or deviation record MUST cite the affected regulatory domain explicitly.
4. The repository MUST prefer explicit control mapping and evidence paths over generic compliance claims.
5. No artifact in the repository may imply that the repository alone establishes full legal or regulatory compliance for a financial institution. Institution-specific legal interpretation, operating model, and deployment controls remain out of scope for repository-only claims.
6. Existing targeted artifacts remain authoritative in their own domains, especially:
   - [ADR-018](./ADR-018-iso-11179-based-data-definition-framework-for-bcbs-239-and-mifid-ii.md) for BCBS 239 and MiFID II-aligned data-definition governance,
   - [ADR-029](./ADR-029-eu-financial-c3-security-baseline-mandate.md) and [EU Financial C=3 Security Requirements](../../docs/technical/EU_FINANCIAL_C3_SECURITY_REQUIREMENTS.md) for security and resilience baselines aligned to DORA-style expectations,
   - [Log Retention and Disposal Policy](../../docs/technical/LOG_RETENTION_AND_DISPOSAL_POLICY.md) and [Log Integrity and Access Control Policy](../../docs/technical/LOG_INTEGRITY_AND_ACCESS_CONTROL.md) for retention, audit, access, and privacy-relevant logging controls.
7. If current repository behavior falls short of this regulatory baseline, the gap MUST be implemented, planned, or registered in [ARCHITECTURE_DEVIATIONS_AND_EXCEPTIONS.md](../ARCHITECTURE_DEVIATIONS_AND_EXCEPTIONS.md).

## Consequences

### Positive

- The repository gains one clear architecture anchor for financial-sector regulation instead of relying on scattered references.
- Future ADRs and requirements can state which regulatory domain they support without repeating the full baseline each time.
- Gaps in privacy, reporting traceability, resilience, access control, and evidence become easier to classify and track.
- Existing work on BCBS 239, MiFID II, C=3 security, logging, retention, and deviations now sits under one explicit architecture umbrella.

### Negative

- More architecture and implementation changes will need explicit regulatory-domain mapping.
- Review overhead increases because vague control language is no longer sufficient for regulated features.
- Current gaps that were previously implicit may now need to be documented as deviations or new requirements.

## Implementation Notes

- Use this ADR as the cross-cutting regulatory reference when writing new ADRs, requirement documents, security features, implementation plans, and deviation entries.
- Keep domain-specific normative detail in targeted artifacts rather than overloading this ADR.
- Prefer repository language such as "supports", "maps to", or "provides evidence for" over blanket compliance wording.
- Where a regulatory domain is only partially covered today, record the gap explicitly instead of implying full coverage.
- Use the architecture deviation register for temporary exceptions, incomplete controls, or deployment-specific gaps.