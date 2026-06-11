# EU Financial Regulatory Gap Analysis

**Baseline**: [DQ-REG-EU-FIN-001](../EU_FINANCIAL_REGULATORY_CONTROL_MAPPING.md)  
**Version**: 1.0  
**Date**: 2026-04-22  
**Owner**: Engineering + Security + Compliance + Data Governance  
**Related ADR**: [ADR-030](../../../architecture/adr/ADR-030-eu-financial-regulatory-baseline-and-control-mapping.md)

## 1. Purpose

Provide a current-state repository gap analysis against the EU financial regulatory control baseline captured in [EU_FINANCIAL_REGULATORY_CONTROL_MAPPING.md](../EU_FINANCIAL_REGULATORY_CONTROL_MAPPING.md).

This analysis is intended to:

- identify material repository-level control gaps,
- separate documented controls from runtime-enforced controls,
- connect current gaps to existing evidence and deviations,
- guide future ADRs, requirements, implementation plans, and exception handling.

This is a repository engineering gap analysis, not a statement of institutional non-compliance or a legal assessment.

## 2. Assessment Method

Each gap is assessed using the following dimensions:

- **Regulatory domains**: which named baseline domains are affected,
- **Control area**: which repository control family is weak or incomplete,
- **Current state**: what exists now,
- **Severity**: relative engineering/compliance significance for repository planning,
- **Current treatment**: whether the gap is already planned, implemented, or explicitly deviated,
- **Next action**: the most direct repository follow-up.

## 3. Executive Summary

Current repository governance is strongest in these areas:

- architecture-level definition governance for BCBS 239 and MiFID II-aligned semantics,
- security and resilience baseline articulation for DORA-style expectations,
- logging, retention, redaction, and observability policy documentation,
- architecture deviation handling for known security/control gaps.

The most material remaining gaps are:

- no repository-wide data protection and data-access policy beyond narrower observability and auth surfaces,
- incomplete treatment of sensitive business-data classes and handling rules,
- only partial encryption-at-rest coverage for sensitive attributes,
- missing CRR- and EMIR-oriented reporting-control evidence packs or requirements,
- documented controls that are not yet fully enforced at runtime in internal transport and observability RBAC.

## 4. Gap Matrix

| Gap ID | Regulatory domains | Control area | Severity | Current treatment |
| --- | --- | --- | --- | --- |
| `EU-GAP-001` | BCBS 239, GDPR, CRR, MiFID II, EMIR, DORA | Data protection and data access policy | high | tracked by [ARCH-EXC-0006](../../../architecture/deviations/ARCH-EXC-0006-repository-wide-data-protection-and-data-access-policy-is-not-yet-defined.md) |
| `EU-GAP-002` | GDPR, BCBS 239, MiFID II, CRR, EMIR | Sensitive data classification and handling rules | high | partially covered in logging/redaction docs |
| `EU-GAP-003` | BCBS 239, GDPR, CRR, MiFID II, EMIR, DORA | Encryption at rest for sensitive attributes | high | partially implemented, not governed broadly |
| `EU-GAP-004` | DORA, GDPR | Secure internal transport not fully enforced | high | tracked by [ARCH-EXC-0001](../../../architecture/deviations/ARCH-EXC-0001-internal-service-transport-still-defaults-to-plaintext-links.md) |
| `EU-GAP-005` | DORA, GDPR | Observability RBAC documented but not runtime-enforced | high | tracked by [ARCH-EXC-0005](../../../architecture/deviations/ARCH-EXC-0005-c3-observability-rbac-is-documented-but-not-yet-enforced.md) |
| `EU-GAP-006` | CRR, EMIR, BCBS 239 | Regulated reporting evidence and control attestation | medium | baseline defined by [DQ-REG-CRR-EMIR-001](../CRR_EMIR_REPORTING_EVIDENCE_REQUIREMENTS.md); feature-specific evidence bundles still pending |
| `EU-GAP-007` | MiFID II, EMIR, CRR | Regulated workflow record-keeping controls | medium | only partially covered via generic audit/logging artifacts |

## 5. Detailed Gaps

### EU-GAP-001: Repository-Wide Data Protection and Data Access Policy Is Missing

- **Regulatory domains**: BCBS 239, GDPR, CRR, MiFID II, EMIR, DORA
- **Control area**: data protection, retention, disposal, access control
- **Severity**: high

**Current state**

- The repository has explicit access-control and protection language for observability, API scopes, and logging/redaction.
- The repository does not yet have one cross-cutting policy that states how business data, personal data, operational data, and sensitive data must be classified, accessed, reviewed, retained, and protected across the full platform.

**Evidence**

- [LOG_INTEGRITY_AND_ACCESS_CONTROL.md](../LOG_INTEGRITY_AND_ACCESS_CONTROL.md)
- [EDR-023-API-auth-scope-enforcement-and-role-based-access.md](../../engineering-decisions/EDR-023-API-auth-scope-enforcement-and-role-based-access.md)
- [EU_FINANCIAL_REGULATORY_CONTROL_MAPPING.md](../EU_FINANCIAL_REGULATORY_CONTROL_MAPPING.md)

**Why it matters**

- GDPR-style expectations require more than log-retention and redaction controls.
- DORA-style governance also expects clear control ownership and explicit policy treatment for sensitive operational and administrative data.
- BCBS 239, CRR, MiFID II, and EMIR expectations also require the repository to treat regulated data, evidence, and traceability as first-class policy concerns instead of assuming log and credential controls are sufficient.

**Current treatment**

- Explicitly tracked by [ARCH-EXC-0006](../../../architecture/deviations/ARCH-EXC-0006-repository-wide-data-protection-and-data-access-policy-is-not-yet-defined.md).

**Next action**

- Create a repository-wide data protection and data access policy.

### EU-GAP-002: Sensitive Data Classification and Handling Rules Are Incomplete

- **Regulatory domains**: GDPR, BCBS 239, MiFID II, CRR, EMIR
- **Control area**: sensitive-data handling, traceability, record integrity
- **Severity**: high

**Current state**

- Logging artifacts identify some sensitive categories such as credentials, tokens, PII, and raw payload data.
- The repository does not yet define a broader platform data-classification model that distinguishes personal data, reporting data, confidential business data, exception evidence, and operational secrets with required handling rules.

**Evidence**

- [LOGGING_AND_MONITORING_POLICY_ISO27001.md](../LOGGING_AND_MONITORING_POLICY_ISO27001.md)
- [LOG_INTEGRITY_AND_ACCESS_CONTROL.md](../LOG_INTEGRITY_AND_ACCESS_CONTROL.md)
- [ISO_11179_DATA_DEFINITION_FRAMEWORK.md](../ISO_11179_DATA_DEFINITION_FRAMEWORK.md)

**Why it matters**

- Without explicit classification, access rules, encryption expectations, retention rules, and reporting evidence controls remain uneven.
- Regulated data semantics are being improved, but handling obligations per sensitivity class are still implicit.

**Current treatment**

- Partially covered by redaction and retention policies.
- No dedicated requirement yet.

**Next action**

- Add a technical classification and handling standard for sensitive data classes.

### EU-GAP-003: Encryption-at-Rest Expectations for Sensitive Attributes Remain Partial

- **Regulatory domains**: GDPR, DORA
- **Control area**: secure storage and cryptographic governance
- **Severity**: high

**Current state**

- Selected application configuration secrets are encrypted at rest in the FastAPI app configuration repository.
- The repository does not yet define a broader requirement for which sensitive attributes, evidence artifacts, or operational secrets must be encrypted at rest across repository-managed stores.

**Evidence**

- [dq-api/fastapi/app/infrastructure/security/entity_field_encryptor.py](../../../dq-api/fastapi/app/infrastructure/security/entity_field_encryptor.py)
- [dq-api/fastapi/tests/infrastructure/unit/repositories/postgres/test_app_config_repository_postgres.py](../../../dq-api/fastapi/tests/infrastructure/unit/repositories/postgres/test_app_config_repository_postgres.py)
- [EU_FINANCIAL_REGULATORY_CONTROL_MAPPING.md](../EU_FINANCIAL_REGULATORY_CONTROL_MAPPING.md)

**Why it matters**

- Current implementation proves the repository can encrypt sensitive values, but there is no platform-level rule for broader sensitive-attribute coverage.
- This leaves inconsistent protection expectations across repositories, stores, and future features.

**Current treatment**

- Partial implementation exists.
- Security feature baseline now tracked in [SEC-5 Sensitive Data Encryption-at-Rest and Key Segregation](../../features/SEC_5_SENSITIVE_DATA_ENCRYPTION_AND_KEY_SEGREGATION.md).

**Next action**

- Implement the SEC-5 key-segregation baseline and record unsupported or legacy single-key surfaces as deviations.

### EU-GAP-004: Secure Internal Transport Baseline Is Not Yet Runtime-Enforced Everywhere

- **Regulatory domains**: DORA, GDPR
- **Control area**: secure transport and cryptographic governance
- **Severity**: high

**Current state**

- The repository has an accepted internal TLS ADR and related implementation plan.
- Multiple internal service links still use plaintext defaults.

**Evidence**

- [ADR-027](../../../architecture/adr/ADR-027-internal-service-communication-uses-repository-managed-tls.md)
- [ARCH-EXC-0001](../../../architecture/deviations/ARCH-EXC-0001-internal-service-transport-still-defaults-to-plaintext-links.md)
- [SEC_1_INTERNAL_SERVICE_TLS.md](../../features/SEC_1_INTERNAL_SERVICE_TLS.md)

**Why it matters**

- This is a documented baseline-to-runtime enforcement gap on a critical transport surface.

**Current treatment**

- Explicitly tracked by [ARCH-EXC-0001](../../../architecture/deviations/ARCH-EXC-0001-internal-service-transport-still-defaults-to-plaintext-links.md).

**Next action**

- Continue execution of SEC-1 and close the deviation when canonical TLS endpoints are operational.

### EU-GAP-005: Observability RBAC Is Still More Documented Than Enforced

- **Regulatory domains**: DORA, GDPR
- **Control area**: privileged access and least-privilege enforcement
- **Severity**: high

**Current state**

- Least-privilege observability policy exists.
- Deployment evidence still says RBAC enforcement is pending OIDC integration.

**Evidence**

- [LOG_INTEGRITY_AND_ACCESS_CONTROL.md](../LOG_INTEGRITY_AND_ACCESS_CONTROL.md)
- [LOGGING_AND_MONITORING_POLICY_IMPLEMENTATION_CHECKLIST.md](../LOGGING_AND_MONITORING_POLICY_IMPLEMENTATION_CHECKLIST.md)
- [ARCH-EXC-0005](../../../architecture/deviations/ARCH-EXC-0005-c3-observability-rbac-is-documented-but-not-yet-enforced.md)

**Why it matters**

- Privileged monitoring and log surfaces remain sensitive in a regulated context.

**Current treatment**

- Explicitly tracked by [ARCH-EXC-0005](../../../architecture/deviations/ARCH-EXC-0005-c3-observability-rbac-is-documented-but-not-yet-enforced.md).

**Next action**

- Complete supported deployment-path RBAC enforcement and close the deviation with runtime evidence.

### EU-GAP-006: CRR and EMIR Reporting Evidence Still Needs Concrete Evidence Bundles

- **Regulatory domains**: CRR, EMIR, BCBS 239
- **Control area**: reporting evidence, traceability, control attestation
- **Severity**: medium

**Current state**

- The repository now has a requirement baseline for CRR- and EMIR-relevant reporting evidence.
- It does not yet have concrete evidence packs or release-level evidence bundles showing how specific repository outputs support reporting-grade evidence for a concrete use case.

**Evidence**

- [ADR-018](../../../architecture/adr/ADR-018-iso-11179-based-data-definition-framework-for-bcbs-239-and-mifid-ii.md)
- [ISO_11179_DATA_DEFINITION_FRAMEWORK.md](../ISO_11179_DATA_DEFINITION_FRAMEWORK.md)
- [EU_FINANCIAL_REGULATORY_CONTROL_MAPPING.md](../EU_FINANCIAL_REGULATORY_CONTROL_MAPPING.md)
- [CRR_EMIR_REPORTING_EVIDENCE_REQUIREMENTS.md](../CRR_EMIR_REPORTING_EVIDENCE_REQUIREMENTS.md)

**Why it matters**

- A baseline requirement improves governance, but reporting-oriented claims still need concrete feature or release evidence to be reviewable.

**Current treatment**

- Partially addressed through [CRR_EMIR_REPORTING_EVIDENCE_REQUIREMENTS.md](../CRR_EMIR_REPORTING_EVIDENCE_REQUIREMENTS.md).

**Next action**

- Create a concrete reporting evidence pack or release-level evidence bundle when a CRR- or EMIR-relevant use case is claimed.

### EU-GAP-007: Regulated Workflow Record-Keeping Controls Remain Generic

- **Regulatory domains**: MiFID II, EMIR, CRR
- **Control area**: audit evidence and record-keeping
- **Severity**: medium

**Current state**

- Logging and retention controls exist at a generic platform level.
- The repository does not yet define specific record-keeping expectations for regulated workflow artifacts that may need longer retention, stronger provenance, or workflow-specific evidence treatment.

**Evidence**

- [LOG_RETENTION_AND_DISPOSAL_POLICY.md](../LOG_RETENTION_AND_DISPOSAL_POLICY.md)
- [ADR-018](../../../architecture/adr/ADR-018-iso-11179-based-data-definition-framework-for-bcbs-239-and-mifid-ii.md)

**Why it matters**

- Generic audit controls may be insufficient if the platform is used in more explicitly regulated operational workflows.

**Current treatment**

- Partially addressed through generic audit and retention artifacts.

**Next action**

- Define whether repository-managed workflow records need dedicated retention, provenance, and approval evidence rules for regulated use cases.

## 6. Priority Follow-Up

Recommended next repository actions, in order:

1. Create a repository-wide data protection and data access policy.
2. Add a sensitive-data classification and handling standard.
3. Define encryption-at-rest expectations beyond selected configuration secrets.
4. Create a dedicated CRR/EMIR reporting-evidence requirement or explicit deviation.
5. Continue closing active runtime-enforcement deviations for internal TLS and observability RBAC.

## 7. Candidate New Deviations

The following gaps are material enough that they should be either implemented directly or recorded as dedicated architecture deviations if they remain open:

- `EU-GAP-003` broader encryption-at-rest baseline gap.

## 8. Review Trigger

Review this gap analysis whenever:

- a new regulatory baseline artifact is added,
- a listed gap is materially reduced or closed,
- a new deviation is created for one of the untracked gaps,
- the repository begins claiming stronger reporting, privacy, or resilience support for regulated financial-sector use cases.