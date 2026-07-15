# Regulatory Compliance Narratives: Synthetic/Test and Real/Evidence Storage Boundaries

**Document ID**: DQ-REG-SEC3-001  
**Version**: 1.0  
**Date**: 2026-07-15  
**Owner**: Data Governance + Compliance  
**Related**: [ADR-030](../../architecture/adr/ADR-030-eu-financial-regulatory-baseline-and-control-mapping.md), [ADR-031](../../architecture/adr/ADR-031-synthetic-test-object-storage-buckets-and-synthetic-evidence-boundaries.md), [DQ-OBJ-SYN-001](../OBJECT_STORAGE_SYNTHETIC_BUCKET_AND_SYNTHETIC_EVIDENCE_REQUIREMENTS.md), [SEC-3 Feature](../../features/SEC_3_SYNTHETIC_TEST_BUCKET_AND_EVIDENCE_BOUNDARIES.md)  
**Fulfills**: SEC3-I-W4-03

## 1. Purpose

This document makes the synthetic/test and real/evidence storage classification boundary explicit for each regulatory framework in the platform's governing baseline. It is not legal advice. It maps the boundary to regulatory obligations so that auditors, regulators, and institutional compliance teams can understand how the platform prevents synthetic test data from being presented as regulated evidence.

## 2. Platform Position

The platform classifies all repository-managed object-storage locations as either:

- `synthetic_test` — generated data, mock data, preview materializations, fixture-derived data, and test-run outputs. Never the source of production-grade evidence.
- `real_evidence` — operational evidence, exception evidence, source-data-aligned artifacts, and regulated-reporting support.

This classification is enforced by:

- Bucket naming conventions ([DQ-OBJ-NAME-001](./BUCKET_PREFIX_NAMING_CONVENTIONS.md))
- Delivery-note labels (`object_storage_classification`, `evidence_classification`)
- Fail-fast validation that rejects evidence-style URIs for synthetic outputs
- Mixed-classification export guards
- Deviation tracking for ambiguous flows

## 3. Regulatory Mapping

### 3.1 BCBS 239 — Principle 2: Accuracy and Completeness

**Relevant principles**: BCBS 239 Principle 2 (Accuracy and completeness), Principle 3 (Timeliness), Principle 4 (Integrity and reliability).

**Obligation**: Risk data aggregation must be accurate and complete. Institutions must be able to demonstrate that reported risk data accurately reflects the underlying source data and that the data lineage is traceable.

**Platform implementation**:

| Control | Mechanism |
|---------|-----------|
| Data accuracy | Synthetic test data cannot be presented as real risk data because storage targets are classified and fail-fast checks reject synthetic outputs in real/evidence targets. |
| Data completeness | Real/evidence storage targets carry delivery-note labels that trace data provenance. Synthetic results are excluded from evidence exports. |
| Data lineage | Bucket naming conventions and classification labels make the origin of stored data (synthetic vs real) auditable. |
| Data integrity | Mixed-classification export guards prevent synthetic and real evidence from being combined in the same export scope. |

**Narrative for audit**: "The platform prevents synthetic test data from being aggregated into risk reports by classifying all object-storage locations and enforcing that boundary through naming conventions, delivery-note labels, and fail-fast validation. Synthetic test results are excluded from evidence exports and reporting artifacts."

### 3.2 MiFID II — Record-Keeping and Transaction Reporting

**Relevant provisions**: MiFID II Article 16 (Reporting of transactions), Article 17 (Transaction reporting), Annex I (Record-keeping obligations).

**Obligation**: Investment firms must maintain records of transactions and communications. Records must be accurate, complete, and retrievable. Transaction reports must not contain fabricated or test data.

**Platform implementation**:

| Control | Mechanism |
|---------|-----------|
| Record accuracy | Real/evidence storage targets are distinct from synthetic/test targets. Storage classification labels prevent accidental inclusion of test data in reporting records. |
| Record completeness | Delivery notes for real/evidence deliveries carry classification labels that confirm the data source. |
| Record retention | Real/evidence storage targets follow retention policies. Synthetic/test storage targets are excluded from retention requirements. |
| Retrieval | Classification labels enable auditors to filter and retrieve only real/evidence records for regulatory examination. |

**Narrative for audit**: "The platform classifies all transaction-related storage locations and prevents synthetic test data from being included in MiFID II reporting records. Real/evidence storage targets are distinct from synthetic/test targets, and delivery-note labels confirm the classification of each stored record."

### 3.3 EMIR — Trade Reporting and Data Lineage

**Relevant provisions**: EMIR Article 9 (Reporting of derivative contracts), Article 11 (Reporting obligations of trade repositories), RTS 23 (Reporting standards).

**Obligation**: Derivative trades must be reported to trade repositories with accurate, complete, and traceable data. Data lineage must be maintained from trade execution through reporting.

**Platform implementation**:

| Control | Mechanism |
|---------|-----------|
| Trade data accuracy | Real/evidence storage targets are classified and distinct from synthetic/test targets. Storage classification labels confirm data provenance. |
| Data lineage | Bucket naming conventions and classification labels trace data from source execution through storage to reporting artifacts. |
| Reporting integrity | Mixed-classification export guards prevent synthetic test trades from being included in EMIR reporting packages. |

**Narrative for audit**: "The platform classifies all trade-related storage locations and prevents synthetic test trades from being included in EMIR reporting packages. Real/evidence storage targets are distinct from synthetic/test targets, and delivery-note labels confirm the classification of each stored trade record."

### 3.4 DORA — ICT Risk Management and Operational Resilience

**Relevant provisions**: DORA Article 5 (ICT risk management), Article 8 (ICT-related incident reporting), Article 11 (ICT third-party risk), Annex I (Operational resilience requirements).

**Obligation**: Financial entities must manage ICT risks including data integrity, access control, and operational resilience. Incident reports must be accurate and complete. Third-party risk must be managed.

**Platform implementation**:

| Control | Mechanism |
|---------|-----------|
| Data integrity | Classification boundaries prevent data contamination between synthetic/test and real/evidence storage. |
| Access control | Classification labels enable role-based access control where operators can be restricted to synthetic/test or real/evidence targets. |
| Incident reporting | Real/evidence storage targets carry classification labels that confirm the accuracy of incident report data. |
| Third-party risk | Classification boundaries are enforced at the storage level, independent of third-party integrations. |

**Narrative for audit**: "The platform classifies all ICT-related storage locations and prevents data contamination between synthetic/test and real/evidence storage. Classification labels enable role-based access control and confirm the accuracy of incident report data."

### 3.5 GDPR — Personal Data Protection

**Relevant provisions**: GDPR Article 5 (Principles relating to processing of personal data), Article 17 (Right to erasure), Article 30 (Records of processing activities).

**Obligation**: Personal data must be processed lawfully, accurately, and for specified purposes. Records of processing must be maintained and accurate. The right to erasure must be supported.

**Platform implementation**:

| Control | Mechanism |
|---------|-----------|
| Data accuracy | Real/evidence storage targets carry classification labels that confirm the data source. Synthetic test data cannot be confused with real personal data. |
| Purpose limitation | Classification boundaries prevent synthetic test data from being used for purposes that require real personal data. |
| Right to erasure | Classification labels enable precise identification of real personal data storage targets for erasure requests. Synthetic/test storage targets are excluded from erasure scope. |
| Processing records | Delivery notes for real/evidence deliveries carry classification labels that confirm the processing context. |

**Narrative for audit**: "The platform classifies all personal data storage locations and prevents synthetic test data from being confused with real personal data. Classification labels enable precise identification of real personal data storage targets for erasure requests and confirm the processing context of each stored record."

## 4. Cross-Regulatory Controls

| Control | BCBS 239 | MiFID II | EMIR | DORA | GDPR |
|---------|----------|----------|------|------|------|
| Storage classification | ✅ | ✅ | ✅ | ✅ | ✅ |
| Naming conventions | ✅ | ✅ | ✅ | ✅ | ✅ |
| Delivery-note labels | ✅ | ✅ | ✅ | ✅ | ✅ |
| Fail-fast validation | ✅ | ✅ | ✅ | ✅ | ✅ |
| Export guards | ✅ | ✅ | ✅ | ✅ | ✅ |
| Deviation tracking | ✅ | ✅ | ✅ | ✅ | ✅ |

## 5. Institutional Compliance Notes

This document maps the platform's classification boundary to regulatory obligations. It does not replace institutional compliance assessments. Institutions should:

1. Map the platform's classification controls to their own regulatory control frameworks.
2. Verify that classification labels are populated for all relevant data flows.
3. Include classification boundary evidence in their own audit responses.
4. Update this document when new regulatory frameworks or provisions are added to the platform's governing baseline.
