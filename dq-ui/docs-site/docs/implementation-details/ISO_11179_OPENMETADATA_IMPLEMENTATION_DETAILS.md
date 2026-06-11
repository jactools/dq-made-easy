# ISO 11179 + OpenMetadata Implementation Details

This note turns the ISO 11179-based data definition framework into an actionable backlog.

Goal: reuse the existing OpenMetadata server as the initial registry backend for governed data definitions, while keeping dq-made-easy as the canonical policy and contract layer above it.

## Problem Statement

The platform already has OpenMetadata integration for catalog and contract lookups, but the ISO 11179 framework needs a concrete backend mapping and migration path.

What is needed is a registry implementation that:
- maps ISO 11179 concepts to OpenMetadata entities and metadata surfaces
- keeps governed definitions, ownership, versioning, and lineage in a central catalog backend
- preserves dq-made-easy-specific policy enforcement and contract stability
- supports BCBS 239 and MiFID II-oriented traceability and audit evidence
- migrates existing free-text or ad hoc meanings into governed definitions without breaking current consumers

## Recommended Backend Split

- OpenMetadata is the operational registry backend for governed business metadata.
- dq-made-easy is the policy, contract, and runtime enforcement layer.
- Runtime records such as execution runs, delivery notes, and exception rows remain in platform stores unless explicitly mirrored for governance reporting.
- Registry-backed identifiers should be referenced in new contracts instead of ad hoc field names.

## OpenMetadata Mapping Strategy

### Conceptual mapping

| ISO 11179 concept | OpenMetadata surface | Notes |
|---|---|---|
| Conceptual Domain | Glossary, category, or domain grouping | Use to group related business meanings |
| Data Element Concept | Glossary term or custom metadata entity | Represents the abstract business meaning |
| Object Class | Glossary term, domain label, or custom property | The business object the concept applies to |
| Property | Custom property or term description | The characteristic being defined |
| Data Element | Glossary term plus custom metadata | Governs the platform-visible definition |
| Value Domain | Custom property, enum metadata, or data type metadata | Captures allowed values, units, formats, constraints |
| Permissible Value | Controlled vocabulary entry | Use when the domain is enumerated |
| Registration Authority | Ownership / stewardship metadata | Team or function responsible for approval |
| Registration Status | Term status / lifecycle metadata | draft, approved, deprecated, retired, etc. |
| Provenance | Change history / audit metadata | Created by, approved by, timestamps, reason |

### Platform concept mapping

| dq-made-easy concept | OpenMetadata representation | Notes |
|---|---|---|
| Data Product | Glossary domain or category grouping | Top-level business boundary |
| Data Set | Glossary grouping / domain tag | Logical collection within a product |
| Data Object | Glossary term / business entity concept | Concrete business object |
| Data Object Version | Versioned metadata record | Versioned schema boundary |
| Attribute | Glossary term with value-domain metadata | Governed field definition |
| Data Delivery | Operational artifact reference | Keep runtime record in dq-made-easy |
| Data Delivery Note | Runtime note with optional mirrored summary | Use dq-made-easy as source of truth |
| Rule / Rule Version | Governed definition references | Registry metadata for meaning and lineage |
| GX Suite | Executable artifact reference | Keep runtime artifact ownership in dq-made-easy |
| Run Plan | Governed execution plan reference | Can reference registry terms for scope/meaning |
| Execution Run | Runtime record | Keep in dq-made-easy |
| Exception Record | Runtime evidence record | Keep in dq-made-easy |

## Numbered Backlog

1. [ ] (ISO11179-OM-01) Define the canonical ISO 11179 to OpenMetadata entity mapping.
   - Map concepts, object classes, properties, data elements, value domains, and lifecycle states.
   - Decide which surfaces use glossary terms, custom metadata, tags, or domain groupings.
   - Document the mapping in a reusable reference table.

2. [ ] (ISO11179-OM-02) Define the dq-made-easy registry contract.
   - Introduce stable platform identifiers for governed definitions.
   - Keep dq-made-easy as the source of truth for contract validation and policy enforcement.
   - Ensure external API and execution contracts reference registry identifiers where meaning matters.

3. [ ] (ISO11179-OM-03) Design the OpenMetadata sync model.
   - Decide whether definitions are pushed, pulled, or bi-directionally synchronized.
   - Define how glossary terms, custom properties, and lifecycle state are written.
   - Preserve provenance and version history during sync.

4. [ ] (ISO11179-OM-04) Add storage and lookup support for registry-backed identifiers.
   - Persist the mapping between platform identifiers and OpenMetadata entity identifiers.
   - Support lookup by platform identifier, glossary term, and business concept.
   - Fail fast when a requested definition cannot be resolved.

5. [ ] (ISO11179-OM-05) Add migration rules for existing platform concepts.
   - Map current data product, data set, data object, rule, suite, and delivery concepts to governed definitions.
   - Identify ad hoc meanings that require normalization.
   - Record retirement plans for legacy definitions.

6. [ ] (ISO11179-OM-06) Add governance and approval workflow alignment.
   - Define who approves new or changed definitions.
   - Preserve audit evidence for approvals, deprecations, and retirements.
   - Ensure the approval flow supports BCBS 239 and MiFID II evidence needs.

7. [ ] (ISO11179-OM-07) Add validation and compatibility tests.
   - Verify lookup and sync behavior for governed definitions.
   - Verify missing or ambiguous definitions fail fast.
   - Verify the framework can serve current catalog, execution, and reporting consumers.

## Recommended First Slice

If the goal is to show stakeholders visible progress quickly, the next implementation should be a thin vertical slice for governed-definition lookup, not a full sync or approval workflow.

The first slice should prove five things:
- OpenMetadata can act as the initial registry backend.
- dq-made-easy remains the contract and policy layer above it.
- Stable registry-backed identifiers can be resolved from the platform.
- Missing or ambiguous definitions fail fast.
- The same lookup path can later be reused by contracts, catalog views, product specs, and execution metadata.

### Scope of the first slice

Keep the scope deliberately narrow:
- support read-only lookup only
- support three definition types only: `data_product`, `data_object`, and `attribute`
- seed only 5 to 10 governed definitions for one realistic demo domain
- expose one API endpoint for direct lookup by stable identifier
- do not implement write-back, bi-directional sync, or approval workflow yet

This is enough to demonstrate the architecture without committing to the larger operational model too early.

## Concrete 1-2 Day Implementation Plan

### Day 1 goal

Implement a minimal registry contract and a resolver service that reads governed definitions from OpenMetadata-backed metadata and returns a canonical dq-made-easy response model.

### Day 2 goal

Add a single API endpoint, seed demo definitions, and show fail-fast behavior for missing or ambiguous lookups.

## First Slice Task List

1. [x] (ISO11179-OM-S1-01) Add the canonical governed-definition read model.
   Create `dq-api/fastapi/app/api/v1/schemas/registry_definition_view.py` with a read-only response model covering at least `definition_id`, `definition_type`, `definition_name`, `business_definition`, `object_class`, `property`, `representation_term`, `value_domain`, `status`, `owner`, `source_system`, `openmetadata_entity_id`, `openmetadata_entity_type`, `version`, `provenance`, and `applies_to`.

2. [x] (ISO11179-OM-S1-02) Implement the OpenMetadata-backed resolver service.
   Add `dq-api/fastapi/app/application/services/registry_definition_resolver.py`, modeled after `dq-api/fastapi/app/application/services/data_contract_resolver.py`, with a public `resolve_definition(definition_id: str) -> dict[str, Any]` method and a fail-fast `RegistryDefinitionLookupError` for missing, ambiguous, or structurally incomplete definitions.

3. [x] (ISO11179-OM-S1-03) Add dependency wiring for registry-definition lookup.
   Extend `dq-api/fastapi/app/core/dependencies.py` with `get_registry_definition_resolver()` so the new resolver follows the same dependency pattern as the current OpenMetadata-backed services.

4. [x] (ISO11179-OM-S1-04) Expose a read-only registry-definition endpoint.
   Add `dq-api/fastapi/app/api/v1/endpoints/registry_definitions.py` and register it in `dq-api/fastapi/app/api/v1/router.py` under the existing data-catalog group with `GET /api/data-catalog/v1/registry/definitions/&#123;definition_id&#125;` returning `200` on success, `404` on missing definitions, `409` on ambiguous identifiers, and `503` when OpenMetadata is unavailable or misconfigured.

5. [x] (ISO11179-OM-S1-05) Define the demo payload contract for the stakeholder slice.
   Ensure the endpoint returns a normalized dq-made-easy response shape for examples like `def.attribute.customer_id`, including the governed meaning, owner, lifecycle state, value domain, provenance, and OpenMetadata reference fields.

6. [x] (ISO11179-OM-S1-06) Seed a minimal demo definition set.
   Create a bounded demo set for one domain, preferably `retail_banking`, with 5 to 10 definitions covering one `data_product`, one `data_object`, and three to five `attribute` definitions such as `def.data_product.retail_banking`, `def.data_object.customer`, `def.attribute.customer_id`, `def.attribute.customer_status`, and `def.attribute.account_opened_at`.
   Implemented as `dq-metadata/demo/openmetadata_registry_definitions.retail_banking.json` plus the strict loader `scripts/seed_openmetadata_registry_definitions.sh` -> `dq-metadata/scripts/seed_openmetadata_registry_definitions.py`.

7. [x] (ISO11179-OM-S1-07) Add resolver-level tests for fail-fast behavior.
   Add `dq-api/fastapi/tests/application/services/test_registry_definition_resolver.py` covering successful resolution, missing identifiers, ambiguous identifiers, and incomplete OpenMetadata payloads.

8. [x] (ISO11179-OM-S1-08) Add API-level tests for contract shape and error mapping.
   Add `dq-api/fastapi/tests/api/test_registry_definitions_endpoint.py` verifying snake_case response fields plus `200`, `404`, `409`, and `503` response behavior.

9. [x] (ISO11179-OM-S1-09) Prepare the stakeholder demo flow.
   Demonstrate one successful lookup, such as `GET /api/data-catalog/v1/registry/definitions/def.attribute.customer_id`, and one fail-fast `404` lookup for an unknown identifier to show that governed-definition resolution is live and enforced.
   Use `./scripts/seed_openmetadata_registry_definitions.sh` to load the committed retail-banking demo set before running the lookup against a live OpenMetadata stack.

## Definition of Done for the First Slice

The first slice is complete when all of the following are true:
- a stakeholder can call a single API endpoint with a stable `definition_id`
- the API returns a normalized governed-definition response from OpenMetadata-backed metadata
- the lookup fails fast for missing or ambiguous definitions
- the implementation uses the existing resolver/dependency patterns already present in the repository
- the demo can show one product, one object, and several governed attributes with stable identifiers

## Why This Slice Should Come Before Sync and Product Spec Work

This slice should be implemented before full sync or Open Data Product Specification work because it establishes the one thing every later feature depends on: stable, resolvable governed-definition identifiers.

Without this lookup capability:
- product specs cannot reliably reference governed product semantics
- contracts cannot reference registry-backed field meanings
- run plans and catalog artifacts cannot attach stable semantic identifiers
- stakeholder demos remain design-heavy and implementation-light

With this lookup capability in place, the next steps become much more concrete:
- add OpenMetadata sync
- add mapping persistence
- add product-spec linkage
- add contract references to governed identifiers

## Implemented Next Slice: Attribute Definition Mapping

The next implemented slice moves governed-definition linkage into the Data Catalog workflow instead of the rule authoring flow.

### What is now implemented

- A persisted `attribute_definition_mappings` model in the SQLAlchemy schema, with Alembic migration authority.
- Read and write endpoints under the existing data-catalog API surface for attribute-to-definition mappings.
- A searchable registry-definition list endpoint for dedicated UI workflows.
- A dedicated dq-made-easy UI page for mapping Definitions to versioned attributes.
- Effective mapping resolution on `attributes-catalog` reads so the UI can distinguish between explicit, inherited, and explicitly-cleared mappings.

### Persistence model

The linkage is stored as a dedicated per-attribute record, not in JSON blobs and not inferred heuristically at write time.

- `mapping_state = mapped` means the attribute version has an explicit definition link.
- `mapping_state = unmapped` means the attribute version has an explicit tombstone that clears inheritance for that version and later descendants.
- No record on the current version means the read path attempts inheritance from the latest earlier version of the same data object that contains an attribute with the same name.

### Effective mapping statuses returned by the API

- `explicit`: the current attribute version has its own mapping record.
- `inherited`: the current attribute version inherited the mapping from a prior version.
- `explicit_unmapped`: the current attribute version explicitly cleared the link.
- `inherited_unmapped`: the current attribute version inherits a prior explicit clear.
- `unmapped`: no effective definition link could be resolved.

### Fail-fast behavior

This slice follows the repository no-fallback policy.

- Mapping writes validate the target registry definition before persisting.
- Unknown definitions fail fast and return an error response instead of silently storing an unverified reference.
- OpenMetadata unavailability still surfaces as a failing registry-definition operation rather than a degraded local fallback.

### UI placement

The dedicated page sits in the Data Catalog navigation as `Definition Mappings`.

- The steward selects a product, dataset, object, and version.
- The page lists the versioned attributes and shows their effective mapping status.
- The workbench allows searching registry Definitions, applying an explicit override for the selected version, or explicitly clearing the link.

### Version inheritance rule

The intended governance rule is now encoded in the read model:

- a later version preserves the prior definition link by default
- the user can override the inherited mapping on that later version
- the user can also clear the mapping on that later version, which blocks further inheritance until another explicit mapping is set

## Suggested Demo Narrative

Use the first stakeholder demo to show this simple flow:
- call `GET /api/data-catalog/v1/registry/definitions/def.attribute.customer_id`
- show the governed business meaning, owner, lifecycle state, value domain, and OpenMetadata reference
- call the same endpoint with an unknown ID and show a fail-fast `404`
- explain that this is the foundation for product specs, contract references, and governed execution metadata

That is enough to demonstrate momentum without overcommitting to the full target architecture.

## Migration Sequence

### Phase 1: Inventory and classification
- Inventory current catalog, rule, execution, and delivery fields.
- Classify each field as concept, object class, property, data element, or value domain.
- Identify fields that already have stable meaning versus those that need normalization.

### Phase 2: Registry model definition
- Define the platform registry contract.
- Map the first set of governed definitions into OpenMetadata.
- Establish the approval and lifecycle metadata that will be stored for each definition.

### Phase 3: Synchronization and lookup
- Implement sync from dq-made-easy registry records to OpenMetadata.
- Add read-path lookup from contracts and UIs to the registry backend.
- Fail fast when a consumer requests an undefined meaning.

### Phase 4: Consumer migration
- Update catalog, execution, delivery, and reporting contracts to reference governed identifiers.
- Replace free-text meaning dependencies with registry-backed lookups.
- Maintain backward compatibility until the migration is complete.

### Phase 5: Governance hardening
- Add approval workflows and audit evidence.
- Add lifecycle state enforcement and deprecation handling.
- Review the registry model against BCBS 239 and MiFID II evidence needs.

## Acceptance Criteria

- OpenMetadata can serve as the initial registry backend for governed data definitions.
- dq-made-easy retains control of policy, contract, and runtime enforcement.
- Canonical platform concepts can be resolved to registry-backed identifiers.
- Missing or ambiguous definitions fail fast rather than silently falling back.
- Existing consumers can migrate incrementally without breaking current execution or delivery flows.

## Related references

- [ISO 11179 framework](/docs/technical/ISO_11179_DATA_DEFINITION_FRAMEWORK/)
- [ADR-018](/docs/architecture/adr/ADR-018-iso-11179-based-data-definition-framework-for-bcbs-239-and-mifid-ii/)
- [OpenMetadata catalog setup](/docs/technical/API_5_SETUP_GUIDE/)
- [API-5 implementation plan](/docs/implementation-details/API_5_IMPLEMENTATION_PLAN/)
