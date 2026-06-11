# ABS-3 Delivery-Linked Rule Execution - Implementation Plan

**Status**: Draft
**Target**: Delivery-linked execution over ABS-2 materialized data
**Date**: 2026-04-15

Related feature plan: [ABS-3 Delivery-Linked Rule Execution and Result Notes](../status/current/ABS_3_DELIVERY_LINKED_RULE_EXECUTION.md)

Current-state references:
- [ABS-3 Delivery-Linked Rule Execution and Result Notes](../status/current/ABS_3_DELIVERY_LINKED_RULE_EXECUTION.md)
- [Abstraction features summary](../status/current/ABSTRACTION_FEATURES.md)

## Overview

ABS-3 is the composition layer that connects ABS-2 materialized deliveries with the existing rule execution stack.

- ABS-2 creates the materialized delivery and the Data Delivery Note.
- ABS-1 provides GX suite retrieval, grouped execution, and the separation between aggregate outcomes and exception records.
- ABS-3 binds those pieces together so a concrete delivery can be executed against the relevant GX suites and run plans, and the resulting execution summary can be attached to the same Data Delivery Note.

## Implementation Principles

- Keep delivery creation separate from execution.
- Keep execution abstraction separate from output persistence.
- Preserve Data Delivery Id and Data Delivery Location as immutable delivery identity fields.
- Fail fast when a delivery, suite, run plan, or storage dependency is missing.
- Do not collapse aggregate outcomes and exception records into one store.

## Work Items

1. Define the delivery-linked execution request and selector contract.
	- Accept Data Delivery Id and optional run-plan or GX suite selector.
	- Fail fast when the target delivery is missing or incompatible.
	- Preserve the delivery identity as the execution anchor.

2. Resolve applicable GX suites and run plans.
	- Resolve suites that match the selected delivery scope.
	- Resolve run plans without mutating the delivery artifact.
	- Fail fast if no executable suite set exists for the delivery.

3. Execute rules against the selected delivery.
	- Reuse the existing execution engine path for GX suites.
	- Execute against the concrete delivery location from ABS-2.
	- Support reruns against a pinned delivery.
	- Implemented by the delivery-linked execution orchestration service, the data-catalog execution endpoint, and the focused delivery execution endpoint tests.

4. Persist execution outputs.
	- Store aggregate outcomes in the rule/result store.
	- Store exception records in the dedicated exception store.
	- Preserve the ABS-1.6 separation model.
	- Implemented by the GX execution report endpoint and dedicated violation persistence tests.

5. Enrich the Data Delivery Note.
	- Attach execution status, suite references, run-plan references, counts, and result summaries.
	- Keep Data Delivery Id and Data Delivery Location stable.
	- Allow later re-execution to append new execution entries without rewriting the delivery identity.

6. Add retrieval APIs.
	- Return delivery-linked execution status.
	- Return the enriched Data Delivery Note.
	- Return not-found or incompatible-target errors explicitly.

7. Add validation and compatibility tests.
	- Verify delivery-linked execution resolves the correct suites and run plans.
	- Verify outcomes and exception records are persisted separately.
	- Verify the Data Delivery Note contains execution references.

## Phase 1: Delivery Anchor and Request Contract

**Goal**: define the delivery-linked execution request and the target-selection contract.

### Outcomes

- A request can name a concrete Data Delivery Id.
- The request can optionally specify a run-plan selector or GX suite selector.
- The service fails fast when the delivery is missing or incompatible.
- The delivery identity remains the execution anchor throughout the flow.

### Deliverables

- request schema for delivery-linked execution
- validation rules for missing or incompatible deliveries
- initial API surface for execution submission

## Phase 2: GX Suite and Run Plan Resolution

**Goal**: resolve the execution inputs for the selected delivery.

### Outcomes

- Applicable GX suites can be resolved for the target delivery.
- Applicable run plans can be resolved without mutating the delivery artifact.
- Grouped execution can reuse the existing ABS-1 planning and execution path.
- A pinned rerun can be targeted at the same delivery.

### Deliverables

- delivery-to-suite resolution rules
- run-plan lookup and selector handling
- planner integration that reuses existing GX execution machinery

## Phase 3: Execution, Persistence, and DDN Enrichment

**Goal**: execute rules against the selected delivery and attach the results to the Data Delivery Note.

### Outcomes

- Rules execute against the concrete delivery location from ABS-2.
- Aggregate outcomes are stored in the rule/result store.
- Exception records are stored in the dedicated exception store.
- The Data Delivery Note records execution status, references, and summary data.
- Later executions can append new execution entries without changing the delivery identity.

### Deliverables

- execution orchestration service
- persistence updates for outcome and exception stores
- Data Delivery Note enrichment model

## Phase 4: Retrieval, UI Surface, and Validation

**Goal**: expose the execution state and verify the delivery-linked flow end to end.

### Outcomes

- Users can retrieve execution status by Data Delivery Id.
- Users can inspect the enriched Data Delivery Note.
- Missing or incompatible targets fail with explicit diagnostics.
- The delivery-linked flow is covered by validation and compatibility tests.

### Deliverables

- retrieval APIs for delivery-linked execution and note lookup
- UI read path for the enriched note
- test coverage for resolution, execution, persistence, and note enrichment

## Success Criteria

- A concrete delivery can be executed without changing its identity.
- GX suites and run plans can be resolved for that delivery.
- Aggregate outcomes and exception records remain separated.
- The Data Delivery Note contains execution summary and references.
- Missing or incompatible deliveries fail fast with explicit diagnostics.

## Dependencies

- [ABS-1 Execution Abstraction](../status/current/ABSTRACTION_FEATURES.md#abs-1-execution-abstraction-gx--pyspark)
- [ABS-2 Data Catalog Materialization](../status/current/ABS_2_DATA_CATALOG_MATERIALIZATION.md)
- [ABS-3 definition](../status/current/ABS_3_DELIVERY_LINKED_RULE_EXECUTION.md)
- [DQ-7.4 GX suite orchestration](./DQ_7_4_GX_SUITE_ORCHESTRATION_IMPLEMENTATION_DETAILS.md)
