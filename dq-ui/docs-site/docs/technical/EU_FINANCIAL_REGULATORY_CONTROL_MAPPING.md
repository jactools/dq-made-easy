# EU Financial Regulatory Control Mapping

**Requirement ID**: DQ-REG-EU-FIN-001  
**Version**: 1.0  
**Effective Date**: 2026-04-22  
**Owner**: Engineering + Security + Compliance + Data Governance  
**Related ADR**: [ADR-030](/docs/architecture/adr/ADR-030-eu-financial-regulatory-baseline-and-control-mapping/)  
**Related gap analysis**: [EU_FINANCIAL_REGULATORY_GAP_ANALYSIS.md](/docs/technical/gap-analysis/EU_FINANCIAL_REGULATORY_GAP_ANALYSIS/)

## 1. Purpose

Translate the repository's named EU financial regulatory baseline into a concrete control-mapping reference for architecture, implementation planning, evidence, and deviation handling.

This document exists so repository work can map controls explicitly to:

- BCBS 239,
- GDPR,
- CRR,
- MiFID II,
- EMIR,
- DORA.

This is a repository engineering control map, not a legal interpretation and not a complete institutional compliance framework.

## 2. Scope

This control-mapping requirement applies to repository-managed architecture, platform controls, technical requirements, implementation plans, and deviation records that materially affect:

- regulated reporting data,
- governed business/data definitions,
- personal data and sensitive operational data,
- access control and privileged access,
- security, resilience, and dependency risk,
- logging, record-keeping, and audit evidence,
- transport and cryptographic control surfaces.

## 3. Usage Rules

1. New ADRs, requirement documents, implementation plans, and architecture deviations SHOULD cite this document when they affect one or more mapped regulatory domains.
2. Teams MUST prefer explicit mapping to control areas and evidence sources over generic statements such as "compliant" or "regulated-ready".
3. Where coverage is partial, the artifact MUST say so explicitly and either point to a plan or to an approved deviation.
4. Repository artifacts MUST use language such as "supports", "maps to", "provides evidence for", or "partially covers" rather than implying full institutional compliance.

## 4. Control Areas

The repository uses the following common control areas across all mapped regulatory domains:

- governed data definitions and lineage,
- data accuracy, completeness, timeliness, and traceability,
- data protection, retention, and disposal,
- access control and privileged-access governance,
- logging, audit evidence, and record-keeping,
- secure transport, encryption, and cryptographic governance,
- resilience, continuity, and third-party dependency control.

## 5. Regulatory Control Mapping

### 5.1 BCBS 239

**Repository interpretation**

- Risk and reporting data must remain governed, traceable, and auditable across data definitions, lineage, delivery, and quality evidence.

**Primary control areas**

- governed data definitions and lineage,
- data accuracy, completeness, timeliness, and traceability,
- logging, audit evidence, and record-keeping.

**Primary repository artifacts**

- [ADR-018](/docs/architecture/adr/ADR-018-iso-11179-based-data-definition-framework-for-bcbs-239-and-mifid-ii/)
- [ISO_11179_DATA_DEFINITION_FRAMEWORK.md](/docs/technical/ISO_11179_DATA_DEFINITION_FRAMEWORK/)

**Current coverage assessment**

- Strong architecture intent for governed definitions and traceability.
- Coverage is still repository-architecture focused rather than end-to-end institutional reporting control evidence.

### 5.2 GDPR

**Repository interpretation**

- Personal data and sensitive data must be handled with controlled access, retention discipline, disposal paths, and avoidance of unnecessary exposure in logs or operational artifacts.

**Primary control areas**

- data protection, retention, and disposal,
- access control and privileged-access governance,
- secure transport, encryption, and cryptographic governance,
- logging, audit evidence, and record-keeping.

**Primary repository artifacts**

- [LOG_RETENTION_AND_DISPOSAL_POLICY.md](/docs/technical/LOG_RETENTION_AND_DISPOSAL_POLICY/)
- [LOG_INTEGRITY_AND_ACCESS_CONTROL.md](/docs/technical/LOG_INTEGRITY_AND_ACCESS_CONTROL/)
- [LOGGING_AND_MONITORING_POLICY_ISO27001.md](/docs/technical/LOGGING_AND_MONITORING_POLICY_ISO27001/)

**Current coverage assessment**

- Retention, disposal, redaction, and observability access controls are documented.
- A single repository-wide data-protection and data-access policy is not yet established.
- Sensitive-field encryption exists for selected configuration secrets, but broad sensitive-attribute policy coverage remains partial.

### 5.3 CRR

**Repository interpretation**

- Prudential or supervisory-reporting-relevant data dependencies must be governed, stable, reviewable, and traceable.

**Primary control areas**

- governed data definitions and lineage,
- data accuracy, completeness, timeliness, and traceability,
- logging, audit evidence, and record-keeping.

**Primary repository artifacts**

- [ADR-018](/docs/architecture/adr/ADR-018-iso-11179-based-data-definition-framework-for-bcbs-239-and-mifid-ii/)
- [ISO_11179_DATA_DEFINITION_FRAMEWORK.md](/docs/technical/ISO_11179_DATA_DEFINITION_FRAMEWORK/)
- [CRR_EMIR_REPORTING_EVIDENCE_REQUIREMENTS.md](/docs/technical/CRR_EMIR_REPORTING_EVIDENCE_REQUIREMENTS/)

**Current coverage assessment**

- The repository has a strong semantic-governance direction.
- A reporting-evidence baseline now exists, but concrete release evidence bundles or evidence packs for specific reporting use cases still need to be produced where claimed.

### 5.4 MiFID II

**Repository interpretation**

- Record-keeping, controlled data semantics, and auditability must be preserved for data and rule/reporting artifacts that can influence regulated workflows or evidence.

**Primary control areas**

- governed data definitions and lineage,
- logging, audit evidence, and record-keeping,
- data accuracy, completeness, timeliness, and traceability.

**Primary repository artifacts**

- [ADR-018](/docs/architecture/adr/ADR-018-iso-11179-based-data-definition-framework-for-bcbs-239-and-mifid-ii/)
- [ISO_11179_DATA_DEFINITION_FRAMEWORK.md](/docs/technical/ISO_11179_DATA_DEFINITION_FRAMEWORK/)

**Current coverage assessment**

- MiFID II is explicitly named in data-definition governance work.
- More direct technical controls for retention and evidence of regulated workflow records may still need dedicated treatment depending on the use case.

### 5.5 EMIR

**Repository interpretation**

- Trade or transaction-reporting-like data flows need lineage, timeliness, reviewable evidence, and controlled semantics where the platform participates in those flows.

**Primary control areas**

- governed data definitions and lineage,
- data accuracy, completeness, timeliness, and traceability,
- logging, audit evidence, and record-keeping.

**Primary repository artifacts**

- [ADR-018](/docs/architecture/adr/ADR-018-iso-11179-based-data-definition-framework-for-bcbs-239-and-mifid-ii/)
- [ISO_11179_DATA_DEFINITION_FRAMEWORK.md](/docs/technical/ISO_11179_DATA_DEFINITION_FRAMEWORK/)
- [ADR-014](/docs/architecture/adr/ADR-014-gx-suite-registry-pyspark-execution-and-exception-store-separation/)
- [CRR_EMIR_REPORTING_EVIDENCE_REQUIREMENTS.md](/docs/technical/CRR_EMIR_REPORTING_EVIDENCE_REQUIREMENTS/)

**Current coverage assessment**

- The repository has building blocks for lineage, governed semantics, and separated execution evidence.
- A reporting-evidence baseline now exists, but concrete EMIR-oriented evidence bundles or attestations still need to be produced when the repository makes such claims.

### 5.6 DORA

**Repository interpretation**

- ICT risk, resilience, access control, incident evidence, dependency visibility, secure transport, and third-party risk must be explicit in engineering controls and deviation handling.

**Primary control areas**

- access control and privileged-access governance,
- secure transport, encryption, and cryptographic governance,
- resilience, continuity, and third-party dependency control,
- logging, audit evidence, and record-keeping.

**Primary repository artifacts**

- [ADR-029](/docs/architecture/adr/ADR-029-eu-financial-c3-security-baseline-mandate/)
- [EU_FINANCIAL_C3_SECURITY_REQUIREMENTS.md](/docs/technical/EU_FINANCIAL_C3_SECURITY_REQUIREMENTS/)
- [ADR-027](/docs/architecture/adr/ADR-027-internal-service-communication-uses-repository-managed-tls/)
- [ADR-028](/docs/architecture/adr/ADR-028-post-quantum-cryptography-must-be-implemented-by-2026-12-31/)
- [ARCHITECTURE_DEVIATIONS_AND_EXCEPTIONS.md](/docs/architecture/ARCHITECTURE_DEVIATIONS_AND_EXCEPTIONS/)

**Current coverage assessment**

- Strong explicit security and resilience baseline exists.
- Some required controls remain documented as active deviations rather than fully implemented runtime controls.

## 6. Current Gap Themes

The following cross-cutting themes are currently only partially covered at repository level and should be treated as candidates for dedicated requirements, implementation plans, or deviation tracking:

- a repository-wide data protection and data access policy beyond observability/logging surfaces,
- explicit treatment of sensitive business-data classes and required handling controls,
- broader encryption-at-rest expectations for sensitive attributes beyond currently implemented configuration secrets,
- regulated-reporting evidence packs or control attestations for CRR- and EMIR-relevant use cases,
- full runtime enforcement for all documented least-privilege and secure-transport controls.

## 7. Existing Supporting Deviations

The following approved deviations already support this control map by making current gaps explicit:

- [ARCH-EXC-0001](/docs/architecture/deviations/ARCH-EXC-0001-internal-service-transport-still-defaults-to-plaintext-links/)
- [ARCH-EXC-0005](/docs/architecture/deviations/ARCH-EXC-0005-c3-observability-rbac-is-documented-but-not-yet-enforced/)
- [ARCH-EXC-0006](/docs/architecture/deviations/ARCH-EXC-0006-repository-wide-data-protection-and-data-access-policy-is-not-yet-defined/)

Additional deviations SHOULD be created where privacy, data protection, regulated-reporting evidence, or sensitive-data control gaps are acknowledged but not yet remediated.

## 8. Evidence Expectations

Evidence referenced from repository artifacts SHOULD include, where applicable:

- ADRs and requirement documents that define the control intent,
- implementation plans or checklists that define delivery tasks,
- validation scripts, tests, or smoke checks that demonstrate the control,
- retention, audit, and access-control documents,
- architecture deviations where temporary non-compliance remains,
- release-readiness checks that reference the applicable requirement ID.

## 9. Change Control

- This document MUST be reviewed whenever a new financial regulatory domain is added to repository governance or when a major cross-cutting control area changes.
- When a new requirement or ADR materially strengthens a mapped area, update the relevant domain section instead of creating duplicate baseline language elsewhere.
- When coverage is improved from partial to enforced, update this control map and close or narrow related deviations.