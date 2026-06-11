# ARCH-EXC-0007: CRR and EMIR Reporting Evidence Baseline Is Not Yet Defined

**Status**: Closed
**Category**: compliance
**Owner**: Data Governance
**First recorded**: 2026-04-22
**Last reviewed**: 2026-04-22
**Next review date**: none - closed on 2026-04-22
**Target closure date**: 2026-04-22
**Risk level**: high
**Impact level**: high
**Governing baseline**: [ADR-030 EU Financial Regulatory Baseline and Control Mapping](../adr/ADR-030-eu-financial-regulatory-baseline-and-control-mapping.md), [DQ-REG-EU-FIN-001](../../docs/technical/EU_FINANCIAL_REGULATORY_CONTROL_MAPPING.md), [ADR-018 ISO 11179-Based Data Definition Framework for BCBS 239 and MiFID II](../adr/ADR-018-iso-11179-based-data-definition-framework-for-bcbs-239-and-mifid-ii.md)

## Affected Surface

Repository evidence expectations for regulated reporting-oriented use cases that depend on governed semantics, lineage, traceability, timeliness, and reviewable control attestations for CRR- and EMIR-relevant data flows.

## Summary

This deviation was opened because the repository lacked a reporting-evidence baseline or control-attestation model for CRR- and EMIR-oriented use cases. That baseline is now defined.

## Rationale

The repository first established semantic and governance foundations through ADR-018 and then broadened the regulatory baseline through ADR-030, but no dedicated requirement or evidence pack has yet been created for reporting-grade evidence expectations.

## Risk Details

Architecture intent alone is weaker than explicit evidence and attestation paths when financial-sector users need to understand whether repository-managed outputs can support prudential or transaction-reporting controls.

## Impact Details

This affects how future reporting-aligned features, data products, lineage claims, and control narratives are positioned, reviewed, and evidenced for regulated financial-sector scenarios.

## Compensating Controls

ADR-018 and the ISO 11179 framework already provide strong direction for governed definitions, lineage, and traceability, and the new reporting-evidence requirement now supplies the missing baseline layer. Concrete evidence packs still remain a delivery concern for specific reporting-oriented releases or features.

## Validation and Evidence

- [CRR_EMIR_REPORTING_EVIDENCE_REQUIREMENTS.md](../../docs/technical/CRR_EMIR_REPORTING_EVIDENCE_REQUIREMENTS.md) now defines requirement `DQ-REG-CRR-EMIR-001` as the reporting-evidence baseline for CRR- and EMIR-relevant use cases.
- [EU_FINANCIAL_REGULATORY_CONTROL_MAPPING.md](../../docs/technical/EU_FINANCIAL_REGULATORY_CONTROL_MAPPING.md) now references that requirement in the CRR and EMIR sections.
- [EU_FINANCIAL_REGULATORY_GAP_ANALYSIS.md](../../docs/technical/gap-analysis/EU_FINANCIAL_REGULATORY_GAP_ANALYSIS.md) narrows `EU-GAP-006` to concrete evidence bundles rather than the absence of a baseline.

## Exit Criteria

Met on 2026-04-22 by adoption of [CRR_EMIR_REPORTING_EVIDENCE_REQUIREMENTS.md](../../docs/technical/CRR_EMIR_REPORTING_EVIDENCE_REQUIREMENTS.md).