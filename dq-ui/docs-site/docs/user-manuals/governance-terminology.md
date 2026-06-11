# Governance Terminology Reference Card

**Time to read:** 4 minutes
**Last updated:** 2026-05-04

## Purpose
This card collects the governance terms used in the app and its scripts, especially the business term and technical attribute work, so readers can find the approved wording in one place.

## Terms

| Term | Explanation | Last updated | Typical app context |
| --- | --- | --- | --- |
| Rule Kind | The canonical rule-shape label used by the app and scripts when selecting, filtering, validating, or reporting rules. Use this instead of check type in repo-owned code and docs. | 2026-05-04 | Validator scripts, rule authoring, supported-case catalogs, and lifecycle reporting |
| Business Term | The business-facing concept used in rule expressions, catalog matching, and governance screens when the screen is about meaning rather than storage. | 2026-05-03 | Business-term mapping, drift review, and rule authoring |
| Technical Attribute | The governed field or column attached to a data-object version. Use this when the screen is about the concrete technical field surface. | 2026-05-03 | Technical field screens, attribute mapping, and drift review |
| Business Term suggestions | Catalog-sourced matches that help resolve a business term. | 2026-05-03 | Suggestion lists shown while mapping or reviewing business terms |
| Business Term drift | Changes detected in the business term layer. | 2026-05-03 | Drift review panels and governance alerts |
| Technical Attribute drift | Changes detected in the technical field layer. | 2026-05-03 | Drift review panels and validation summaries |
| Affected Business Terms | The business terms whose meaning, mapping, or resolution changed. | 2026-05-03 | Change summaries, audit entries, and review results |
| Map Business Terms to Technical Attributes | The primary action framing for the modal that connects business meaning to the governed technical field layer. | 2026-05-03 | Mapping modal and workflow entry points |
| Catalog Suggestions | The catalog-backed suggestion set shown to help users resolve business terms. | 2026-05-03 | Catalog suggestion panels and helper lists |

## Context
Use rule-kind wording when the app or a script is talking about the canonical rule shape. Use business-term wording first when both layers appear together. Use technical-attribute wording when the screen is about the data-object-version field surface. Reserve Data Element for model documentation only if it is explicitly mapped to the technical attribute layer.

## Related cards
- [ADR-033: Business Term and Technical Attribute Terminology for Governance Screens](/docs/architecture/adr/ADR-033-business-term-and-technical-attribute-terminology-for-governance-screens/)