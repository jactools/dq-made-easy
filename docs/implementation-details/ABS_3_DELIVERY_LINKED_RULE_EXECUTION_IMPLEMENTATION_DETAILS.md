# ABS-3 Delivery-Linked Rule Execution - Implementation Details

This note turns ABS-3 into an actionable backlog.

For the phased implementation plan, see [ABS-3 Delivery-Linked Rule Execution - Implementation Plan](./ABS_3_DELIVERY_LINKED_RULE_EXECUTION_IMPLEMENTATION_PLAN.md).

Goal: build the layer that consumes ABS-2 deliveries, runs existing rule execution features against that delivery, and attaches execution results to the same Data Delivery Note while preserving the ABS-1 separation between aggregate outcomes and exception records.

## Problem Statement

The platform can already materialize data and it has an execution abstraction for GX suites and run plans, but those pieces are still separate.

What is needed is a delivery-linked execution flow that:

- starts from a concrete Data Delivery Id and Data Delivery Location
- resolves the applicable GX suites and run plans for that delivery
- executes the rules against the generated data
- persists aggregate outcomes and exception records in their proper stores
- updates the Data Delivery Note with execution summary and references

## Proposed Model Split

- ABS-2 remains responsible for generating and persisting the delivery artifact.
- ABS-1 remains responsible for GX suite compilation, retrieval, grouped execution, and outcome/exception separation.
- ABS-3 coordinates both sides for delivery-linked execution and delivery-note enrichment.
- The Data Delivery Note becomes the shared user-facing summary for delivery plus execution results.

## Current Foundation

The first part of this work builds on delivery-note and delivery-resolution support that already exists in the platform:

- `GET /data-catalog/v1/data-deliveries/{data_delivery_id}/note` returns the delivery note for one concrete delivery.
- The note endpoint can optionally enrich the read model with storage-backed file names and object counts when `include_storage_details=true` is requested.
- The delivery resolver already validates the requested delivery against the target `dataObjectVersionId` and resolves `delivery_location` for execution.
- The delivery note model is already treated as a storage-independent read model that can be enriched by downstream services, including warnings for unsupported delivery formats.

## Delivery Phases

### Phase 1 - Delivery Anchor and Request Contract

Define the delivery-linked execution request and the target-selection contract.

#### Phase 1 Request Contract

The first ABS-3 slice uses the concrete delivery identity as its anchor and lets the caller optionally narrow execution to a specific GX suite or run plan.

Required input:

- `data_delivery_id`

Optional input:

- `execution_selector`

The `execution_selector.selector_type` value is one of:

- `gx_suite`
- `run_plan`

#### Suggested Request Shape

```json
{
   "data_delivery_id": "del-30",
   "execution_selector": {
      "selector_type": "gx_suite",
      "gx_suite_id": "gx_suite_8f40b9ea",
      "suite_version": 3
   }
}
```

```json
{
   "data_delivery_id": "del-30",
   "execution_selector": {
      "selector_type": "run_plan",
      "run_plan_id": "rp_123",
      "run_plan_version": 7
   }
}
```

#### Validation Rules

- Reject a blank or missing `data_delivery_id` with an explicit client error.
- Reject an `execution_selector` that does not specify exactly one selector type.
- Reject a selector that does not resolve to the target delivery.
- Reject a selector that points at an incompatible or inactive GX suite or run plan.
- Resolve the concrete delivery location server-side from the delivery identity rather than trusting a client-provided storage path.

#### Phase 1 Deliverables

- request schema for delivery-linked execution
- validation rules for missing or incompatible deliveries
- initial API surface for execution submission

#### Suggested API Shape

- `POST /data-catalog/v1/data-deliveries/{data_delivery_id}/executions`

### Phase 2 - GX Suite and Run Plan Resolution

Resolve the executable GX suites and run plans for the selected delivery.

The Phase 2 resolution contract is implemented in the delivery-linked execution request resolver. It resolves all active GX suites that match the delivery's `data_object_version_id`, derives the applicable run plans for those suites, and builds the grouped execution plan that later execution slices can consume.

### Phase 3 - Execution, Persistence, and DDN Enrichment

Execute rules against the selected delivery and attach the results to the Data Delivery Note.

ABS3-EXE-03 is implemented by [delivery_linked_execution_orchestrator.py](/Users/jacbeekers/gitrepos/dq-rulebuilder/dq-api/fastapi/app/application/services/delivery_linked_execution_orchestrator.py), the delivery execution endpoint in [data_catalog.py](/Users/jacbeekers/gitrepos/dq-rulebuilder/dq-api/fastapi/app/api/v1/endpoints/data_catalog.py), and the delivery-linked execution endpoint tests in [test_delivery_linked_execution_endpoints.py](/Users/jacbeekers/gitrepos/dq-rulebuilder/dq-api/fastapi/tests/api/test_delivery_linked_execution_endpoints.py).

### Phase 4 - Retrieval, UI Surface, and Validation

Expose execution status, delivery-note retrieval, and end-to-end validation.

## Numbered Backlog

### Phase 1 Backlog

1. [x] (ABS3-EXE-01) Define delivery-linked execution request.
   - Accept Data Delivery Id and optional run plan or GX suite selector.
   - Fail fast when the target delivery is missing or incompatible.
   - Preserve the delivery identity as the execution anchor.

### Phase 2 Backlog

2. [x] (ABS3-EXE-02) Resolve applicable GX suites and run plans.
   - Resolve suites that match the selected delivery scope.
   - Resolve run plans without mutating the delivery artifact.
   - Fail fast if no executable suite set exists for the delivery.

   Implemented by [delivery_linked_execution_request_resolver.py](/Users/jacbeekers/gitrepos/dq-rulebuilder/dq-api/fastapi/app/application/services/delivery_linked_execution_request_resolver.py), the delivery execution receipt schema in [data_catalog_view.py](/Users/jacbeekers/gitrepos/dq-rulebuilder/dq-api/fastapi/app/api/v1/schemas/data_catalog_view.py), and the delivery-linked execution endpoint tests in [test_delivery_linked_execution_endpoints.py](/Users/jacbeekers/gitrepos/dq-rulebuilder/dq-api/fastapi/tests/api/test_delivery_linked_execution_endpoints.py).

### Phase 3 Backlog

3. [x] (ABS3-EXE-03) Execute rules against the selected delivery.
   - Reuse the existing execution engine path for GX suites.
   - Execute against the concrete delivery location from ABS-2.
   - Support reruns against a pinned delivery.

4. [x] (ABS3-EXE-04) Persist execution outputs.
   - Store aggregate outcomes in the rule/result store.
   - Store exception records in the dedicated exception store.
   - Preserve the ABS-1.6 separation model.

   Implemented by the GX execution report endpoint, which keeps run summaries in the GX run repository and writes violation records into the dedicated GX violation repository.

5. [x] (ABS3-EXE-05) Enrich the Data Delivery Note.
   - Attach execution status, suite references, run-plan references, counts, result summaries, and storage location.
   - Keep Data Delivery Id and Data Delivery Location stable.
   - Allow later re-execution to append new execution entries without rewriting the delivery identity.
   - Use business keys of related items instead of internal ids.

### Phase 4 Backlog

6. [x] (ABS3-EXE-06) Add retrieval APIs.
   - Return delivery-linked execution status.
   - Return the enriched Data Delivery Note.
   - Return not-found or incompatible-target errors explicitly.

   Implemented by the delivery-linked execution status endpoint and enriched Data Delivery Note endpoint in [data_catalog.py](/Users/jacbeekers/gitrepos/dq-rulebuilder/dq-api/fastapi/app/api/v1/endpoints/data_catalog.py), with coverage in [test_delivery_linked_execution_endpoints.py](/Users/jacbeekers/gitrepos/dq-rulebuilder/dq-api/fastapi/tests/api/test_delivery_linked_execution_endpoints.py) and [test_data_catalog_endpoints.py](/Users/jacbeekers/gitrepos/dq-rulebuilder/dq-api/fastapi/tests/api/test_data_catalog_endpoints.py).

7. [x] (ABS3-EXE-07) Add validation and compatibility tests.
   - Verify delivery-linked execution resolves the correct suites and run plans.
   - Verify outcomes and exception records are persisted separately.
   - Verify the Data Delivery Note contains execution references.

   Covered by [test_delivery_linked_execution_endpoints.py](/Users/jacbeekers/gitrepos/dq-rulebuilder/dq-api/fastapi/tests/api/test_delivery_linked_execution_endpoints.py) and [test_data_catalog_endpoints.py](/Users/jacbeekers/gitrepos/dq-rulebuilder/dq-api/fastapi/tests/api/test_data_catalog_endpoints.py).

## Suggested API Shape

- `POST /data-catalog/v1/data-deliveries/{data_delivery_id}/executions`
- `GET /data-catalog/v1/data-deliveries/{data_delivery_id}/executions/{execution_id}`
- `GET /data-catalog/v1/data-deliveries/{data_delivery_id}/note`

## Acceptance Criteria

- A concrete delivery can be executed without changing its delivery identity.
- GX suites and run plans can be resolved for that delivery.
- Aggregate outcomes and exception records remain stored separately.
- The Data Delivery Note shows the execution summary and references.
- Missing or incompatible deliveries fail fast with explicit diagnostics.

## Related references

- [ABS-1 definition](../features/ABSTRACTION_FEATURES.md)
- [ABS-2 definition](../features/ABS_2_DATA_CATALOG_MATERIALIZATION.md)
- [ABS-2 implementation details](./ABS_2_DATA_CATALOG_MATERIALIZATION_IMPLEMENTATION_DETAILS.md)
- [API-7 Data Delivery Resolution Plan](./API_7_DATA_DELIVERY_RESOLUTION.md)
- [DQ-7.4 GX suite orchestration](./DQ_7_4_GX_SUITE_ORCHESTRATION_IMPLEMENTATION_DETAILS.md)
