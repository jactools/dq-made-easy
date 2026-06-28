# ADR-018: ISO 11179-Based Data Definition Framework for BCBS 239 and MiFID II

**Status**: Accepted  
**Date**: 2026-04-15  
**Related**: [ADR-007](./ADR-007-dual-standard-api-contracts-openapi-odcs.md), [ADR-014](./ADR-014-gx-suite-registry-pyspark-execution-and-exception-store-separation.md), [ADR-017](./ADR-017-canonical-snake_case-api-fields.md)

## Context

dq-rulebuilder already models data products, data sets, data objects, versions, deliveries, rule artifacts, and execution results, but those concepts need a single normative definition framework to keep metadata consistent across services, APIs, and downstream consumers.

A platform-wide data definition framework is needed because:
- data definitions are reused across catalog, validation, execution, delivery, and reporting flows
- inconsistent naming, semantics, and identifiers make lineage and governance harder to prove
- BCBS 239 requires strong data aggregation, traceability, accuracy, completeness, timeliness, and governance controls
- MiFID II reporting and record-keeping obligations require consistent, auditable, and well-defined data elements
- the repository already has multiple contracts and artifacts that depend on stable field meaning across components

ISO/IEC 11179 provides a metadata registry model for defining data elements, data element concepts, value domains, and registration metadata in a structured and repeatable way. Using that model as the canonical definition framework gives the platform a common semantic layer for business and technical data definitions.

## Decision

Adopt an ISO/IEC 11179-based data definition framework as the canonical platform standard for all new and migrated data definitions.

The framework must:
- represent business concepts, data element concepts, and data elements explicitly
- define value domains, permissible values, units, formats, and constraints in a machine-readable way
- support registration metadata, ownership, versioning, provenance, and lifecycle state
- provide stable identifiers for data definitions across services and releases
- be the source of truth for data-catalog, execution, materialization, and reporting contracts where data meaning matters
- be designed to support BCBS 239 and MiFID II requirements for traceability, accuracy, auditability, and governance

The platform must not introduce new canonical data definitions outside this framework.

## Consequences

### Positive

- Shared semantics across catalog, rule execution, materialization, and reporting
- Better traceability from business concept to API contract to persisted result
- Stronger governance, ownership, and version control for critical data elements
- Clearer support for audit, lineage, and regulatory reporting requirements
- Reduced ambiguity when integrating external systems or downstream consumers

### Negative

- Additional modeling and governance overhead for teams defining new data elements
- Migration effort for existing definitions that do not yet map cleanly to ISO 11179 concepts
- Need for registry tooling, lifecycle management, and review processes
- Potential short-term friction while teams adapt from ad hoc definitions to governed definitions

## Implementation Guidance

- Treat the ISO 11179 framework as the canonical semantic layer for the platform.
- Reuse the existing OpenMetadata server as the initial registry backend where it can represent governed terms, ownership, versioning, lineage, and lifecycle state.
- Create or extend a metadata registry model that can store data element concepts, data elements, value domains, permissible values, definitions, examples, ownership, and lifecycle state.
- Use dq-made-easy as the canonical policy and contract layer above OpenMetadata so platform identifiers and validation rules remain stable.
- Align new catalog and execution contracts to reference registry identifiers rather than ad hoc free-text meanings.
- Map BCBS 239 controls to definition quality requirements such as completeness, traceability, consistency, accuracy, and governance evidence.
- Map MiFID II-related reporting fields to governed data elements with explicit provenance and version history.
- Incrementally migrate existing definitions and document any temporary exceptions with a retirement plan.

## Related Artifacts

- Architecture index: [ARCHITECTURAL_DECISIONS.md](../ARCHITECTURAL_DECISIONS.md)
- Framework draft: [ISO_11179_DATA_DEFINITION_FRAMEWORK.md](../../docs/technical/ISO_11179_DATA_DEFINITION_FRAMEWORK.md)
- OpenMetadata implementation details: [ISO_11179_OPENMETADATA_IMPLEMENTATION_DETAILS.md](../../docs/implementation-details/ISO_11179_OPENMETADATA_IMPLEMENTATION_DETAILS.md)
- Open Data Product Specification implementation details: [ISO_11179_OPEN_DATA_PRODUCT_SPECIFICATION_IMPLEMENTATION_DETAILS.md](../../docs/implementation-details/ISO_11179_OPEN_DATA_PRODUCT_SPECIFICATION_IMPLEMENTATION_DETAILS.md)
- Data catalog and delivery notes: [ABS-2 Data Catalog Materialization and Data Delivery Notes](../../docs/features/ABS_2_DATA_CATALOG_MATERIALIZATION.md)
- Delivery-linked execution: [ABS-3 Delivery-Linked Rule Execution and Result Notes](../../docs/features/ABS_3_DELIVERY_LINKED_RULE_EXECUTION.md)
- GX suite and execution separation: [ADR-014](./ADR-014-gx-suite-registry-pyspark-execution-and-exception-store-separation.md)
- Canonical API field naming: [ADR-017](./ADR-017-canonical-snake_case-api-fields.md)
