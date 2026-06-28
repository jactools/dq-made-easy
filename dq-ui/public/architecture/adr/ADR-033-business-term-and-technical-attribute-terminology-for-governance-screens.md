# ADR-033: Business Term and Technical Attribute Terminology for Governance Screens

**Status**: Accepted
**Date**: 2026-05-03
**Related**: [ADR-024](./ADR-024-pages-must-follow-selected-ui-components-and-shared-styles.md), [API-5 Implementation Plan](../../docs/implementation-details/API_5_IMPLEMENTATION_PLAN.md)

## Context

The governance UI uses several labels for the same conceptual flow:

- business-facing catalog terms used in rule expressions
- technical fields attached to versioned catalog records
- drift detection and revalidation views that show both layers side by side

The repository already distinguishes governed technical fields from business meaning in the data model. In particular, the active technical field surface is modeled as a version-attached attribute layer, while business catalog resolution is handled through the alias/business term flow.

The UI needed a single vocabulary so users would not have to infer whether a screen was talking about a business concept, a technical field, or an internal mapping helper.

## Decision

Use the following canonical UI vocabulary for governance and mapping screens:

- `Business Term` for the business-facing concept that users search for, review, and map
- `Technical Attribute` for the governed field or column attached to a data-object version
- `Business Term suggestions` for catalog-sourced matches that help resolve a business term
- `Business Term drift` for changes in the business term layer
- `Technical Attribute drift` for changes in the technical field layer
- `Manual Mapping` for user-provided mappings when catalog resolution is not sufficient

Keep backend payload keys, database column names, and route contracts unchanged unless a separate schema migration is explicitly planned.

## Rationale

- `Alias` is too ambiguous in the governance UI because it can be read as either a generic synonym or an internal implementation detail.
- `Data Element` is not a suitable replacement for the alias layer because the repository already uses the governed technical field layer for that concept.
- A business term / technical attribute split matches how users think about catalog resolution, drift review, and revalidation.
- The wording keeps the UI aligned with the supported model while avoiding unnecessary contract churn.

## Scope Boundaries

This decision applies to user-facing copy in the governance and mapping UI, including:

- Catalog Drift review screens
- business term mapping modals
- alias resolution diagnostics panels
- audit trail summaries for drift review actions
- feature lists and help text that describe the governance flow

It does not by itself:

- rename backend contract fields such as `aliasName`, `aliasMappings`, or `affectedAliases`
- rename database tables or columns such as `alias_source_metadata`
- introduce compatibility shims or dual-label payloads
- change the semantics of the catalog resolution pipeline

## Consequences

**Positive**
- The governance UI becomes easier to read and reason about.
- Business meaning and technical field meaning are shown explicitly instead of being conflated.
- The same vocabulary can be reused in help text, audit entries, and drift review flows.

**Negative**
- Several UI strings need to be updated together to keep the vocabulary consistent.
- Existing internal identifiers will continue to use alias-oriented names until a separate contract migration is proposed.

## Implementation Guidance

- Update the mapping modal to say `Map Business Terms to Technical Attributes`.
- Update drift review panels to say `Affected Business Terms`, `Business Term drift`, and `Technical Attribute drift`.
- Update diagnostics and audit summaries to describe reviews in terms of business terms, not aliases.
- Keep business term wording first whenever a screen presents both business meaning and technical field context.

## Related Artifacts

- [ADR-024](./ADR-024-pages-must-follow-selected-ui-components-and-shared-styles.md)
- [API-5 Implementation Plan](../../docs/implementation-details/API_5_IMPLEMENTATION_PLAN.md)
- [API-5 Metadata Integration](../../docs/features/API_5_METADATA_INTEGRATION.md)
- [API-5 Setup Guide](../../docs/technical/API_5_SETUP_GUIDE.md)
- [Architecture Decision Records](../ARCHITECTURAL_DECISIONS.md)
