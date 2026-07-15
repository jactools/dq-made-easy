# ABS-2 Data Catalog Materialization - Implementation Details

This note turns ABS-2 into an actionable backlog.

Goal: build a catalog-scoped materialization service that selects items from the data catalog, generates output into AIStor or another S3-compatible storage target, and persists a Data Delivery Note identified by Data Delivery Id and Data Delivery Location.

## Problem Statement

The platform has partial support for test-data generation and delivery-oriented execution, but it does not yet expose a foundational catalog materialization service.

What is needed is a service that:

- resolves selection across data product, data set, data object, and data object version scopes
- invokes a generator contract for the selected scope
- writes output to object storage in a durable, discoverable location
- records a Data Delivery Note that can be read without direct storage access
- tracks async job status and explicit failure diagnostics

## Proposed Model Split

- The catalog selection remains the logical input boundary.
- The materialized output is the runtime artifact.
- The Data Delivery Note is the durable read model for one concrete generated delivery.
- The note uses Data Delivery Id and Data Delivery Location as the stable identifiers for user-facing lookup.

## Current Implementation

Implemented today:

- A test-data materialization API exists at `POST /api/rulebuilder/v1/test-data/materializations` and `GET /api/rulebuilder/v1/test-data/materializations/&#123;request_id&#125;`.
- A generic ABS-2-shaped API wrapper now also exists at `POST /api/data-catalog/v1/materialization-requests`, `GET /api/data-catalog/v1/materialization-requests/&#123;request_id&#125;`, and `POST /api/data-catalog/v1/materialization-requests/&#123;request_id&#125;/complete`.
- The generic request model now accepts exactly one selector from `data_product_id`, `data_set_id`, `data_object_id`, or `data_object_version_id`, plus `sample_count`, `output_format`, optional `output_uri`, and optional selected attributes.
- The generic route resolves that selector fail fast to one or more concrete `data_object_version_id` targets, stores the original selector and resolved target set on the request record, and preserves per-target output metadata for batch processing.
- The queue and worker contract now operate on a catalog-driven target bundle, so each resolved target carries its own `data_object_version_id`, `sample_count`, `output_format`, `output_uri`, and attribute payload into execution.
- The API enqueues async jobs in Redis, records `pending` / `started` / `completed` / `failed` state, and includes a `correlation_id` and explicit error messages in the request record.
- A worker exists in `dq-engine/test_data_materialization_worker.py` that writes generated output to AIStor or another S3-compatible target in `parquet` or `delta` format.
- The worker reports successful completion back to FastAPI through the materialization completion API; it does not persist delivery data through direct database access.
- Successful materializations now create one Data Delivery row and Data Delivery Note per resolved target through the API-owned repository path, including the reuse fast-path when output already exists for all targets.
- Materialized delivery notes can now expose storage/evidence interpretation labels for synthetic/test outputs so API consumers can distinguish synthetic results from real/evidence artifacts.
- Test-data materialization request and completion flows now fail fast when an `output_uri` uses explicit evidence/reporting-style namespace terms, so synthetic outputs are not persisted under obviously real/evidence semantics without explicit handling.
- Multi-target materialization results now also expose an aggregate delivery summary with target counts, delivery counts, delivery identifiers, delivery locations, output formats, and total row counts at the request level.
- Delivery-note retrieval already exists at `GET /data-catalog/v1/data-deliveries/&#123;data_delivery_id&#125;/note`, and the note can be rendered without direct storage access.
- The delivery note is already extensible enough for downstream execution enrichment, and ABS-3 is using that capability.

ABS-2 is now complete. Future work can still expand the public request contract with heterogeneous per-target controls, but the current target-bundle contract satisfies the ABS-2 generator boundary and delivery-summary semantics.

## Numbered Backlog

1. [x] (ABS2-MAT-01) Define catalog selection resolution.
   - Support selection by data product, data set, data object, and data object version.
   - Fail fast when a selection is ambiguous or does not resolve.
   - Preserve the resolved scope in the materialization request.

   Complete: the generic `data-catalog` materialization route accepts all four selector types and resolves them fail fast to one or more concrete `data_object_version_id` targets, preserving the requested selector and resolved target set on the request record.

2. [x] (ABS2-MAT-02) Define the generator contract.
   - Accept a resolved catalog scope and requested output shape.
   - Produce deterministic output for a given input scope and seed/config.
   - Reject unsupported targets explicitly.

   Complete: the queue and worker now consume a catalog-driven target bundle that carries the resolved scope, selected attributes, `sample_count`, `output_format`, and `output_uri` for each target, while unsupported targets still fail fast.

3. [x] (ABS2-MAT-03) Implement object-storage materialization.
   - Write generated output to AIStor or another S3-compatible backend.
   - Store the canonical output location as Data Delivery Location.
   - Fail fast if the storage target is unavailable.

   Complete: `dq-engine/test_data_materialization_worker.py` writes generated `parquet` or `delta` output to S3-compatible storage for catalog-scoped requests and fails fast on invalid or unavailable storage targets.

4. [x] (ABS2-MAT-04) Persist a Data Delivery Note.
   - Use Data Delivery Id and Data Delivery Location as the primary identifiers.
   - Capture the originating catalog scope, output format, timestamps, and storage metadata.
   - Keep the note separate from the storage object itself.

   Complete: the materialization flow persists a Data Delivery Note on successful completion through an API-owned callback path for each resolved target, including reused-existing outputs, and exposes a request-level aggregate delivery summary above the per-target notes.

5. [x] (ABS2-MAT-05) Add job tracking and diagnostics.
   - Track queued, running, succeeded, and failed materialization states.
   - Record explicit error codes and messages for missing inputs, generator failures, and storage failures.
   - Expose correlation ids for troubleshooting.

   Complete: the shared materialization request record tracks lifecycle state, timestamps, error message, queue metadata, `correlation_id`, selector metadata, and aggregate delivery summary for both narrow and generic ABS-2 routes.

6. [x] (ABS2-MAT-06) Add retrieval APIs.
   - Return materialization status by request id.
   - Return a Data Delivery Note by Data Delivery Id.
   - Return a not-found error when the requested delivery does not exist.

   Complete: `GET /api/rulebuilder/v1/test-data/materializations/&#123;request_id&#125;` returns materialization status, the generic wrapper exposes `GET /api/data-catalog/v1/materialization-requests/&#123;request_id&#125;` with persisted selector metadata, resolved target sets, and aggregate delivery summary, and `GET /data-catalog/v1/data-deliveries/&#123;data_delivery_id&#125;/note` returns each per-target delivery note.

7. [x] (ABS2-MAT-07) Add downstream execution metadata hooks.
   - Allow a future rule-execution service to append execution status, outputs, and references to the Data Delivery Note.
   - Keep rule execution outside the ABS-2 materialization service itself.
   - Preserve the Data Delivery Id and Data Delivery Location as the stable identifiers.

   Complete: the delivery-note endpoint already supports downstream execution enrichment, ABS-3 consumes that capability, and ABS-2 now owns the creation of the underlying delivery-note lifecycle for generated outputs.

8. [x] (ABS2-MAT-08) Add validation and compatibility tests.
   - Verify each catalog scope resolves correctly.
   - Verify storage failures remain fail-fast.
   - Verify the Data Delivery Note can be read without storage access.

   Complete: tests cover queueing, fail-fast attribute validation, selector resolution across all four scope types, multi-target dataset materialization, aggregate delivery summary contracts, batch completion callback persistence, worker-to-API round trips, reuse fast-path behavior, callback failures, storage failures, and delivery-note rendering without storage access.

## Current Implementation References

- Materialization enqueue/read API: `dq-api/fastapi/app/api/v1/endpoints/testing.py`
- Generic materialization request wrapper API: `dq-api/fastapi/app/api/v1/endpoints/data_catalog.py`
- Materialization worker: `dq-engine/test_data_materialization_worker.py`
- Delivery note retrieval API: `dq-api/fastapi/app/api/v1/endpoints/data_catalog.py`
- Delivery note repository reads: `dq-api/fastapi/app/infrastructure/repositories/postgres_data_catalog_repository.py`
- Materialization API tests: `dq-api/fastapi/tests/api/test_test_data_materializations.py`
- Materialization integration tests: `dq-api/fastapi/tests/integration/test_test_data_materialization_enqueue.py`
- Delivery note endpoint tests: `dq-api/fastapi/tests/api/test_data_catalog_endpoints.py`

## Suggested API Shape

- `POST /data-catalog/v1/materialization-requests`
- `GET /data-catalog/v1/materialization-requests/&#123;request_id&#125;`
- `POST /data-catalog/v1/materialization-requests/&#123;request_id&#125;/complete`
- `GET /data-catalog/v1/data-deliveries/&#123;data_delivery_id&#125;/note`

## Acceptance Criteria

- Users can request materialization from catalog scopes broader than a single object version.
- Generated output is written to AIStor or another supported object store.
- Each successful run creates a Data Delivery Note with Data Delivery Id and Data Delivery Location.
- The note is readable without direct access to the underlying storage object.
- Missing scope or storage failures fail fast with explicit diagnostics.

## Related references

- [ABS-2 definition](/docs/features/ABS_2_DATA_CATALOG_MATERIALIZATION/)
- [API-7 Data Delivery Resolution Plan](/docs/implementation-details/API_7_DATA_DELIVERY_RESOLUTION/)
- [API-7 Real DQ Rule Execution Milestone](/docs/implementation-details/API_7_REAL_DQ_RULE_EXECUTION_MILESTONE/)
