# Data Assets Feature

Goal: introduce Data Assets as first-class DQ-owned catalog entities that can be created independently of imported metadata and can combine one or more existing data object versions with joins, filters, or schema-only uploaded structure definitions.

Implementation details: [DQ_3C_DATA_ASSETS_IMPLEMENTATION_DETAILS.md](/docs/implementation-details/DQ_3C_DATA_ASSETS_IMPLEMENTATION_DETAILS/)

## Why This Exists

The current Data Catalog is centered on imported metadata and mirrors the external metadata model where appropriate. That works for catalog discovery, but it does not cover DQ-only business views that users want to curate inside the DQ solution itself.

Data Assets fill that gap:
- they live only in the DQ solution;
- they can be based on one or more existing data object versions;
- they can include joins and filters as part of the asset definition;
- they can be created manually in the UI;
- they can be created by uploading a structure file in supported formats;
- they can be selected immediately as rule inputs, replacing the standalone reusable-join flow.

This feature also replaces the standalone reusable-join authoring flow in the UI with a broader asset-building experience.

## Product Scope

### Data Asset identity
- A Data Asset is a DQ-owned catalog entity with its own name, description, ownership, lifecycle, and audit history.
- The asset is not a mirrored OpenMetadata object and is not expected to sync back to the source metadata platform.
- Imported data object versions remain the source references that a Data Asset can compose, but the Data Asset itself is a separate DQ concept.

### Data Asset composition
- A Data Asset can reference one or more existing data object versions.
- When the source is OpenMetadata-backed, the asset references the fields the user selects instead of changing the underlying source field definitions.
- Source field data types are inherited from the OpenMetadata-backed object and cannot be changed in the Data Asset layer.
- A Data Asset can include join definitions across those sources.
- A Data Asset can include filters that narrow or shape the resulting asset.
- A Data Asset can define new derived fields or attributes that reference selected source fields through expressions.
- Derived fields can be used to build curated business views without mutating the source metadata.
- The asset should preserve the relationship back to each source version so users can inspect provenance.
- Every saved Data Asset exposes a generated ODCS-based contract that users can download.
- Generated contracts are stored in the database as versioned records linked to the Data Asset, including who, when, where, and what changed.

### Creation modes
- Manual creation in the UI for users who want to build an asset from scratch.
- Source-based creation from existing data object versions.
- Upload-based creation from a structure file that the system normalizes into the internal asset model.

### Supported upload inputs
- CSV
- TSV
- Excel
- JSON or JSON Schema

The exact import rules should be fail-fast: unsupported formats, malformed files, and ambiguous structure mappings must produce explicit validation errors rather than falling back to guessed mappings.
Uploaded structures are treated as schema-only definitions, not as data samples or materialized snapshots.

### Rule input integration
- Data Assets should be selectable as rule inputs immediately after creation.
- Rules should target the Data Asset as the authored business shape, not the underlying reusable join concept.
- When a rule references a Data Asset, the asset's selected source fields and derived attributes should be available to the rule authoring experience.

### Test-data generation integration
- The test-data generator should accept a Data Asset as a generation target, not only a raw data object version.
- For OpenMetadata-backed assets, generation should use the selected source fields plus derived fields as the schema exposed to the generator.
- The generator should fail fast if a Data Asset cannot be resolved to a concrete field schema or if a derived field expression is invalid.
- This replaces the old assumption that reusable joins are the only non-version catalog structure that can participate in test-data generation.

## Playground Shortlist

General starter bundle:

- [Office for National Statistics](https://www.ons.gov.uk/): UK population, inflation, GDP, and labour-market series. Best for demonstrating multiple time-series assets with clear provenance and OGL v3.0 reuse terms.
- [Australian Bureau of Statistics](https://www.abs.gov.au/): Population, CPI, GDP, earnings, unemployment, and regional datasets. Best for showing curated asset views over official statistics with Creative Commons reuse terms.
- [Stats NZ](https://www.stats.govt.nz/): Population, GDP, CPI, unemployment, trade, and regional summaries. Best for showing a compact national-statistics playground with CC BY 4.0 reuse terms.

Finance terminology bundle:

- [ECB Data Portal](https://data.ecb.europa.eu/): Euro exchange rates, yield curves, money market reporting, investment funds, monetary financial institutions, and banking-supervision-related statistics. ECB statistics are offered with free access and free reuse, and the dataset names use the kind of terminology users see in financial-domain models.
- [Bank of England Database](https://www.bankofengland.co.uk/boeapps/database/): Exchange rates, yield curves, SONIA, money and credit, capital issuance, financial derivative positions, monetary financial institutions, and banking-sector regulatory capital. The database series are covered by the UK Open Government Licence v3.0 unless a specific series is marked as third-party licensed and should therefore be excluded.

These are good starter candidates because they are public, non-US, tabular, and naturally map to Data Asset patterns like selected source fields, derived fields, filters, and rule-input selection.
Playground source bundles should be downloaded once into AIStor and then reused from there across workspaces.
Workspace admins should be able to choose which playground sources are enabled in a workspace; by default, all listed sources are allowed.

## Proposed User Journeys

1. Browse the Data Catalog and create a new Data Asset from selected source versions.
2. Create a new Data Asset manually and then attach sources, joins, and filters.
3. Upload a structure file and review the parsed preview before saving.
4. Edit a Data Asset to change sources, joins, filters, description, or ownership.
5. Re-open an existing Data Asset to inspect its lineage, source versions, and saved structure.

## Domain Model Sketch

- `data_asset`: the catalog entity visible to users.
- `data_asset_version`: versioned saved state for the asset itself.
- `data_asset_source`: reference to one source data object version or uploaded source block.
- `data_asset_field`: selected source field binding or derived attribute definition.
- `data_asset_join`: join clause or relationship block used by the asset.
- `data_asset_filter`: filter clause applied within the asset definition.
- `data_asset_upload`: uploaded structure metadata, parser result, and validation status.

This model should stay DQ-native and should not require the catalog import pipeline to own the asset lifecycle.

## Tracked Work Items (Proposed)

- [x] `DA-1` Define the Data Asset domain model, persistence shape, and repository contracts.
- [x] `DA-2` Add API endpoints for listing, creating, updating, versioning, and deleting Data Assets.
- [x] `DA-3` Add Data Catalog UI pages for browsing and managing Data Assets.
- [x] `DA-4` Build a source-selection flow that lets users base an asset on one or more existing data object versions.
- [x] `DA-5` Build a composition editor for joins and filters inside the Data Asset builder.
- [x] `DA-6` Add manual-create flows for assets that start without imported source bindings.
- [x] `DA-7` Add upload-and-preview support for CSV, TSV, Excel, and JSON structure inputs.
- [x] `DA-7a` Treat uploaded structures as schema-only definitions and preserve field-level mappings.
- [x] `DA-8` Add validation and preview errors for malformed uploads, unsupported formats, missing source references, and invalid join/filter expressions.
- [x] `DA-9` Add audit history and version comparison for Data Assets.
- [x] `DA-10` Migrate or retire the standalone reusable-join UI so Data Assets become the primary authoring surface.
- [x] `DA-11` Expose Data Assets as immediate rule inputs in rule authoring flows.
- [x] `DA-12` Allow derived Data Asset fields to reference OpenMetadata-backed source fields without changing source field types.
- [x] `DA-13` Extend the test-data generator so it can generate from user-created Data Assets.
- [x] `DA-14` Add workspace-admin controls for enabling or disabling playground source bundles, with all sources allowed by default.
- [x] `DA-15` Add one-time AIStor ingestion and reuse for playground source bundles.
- [x] `DA-16` Generate a downloadable ODCS contract for each Data Asset.
- [x] `DA-17` Persist generated Data Asset contracts as versioned database records with generation metadata.

## Acceptance Criteria

- [x] `DA-AC-01` Users can create a Data Asset from one or more existing data object versions.
- [x] `DA-AC-02` Users can create a Data Asset manually without relying on imported metadata as the only entry point.
- [x] `DA-AC-03` Users can upload supported structure files and review a normalized preview before saving.
- [x] `DA-AC-04` A Data Asset can include joins and filters as part of its definition.
- [x] `DA-AC-05` Data Assets are stored and managed inside the DQ solution only.
- [x] `DA-AC-06` Unsupported uploads and invalid source mappings fail fast with explicit errors.
- [x] `DA-AC-07` The UI no longer presents reusable joins as a standalone catalog entity once the Data Asset flow is active.
- [x] `DA-AC-08` Data Assets are discoverable in the Data Catalog with audit and version history.
- [x] `DA-AC-09` Uploaded structures are modeled as schema-only definitions.
- [x] `DA-AC-10` Data Assets can be selected as rule inputs immediately after creation.
- [x] `DA-AC-11` OpenMetadata-backed source fields are reference-bound and their data types remain immutable in the Data Asset layer.
- [x] `DA-AC-12` Users can add derived fields that reference selected source fields, such as `NetAmount = Amount * Discount_Pct`.
- [x] `DA-AC-13` The test-data generator can target a Data Asset and uses the Data Asset's resolved schema.
- [x] `DA-AC-14` Workspace admins can restrict which playground source bundles are available, and the default workspace state allows all bundles.
- [x] `DA-AC-15` Each created Data Asset exposes a downloadable ODCS-based contract generated from its current authored state.
- [x] `DA-AC-16` Generated Data Asset contracts are stored in the database as linked versioned records with who, when, where, and what metadata.

