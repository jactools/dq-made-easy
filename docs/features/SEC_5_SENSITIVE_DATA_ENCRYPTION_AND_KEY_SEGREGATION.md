# SEC-5 Sensitive Data Encryption-at-Rest and Key Segregation

Goal: define a repository-managed encryption-at-rest baseline for sensitive data, secrets, and evidence-bearing attributes, aligned with the repository's broader EU regulatory baseline for data usage and protection (including BCBS 239, GDPR, CRR, MiFID II, EMIR, and DORA where applicable), with explicit key segregation requirements so the platform does not rely on one single encryption key for all sensitive attributes.

Related regulatory gaps: [EU Financial Regulatory Gap Analysis](../technical/gap-analysis/EU_FINANCIAL_REGULATORY_GAP_ANALYSIS.md)

Current implementation evidence: [entity_field_encryptor.py](../../dq-api/fastapi/app/infrastructure/security/entity_field_encryptor.py)

This file defines the stable scope and acceptance contract for the security feature.

Note: The lists below use stable IDs so tasks and acceptance criteria can be referenced unambiguously across engineering work, deviations, validation scripts, and release notes.

## Phase 1: Sensitive Data Scope and Coverage Inventory

- [ ] (SEC5-F-P1-01) Define which repository-managed data classes are treated as sensitive for encryption-at-rest purposes under the repository's EU regulatory baseline, including credentials, tokens, secrets, personal data, regulated evidence-bearing attributes, and other high-impact operational values.
- [ ] (SEC5-F-P1-02) Inventory every repository-managed store, payload, artifact, and persistence path where those sensitive classes can appear.
- [ ] (SEC5-F-P1-03) Identify which sensitive attributes are already encrypted, which are plaintext today, and which are delegated to vendor-managed encryption surfaces.
- [ ] (SEC5-F-P1-04) Distinguish repository-managed attribute encryption from infrastructure-level disk or volume encryption so application-layer expectations remain explicit.

## Phase 2: Key Segregation Baseline

- [ ] (SEC5-F-P2-01) Define the approved key hierarchy for repository-managed sensitive-data encryption, including key-encryption-key and data-encryption-key layering or an equivalent scoped model.
- [ ] (SEC5-F-P2-02) Require key separation by approved scope such as data class, attribute family, store boundary, workspace boundary, or another justified blast-radius boundary.
- [ ] (SEC5-F-P2-03) Explicitly prohibit using one single shared key for all sensitive attributes across the platform.
- [ ] (SEC5-F-P2-04) Define when per-attribute, per-family, per-store, or per-tenant key scopes are required versus when a broader shared scope is acceptable.
- [ ] (SEC5-F-P2-05) Require encrypted values or adjacent metadata to remain traceable to key scope and key version so rotation and incident response are possible.
- [ ] (SEC5-F-P2-06) Ensure missing or unavailable required key material fails fast instead of downgrading to plaintext storage or a weaker fallback key.

## Phase 3: Rotation, Containment, and Lifecycle Management

- [ ] (SEC5-F-P3-01) Define rotation requirements for each approved key scope, including emergency rotation and planned rollover.
- [ ] (SEC5-F-P3-02) Define re-encryption or migration expectations for previously stored ciphertext when keys rotate or scopes are narrowed.
- [ ] (SEC5-F-P3-03) Define compromise-containment expectations so exposure of one key scope does not automatically expose all sensitive attributes.
- [ ] (SEC5-F-P3-04) Define retirement, revocation, escrow, backup, and recovery expectations for repository-managed encryption keys.

## Phase 4: Validation, Deviations, and Operational Evidence

- [ ] (SEC5-F-P4-01) Add validation or review guidance that sensitive attributes are mapped to approved encryption scopes rather than an undocumented global key.
- [ ] (SEC5-F-P4-02) Add tests that prove at least two independently scoped sensitive attribute families can be encrypted and decrypted without sharing the same effective key material.
- [ ] (SEC5-F-P4-03) Add fail-fast tests that demonstrate decryption does not silently succeed when ciphertext is presented with the wrong key scope.
- [ ] (SEC5-F-P4-04) Record unsupported stores, legacy single-key implementations, or vendor-managed limitations as explicit deviations with owners and closure dates.
- [ ] (SEC5-F-P4-05) Document operator guidance for key provisioning, key rotation, key-version troubleshooting, and incident response for encrypted attributes.

## Acceptance Criteria

- [ ] (SEC5-F-AC-01) The repository defines which sensitive data classes require encryption at rest and where they can appear, in line with the repository's EU regulatory baseline.
- [ ] (SEC5-F-AC-02) Repository-managed sensitive attribute encryption uses documented key scopes instead of one global key for every attribute.
- [ ] (SEC5-F-AC-03) A compromise or rotation event for one approved key scope does not require assuming all encrypted sensitive attributes are exposed.
- [ ] (SEC5-F-AC-04) Encrypted values can be traced to an approved key scope and key version or the implementation is explicitly deviated.
- [ ] (SEC5-F-AC-05) Missing key material or wrong-key usage fails clearly rather than downgrading to plaintext or a fallback shared key.
- [ ] (SEC5-F-AC-06) Remaining plaintext or single-key legacy surfaces are tracked explicitly until remediated.

## Delivery Milestones

- Milestone A (Scope Inventory): `SEC5-F-P1-01` to `SEC5-F-P1-04`
- Milestone B (Key Segregation Baseline): `SEC5-F-P2-01` to `SEC5-F-P2-06`
- Milestone C (Lifecycle and Containment): `SEC5-F-P3-01` to `SEC5-F-P3-04`
- Milestone D (Validation and Deviations): `SEC5-F-P4-01` to `SEC5-F-P4-05`