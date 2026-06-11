# Data Protection and Access Policy

**Policy ID**: DQ-GOV-DATA-001  
**Version**: 1.0  
**Effective Date**: 2026-05-25  
**Owner**: Data Governance + Security + Engineering  
**Review Cycle**: Quarterly (minimum) and after major regulatory, architecture, or incident changes

## 1. Purpose

Define mandatory controls for repository-managed data usage, protection, retention, access, and disposal across dq-made-easy, aligned with the repository's EU regulatory baseline and supporting implementation artifacts.

## 2. Scope

This policy applies to:
- All repository-managed data classes, including personal data, regulated reporting data, evidence-bearing data, business data, administrative data, operational secrets, and support artifacts
- All platform surfaces that create, store, read, export, or evidence those data classes
- All environments (local, test, staging, production)
- All execution paths, including API requests, asynchronous jobs, batch workflows, administrative actions, support requests, exports, and technical evidence flows

## 3. EU Regulatory Baseline Alignment

This policy operationalizes the repository's named EU regulatory baseline for data usage and protection, including where relevant:
- BCBS 239
- GDPR
- CRR
- MiFID II
- EMIR
- DORA
- applicable NIS2-style governance expectations

The policy is intended for repository engineering, architecture, and evidence handling. It is not a legal interpretation and does not replace institution-specific compliance governance.

## 4. Policy Statements

### 4.1 Classification and Data Minimization

- Repository-managed data MUST be classified before it is broadly consumed, exported, or retained.
- Implementations MUST distinguish public, internal, confidential, restricted, and sensitive data handling expectations where those classes are used.
- New features MUST follow data minimization and need-to-know principles.
- Evidence-bearing or regulated artifacts MUST remain traceable without exposing unnecessary payload detail.

### 4.2 Handling Rules by Surface

Platform code and documentation MUST define handling rules for:
- API payloads and request/response bodies
- Logs, traces, metrics, screenshots, and observability exports
- Database rows, object storage, and archived evidence bundles
- Exception records, support tickets, and administrative workflows
- Downloads, reports, and any external sharing or export path

The default rule is minimum necessary exposure. Sensitive data MUST be redacted, masked, tokenized, pseudonymized, omitted, or otherwise protected when a lower-exposure representation is sufficient.

### 4.3 Access Control and Privileged Access

- Access to sensitive data MUST follow least privilege.
- Workspace roles, administrative roles, service roles, and break-glass access paths MUST be explicit.
- Time-bounded approval MUST be required where a workspace permits a steward or admin to choose a masking method or encryption key.
- Sensitive exports or external sharing MUST require an approved purpose and destination.
- Administrative actions affecting sensitive data MUST be auditable.

### 4.4 Retention, Disposal, and Erasure Rights

- Retention schedules MUST be defined by data class and regulatory driver.
- Retention MUST not exceed evidence or business need.
- Archive, deletion, retraction, legal hold, and disposal rules MUST be explicit.
- GDPR erasure and right-to-be-forgotten handling MUST be supported where applicable, along with equivalent handling for other regulated EU data classes.

### 4.5 Masking, Encryption, and Key Management

- Sensitive operational and evidence-bearing attributes MUST follow the SEC-5 key-segregation baseline.
- Masking MUST be used where it is sufficient for the intended purpose.
- Encryption MUST be used when masking is not sufficient or when the applicable handling rule requires it.
- Required key material MUST fail fast when unavailable; the platform MUST not silently downgrade to plaintext or a weaker fallback key.
- Repository-controlled key scope decisions MUST be documented and traceable.

### 4.6 Logging, Monitoring, and Evidence

- Logs and evidence records MUST not expose sensitive data unless explicitly required and documented.
- Data-protection-related workflows SHOULD emit enough metadata to support auditability, incident review, and governance analysis.
- Retention and evidence storage MUST align with the logging, monitoring, and retention policies where those concerns overlap.

### 4.7 PII-Aware Masking by Workflow

The platform MUST apply workflow-specific masking rules when sensitive or personal data flows through validation, drilldown, evidence, or incident workflows.

- Validation workflows MUST prefer metadata-safe outputs and MUST mask personal data in failure summaries, exception details, and supporting diagnostics unless an approved exception explicitly requires the raw value.
- Drilldown workflows MUST expose the minimum necessary identifiers for investigation and MUST mask direct personal data fields in tables, timelines, and search results when the same purpose can be served with a redacted or tokenized representation.
- Evidence workflows MUST separate reviewed proof summaries from raw command evidence and MUST mask personal data in committed proof artifacts, screenshots, and exported reports unless the evidence owner has documented a narrower exception and access path.
- Incident workflows MUST mask personal data in alerts, notifications, support payloads, and triage notes unless the responder role requires a controlled unmasked view for active remediation.
- When masking is applied, the chosen method MUST be one of the repository-approved masking methods, and the selected method MUST be traceable in the owning workspace or policy record.
- When a workflow cannot preserve its purpose without unmasked personal data, the exception MUST be explicit, time-bounded, and governed by the access-control and deviation rules in this policy.

### 4.8 Exceptions and Deviations

- Unsupported stores, vendor-managed limitations, and legacy single-key or plaintext surfaces MUST be recorded as explicit deviations with owners and closure dates.
- Temporary exceptions MUST be narrowly scoped, time-bounded, and traceable to an approved deviation.
- No silent fallback to weaker protection is permitted.

## 5. Roles and Responsibilities

- Data Governance:
  - owns the policy baseline and approval of major exceptions
  - defines policy review cadence and governance requirements
- Security:
  - reviews masking, encryption, access, and key-management controls
  - maps sensitive-data controls to the EU regulatory baseline
- Engineering:
  - implements the policy in product and platform code
  - updates services, UIs, tests, and documentation when rules change
- Platform / SRE:
  - operates retention, storage, and access controls that support the policy
  - maintains auditability and operational evidence
- Workspace Owners / Admins:
  - apply approved handling rules in the workspace context
  - ensure sensitive data is only exposed when necessary and authorized

## 6. Minimum Technical Implementation Baseline

For dq-made-easy, the following baseline is required:
- Data protection and access guidance is visible in the technical documentation set and linked from the EU regulatory control map
- Sensitive-data classification, masking, encryption, retention, and access controls are represented in the UI and service behavior where applicable
- The repository-wide policy gap is tracked explicitly through ARCH-EXC-0006 until fully closed
- SEC-5 defines encryption-at-rest and key segregation for sensitive attributes
- Logging and retention controls remain aligned with this policy for evidence-bearing data

## 7. Verification and Evidence

Compliance evidence SHOULD include:
- policy references in architecture decisions, implementation checklists, and deviation records
- tests showing sensitive data is not exposed in logs, exports, or support surfaces
- tests showing masking/encryption decisions do not silently downgrade to plaintext
- access-control and retention evidence for regulated or sensitive data paths
- governance review records showing policy ownership and exception handling

Policy compliance MUST be assessed quarterly and after major architecture changes.

## 8. Exceptions

Any exception to this policy MUST:
- be documented in an approved deviation or equivalent governance record
- include a rationale, owner, review date, and closure target
- remain narrow in scope and duration
- fail fast instead of silently substituting a weaker control

## 9. Change Control

This policy MUST be reviewed when:
- the EU regulatory baseline or interpretation changes
- data classes or sensitive-data workflows change materially
- masking, encryption, or access-control behavior changes materially
- a major incident or audit reveals a policy gap
