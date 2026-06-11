# Data Protection and Access Policy Implementation Checklist

Purpose: translate the repository's EU data-usage and data-protection baseline into concrete dq-made-easy implementation tasks with clear ownership and evidence outputs.

Related policy: [Data Protection and Access Policy](./DATA_PROTECTION_AND_ACCESS_POLICY.md)
Related ADR: [ADR-030 EU Financial Regulatory Baseline and Control Mapping](../../architecture/adr/ADR-030-eu-financial-regulatory-baseline-and-control-mapping.md)
Related control map: [EU Financial Regulatory Control Mapping](./EU_FINANCIAL_REGULATORY_CONTROL_MAPPING.md)
Related gap analysis: [EU Financial Regulatory Gap Analysis](./gap-analysis/EU_FINANCIAL_REGULATORY_GAP_ANALYSIS.md)
Related deviation: [ARCH-EXC-0006: Repository-Wide Data Protection and Data Access Policy Is Not Yet Defined](../../architecture/deviations/ARCH-EXC-0006-repository-wide-data-protection-and-data-access-policy-is-not-yet-defined.md)
Related security baseline: [SEC-5 Sensitive Data Encryption-at-Rest and Key Segregation](./SEC_5_SENSITIVE_DATA_ENCRYPTION_AND_KEY_SEGREGATION.md)

This document defines the engineering checklist for a repository-wide policy baseline. It is not a legal interpretation and not a complete institutional compliance framework.

## 1. Baseline and Governance Scope

- [ ] Adopt one cross-cutting policy for data usage, protection, retention, access, and disposal across platform-managed data.
- [ ] Explicitly name BCBS 239, GDPR, CRR, MiFID II, EMIR, DORA, and applicable NIS2-style governance as governing reference domains where relevant.
- [ ] Define policy owners, approvers, review cadence, and deviation handling.
- [ ] Enumerate covered data classes, including personal data, regulated reporting data, evidence-bearing data, business data, administrative data, operational secrets, and support artifacts.

Validation evidence:
- [ ] Policy review links the checklist to ARCH-EXC-0006, the control map, and the gap analysis.

## 2. Classification and Handling Rules

- [ ] Define classification levels for platform data, including the handling expectations for public, internal, confidential, restricted, and sensitive classes.
- [ ] Define handling rules for API payloads, logs, exports, screenshots, object storage, database rows, exception evidence, and support tickets.
- [ ] Define minimum-necessary and need-to-know rules, including data minimization expectations for new features.
- [ ] Define when redaction, masking, tokenization, pseudonymization, or omission is required.
- [ ] Define workflow-specific PII masking rules for validation outputs, drilldown views, committed evidence, and incident workflows.
- [ ] Require record-keeping rules for evidence-bearing or regulated artifacts so they remain traceable without oversharing.

Validation evidence:
- [ ] Add tests or policy checks that confirm sensitive data is not exposed in logs, exports, or support surfaces.

## 3. Access Control and Privileged Access

- [ ] Map data classes to workspace roles, admin roles, service roles, and break-glass access paths.
- [ ] Require explicit approval and time-bounded access for sensitive classes where the current workspace permits user choice.
- [ ] Define access review and attestation cadence for administrative and regulated-data access.
- [ ] Ensure external sharing or export requires an approved purpose and destination.

Validation evidence:
- [ ] Add access-control review notes or tests that show sensitive data paths are governed by explicit roles and scopes.

## 4. Retention, Disposal, and Erasure Rights

- [ ] Define retention schedules by data class and regulatory driver.
- [ ] Define legal hold, archive, deletion, and retraction rules.
- [ ] Define GDPR erasure and right-to-be-forgotten workflows, plus equivalent handling for other applicable EU-regulatory data classes.
- [ ] Ensure retention does not exceed evidence or business need.

Validation evidence:
- [ ] Retention and disposal rules are linked from the policy, control map, and supporting feature or implementation docs.

## 5. Encryption, Masking, and Key Management

- [ ] Apply the SEC-5 key-segregation baseline to sensitive operational and evidence-bearing attributes.
- [ ] Define when masking is sufficient versus when encryption is mandatory.
- [ ] Define who may select masking methods or encryption keys and under what workspace conditions.
- [ ] Require fail-fast behavior when required key material is missing or unavailable.
- [ ] Record the approved masking methods for each sensitive workflow so validation, drilldown, evidence, and incident handling stay traceable.

Validation evidence:
- [ ] Encryption and masking rules have tests that prove sensitive data does not silently downgrade to plaintext or a shared fallback key.

## 6. Validation, Deviations, and Evidence

- [ ] Add tests proving sensitive data is redacted from logs and support surfaces.
- [ ] Add tests proving protected data cannot silently fall back to plaintext.
- [ ] Record unsupported stores, legacy surfaces, and vendor-managed gaps as explicit deviations with owners and closure dates.
- [ ] Keep evidence artifacts linked from the control map, gap analysis, and relevant feature work.

Acceptance criteria:
- [ ] A single repository-wide policy baseline exists and references the EU regulatory domains.
- [ ] Classification, access, retention, and protection rules are explicit and discoverable.
- [ ] Sensitive data handling is validated and deviations are tracked.
- [ ] Architecture and feature work can cite this checklist when implementing data-protection controls.
