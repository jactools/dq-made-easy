# ISO 11179-Based Data Definition Framework for dq-made-easy

**Status**: Draft  
**Owner**: Engineering + Data Governance  
**Related ADR**: [ADR-018](/docs/architecture/adr/ADR-018-iso-11179-based-data-definition-framework-for-bcbs-239-and-mifid-ii/)

## 1. Purpose

Define a canonical metadata framework for data meaning across dq-made-easy so data definitions remain consistent, governed, auditable, and reusable across catalog, execution, materialization, delivery, and reporting flows.

This framework is based on ISO/IEC 11179 and is intended to support BCBS 239 and MiFID II-style requirements for traceability, accuracy, completeness, timeliness, governance, and evidence.

## 2. Why this is needed

The platform already has stable concepts for:
- data products, data sets, data objects, and data object versions
- deliveries and delivery notes
- rules, rule versions, GX suites, and run plans
- execution results and exception records
- API and UI contracts that depend on stable field meaning

What is missing is a single semantic layer that defines what those things mean, how they are related, and which identifiers remain stable over time.

Without that layer, different services can describe the same business concept using different names, formats, or assumptions.

## 3. Framework Principles

1. Use ISO/IEC 11179 concepts as the semantic baseline.
2. Separate business meaning from technical storage details.
3. Give each governed data definition a stable identifier and lifecycle state.
4. Define value domains explicitly, including format, units, permissible values, and constraints.
5. Prefer registry-backed definitions over free-text meanings in service contracts.
6. Keep version history and provenance attached to every governed definition.
7. Fail fast when a service depends on an undefined or ambiguous data meaning.

## 4. ISO 11179 Concept Model

The canonical concepts for this platform are:

### 4.1 Conceptual layer

- **Conceptual Domain**: the business subject area or bounded meaning space.
- **Data Element Concept**: the abstract idea being represented, such as a business attribute or operational measure.
- **Object Class**: the thing to which the concept applies, such as customer, delivery, rule, execution run, or run plan.
- **Property**: the characteristic being described, such as status, location, timestamp, threshold, or version.

### 4.2 Data definition layer

- **Data Element**: the governed representation of a concept in the platform.
- **Representation Term**: the semantic type family, such as identifier, name, code, amount, timestamp, status, location, or note.
- **Value Domain**: the allowed set of values, types, formats, units, or enumerations.
- **Permissible Value**: an allowed member of a value domain, especially for controlled vocabularies.

### 4.3 Registry layer

- **Registration Authority**: the team or governance function responsible for approving or stewarding a definition.
- **Registration Status**: lifecycle state, such as draft, reviewed, approved, deprecated, or retired.
- **Version**: immutable revision of a data definition.
- **Provenance**: source, author, approval, and change history information.

## 5. Current Platform Mapping

The following current platform concepts should be mapped into the framework.

### 5.1 Catalog hierarchy

| Current concept | ISO 11179 role | Notes |
|---|---|---|
| Data Product | Object Class / business context | Top-level business domain or product boundary |
| Data Set | Object Class / grouping context | Logical grouping within a product |
| Data Object | Object Class | Concrete entity or table-like business object |
| Data Object Version | Data Element or versioned object definition | Versioned schema boundary used by execution and delivery |
| Attribute | Data Element Concept / Data Element | A governed field with meaning and constraints |
| Data Delivery | Operational instance of a Data Element/Artifact | Runtime snapshot of delivered data |
| Data Delivery Note | Registry-backed operational metadata record | Read model describing one concrete delivery |

### 5.2 Rule and execution concepts

| Current concept | ISO 11179 role | Notes |
|---|---|---|
| Rule | Data Element Concept / business rule definition | Governs a check against data |
| Rule Version | Versioned governed definition | Immutable revision of a rule |
| GX Suite | Executable artifact derived from a governed definition | Portable runtime object |
| Run Plan | Governed execution plan | Scheduling and governance wrapper |
| Execution Run | Operational event record | Records actual execution of a suite or run plan |
| Exception Record | Controlled result record | Minimal row-level violation evidence |

### 5.3 Delivery-linked materialization concepts

| Current concept | ISO 11179 role | Notes |
|---|---|---|
| Materialized Output | Runtime artifact | Generated output written to AIStor or S3-compatible storage |
| Data Delivery Id | Stable operational identifier | Must not change once issued |
| Data Delivery Location | Location representation | Canonical storage reference for one delivery |
| Delivery Note Extension | Annotated operational metadata | Can carry downstream execution summary |

### 5.4 Product specification and contract layering

| Current concept | ISO 11179 role | Notes |
|---|---|---|
| Open Data Product Specification 4.1 | Product-level governed specification | Describes the data product as a governed business asset |
| ODCS 3.1 | Contract-level specification | Describes delivery and data-quality contracts for product data |

Open Data Product Specification 4.1 should govern the product boundary and its business meaning, while ODCS 3.1 should govern the data contracts attached to that product. Both can be backed by the same ISO 11179 registry model and OpenMetadata backend, but they serve different layers of the platform.

## 6. Canonical Definition Structure

Every governed definition should be representable with a shared structure.

### 6.1 Required fields

- `definition_id`: stable platform identifier
- `definition_name`: canonical name
- `definition_type`: concept, data_element_concept, data_element, value_domain, permissible_value, or registry_entry
- `business_definition`: human-readable meaning
- `object_class`: the entity or scope the definition applies to
- `property`: the characteristic being described
- `representation_term`: the semantic type family
- `value_domain`: type, format, enum, unit, or constraint set
- `version`: immutable version identifier
- `status`: draft, approved, deprecated, retired, or equivalent
- `owner`: accountable steward or team
- `source_system`: origin system or registry source
- `provenance`: created_by, approved_by, created_at, approved_at, change_reason
- `applies_to`: current platform objects or contracts that consume the definition

### 6.2 Optional fields

- `description`
- `synonyms`
- `examples`
- `allowed_values`
- `constraints`
- `sensitivity`
- `retention_class`
- `regulatory_tags`
- `lineage_refs`
- `compatibility_notes`

## 7. Recommended Registry Objects

The platform should treat the following as first-class registry objects or registry views.

1. **Concept Registry**
   - Stores the business concepts and object classes.
   - Answers: what is this thing?

2. **Data Element Registry**
   - Stores governed platform definitions used in APIs, reports, and execution artifacts.
   - Answers: what does this field mean?

3. **Value Domain Registry**
   - Stores allowed types, formats, units, enumerations, and constraints.
   - Answers: what values are valid?

4. **Lifecycle and Approval Registry**
   - Stores review, approval, deprecation, and retirement states.
   - Answers: can this definition be used now?

5. **Mapping Registry**
   - Stores the relationship between governed definitions and current platform artifacts.
   - Answers: where is this definition used?

## 8. OpenMetadata as the registry backend

Yes. The existing OpenMetadata server can be reused as the initial operational backend for this framework.

Recommended usage:
- use OpenMetadata glossary terms and custom properties as the first registry surface for governed data definitions
- map ISO 11179 concepts to OpenMetadata entities, classifications, tags, and term metadata where they fit naturally
- use OpenMetadata ownership, versioning, and lineage features to capture provenance and stewardship
- keep dq-made-easy-specific policy checks, stable identifiers, and contract validation in the platform layer above OpenMetadata
- keep runtime-only operational records, such as execution runs and exception rows, in the platform stores unless they are explicitly mirrored for governance reporting

What OpenMetadata should own:
- governed data element definitions and synonyms
- business concept metadata
- ownership, approval, and lifecycle status
- value-domain descriptions where the catalog model can express them cleanly
- lineage and usage references for cataloged definitions

What should remain in dq-made-easy:
- canonical API and execution contracts
- data delivery notes and runtime execution summaries
- exception-store persistence for row-level violations
- policy enforcement for BCBS 239 and MiFID II controls

This makes OpenMetadata the practical registry backend, while the framework remains the canonical semantic contract for the platform.

## 9. Platform Rules

### 9.1 Naming and identifiers

- Use stable registry identifiers in contracts where meaning matters.
- Use snake_case JSON on the wire for API payloads.
- Avoid ad hoc, free-text field names when a governed definition exists.
- Do not reassign a definition identifier to a different meaning.

### 9.2 Contract alignment

The following platform areas should reference the registry:
- data catalog metadata and delivery notes
- GX suite and run-plan artifacts
- rule versioning and execution metadata
- reporting and monitoring fields
- audit and governance records

### 9.3 Change control

- Any new canonical definition requires review and registration.
- Breaking semantic changes must create a new version.
- Deprecated definitions remain readable for compatibility but should not be used for new work.
- Retired definitions must be traceable for historical audit purposes.

## 10. BCBS 239 Alignment

This framework supports BCBS 239 by improving:
- accuracy of reported data definitions
- completeness of metadata and lineage
- traceability from business meaning to operational record
- timeliness through consistent, versioned semantics
- adaptability by allowing controlled change and versioning
- governance by assigning ownership and approval states

## 11. MiFID II Alignment

This framework supports MiFID II-style requirements by:
- ensuring regulated fields are defined consistently
- preserving evidence of provenance and version history
- maintaining clear reporting semantics for downstream consumers
- reducing ambiguity in operational and regulatory reporting data

## 12. Implementation Sequence

1. Inventory current platform fields and concepts.
2. Map existing objects to ISO 11179 concepts.
3. Register canonical data definitions for the most reused objects first.
4. Update new API and registry contracts to consume governed identifiers.
5. Add validation so undefined meanings cannot silently enter new contracts.
6. Migrate legacy free-text meanings into governed definitions over time.
7. Add review and approval workflow for definition changes.

## 13. Initial Scope for This Repository

The first set of governed definitions should cover:
- Data Product
- Data Set
- Data Object
- Data Object Version
- Data Delivery
- Data Delivery Note
- Rule
- Rule Version
- GX Suite
- Run Plan
- Execution Run
- Exception Record
- Materialization Request

## 14. Open Questions

- Should the registry live in Postgres first or in a dedicated metadata service?
- Which group owns definition approval: platform, data governance, or a joint board?
- How much of the registry should be surfaced in the UI versus remaining API-only?
- Should version changes be approved synchronously or through a staged review flow?

## 15. Related Documents

- [ADR-018](/docs/architecture/adr/ADR-018-iso-11179-based-data-definition-framework-for-bcbs-239-and-mifid-ii/)
- [ISO 11179 + OpenMetadata implementation details](/docs/implementation-details/ISO_11179_OPENMETADATA_IMPLEMENTATION_DETAILS/)
- [ISO 11179 + Open Data Product Specification implementation details](/docs/implementation-details/ISO_11179_OPEN_DATA_PRODUCT_SPECIFICATION_IMPLEMENTATION_DETAILS/)
- [ABS-2 Data Catalog Materialization and Data Delivery Notes](/docs/features/ABS_2_DATA_CATALOG_MATERIALIZATION/)
- [ABS-3 Delivery-Linked Rule Execution and Result Notes](/docs/features/ABS_3_DELIVERY_LINKED_RULE_EXECUTION/)
- [ADR-014](/docs/architecture/adr/ADR-014-gx-suite-registry-pyspark-execution-and-exception-store-separation/)
- [ADR-017](/docs/architecture/adr/ADR-017-canonical-snake_case-api-fields/)
