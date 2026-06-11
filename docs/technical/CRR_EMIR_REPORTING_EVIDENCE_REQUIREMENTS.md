# CRR and EMIR Reporting Evidence Requirements

**Requirement ID**: DQ-REG-CRR-EMIR-001  
**Version**: 1.0  
**Effective Date**: 2026-04-22  
**Owner**: Data Governance + Engineering + Compliance  
**Related ADRs**: [ADR-030](../../architecture/adr/ADR-030-eu-financial-regulatory-baseline-and-control-mapping.md), [ADR-018](../../architecture/adr/ADR-018-iso-11179-based-data-definition-framework-for-bcbs-239-and-mifid-ii.md)  
**Related baseline**: [DQ-REG-EU-FIN-001](./EU_FINANCIAL_REGULATORY_CONTROL_MAPPING.md)

## 1. Purpose

Define the repository-level evidence baseline for CRR- and EMIR-relevant reporting use cases.

This requirement translates the regulatory control-mapping baseline into concrete expectations for repository-managed evidence, traceability, lineage, and reviewability when the platform is used in reporting-oriented financial-sector scenarios.

This is an engineering evidence baseline. It does not claim that repository artifacts alone satisfy all institutional CRR or EMIR obligations.

## 2. Scope

This requirement applies when repository-managed features, data products, execution flows, or delivery artifacts are positioned as inputs to:

- prudential or supervisory reporting,
- transaction or trade-reporting-aligned workflows,
- regulated financial evidence chains that depend on governed definitions, lineage, data-quality evidence, or reviewable control attestations.

## 3. Baseline Principles

1. Reporting-relevant evidence MUST be traceable from governed definition to operational artifact.
2. Repository claims about reporting support MUST be backed by explicit evidence artifacts, not only architecture intent.
3. Evidence MUST be reviewable, versioned, and attributable to repository-managed controls.
4. Where evidence is incomplete, the gap MUST be planned explicitly or recorded as a deviation.
5. The repository MUST use language such as "supports", "provides evidence for", or "maps to" rather than implying full regulatory compliance.

## 4. Requirement Statements

### 4.1 Governed Definitions and Stable Semantics

- Reporting-relevant data elements, identifiers, and data-product semantics MUST map to governed definitions where meaning materially affects downstream reporting evidence.
- Governed definitions SHOULD reference the semantic model established by [ADR-018](../../architecture/adr/ADR-018-iso-11179-based-data-definition-framework-for-bcbs-239-and-mifid-ii.md) and [ISO_11179_DATA_DEFINITION_FRAMEWORK.md](./ISO_11179_DATA_DEFINITION_FRAMEWORK.md).
- Repository artifacts MUST avoid relying on ad hoc, ungoverned meanings for reporting-significant fields when a governed definition exists.

### 4.2 Lineage and Provenance Evidence

- Reporting-oriented repository flows MUST be able to identify the upstream governed definition, producing service or workflow, relevant version, and downstream artifact boundary.
- Evidence SHOULD show which versioned rule, contract, delivery artifact, or transformation logic influenced a reporting-relevant output.
- Provenance fields and version references MUST be retained wherever the repository already supports them.

### 4.3 Data Quality and Timeliness Evidence

- Repository-managed reporting-aligned flows SHOULD be able to point to data-quality evidence, execution evidence, or validation evidence that is relevant to the reported artifact.
- If timeliness is claimed for a reporting flow, the repository MUST identify which timestamps, workflow states, or execution records provide that evidence.
- Data-quality or execution failures that materially affect reporting evidence MUST be visible in logs, results, or exception artifacts rather than remaining implicit.

### 4.4 Record-Keeping and Reviewability

- Evidence for reporting-aligned use cases MUST be reviewable after the fact through versioned documents, repository artifacts, logs, execution metadata, delivery notes, or equivalent records.
- Repository-managed changes to reporting-relevant semantics or controls MUST remain auditable through Git history, ADR history, or equivalent version-controlled artifacts.
- Where retention duration is use-case-specific, the repository MUST state that institutional retention policy remains authoritative beyond repository defaults.

### 4.5 Minimum Evidence Bundle

For a repository feature or release that claims CRR- or EMIR-relevant reporting support, the minimum evidence bundle SHOULD include:

1. the governing definition or semantic reference,
2. the relevant ADR or requirement reference,
3. lineage or provenance references,
4. data-quality or execution evidence where applicable,
5. record of relevant deviations or known limitations,
6. reviewable release or change-control evidence.

### 4.6 Deviations and Partial Coverage

- If a reporting-oriented feature lacks one or more required evidence elements, the limitation MUST be documented explicitly in feature notes, implementation notes, or the architecture deviation register.
- Missing evidence baselines for reporting claims MUST NOT be hidden behind generic statements such as "regulatory ready".

## 5. Evidence Sources

Evidence used to support this requirement MAY include:

- governed-definition artifacts and registry references,
- ADRs and technical requirements,
- delivery notes and contract artifacts,
- rule execution records and validation outputs,
- exception-store evidence where appropriate,
- release-readiness evidence,
- architecture deviations documenting gaps or limitations.

## 6. Current Repository Position

The repository already has strong foundations for this baseline through:

- [ADR-018](../../architecture/adr/ADR-018-iso-11179-based-data-definition-framework-for-bcbs-239-and-mifid-ii.md),
- [ISO_11179_DATA_DEFINITION_FRAMEWORK.md](./ISO_11179_DATA_DEFINITION_FRAMEWORK.md),
- versioned architecture artifacts,
- execution, delivery, and exception evidence patterns.

What this requirement adds is the explicit reporting-evidence baseline that was previously missing for CRR- and EMIR-oriented use cases.

## 7. Verification and Review

- Releases positioned for CRR- or EMIR-relevant use cases SHOULD include a review against `DQ-REG-CRR-EMIR-001`.
- New reporting-oriented features SHOULD identify how their evidence bundle is assembled.
- Open limitations SHOULD be reflected in implementation plans or deviations.

## 8. Change Control

- Update this requirement when the repository adds stronger reporting evidence patterns, evidence packs, or lineage/provenance capabilities.
- If a future dedicated evidence pack is created, it SHOULD cite this requirement as the governing baseline.