# ARCH-EXC-0006: Repository-Wide Data Protection and Data Access Policy Is Not Yet Defined

**Status**: Approved
**Category**: compliance
**Owner**: Data Governance
**First recorded**: 2026-04-22
**Last reviewed**: 2026-04-22
**Next review date**: 2026-05-31
**Target closure date**: 2026-09-30
**Risk level**: high
**Impact level**: high
**Governing baseline**: [ADR-030 EU Financial Regulatory Baseline and Control Mapping](../adr/ADR-030-eu-financial-regulatory-baseline-and-control-mapping.md), [DQ-REG-EU-FIN-001](../../docs/technical/EU_FINANCIAL_REGULATORY_CONTROL_MAPPING.md)

## Affected Surface

Repository-wide policy treatment for personal data, sensitive operational data, business data classes, access review expectations, handling rules, retention alignment, and cross-surface data protection responsibilities.

## Summary

The repository does not yet define one cross-cutting data protection and data access policy for platform data beyond narrower controls for observability, logging, API authorization, and the repository's broader EU regulatory baseline for data usage and protection.

## Rationale

Governance work was established incrementally through security, logging, auth, retention, and financial-regulatory artifacts, but those controls were written per surface rather than unified into one repository-wide data protection and access policy.

## Risk Details

Without a single policy baseline, data handling rules remain fragmented, contributors can apply inconsistent assumptions to business data and personal data, and privacy or access obligations from GDPR, DORA, BCBS 239, CRR, MiFID II, EMIR, and applicable NIS2-style governance can be interpreted too narrowly around logs and credentials only.

## Impact Details

This affects policy clarity for API payloads, exception evidence, data-delivery artifacts, operational data, administrative surfaces, and future regulated-use-case features that need one authoritative handling model.

## Compensating Controls

The repository already has explicit controls for API scopes, observability access, logging redaction, and retention/disposal, and the EU financial regulatory control map plus gap analysis now make the missing cross-cutting policy visible instead of implicit.

## Validation and Evidence

- [EU_FINANCIAL_REGULATORY_CONTROL_MAPPING.md](../../docs/technical/EU_FINANCIAL_REGULATORY_CONTROL_MAPPING.md) explicitly notes that a single repository-wide data-protection and data-access policy is not yet established.
- [EU_FINANCIAL_REGULATORY_GAP_ANALYSIS.md](../../docs/technical/gap-analysis/EU_FINANCIAL_REGULATORY_GAP_ANALYSIS.md) records this as `EU-GAP-001`.
- [LOG_INTEGRITY_AND_ACCESS_CONTROL.md](../../docs/technical/LOG_INTEGRITY_AND_ACCESS_CONTROL.md) and [EDR-023-API-auth-scope-enforcement-and-role-based-access.md](../../docs/engineering-decisions/EDR-023-API-auth-scope-enforcement-and-role-based-access.md) show the current per-surface control pattern rather than one platform-wide policy.

## Exit Criteria

A repository-wide data protection and data access policy is adopted, linked from the regulatory control mapping and technical index, and defines data classes, access principles, handling rules, review expectations, and policy ownership across the platform, aligned with BCBS 239, GDPR, CRR, MiFID II, EMIR, DORA, and applicable NIS2-style governance where relevant.