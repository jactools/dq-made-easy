# ADR-014: GX Suite Registry, PySpark Execution, Self-Built PySpark Integration, and Exception Store Separation

**Status**: Accepted
**Date**: 2026-03-22

### Context
DQ rule execution is transitioning from expression-only runtime behavior toward executable artifacts derived from DQ-7 compiler output. DQ-7.3 established deterministic intermediate artifacts, and DQ-7.4 now needs a concrete runtime and integration strategy for Great Expectations (GX) plus compatible self-built PySpark execution solutions.

The implementation must satisfy the following operational requirements:
- GX suites must run against multiple data source types.
- Rules are assigned by stewards at Data Object or Data Set scope, not directly at Data Object Version scope.
- Initial execution container/runtime is PySpark-based.
- The execution seam must allow teams to plug in self-built PySpark solutions without changing rule authoring semantics or bypassing the canonical artifact boundary.
- Execution always resolves to one or more Data Object Versions, and rules/suites for the same data object version should execute in a clubbed batch to reduce spin-up/spin-down overhead.
- Aggregate DQ outcomes and row-level exception records must be separated.
- Exception rows must store only minimal fields (data primary key, ruleId, reason) and must not be stored in the rule/result database.
- End-to-end logging and monitoring are required.
- GX suites are first-class retrievable objects exposed through API, including retrieval by data object, data object version, data set, and data product scope.
- Every DQ run plan must have a neutral canonical validation plan; engine-specific run plans such as GX, Soda, or SQL are projections of that canonical plan.
- Data Products in this scope are ODCS Data Products, and `dataProductId` refers to the canonical ODCS Data Product identifier.
- Unsupported custom runtime mappings or missing custom-runtime capabilities must fail fast; the platform must not silently fall back to a different runtime.

### Decision
Adopt a **GX suite registry + PySpark-first grouped execution model** with an explicit self-built PySpark integration seam and strict data persistence separation.

1. **GX suite as first-class artifact**
   - Persist GX suites and metadata as retrievable artifacts.
   - Treat suite payloads as portable objects for internal execution, external execution, or self-built PySpark integrations.
   - Version the envelope contract in Git as JSON Schema; keep runtime-generated artifact instances in the registry database.

2. **Retrieval API contract**
   - Expose GX suites via API endpoints supporting these query scopes:
       - `dataObjectId`
     - `dataObjectVersionId`
     - `datasetId`
     - `dataProductId`
   - Interpret `dataProductId` as an ODCS Data Product identifier.
    - Treat `dataObjectId` and `datasetId` as assignment-scope identifiers.
    - Treat `dataObjectVersionId` as resolved execution scope.
   - Support direct fetch by suite identifier and version.

3. **Canonical validation-plan contract**
   - Persist every DQ run plan through the neutral validation-plan model first.
   - Treat `validation_run_plans` and `validation_run_plan_versions` as the authoritative run-plan contract for execution and lifecycle interfaces.
   - Project GX, Soda, or SQL run plans from that canonical validation plan rather than making the engine-specific plan the primary contract.
   - Route execution through the canonical run and execution-plan interfaces so engine-specific implementations remain swappable without changing the public run-plan contract.

4. **PySpark-first executor runtime and integration seam**
   - Use a PySpark-based execution container as initial runtime.
   - Build a grouped execution plan by `dataObjectVersionId`.
   - Execute all suites for the grouped object version in one Spark session where possible.
   - Preserve an explicit artifact and run-planning seam so self-built PySpark solutions can consume compiled rule output or grouped plans without rewriting rule definitions.
   - Do not silently fall back from a self-built PySpark integration to the platform GX runtime when requested capabilities are unavailable.

5. **Persistence separation policy**
   - Rule/result database stores run metadata and aggregate outcomes only.
   - Exception records are written to a separate exception store.
   - Exception record minimum schema:
     - `dataPrimaryKey`
     - `ruleId`
     - `violationReason`
   - Exception rows must not be persisted in the rule/result database.

6. **Observability baseline**
   - Require structured logs, metrics, and correlation tracing across API, compiler, executor, and persistence paths.
   - Establish alerting on compile failures, executor failures/timeouts, and exception-store write failures.

### Consequences
**Positive**
- Supports heterogeneous source execution while keeping a single initial runtime profile (PySpark).
- Reduces execution latency and overhead through grouped session reuse.
- Enables safer and cheaper exception retention by isolating row-level violations from core run metadata.
- Allows external systems to retrieve and run standard GX suites through stable API contracts.
- Allows teams to integrate their own PySpark packaging, orchestration, or operational model while still reusing the platform compiler and execution metadata contracts.
- Improves operational reliability through explicit monitoring/tracing requirements.

**Negative**
- Introduces an additional persistence boundary (exception store) and associated operational complexity.
- Adds another supported runtime integration seam that must remain contract-compatible and fail closed when unsupported.
- Requires governance for exception retention, purge, and access control.
- Requires suite versioning and compatibility guarantees across retrieval clients.

### Implementation Guidance
- Use DQ-7.3 intermediate artifacts as the canonical compiler source for GX suite generation.
- Use the neutral validation-plan aggregate as the canonical run-plan interface, with GX/Soda/SQL run plans modeled as engine-specific projections of that plan.
- Separate assignment scope from execution scope in the contract and storage model: assignment attaches at `dataObjectId` or `datasetId`, execution targets resolve to one or more `dataObjectVersionId` values.
- Keep the self-built PySpark integration boundary at the portable artifact and run-planning seam rather than coupling custom executors to internal GX-only worker payloads.
- Use Alembic as the authoritative mechanism for future schema creation and modification; treat legacy bootstrap SQL as transitional until a baseline migration chain is established.
- Implement DQ-7.4 in phases:
  - Phase A: suite registry + retrieval APIs
  - Phase B: grouped PySpark execution
  - Phase C: exception store split
  - Phase D: observability hardening
- Ensure all retrieval endpoints are tenant-aware and authorization-scoped where applicable.
- Standardize run correlation fields (`correlationId`, `runId`, `suiteId`, scope identifiers) across all logs and telemetry.
- Preserve explicit runtime identity in contracts and persistence so platform GX execution and self-built PySpark integrations can coexist without inference or fallback.

### Related Artifacts
- DQ feature tracker: `docs/features/DQ_FEATURES.md`
- ABS-1 feature definition: `docs/features/ABS_1_EXECUTION_ABSTRACTION.md`
- DQ-7.3 compiler progress: `docs/implementation-details/DQ_7_3_RULE_COMPILER_IMPLEMENTATION_PROGRESS.md`
- DQ-7.4 implementation details: `docs/implementation-details/DQ_7_4_GX_SUITE_ORCHESTRATION_IMPLEMENTATION_DETAILS.md`
- Contract package: `docs/contracts/gx-artifact-envelope/v1/schema.json`
- Prior strategy ADR: `ADR-011-executable-rule-transformation-strategy-dsl-first-with-great-expectations-adapter.md`
