# EU Financial C=3 Security Requirements

**Requirement ID**: DQ-SEC-EU-C3-001  
**Version**: 1.0  
**Effective Date**: 2026-04-22  
**Owner**: Engineering + Security + Compliance  
**Review Cycle**: Quarterly (minimum), after major architecture changes, and after material regulatory updates

## 1. Purpose

Define the mandatory engineering security baseline for dq-made-easy when the application is handled as a `C=3` system in an EU financial-institution context.

This document translates regulatory and supervisory security expectations into repository-level engineering requirements.

## 2. Scope

This requirement applies to:

- all dq-made-easy services, workers, gateways, data stores, observability components, and supporting automation,
- all repository-managed environments and deployment patterns,
- all change flows that affect authentication, authorization, transport security, data protection, resilience, monitoring, or third-party risk,
- all releases presented as suitable for a `C=3` financial-sector use case.

## 3. Classification Assumption

For this document, `C=3` is treated as a high-criticality application classification supplied by governance stakeholders.

That means the engineering baseline MUST assume elevated requirements for:

- confidentiality,
- integrity,
- availability,
- auditability,
- resilience,
- controlled change and exception handling.

## 4. Regulatory Alignment

This requirement is aligned primarily to EU financial-sector ICT and cyber-resilience expectations, especially:

- DORA-style ICT risk-management and operational resilience expectations,
- NIS2-style cyber-risk governance expectations where applicable,
- supervisory expectations for financial institutions concerning access control, resilience, incident evidence, dependency risk, and security oversight.

This is an engineering baseline, not a substitute for formal legal or compliance interpretation.

## 5. Requirement Statements

### 5.1 Governance and Risk Control

- A `C=3` release MUST identify the governing security baseline and related ADRs.
- Security-impacting deviations MUST be recorded in the architecture deviation register before release.
- Owners MUST be assigned for security baseline compliance, evidence, and exception review.
- Security baseline compliance MUST be reviewed at least quarterly and before production release.

### 5.2 Identity, Access, and Privileged Control

- Administrative and privileged access MUST use centrally managed identity and strong authentication.
- Least privilege MUST apply to human roles, service roles, API scopes, and observability/admin surfaces.
- Shared privileged credentials MUST NOT be the default operating model.
- Access reviews MUST be possible and evidenced for privileged roles and sensitive integrations.
- Break-glass or emergency access, if present, MUST be documented, controlled, and auditable.

### 5.3 Secure Transport and Cryptography

- Sensitive service-to-service and user-to-service traffic MUST use approved secure transport.
- Plaintext defaults for in-scope internal traffic MUST be treated as deviations until removed.
- Cryptographic choices for `C=3` deployments MUST follow approved repository baselines, including [ADR-027](/docs/architecture/adr/ADR-027-internal-service-communication-uses-repository-managed-tls/) and [ADR-028](/docs/architecture/adr/ADR-028-post-quantum-cryptography-must-be-implemented-by-2026-12-31/).
- Keys, certificates, trust bundles, and signing configurations MUST have explicit ownership and rotation/update paths.
- Weak, deprecated, or undocumented cryptographic defaults MUST NOT remain untracked in `C=3` releases.

### 5.4 Logging, Monitoring, and Audit Evidence

- The logging and monitoring baseline in [LOGGING_AND_MONITORING_POLICY_ISO27001.md](/docs/technical/LOGGING_AND_MONITORING_POLICY_ISO27001/) MUST apply.
- Security-relevant events MUST be logged, correlated, and reviewable.
- Monitoring and alerting MUST cover authentication failures, service failure, dependency failure, and resilience-significant degradation.
- Evidence required for incident response, audit, and supervisory review MUST be retained and retrievable.

### 5.5 Vulnerability, Patch, and Dependency Management

- Critical security vulnerabilities affecting internet-facing, authentication, cryptographic, or privileged-control surfaces MUST be triaged immediately and remediated or formally deviated.
- High-severity vulnerabilities MUST have a documented remediation plan and due date.
- Repository-managed dependencies and container images MUST be tracked and reviewed for security impact.
- Unsupported or end-of-life security-critical dependencies MUST NOT remain in a `C=3` release without approved deviation handling.

### 5.6 Secure Change and Delivery Controls

- Security-impacting changes MUST undergo peer review and explicit security-aware review when they affect critical control surfaces.
- Release readiness MUST include verification of baseline compliance and exception review.
- Infrastructure, configuration, and secrets changes MUST be controlled and auditable.
- Changes that weaken the `C=3` security baseline MUST NOT ship without an approved deviation.

### 5.7 Resilience, Recovery, and Operational Continuity

- Backup, restore, and recovery procedures for critical data and security-relevant configuration MUST be defined and testable.
- Single points of operational failure that materially affect a `C=3` deployment MUST be documented and mitigated or deviated.
- Incident response and service recovery paths MUST preserve evidence needed for root cause analysis and compliance reporting.
- Material resilience gaps MUST be visible in implementation plans or deviation records.

### 5.8 Third-Party and Supply-Chain Risk

- Third-party services, images, libraries, and identity/security dependencies that materially affect the application MUST have clear ownership.
- Vendor-managed capability gaps that block the security baseline MUST be recorded explicitly as architecture deviations.
- Repository defaults MUST not assume security support that has not been validated for critical dependencies.
- Dependency risk affecting authentication, cryptography, logging, monitoring, or resilience MUST be reviewed as part of release readiness.

## 6. Verification and Evidence

Compliance evidence SHOULD include:

- release-check evidence against `DQ-SEC-EU-C3-001`,
- architecture deviation review status,
- security-relevant configuration evidence,
- logging/monitoring evidence for critical events,
- vulnerability triage records for open critical or high findings,
- recovery and resilience test evidence where applicable.

## 7. Exceptions and Deviations

Any exception to this requirement MUST:

- be recorded in [ARCHITECTURE_DEVIATIONS_AND_EXCEPTIONS.md](/docs/architecture/ARCHITECTURE_DEVIATIONS_AND_EXCEPTIONS/),
- identify owner, risk, impact, review date, and closure target,
- define compensating controls where possible,
- be reviewed before production release when still open.

## 8. Related Documents

- [ADR-016 ISO 27001-Aligned Logging and Monitoring Policy Adoption](/docs/architecture/adr/ADR-016-iso27001-logging-and-monitoring-policy-adoption/)
- [ADR-027 Internal Service Communication Uses Repository-Managed TLS](/docs/architecture/adr/ADR-027-internal-service-communication-uses-repository-managed-tls/)
- [ADR-028 Post-Quantum Cryptography Must Be Implemented by 2026-12-31](/docs/architecture/adr/ADR-028-post-quantum-cryptography-must-be-implemented-by-2026-12-31/)
- [ADR-029 EU Financial C=3 Security Baseline Mandate](/docs/architecture/adr/ADR-029-eu-financial-c3-security-baseline-mandate/)
- [EU Financial C=3 Security Implementation Checklist](/docs/technical/EU_FINANCIAL_C3_SECURITY_IMPLEMENTATION_CHECKLIST/)
- [ARCHITECTURE_DEVIATIONS_AND_EXCEPTIONS.md](/docs/architecture/ARCHITECTURE_DEVIATIONS_AND_EXCEPTIONS/)
- [Release Readiness Checklist](/docs/releases/RELEASE_READINESS_CHECKLIST/)