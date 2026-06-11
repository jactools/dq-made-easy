# ABS-3 Delivery-Linked Rule Execution and Result Notes

Goal: combine ABS-2 materialized deliveries with existing rule execution features so a selected delivery can be executed against GX suites and run plans, while the resulting execution summary is captured on the same Data Delivery Note.

## Why this exists

ABS-2 creates the delivery artifact and Data Delivery Note. ABS-1 creates the execution abstraction and separates outcomes from exception records. ABS-3 joins those pieces into a delivery-linked execution capability:

- choose a concrete Data Delivery Id and Data Delivery Location produced by ABS-2
- resolve the applicable GX suites and run plan for that delivery
- execute the rules against the generated data
- persist aggregate outcomes and exception records using the ABS-1.6 separation model
- append execution summary and references to the Data Delivery Note without changing the delivery identity

## Scope

### In scope

- Delivery-linked execution against materialized outputs from ABS-2
- Resolution of GX suites and run plans for a specific delivery
- Capture of execution summary, status, counts, and references on the Data Delivery Note
- Separation of aggregate outcomes and exception records into their respective stores
- Reruns against a pinned delivery
- Retrieval APIs for execution status and delivery-linked result summaries


### Out of scope

- Generating the data itself
- Replacing the ABS-1 suite registry or compilation pipeline
- Hiding execution failures behind success responses
- Mutating the Data Delivery Id or Data Delivery Location after the delivery is created


### Tracked Work Items

- [x] `ABS-3.1` Define delivery-linked execution request and target resolution
- [x] `ABS-3.2` Resolve applicable GX suites and run plans for a selected delivery
- [x] `ABS-3.3` Execute rules against the concrete delivery location
- [x] `ABS-3.4` Persist aggregate outcomes and exception records separately
- [x] `ABS-3.5` Enrich the Data Delivery Note with execution summary and references
- [x] `ABS-3.6` Add retrieval APIs for execution status and enriched delivery notes
  - Execution status retrieval is implemented.
  - Enriched delivery-note retrieval is implemented by the Data Delivery Note endpoint.

## User-facing outcome

A user can materialize data through ABS-2, execute the relevant rules against that concrete delivery, and inspect a single delivery note that shows both the delivery metadata and the attached execution result summary.

## Success criteria

- [x] A concrete delivery can be executed without changing its delivery identity
- [x] GX suites and run plans can be resolved for the selected delivery
- [x] Aggregate outcomes and exception records are stored separately
- [x] The Data Delivery Note includes execution summary and references
- [x] Missing or incompatible deliveries fail fast with explicit diagnostics

## Related implementation note

- [ABS-3 implementation plan](../implementation-details/ABS_3_DELIVERY_LINKED_RULE_EXECUTION_IMPLEMENTATION_PLAN.md)

