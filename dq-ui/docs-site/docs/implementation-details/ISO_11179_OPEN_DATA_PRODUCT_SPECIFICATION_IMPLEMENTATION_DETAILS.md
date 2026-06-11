# ISO 11179 + Open Data Product Specification Implementation Details

This note turns the data-product side of the ISO 11179 framework into an actionable backlog.

Goal: use Open Data Product Specification 4.1 as the governing product-level specification for data products, while keeping OpenMetadata as the registry backend and ODCS 3.1 as the data-contract layer for delivery and data-quality contracts.

## Problem Statement

The repository already uses ODCS for data contracts, but data products need their own governing specification layer.

What is needed is a product-specification model that:
- defines what a data product is, what scope it covers, and which business concepts it owns
- separates product-level meaning from downstream delivery-level contracts
- provides a stable semantic anchor for data products, data sets, and product ownership
- aligns product-level semantics with ISO 11179 concepts and registry-backed identifiers
- can be backed by OpenMetadata so product definitions remain searchable, versioned, and governed

## Recommended Layering

- Open Data Product Specification 4.1 is the product-level governing specification.
- ODCS 3.1 remains the contract-level specification for data-quality and delivery interfaces.
- OpenMetadata is the registry backend for product metadata, ownership, lineage, and lifecycle state.
- dq-made-easy enforces platform policy, stable identifiers, and runtime validation.

## Mapping Strategy

### Open Data Product Specification 4.1 to ISO 11179

| Product-spec concept | ISO 11179 role | Notes |
|---|---|---|
| Data Product | Object Class / business context | Top-level governed product boundary |
| Product Objective | Conceptual Domain / business goal | Why the product exists |
| Product Scope | Object Class / scope boundary | What the product includes and excludes |
| Product Owner | Registration Authority / steward | Accountable role for the product |
| Product Descriptor | Data Element Concept | Governed business meaning of the product |
| Product Attribute | Data Element | Specific governed property of the product |
| Product Contract Reference | External contract link | Points to ODCS or other delivery contracts |
| Product Lifecycle State | Registration Status | draft, active, deprecated, retired, etc. |

### Relationship to ODCS 3.1

- **Open Data Product Specification 4.1** should describe the product as a governed business asset.
- **ODCS 3.1** should describe the data-quality contract for the product’s data delivery interfaces.
- A single data product can have one or more ODCS contracts associated with it.
- The product specification should reference the contract identifiers, but not replace them.

### Relationship to OpenMetadata

OpenMetadata can store the product-spec metadata through glossary terms, custom properties, ownership, lifecycle state, and lineage.

Suggested OpenMetadata surfaces:
- glossary terms for product names and business definitions
- custom metadata for product scope, objectives, and lifecycle
- owner/steward fields for accountability
- lineage links to data sets, data objects, and downstream contracts
- tags or classifications for regulatory or domain grouping

## Numbered Backlog

1. [x] (ISO11179-ODP-01) Define the Open Data Product Specification 4.1 mapping.
   - Map product, scope, objective, owner, and lifecycle concepts to ISO 11179.
   - Decide which product attributes are represented as glossary terms or custom metadata.
   - Document the canonical product-spec field set.

2. [x] (ISO11179-ODP-02) Define the product-spec registry contract.
   - Introduce stable product-spec identifiers.
   - Separate product identifiers from contract identifiers.
   - Preserve product lifecycle and stewardship metadata.

3. [x] (ISO11179-ODP-03) Link product specs to ODCS contracts.
   - Associate each governed data product with its delivery contracts.
   - Ensure contract identifiers remain distinct from product identifiers.
   - Allow one product to reference multiple ODCS contracts where needed.

4. [x] (ISO11179-ODP-04) Add OpenMetadata storage and sync support.
   - Map product-spec metadata into OpenMetadata entities and custom properties.
   - Preserve ownership, lineage, and version history.
   - Fail fast when a product specification cannot be resolved.
   - Current state: product-spec lookup, registry listing, stable-id conflict validation, and OpenMetadata-backed create/update sync are implemented through the canonical product-spec resolver and `POST`/`PUT` API surface.

5. [x] (ISO11179-ODP-05) Add migration rules for existing data products.
   - Classify current data products into governed product-spec records.
   - Normalize product names, scope boundaries, and ownership metadata.
   - Record retirement plans for legacy product definitions.
   - Current state: canonical `POST /api/data-catalog/v1/product-specs/import` now ingests bulk product-spec manifests with backend-owned normalization, dry-run reporting, create/update outcomes, duplicate stable-id protection, and migration metadata persisted through the OpenMetadata sync seam.

6. [x] (ISO11179-ODP-06) Add validation and compatibility tests.
   - Verify product-spec lookup and linkage to ODCS contracts.
   - Verify missing or ambiguous product definitions fail fast.
   - Verify current product, catalog, and reporting consumers continue to work.
   - Current state: focused resolver and API tests cover lookup, registry listing, stewardship summary reporting, stewardship lifecycle actions, linkage, filtering, fail-fast behavior, bulk import/report compatibility, and downstream consumer compatibility scenarios across the canonical product-spec API seam.

## Recommended First Slice

If the goal is to show stakeholders visible progress quickly, the first implementation should be a thin read-only product-spec slice that resolves one governed data product and its linked ODCS contracts.

The first slice should prove five things:
- Open Data Product Specification 4.1 can be represented as a governed product layer in dq-made-easy.
- OpenMetadata can serve the product-spec metadata needed for lookup.
- product-spec identifiers remain distinct from ODCS contract identifiers.
- product specs can reference registry-backed semantics and linked contracts without collapsing the layers.
- missing or ambiguous product definitions fail fast.

### Scope of the first slice

Keep the scope deliberately narrow:
- support read-only lookup only
- support one demo product specification only
- link that product to one or two ODCS contracts only
- expose one API endpoint for lookup by stable product-spec identifier
- do not implement write-back, authoring UI, or lifecycle workflow yet

This is enough to demonstrate the layering without overbuilding the full governance model.

## Concrete 1-2 Day Implementation Plan

### Day 1 goal

Implement a minimal product-spec response model and a resolver that reads a governed product specification from OpenMetadata-backed metadata.

### Day 2 goal

Expose one endpoint, attach one or two linked ODCS contract references, and show fail-fast behavior for unresolved product specs.

## First Slice Task List

Current status: the backend lookup, registry-read, lifecycle write, stewardship workflow, and bulk migration-import slices are implemented. The demo ODCS contract and ODPS product-spec seed assets are committed, the demo product spec has been seeded into the dev OpenMetadata stack, the running dq-made-easy HTTP surface has captured the live lookup walkthrough, the product-spec registry list contract is available for backend-owned filtering and pagination, canonical `POST`/`PUT` lifecycle operations synchronize product-spec records back into OpenMetadata with stable-id conflict checks, canonical `POST /api/data-catalog/v1/product-specs/import` supports manifest-driven migration with dry-run and create/update reporting, and canonical stewardship/reporting routes (`GET /api/data-catalog/v1/product-specs/summary`, `POST /api/data-catalog/v1/product-specs/&#123;product_spec_id&#125;/stewardship-actions`) are now covered by focused resolver/API compatibility tests.

1. [x] (ISO11179-ODP-S1-01) Add the canonical product-spec read model.
   Create `dq-api/fastapi/app/api/v1/schemas/product_spec_view.py` with a read-only response model covering at least `product_spec_id`, `product_name`, `product_version`, `product_lifecycle_state`, `product_owner`, `product_objective`, `product_scope`, `business_definition`, `registry_definition_ids`, `odcs_contract_refs`, `openmetadata_entity_id`, `openmetadata_entity_type`, `source_system`, and `provenance`.

2. [x] (ISO11179-ODP-S1-02) Implement the OpenMetadata-backed product-spec resolver service.
   Add `dq-api/fastapi/app/application/services/product_spec_resolver.py` that reads a product specification by stable identifier, normalizes OpenMetadata-backed metadata into the dq-made-easy read model, and fails fast when the product spec is missing, ambiguous, or structurally incomplete.

3. [x] (ISO11179-ODP-S1-03) Add dependency wiring for product-spec lookup.
   Extend `dq-api/fastapi/app/core/dependencies.py` with `get_product_spec_resolver()` so product-spec resolution follows the same dependency pattern as the existing OpenMetadata-backed services.

4. [x] (ISO11179-ODP-S1-04) Expose a read-only product-spec endpoint.
   Add `dq-api/fastapi/app/api/v1/endpoints/product_specs.py` and register it in `dq-api/fastapi/app/api/v1/router.py` under the existing data-catalog group with `GET /api/data-catalog/v1/product-specs/&#123;product_spec_id&#125;` returning `200` on success, `404` on missing product specs, `409` on ambiguous identifiers, and `503` when OpenMetadata is unavailable or misconfigured.

5. [x] (ISO11179-ODP-S1-05) Define the demo payload contract for the stakeholder slice.
   Ensure the endpoint returns a normalized dq-made-easy response shape that clearly separates the product-spec identifier from linked ODCS contract identifiers and includes product objective, scope, ownership, lifecycle state, and registry-backed semantic references.

6. [x] (ISO11179-ODP-S1-06) Seed a minimal demo product specification.
   Implemented as `dq-metadata/demo/openmetadata_product_specs.retail_banking.json` plus `scripts/seed_openmetadata_product_specs.sh`, with the linked ODCS demo contract committed in `data_sources/contracts/demo-retail-banking-customer-360.odcs.yaml`. The demo product spec has been seeded into the dev OpenMetadata stack and linked to the live imported contract entity.

7. [x] (ISO11179-ODP-S1-07) Add resolver-level tests for fail-fast behavior.
   Add `dq-api/fastapi/tests/application/services/test_product_spec_resolver.py` covering successful resolution, missing product-spec identifiers, ambiguous matches, missing linked contract references, and incomplete OpenMetadata payloads.

8. [x] (ISO11179-ODP-S1-08) Add API-level tests for contract shape and error mapping.
   Add `dq-api/fastapi/tests/api/test_product_specs_endpoint.py` verifying snake_case response fields plus `200`, `404`, `409`, and `503` response behavior.

9. [x] (ISO11179-ODP-S1-09) Prepare the stakeholder demo flow.
   The demo data is now live in OpenMetadata for `ps.retail_banking_customer_360`, and the running dq-made-easy HTTP surface now has captured evidence for both the successful product-spec lookup and the matching fail-fast `404` path.

## Definition of Done for the First Slice

The first slice is complete when all of the following are true:
- a stakeholder can call a single API endpoint with a stable `product_spec_id`
- the API returns a normalized product-spec response from OpenMetadata-backed metadata
- the response clearly separates product-spec identifiers from linked ODCS contract identifiers
- the lookup fails fast for missing or ambiguous product specifications
- the demo shows one governed product spec with ownership, scope, lifecycle state, semantic references, and linked contracts

## Implementation Sequence

1. Inventory current data products and their associated ODCS contracts.
2. Define the canonical product-spec field set.
3. Map those fields into OpenMetadata-backed metadata objects.
4. Add registry-backed identifiers to product-level contracts and APIs.
5. Link each product to one or more ODCS contracts.
6. Add validation so undefined product semantics cannot silently enter the platform.
7. Migrate legacy product records into governed product-spec entries.

## Acceptance Criteria

- Open Data Product Specification 4.1 serves as the governing product-level specification.
- ODCS 3.1 remains the contract-level specification for data-quality and delivery interfaces.
- OpenMetadata can store and serve product-spec metadata.
- dq-made-easy can resolve product definitions by stable identifiers.
- Missing or ambiguous product definitions fail fast instead of falling back silently.

## Related references

- [ISO 11179 framework](/docs/technical/ISO_11179_DATA_DEFINITION_FRAMEWORK/)
- [ADR-018](/docs/architecture/adr/ADR-018-iso-11179-based-data-definition-framework-for-bcbs-239-and-mifid-ii/)
- [OpenMetadata implementation details](/docs/implementation-details/ISO_11179_OPENMETADATA_IMPLEMENTATION_DETAILS/)
- [ODCS integration guide](https://github.com/jactools/dq-rulebuilder/blob/main/dq-api/ODCS_INTEGRATION.md)
- [ADR-007](/docs/architecture/adr/ADR-007-dual-standard-api-contracts-openapi-odcs/)
