# ABS-2 Data Catalog Materialization and Data Delivery Notes

Status: Done

Goal: provide a foundational service that lets users select items from the data catalog, materialize generated output into AIStor or another S3-compatible storage target, and persist a Data Delivery Note that identifies the result by Data Delivery Id and Data Delivery Location.

## Current status

ABS-2 is complete.

What exists today:

- a narrow test-data materialization path for `data_object_version_id`-scoped generation
- generic `data-catalog` materialization request routes that accept one selector from data product, data set, data object, or data object version and resolve it fail fast to one or more concrete object-version targets
- a catalog-driven target-bundle generator contract that carries resolved targets, sample size, output format, output URI, and selected attributes through the queue and worker boundary
- async request tracking for that materialization path
- generated output written to AIStor or another S3-compatible target
- API-owned creation of one Data Delivery Note per successful resolved target, including reused-existing outputs
- an aggregate delivery summary on materialization completion and status responses so multi-target runs expose one request-level delivery view above the per-target notes
- a Data Delivery Note read model and retrieval endpoint that can be rendered without direct storage access
- downstream execution enrichment of the note through ABS-3
- synthetic/test materialization outputs can be labeled in the Data Delivery Note so downstream readers can distinguish synthetic results from real/evidence storage outputs

## Why this exists

The platform already has pieces of test-data generation and delivery resolution, but they are not exposed as a single catalog-scoped capability. ABS-2 turns those pieces into a reusable service boundary:

- selection across data product, data set, data object, and data object version scopes
- a generator contract that can materialize output deterministically
- storage of generated output in AIStor or S3-compatible object storage
- a durable Data Delivery Note for user-facing and API-facing retrieval
- explicit failure handling for missing inputs, unsupported targets, and storage errors

## Scope

### In scope

- Catalog selection resolution by data product, data set, data object, or data object version
- Materialization jobs that write generated outputs to AIStor or S3-compatible storage
- Data Delivery Notes keyed by Data Delivery Id and Data Delivery Location
- Job status tracking and diagnostics for asynchronous generation runs
- Read APIs for delivery note lookup and materialization status

### Out of scope

- Rule execution against generated output
- Replacing the existing real-data execution model
- Silent fallback to alternate storage when the requested storage target is unavailable
- Hiding storage failures behind success responses

## Downstream handoff

ABS-2 does not execute rules itself, but the Data Delivery Note must remain extensible so a downstream execution service can attach rule results, status, and output references to the same delivery identity.

The note should therefore be able to carry execution metadata for later stages without changing the Data Delivery Id or Data Delivery Location that identify the generated delivery.

Where object-storage interpretation matters, the note should also be able to surface labels such as `object_storage_classification` and `evidence_classification` so synthetic/test outputs remain visibly synthetic in downstream retrieval flows.

## User-facing outcome

Today, a user can request test-data materialization for a specific `data_object_version_id` and inspect an existing delivery note through the API.

The target ABS-2 outcome is broader: a user can choose one or more catalog items, request materialization, and later inspect a delivery note that explains exactly what was produced, where it was written, and when it became available.

## Success criteria

- Selected catalog scope resolves unambiguously
- Generated output lands in the requested object-storage target
- Every run produces a durable Data Delivery Note
- The Data Delivery Note can be viewed without direct storage access
- The Data Delivery Note can be enriched later with downstream rule-execution metadata
- Failures are explicit and machine-readable

Current implementation note: the storage-target write path, async request tracking, generic materialization-request wrapper routes, selector-aware fail-fast resolution, catalog-driven target-bundle generator contract, multi-target dataset and product materialization, API-owned per-target delivery-note persistence, aggregate delivery summary metadata, and fail-fast failure diagnostics are all in place.

Future enhancements can still broaden the public request contract with heterogeneous per-target controls, but those are no longer blockers for ABS-2 acceptance.

## Related implementation note

- [ABS-2 implementation details](/docs/implementation-details/ABS_2_DATA_CATALOG_MATERIALIZATION_IMPLEMENTATION_DETAILS/)
- [ABS-3 definition](/docs/features/ABS_3_DELIVERY_LINKED_RULE_EXECUTION/)
