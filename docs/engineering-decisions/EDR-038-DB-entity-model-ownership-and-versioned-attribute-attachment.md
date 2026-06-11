# EDR-038 [DB]: Entity Model Ownership and Versioned Attribute Attachment

**Status**: Accepted
**Date**: 2026-04-20
**Tag**: DB

## Context
The repository's data-catalog model evolved away from an older object-level attribute shape, but that evolution was not yet captured in one explicit decision record.

The supported FastAPI, `dq-ui`, and current `dq-db` seed/schema paths now consistently distinguish:

- `data_objects` as the lifecycle-managed base entity surface
- `data_objects_catalog` as the dataset-scoped catalog identity surface
- `data_object_versions` as the versioned schema and execution-truth surface
- `attributes_catalog` as the active attribute surface attached to a specific data-object version

Without one explicit EDR, the repository still risked ambiguity about where attributes belong, whether object-level `attributeIds` are still allowed, and whether historical `dq-rules-ui` artifacts should influence current model decisions.

## Decision
Adopt the following repository model-ownership rules:

- `data_objects` is the lifecycle-managed base entity and is not the canonical source for active attribute attachment.
- `data_objects_catalog` is the supported dataset-scoped catalog identity for data objects.
- `data_object_versions` is the canonical version-truth surface for schema-aware execution, materialization, and version-specific metadata.
- `attributes_catalog` is the active attribute model and belongs to a specific `data_object_version`; version-attached attributes are the supported attribute surface for current repository behavior.
- The legacy object-level `data_objects.attributeIds` pattern and the legacy `attributes` table are retired from the supported runtime contract and must not be used to describe or extend the active repository model.
- Historical `dq-rules-ui` artifacts that still encode object-level `attributeIds` are unsupported legacy material only and are excluded from repository-wide schema, seed, API, and entity-model claims.

## Rationale
- Lifecycle identity, catalog identity, version truth, and attribute attachment are separate concerns and are clearer when they are modeled explicitly instead of being collapsed into one object-level attribute list.
- Version-attached attributes align the schema model with execution, test-data generation, delivery, and API catalog reads that operate on a specific data-object version.
- Treating historical subtree artifacts as non-canonical prevents stale generated files from silently redefining the active repository model.
- An explicit ownership rule reduces drift across schema docs, seed generators, repository interfaces, and API payload shaping.

## Scope Boundaries
This decision applies to repository entity-model ownership for the supported data-catalog stack, including current schema descriptions, seed sources, repository interfaces, and API behavior.

It does not by itself define:
- frontend API endpoint resolution or runtime configuration rules
- every data-delivery or execution-planning behavior built on top of the model
- historical migration-baseline capture strategy for contract comparison with older services
- whether legacy material should be deleted entirely rather than quarantined

## Consequences
**Positive**
- The supported repository model now has one explicit contract for entity ownership and attribute attachment.
- Future work can reject object-level attribute embedding as a non-supported extension path.
- Schema docs, seeds, and repository interfaces have a clearer basis for consistency checks.
- Historical subtree artifacts no longer block promotion of the supported model into the EDR set.

**Negative**
- Historical legacy-shaped files may still exist in the repository and need to stay explicitly quarantined to avoid confusion.
- Future cleanup work may still be needed to retire obsolete generated artifacts completely.
- Contributors need to understand the distinction between `data_objects`, `data_objects_catalog`, and `data_object_versions` instead of treating them as interchangeable.

## Implementation Guidance
- When adding or changing data-catalog behavior, derive active attribute data from `attributes_catalog` through `data_object_versions`, not from object-level embedded attribute lists.
- Treat `dq-db/mock-data` and the supported FastAPI repository interfaces as authoritative for current model behavior; do not infer current rules from `dq-rules-ui` generated artifacts.
- Keep documentation aligned with the supported model by describing `data_objects` as lifecycle-managed, `data_objects_catalog` as dataset-scoped catalog identity, `data_object_versions` as version truth, and `attributes_catalog` as version-attached attributes.
- If legacy subtree material must remain, keep it clearly marked as unsupported historical reference only.

## Related Artifacts
- `/memories/repo/dq-rulebuilder-model-notes.md`
- `dq-db/README.md`
- `docs/technical/DATABASE_ERD.md`
- `dq-api/fastapi/app/domain/interfaces/v1/data_catalog_repository.py`
- `dq-api/fastapi/migrations/versions/724b9ef3247c_initial_schema.py`
- `dq-db/mock-data/data-objects.csv`
- `dq-rules-ui/README.md`
- `docs/engineering-decisions/EDR-015-DB-postgresql-transaction-isolation-and-mutation-semantics.md`
- `docs/engineering-decisions/EDR-031-DB-delivery-data-consistency-and-fk-mapping.md`