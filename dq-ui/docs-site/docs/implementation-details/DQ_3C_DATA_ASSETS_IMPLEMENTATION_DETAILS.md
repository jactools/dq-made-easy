# DQ-3c Data Assets - Implementation Details

This note records the implementation backlog for DQ-3c Data Assets.

For the product-level feature plan, see [Data Assets Feature](/docs/features/DATA_ASSETS_FEATURES/).

## Problem Statement

The current catalog model is centered on imported metadata and reusable joins. That is not enough for user-authored, DQ-native business views that should live only inside the DQ solution.

What is needed is a Data Asset model that:

- can be created from one or more existing data object versions
- can be created manually without a source object being preselected
- can be created from a schema-only upload preview
- can include joins, filters, and derived fields
- can be selected immediately as a rule input
- can be used by the test-data generator as a generation target
- can reuse open data playground bundles stored once in AIStor
- can be governed by workspace admins through a source-bundle allowlist

## Proposed Model Split

- The Data Asset is the user-facing business object.
- The Data Asset version is the persisted authored state.
- The Data Asset source binding is the reference to selected source fields from an existing object version.
- The derived field is the authored expression that references selected source fields.
- The upload preview is the schema-only ingestion artifact.
- The playground source bundle is the reusable public-data package stored once in AIStor.
- The workspace bundle policy is the admin-scoped allowlist/disablement layer.

## Current Scope

The first implementation slice should stay deliberately narrow:

- support only schema-only uploads for playground or user-provided structure files
- keep OpenMetadata-backed source fields reference-bound and immutable in type
- allow derived fields to reference selected source fields through expressions
- keep Data Assets fail-fast on ambiguous mappings, missing metadata, and unsupported formats
- download each playground source bundle once into AIStor and reuse it from there
- default every workspace to allow all bundled playground sources
- allow workspace admins to disable specific bundles per workspace
- route rule authoring to Data Assets as an immediate input target
- keep reusable joins available only as a migration source, not as the primary authoring surface

## Numbered Backlog

1. [x] (DQ3C-IMP-01) Define the canonical Data Asset contracts.
   - Add domain entities for Data Asset, Data Asset version, source binding, filter, derived field, and upload preview.
   - Keep the public API snake_case and fail fast on missing required payloads.

2. [x] (DQ3C-IMP-02) Implement the repository and persistence model.
   - Persist the authored asset, version history, and source-field references.
   - Preserve provenance back to each referenced data object version.

3. [x] (DQ3C-IMP-03) Add the Data Asset API surface.
   - Add list, get, create, update, version, delete, and validate endpoints.
   - Expose resolved field bindings and derived-field metadata for the UI.

4. [x] (DQ3C-IMP-04) Build the Data Asset UI builder.
   - Add source selection, join editing, filter editing, and derived-field editing.
   - Enforce schema immutability for OpenMetadata-backed source fields.
   - Generate and expose a downloadable ODCS-based contract for each Data Asset.
   - Persist each generated contract as a versioned database record with who, when, where, and what metadata.

5. [x] (DQ3C-IMP-05) Implement schema-only upload preview.
   - Parse CSV, TSV, Excel, plain JSON, and JSON Schema files into the internal schema model.
   - Reject malformed files, unsupported formats, and ambiguous mappings.

6. [x] (DQ3C-IMP-06) Add playground source bundle ingestion to AIStor.
   - Download each approved public-data source bundle one time only.
   - Store the bundle in AIStor with metadata for source URL, license, and bundle id.

7. [x] (DQ3C-IMP-07) Add workspace-admin bundle controls.
   - Allow admins to enable or disable each playground source bundle per workspace.
   - Default all bundled sources to allowed until explicitly restricted.

8. [x] (DQ3C-IMP-08) Connect Data Assets to rule authoring and test-data generation.
   - Allow Data Assets to be selected immediately as rule inputs.
   - Extend the test-data generator so it resolves the Data Asset schema and derived fields.

9. [x] (DQ3C-IMP-09) Retire reusable joins as the primary user flow.
   - Keep compatibility only where needed during migration.
   - Route new authoring flows through Data Assets.

10. [x] (DQ3C-IMP-10) Add end-to-end tests and rollout notes.
    - Cover schema-only upload, AIStor ingestion, workspace bundle policies, rule-input selection, and generator resolution.
    - Document the supported bundle list and the fail-fast behavior.

## Acceptance Criteria

- A user can create a Data Asset from existing object versions, manually, or from a schema-only upload.
- OpenMetadata-backed source fields remain reference-bound and retain their source type.
- Users can add derived fields that reference selected source fields.
- Playground bundles are downloaded once into AIStor and reused across workspaces.
- Workspace admins can disable specific playground bundles, and the default state allows all bundles.
- Data Assets can be selected as rule inputs immediately after creation.
- The test-data generator can target a Data Asset and use its resolved schema.
- Reusable joins are no longer the primary authoring entry point.

## Related References

- [Data Assets Feature](/docs/features/DATA_ASSETS_FEATURES/)
- [DQ features overview](/docs/features/DQ_FEATURES/)
- [AIStor / object storage notes](https://github.com/jactools/dq-rulebuilder/blob/main/memories/repo/dq-rulebuilder-aistor-free-edition-object-store-note.md)
- [DQ-3c rollout and operator notes](/docs/technical/DQ_3C_DATA_ASSETS_ROLLOUT_AND_OPERATOR_NOTES/)
