# Abstraction Features

Status: Done

- [x] #ABS-1 Abstract from technicalities like databases by introducing an ORM or DSL
- [x] #ABS-2 Data catalog materialization and Data Delivery Notes
- [x] #ABS-3 Delivery-linked rule execution and result notes

## ABS-1 Execution Abstraction (GX + PySpark)

Goal: Introduce a stable abstraction layer between DQ rule definitions and execution runtimes so rules can be compiled into portable artifacts (GX suites today), executed efficiently, and integrated by external systems or self-built PySpark execution solutions.

### Related References

- [ABS-1 definition](./ABS_1_EXECUTION_ABSTRACTION.md)
- [ABS-1 implementation details](../implementation-details/ABS_1_EXECUTION_ABSTRACTION_IMPLEMENTATION_DETAILS.md)
- [DQ_7_4 GX suite orchestration](../implementation-details/DQ_7_4_GX_SUITE_ORCHESTRATION_IMPLEMENTATION_DETAILS.md)

### Tracked Work Items

- [x] `ABS-1.1` Define canonical abstraction layer between rule model, GX suites and run plans, and execution runtimes
- [x] `ABS-1.2` Implement GX suite registry as first-class retrievable artifact
- [x] `ABS-1.3` Add retrieval APIs by data object, data object version, dataset, and data product
- [x] `ABS-1.4` Implement PySpark-first grouped execution by data object version
- [x] `ABS-1.5` Add pluggable data source adapter contract (Spark, JDBC, files)
- [x] `ABS-1.6` Split aggregate outcomes and exception records into separate stores
- [x] `ABS-1.7` Enforce minimal exception record schema (primary key, ruleId, reason)
- [x] `ABS-1.8` Complete observability and validation coverage
  - [x] `ABS-1.8a` Add structured logs and tracing on major GX API and worker surfaces
  - [x] `ABS-1.8b` Add metrics, dashboards, and alert baselines for major GX surfaces
  - [x] `ABS-1.8c` Validate compile and retrieval observability end to end in one pass
  - [x] `ABS-1.8d` Validate execution and persistence observability end to end

Current tracker status: the abstraction contract, suite registry, retrieval APIs, grouped execution path, adapter contract, split persistence model, minimal exception fact schema, and the major GX observability primitives are all implemented and validated. ABS-1 is complete, and the seam is intentionally positioned so self-built PySpark integrations or additional engines can be added without changing rule authoring semantics.

### Acceptance Criteria

- [x] Rules can be transformed into portable GX suites
- [x] GX suites are retrievable by object, object version, dataset, and product scope
- [x] Assignment scope is separated from resolved execution-version scope in the contract and storage model
- [x] Grouped execution reduces repeated runtime spin-up/spin-down overhead
- [x] Exception records are not persisted in the rule/result database
- [x] Exception records persist the minimal violation fact shape with optional operational metadata separated out
- [x] Observability coverage is validated across compile, retrieval, execution, and persistence stages
  - `ABS-1.8c` is complete via the combined compile-plus-retrieval bundle: compiler tests, GX retrieval integration, required log-field validation, correlation propagation validation, and monitoring baseline validation.
  - `ABS-1.8d` is complete via the combined execution-plus-persistence bundle: execution API tests, delivery-linked failure persistence tests, exception-storage tests, worker execution tests, and monitoring baseline validation.

### Related References

- [DQ_7_4_GX_SUITE_ORCHESTRATION_IMPLEMENTATION_DETAILS.md](../implementation-details/DQ_7_4_GX_SUITE_ORCHESTRATION_IMPLEMENTATION_DETAILS.md)
- [ADR-014: GX Suite Registry, PySpark Execution, Self-Built PySpark Integration, and Exception Store Separation](../../architecture/adr/ADR-014-gx-suite-registry-pyspark-execution-and-exception-store-separation.md)

## ABS-2 Data Catalog Materialization and Data Delivery Notes

Goal: Build a foundational service that materializes selected data catalog items into AIStor or other S3-compatible storage, while persisting a Data Delivery Note that identifies the concrete output by Data Delivery Id and Data Delivery Location.

### Tracked Work Items

- [x] `ABS-2.1` Define catalog selection and scope resolution across data product, data set, data object, and data object version
- [x] `ABS-2.2` Define generator contract for catalog-driven materialization jobs
- [x] `ABS-2.3` Materialize generated outputs to AIStor or S3-compatible storage
- [x] `ABS-2.4` Persist a Data Delivery Note keyed by Data Delivery Id and Data Delivery Location
- [x] `ABS-2.5` Add async job tracking, status, and failure diagnostics for materialization runs
- [x] `ABS-2.6` Add retrieval APIs for materialization status and Data Delivery Note lookup

Current tracker status: a catalog-scoped multi-target materialization flow now exists end to end, including generic data-catalog materialization-request routes, fail-fast selector resolution across product, set, object, and version inputs, a catalog-driven target-bundle generator contract, async request tracking, worker-owned status transitions, API-owned per-target Data Delivery Note persistence, aggregate delivery summary metadata on the materialization result, and delivery-note retrieval. ABS-2 is complete.

### Acceptance Criteria

- [x] A user can select data products, data sets, data objects, or data object versions for materialization
- [x] Generated output is written to AIStor or another S3-compatible storage target
- [x] Each materialization run creates per-target Data Delivery Notes with Data Delivery Id and Data Delivery Location identifiers
- [x] The Data Delivery Note can be read without direct storage access
- [x] Missing targets or storage failures fail fast with explicit diagnostics

### Related References

- [API_7_DATA_DELIVERY_RESOLUTION.md](../implementation-details/API_7_DATA_DELIVERY_RESOLUTION.md)
- [API_7_REAL_DQ_RULE_EXECUTION_MILESTONE.md](../implementation-details/API_7_REAL_DQ_RULE_EXECUTION_MILESTONE.md)
- [ABS-2 definition](ABS_2_DATA_CATALOG_MATERIALIZATION.md)
- [ABS-2 implementation details](../implementation-details/ABS_2_DATA_CATALOG_MATERIALIZATION_IMPLEMENTATION_DETAILS.md)

## ABS-3 Delivery-Linked Rule Execution and Result Notes

Goal: combine ABS-2 materialized deliveries with existing rule execution features so rules can run against a concrete delivery, while execution results are captured on the same Data Delivery Note.

### Tracked Work Items

- [x] `ABS-3.1` Define delivery-linked execution request and target resolution
- [x] `ABS-3.2` Resolve applicable GX suites and run plans for a selected delivery
- [x] `ABS-3.3` Execute rules against the concrete delivery location
- [x] `ABS-3.4` Persist aggregate outcomes and exception records separately
- [x] `ABS-3.5` Enrich the Data Delivery Note with execution summary and references
- [x] `ABS-3.6` Add retrieval APIs for execution status and enriched delivery notes
  - Execution status retrieval is implemented.
  - Enriched delivery-note retrieval is implemented by the Data Delivery Note endpoint.

### Acceptance Criteria

- [x] A concrete delivery can be executed without changing its delivery identity
- [x] GX suites and run plans can be resolved for the selected delivery
- [x] Aggregate outcomes and exception records remain stored separately
- [x] The Data Delivery Note shows the execution summary and references
- [x] Missing or incompatible deliveries fail fast with explicit diagnostics

### Related References

- [ABS-1 definition](./ABSTRACTION_FEATURES.md)
- [ABS-2 definition](ABS_2_DATA_CATALOG_MATERIALIZATION.md)
