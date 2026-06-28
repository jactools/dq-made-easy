# ADR-035: Explicitly Exclude Great Expectations Data Docs From the Neutral Exception Surface and Require Protected Row-Level Analysis Capability

**Status**: Accepted
**Date**: 2026-05-08
**Related**: [ADR-014](./ADR-014-gx-suite-registry-pyspark-execution-and-exception-store-separation.md), [ADR-034](./ADR-034-engine-neutral-exception-fact-contract-family-and-storage-authority.md), [DQ-7.4 implementation details](../../docs/implementation-details/DQ_7_4_GX_SUITE_ORCHESTRATION_IMPLEMENTATION_DETAILS.md)

## Context

The platform now has a neutral exception-fact contract, neutral exception APIs, and a separate exception store / analytics model. The remaining question is whether Great Expectations (GX) Data Docs should be treated as part of that neutral exception-reporting surface.

Data Docs are GX-native artifacts. They are useful for GX-local debugging, but they are not engine-neutral and they do not match the platform direction established by the exception-fact and reason-analytics contracts. More importantly, row-level analysis must happen in a protected environment with explicit authorization, lineage, and record-identifier controls rather than through an engine-specific public report surface.

The decision must respect the repository's no-fallback policy: if protected row-level analysis is required, the platform should provide that capability directly instead of silently substituting a GX documentation artifact.

## Decision

Explicitly exclude Great Expectations Data Docs from the neutral exception-reporting surface.

Use the platform's protected row-level analysis capability as the supported solution for authorized drill-down into failed records, supporting evidence, and reason analytics.

This means:

- Data Docs are not part of the canonical `/exceptions` family or neutral exception analytics APIs.
- Data Docs are not a substitute for row-level exception facts, exception summaries, or reason analytics.
- Any GX-specific documentation links, if retained at all, must live only behind GX-specific operational views and must remain optional convenience links.
- Row-level analysis must be available through a protected environment that enforces workspace authorization, delivery or execution ownership, and controlled access to record identifiers.

## Consequences

### Positive

- Keeps the neutral exception surface engine-independent and aligned with the canonical exception-fact contract.
- Avoids coupling the platform's reporting model to GX-specific documentation semantics.
- Preserves a single source of truth for row-level failure facts, reason codes, and analytics.
- Makes the authorization boundary explicit for sensitive record-level analysis.
- Reduces the amount of cross-surface duplication that would otherwise be required to mirror Data Docs content.

### Negative

- Removes a familiar GX-native drill-down path from the neutral surface.
- Requires the platform to provide its own protected row-level analysis capability rather than relying on Data Docs as a shortcut.
- Adds implementation work for protected analysis views, permissions, and lineage-aware access checks.

## Implementation Guidance

- Keep Data Docs out of the neutral exception contract, neutral exception APIs, and neutral analytics read models.
- Provide protected row-level analysis views over canonical exception facts and analytics projections instead of exposing GX-native docs as the main drill-down path.
- Reuse the existing workspace-scoped and delivery/execution-scoped authorization model for raw exception fact access.
- Continue to treat GX-native diagnostic artifacts as internal implementation details only.
- If a GX-specific link is provided in the future, it must be optional, clearly labeled as GX-specific, and never required for core exception analysis.

## Related Artifacts

- [docs/contracts/exception-fact/README.md](../../docs/contracts/exception-fact/README.md)
- [docs/contracts/execution-engine-capabilities/README.md](../../docs/contracts/execution-engine-capabilities/README.md)
- [docs/implementation-details/DQ_7_4_GX_SUITE_ORCHESTRATION_IMPLEMENTATION_DETAILS.md](../../docs/implementation-details/DQ_7_4_GX_SUITE_ORCHESTRATION_IMPLEMENTATION_DETAILS.md)