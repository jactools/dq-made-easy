# DQ-20 Execution Dispatch and Lowerer Module Split Plan

Status: Proposed

## Goal

Rename the shared execution layer from `execution_dispatch` / `runtime_lowerers` into the `dq_plan_execution*` namespace, extract its responsibilities into focused sub-modules, and make `gx_dispatch_*` modules GX-only. The end state is a clean separation between engine-agnostic execution plumbing (`dq_plan_execution*`) and engine-specific logic (`gx_dispatch_*`, `spark_expectations_adapter`, `trino_execution_pipeline`).

## Why this change is needed

`execution_dispatch.py` (490 lines) mixes five unrelated responsibilities in one file:
- payload parsing and type coercion
- HTTP API request helpers and run-reporting
- engine dispatch orchestration (the main worker loop)
- report summary / detail envelope construction
- engine routing that delegates into spark_expectations and trino

`runtime_lowerers.py` (271 lines) couples the lowerer registry with per-engine lowering implementations (GX, Trino, Spark Expectations, Soda). Adding a new engine means editing the same file that defines the registry.

`gx_dispatch_dispatch.py` imports seven functions from `execution_dispatch` and re-exports them to `gx_dispatch_worker.py`, blurring the line between generic execution plumbing and GX-specific dispatch.

This makes the execution layer hard to test in isolation, hard to extend, and easy to change in the wrong place.

## Current state

### Files and responsibilities

| File | Lines | Primary responsibility | Problem |
|---|---|---|---|
| `execution_dispatch.py` | 490 | Payload parsing, API reporting, engine routing, summary shaping | Too many responsibilities; not GX-specific but imported by `gx_dispatch_*` |
| `runtime_lowerers.py` | 271 | Lowerer registry + GX/Trino/Soda lowering logic | Registry and engine implementations are coupled |
| `execution_contract.py` | 86 | Shared envelope helpers (metadata, observability, persistence) | Already clean; used by `trino_execution_pipeline` and `execution_dispatch` |
| `gx_dispatch_types.py` | 53 | Shared types (config, errors, source locations) | Uses `gx_` prefix but types are engine-agnostic |
| `gx_dispatch_dispatch.py` | 881 | GX grouped dispatch + generic engine routing via `process_engine_dispatch_message` | Imports 9 symbols from `execution_dispatch`; not GX-only |
| `gx_dispatch_worker.py` | 291 | GX worker entry point | Imports `parse_dispatch_payload` from `execution_dispatch` |
| `gx_dispatch_api.py` | 281 | GX API reporting | Imports `report_run` from `execution_dispatch` |
| `gx_dispatch_payload.py` | 272 | GX payload parsing | Imports `coerce_str`, `coerce_int`, `parse_dispatch_payload` from `execution_dispatch` |
| `spark_expectations_adapter.py` | 989 | Spark Expectations lowering + execution | Duplicates contract helpers; used by `execution_dispatch` routing. Will be renamed to `spark_expectations_execution_adapter.py`. |
| `trino_execution_pipeline.py` | 385 | Trino execution pipeline | Imports from `execution_contract` and `runtime_lowerers`; mostly clean. Will be renamed to `trino_execution_adapter.py`. |
| (missing) | — | GX execution adapter | Not yet created. Needed for Layer 5 completeness. |
| (missing) | — | Soda execution adapter | Not yet created. Soda lowering is a stub. |
| (missing) | — | SQL execution adapter | Not yet created. SQL engine type is listed in supported engines but has no implementation. |

### Import map (what imports what)

```
execution_dispatch.py
  └─ runtime_lowerers.build_failure_envelope
  └─ execution_contract.persist_execution_payload  (lazy, inside execute_engine_rule_payload)
  └─ spark_expectations_adapter.execute_spark_expectations_rule  (lazy)
  └─ trino_execution_pipeline  (lazy)

gx_dispatch_dispatch.py
  └─ execution_dispatch: SUPPORTED_EXECUTION_ENGINES, build_execution_progress, coerce_int,
       coerce_str, execute_engine_rule_payload, normalize_execution_engine,
       parse_dispatch_payload, process_engine_dispatch_message, report_run

gx_dispatch_api.py
  └─ execution_dispatch.report_run

gx_dispatch_payload.py
  └─ execution_dispatch: coerce_int, coerce_str, parse_dispatch_payload

gx_dispatch_worker.py
  └─ execution_dispatch.parse_dispatch_payload

main.py
  └─ runtime_lowerers: build_failure_envelope, build_compiled_artifact_for_engine

trino_execution_pipeline.py
  └─ execution_contract: build_execution_metadata, build_observability_summary, persist_execution_payload
  └─ runtime_lowerers._infer_rule_family

tests/test_spark_expectations_adapter.py
  └─ execution_dispatch.execute_engine_rule_payload

tests/test_trino_execution_pipeline.py
  └─ execution_dispatch.process_engine_dispatch_message

tests/test_runtime_lowerer_registry.py
  └─ runtime_lowerers: lower_rule_to_trino, normalize_engine_type, get_runtime_lowerer
```

### Functions in `execution_dispatch.py` by responsibility

**Payload parsing (4 functions):** `parse_dispatch_payload`, `coerce_str`, `coerce_int`, `normalize_execution_engine`

**API / reporting (6 functions):** `build_token_provider`, `_build_api_request_headers`, `api_request`, `report_run`, `build_execution_progress`, `report_execution_progress`

**Execution orchestration (3 functions):** `execute_engine_rule_payload`, `_request_from_rule_payload`, `process_engine_dispatch_message`

**Report envelope shaping (3 functions):** `_result_status`, `build_execution_report_summary`, `build_execution_report_details`

**Utilities (1 function):** `log_dispatch_received`

**Constants / types (5 items):** `SUPPORTED_EXECUTION_ENGINES`, `ENGINE_ALIASES`, `REPORT_RUN_PATH_TEMPLATE`, plus 4 type aliases

**Output / reporting (3 functions):** `report_run` (API + Kafka), `build_execution_progress` (progress envelope), `report_execution_progress` (API call + progress)

**Persistence (1 function):** `_request_from_rule_payload` (input/output artifact path resolution)

### Functions in `runtime_lowerers.py` by responsibility

**Registry / normalization (4 functions):** `normalize_engine_type`, `_resolve_engine_target`, `get_runtime_capabilities`, `get_runtime_lowerer`

**Failure envelope (2 functions):** `_build_failure_metrics`, `build_failure_envelope`

**Per-engine lowering (3 functions):** `lower_rule_to_gx`, `lower_rule_to_soda` (stub), `lower_rule_to_trino`

**Compilation (1 function):** `build_compiled_artifact_for_engine`

**Utilities (3 items):** `_infer_rule_family`, `_format_expectation_literal`, plus rule-type constants

## Target shape

### New module layout

```
dq_plan_execution.py                  ← Facade (re-exports public API only)
dq_plan_execution_payload.py          ← Payload parsing, coercion, engine normalization
dq_plan_execution_api.py              ← API request helpers, token construction
dq_plan_execution_orchestrator.py     ← Engine dispatch loop, report envelope shaping
dq_plan_execution_contract.py         ← Shared execution contract (renamed from execution_contract.py)
dq_plan_execution_report.py           ← Run reporting (aggregated + detailed), DB writes
dq_plan_execution_persistence.py      ← S3/URI persistence, artifact storage
dq_plan_execution_streaming.py        ← Kafka publishing, violation streaming

dq_plan_lowerers.py                   ← Facade (registry, normalization, shared constants)
dq_plan_lowerers_gx.py                ← GX rule lowering
dq_plan_lowerers_trino.py             ← Trino rule lowering
dq_plan_lowerers_soda.py              ← Soda stub (fail-fast)

gx_dispatch_dispatch.py               ← GX-only dispatch (no longer imports execution_dispatch routing)
gx_dispatch_api.py                    ← GX-only API reporting
gx_dispatch_payload.py                ← GX-only payload parsing
gx_dispatch_worker.py                 ← GX-only worker entry point
gx_dispatch_expectations.py           ← GX-only expectation evaluation
gx_dispatch_config.py                 ← GX-only config loading
gx_dispatch_runtime.py                ← GX-only Spark/S3 runtime
gx_dispatch_telemetry.py              ← GX-only telemetry
```

### Naming convention

- All new shared execution modules use the `dq_plan_execution*` prefix (engine-agnostic, plan-based execution).
- All new lowerer modules use the `dq_plan_lowerers*` prefix (engine-specific rule lowering).
- `gx_dispatch_*` modules remain unchanged in name but become strictly GX-specific.
- `spark_expectations_execution_adapter.py` (renamed from `spark_expectations_adapter.py`) and `trino_execution_adapter.py` (renamed from `trino_execution_pipeline.py`) keep their engine-specific nature with consistent naming.
- `execution_contract.py` is renamed to `dq_plan_execution_contract.py` for namespace consistency.
- Engine-specific dispatch modules follow the pattern `<engine>_dispatch.py`, `<engine>_worker.py`, etc. (e.g., `gx_dispatch_worker.py`, `spark_expectations_dispatch.py`).

### Naming consistency for engine-specific modules

Engine-specific execution adapters use the pattern `<engine>_execution_adapter.py`. This is the only place where the engine name appears as a prefix in the shared layer. The full set:

- `gx_execution_adapter.py` — Great Expectations execution (to be created)
- `spark_expectations_execution_adapter.py` — Spark Expectations execution (renamed from `spark_expectations_adapter.py`)
- `trino_execution_adapter.py` — Trino SQL execution (renamed from `trino_execution_pipeline.py`)
- `soda_execution_adapter.py` — Soda CL execution (stub)
- `sql_execution_adapter.py` — Raw SQL execution (stub)

Each adapter owns the engine-specific execution logic and uses shared output modules (`dq_plan_execution_report`, `dq_plan_execution_persistence`, `dq_plan_execution_streaming`) for reporting, persistence, and streaming.

### What goes in each output module

Currently scattered across `execution_dispatch.py` (`report_run`, `build_execution_progress`), `execution_contract.py` (`persist_execution_payload`), and `spark_expectations_adapter.py` (Kafka publishing):

- `dq_plan_execution_report.py`
  - Run reporting: aggregated + detailed result envelopes
  - DB writes for execution results
  - Progress reporting (`build_execution_progress`, `report_execution_progress`)
  - Status transitions (running → succeeded/failed)

- `dq_plan_execution_persistence.py`
  - S3/URI artifact persistence
  - Output directory resolution
  - File storage (execution JSON, error artifacts)
  - Path normalization (S3 URIs, local paths)

- `dq_plan_execution_streaming.py`
  - Kafka publishing infrastructure
  - Violation streaming (batch + real-time)
  - Publisher lifecycle (start/stop/flush)
  - Retry/backoff logic for message delivery

### Dependency rules (strict, no cycles)

```
Layer 0 (types):               dq_plan_execution_types.py
Layer 1 (contract):            dq_plan_execution_contract.py
Layer 2 (lowerers):            dq_plan_lowerers.py, dq_plan_lowerers_*.py
Layer 3 (shared exec):         dq_plan_execution_payload.py, dq_plan_execution_api.py,
                               dq_plan_execution_orchestrator.py
Layer 3.5 (shared output):     dq_plan_execution_report.py, dq_plan_execution_persistence.py,
                               dq_plan_execution_streaming.py
Layer 4 (facade):              dq_plan_execution.py (re-exports only)
Layer 5 (engine-specific):     spark_expectations_execution_adapter.py,
                               trino_execution_adapter.py,
                               gx_execution_adapter.py  (to be created),
                               soda_execution_adapter.py (stub),
                               sql_execution_adapter.py  (stub)
Layer 6 (engine-specific dispatch): gx_dispatch_*.py, spark_expectations_dispatch.py, trino_dispatch.py
```

No layer may import from a higher layer. A layer may import from any equal-or-lower layer. Engine-specific dispatch modules may import from `dq_plan_execution*` but never from other engine-specific modules.

## Action plan

### Phase 1: Create the new module skeleton and compatibility facade

**Goal:** Establish the new file layout and make the old `execution_dispatch.py` a thin re-export facade so nothing breaks until all callers are updated.

1. Create `dq_plan_execution_types.py` as a new file containing the current types from `gx_dispatch_types.py`, renamed: `GxWorkerConfig` → `DqWorkerConfig`, `GxWorkerConfigError` → `DqWorkerConfigError`, `GxWorkerExecutionError` → `DqWorkerExecutionError`. Keep `SourceLocation` unchanged (already engine-agnostic).
2. Update `gx_dispatch_types.py` to re-export everything from `dq_plan_execution_types.py` with the old names as backward-compat aliases.
3. Create `dq_plan_execution_payload.py` as a new empty file with the module docstring and stubs for `parse_dispatch_payload`, `coerce_str`, `coerce_int`, and `normalize_execution_engine`.
2. Create `dq_plan_execution_api.py` as a new empty file with stubs for `build_token_provider`, `_build_api_request_headers`, `api_request`, `report_run`, `build_execution_progress`, and `report_execution_progress`.
3. Create `dq_plan_execution_orchestrator.py` as a new empty file with stubs for `execute_engine_rule_payload`, `_request_from_rule_payload`, `process_engine_dispatch_message`, `_result_status`, `build_execution_report_summary`, `build_execution_report_details`, and `log_dispatch_received`.
4. Create `dq_plan_execution_contract.py` as a rename of `execution_contract.py`.
5. Create `dq_plan_execution.py` as the public facade that re-exports all public symbols from the three sub-modules above, preserving the exact function names and signatures from the current `execution_dispatch.py` public API.
6. Update `execution_dispatch.py` to import everything from `dq_plan_execution.py` and re-export it, keeping the file alive as a backward-compat shim during the migration.
7. Rename `spark_expectations_adapter.py` → `spark_expectations_execution_adapter.py` and keep a compat shim `spark_expectations_adapter.py` that re-exports everything.
8. Rename `trino_execution_pipeline.py` → `trino_execution_adapter.py` and keep a compat shim `trino_execution_pipeline.py` that re-exports everything.
9. Verify all existing tests pass against the facade with zero behavior changes.

### Phase 2: Migrate payload, API helpers, and output modules

**Goal:** Move payload parsing, coercion, API helpers, and output/reporting from `execution_dispatch.py` into their new home modules, then update callers one at a time.

8. Move `parse_dispatch_payload`, `coerce_str`, `coerce_int`, and `normalize_execution_engine` from `execution_dispatch.py` into `dq_plan_execution_payload.py`.
9. Update `dq_plan_execution.py` facade to import and re-export these from `dq_plan_execution_payload.py`.
10. Update `execution_dispatch.py` compat shim to import from `dq_plan_execution.py` instead of defining these functions locally.
11. Update `dq_plan_execution_api.py` to contain `build_token_provider`, `_build_api_request_headers`, and `api_request` (HTTP request helpers only).
12. Create `dq_plan_execution_report.py` containing `report_run`, `build_execution_progress`, `report_execution_progress`, and all run-reporting logic (aggregated + detailed results).
13. Create `dq_plan_execution_persistence.py` containing artifact persistence helpers (S3/URI writes, output directory resolution, file storage).
14. Create `dq_plan_execution_streaming.py` containing Kafka publishing and violation streaming helpers (currently embedded in `report_run`).
15. Update `dq_plan_execution.py` facade to import and re-export API helpers from `dq_plan_execution_api.py` and output helpers from `dq_plan_execution_report.py`, `dq_plan_execution_persistence.py`, and `dq_plan_execution_streaming.py`.
16. Update `execution_dispatch.py` compat shim to import from `dq_plan_execution.py` instead of defining these locally.
17. Verify all existing tests pass. The `execution_dispatch.py` shim should still work for all current callers.

### Phase 3: Migrate execution orchestrator

**Goal:** Move the execution dispatch loop and report envelope helpers into `dq_plan_execution_orchestrator.py`.

15. Move `execute_engine_rule_payload`, `_request_from_rule_payload`, `process_engine_dispatch_message`, `_result_status`, `build_execution_report_summary`, `build_execution_report_details`, and `log_dispatch_received` from `execution_dispatch.py` into `dq_plan_execution_orchestrator.py`.
16. Update `dq_plan_execution.py` facade to import and re-export orchestrator symbols.
17. Update `execution_dispatch.py` compat shim to import from `dq_plan_execution.py` instead of defining these locally.
18. Update `dq_plan_execution_orchestrator.py` to import its lowerer dependency from `dq_plan_lowerers.py` (not yet created; use the current `runtime_lowerers.py` temporarily and update in Phase 5).
19. Verify all existing tests pass. At this point `execution_dispatch.py` should be a pure re-export shim with zero inline implementation.

### Phase 4: Create the lowerer module skeleton

**Goal:** Split `runtime_lowerers.py` into a registry facade and per-engine lowerer modules.

20. Create `dq_plan_lowerers.py` containing only the registry layer: `normalize_engine_type`, `_resolve_engine_target`, `_infer_rule_family`, `get_runtime_capabilities`, `get_runtime_lowerer`, `_build_failure_metrics`, `build_failure_envelope`, `build_compiled_artifact_for_engine`, and all shared constants (`SUPPORTED_RUNTIME_ENGINES`, `SUPPORTED_RUNTIME_CAPABILITIES`, `ENGINE_TYPE_ALIASES`, `ENGINE_TARGETS`, `ROW_RULE_TYPES`, `AGGREGATE_RULE_TYPES`).
21. Create `dq_plan_lowerers_gx.py` and move `lower_rule_to_gx` into it.
22. Create `dq_plan_lowerers_trino.py` and move `lower_rule_to_trino` into it.
23. Create `dq_plan_lowerers_soda.py` and move `lower_rule_to_soda` into it.
24. Update `dq_plan_lowerers.py` registry (`get_runtime_lowerer`) to lazily import from the per-engine lowerer modules.
25. Update `build_compiled_artifact_for_engine` in `dq_plan_lowerers.py` to use the registry for engine dispatch.
26. Keep `runtime_lowerers.py` alive as a compat shim that re-exports everything from `dq_plan_lowerers.py`.
27. Verify `tests/test_runtime_lowerer_registry.py` passes against the new module structure.

### Phase 5: Update execution_dispatch.py to use new lowerer module

**Goal:** Remove the dependency from `execution_dispatch.py` (and its new home) on `runtime_lowerers.py`.

28. Update `dq_plan_execution_orchestrator.py` to import `build_failure_envelope` from `dq_plan_lowerers.py` instead of `runtime_lowerers.py`.
29. Remove the `from runtime_lowerers import build_failure_envelope` line from `execution_dispatch.py`.
30. Verify all tests pass.

### Phase 6: Update GX modules to use dq_plan_execution (not execution_dispatch)

**Goal:** Make `gx_dispatch_*` modules import from `dq_plan_execution*` instead of `execution_dispatch`, establishing the GX-specific boundary.

31. Update `gx_dispatch_payload.py` to import `coerce_int`, `coerce_str`, and `parse_dispatch_payload` from `dq_plan_execution_payload` instead of `execution_dispatch`.
32. Update `gx_dispatch_api.py` to import `report_run` from `dq_plan_execution_api` instead of `execution_dispatch`.
33. Update `gx_dispatch_dispatch.py` to import its nine symbols from `dq_plan_execution` (the facade) instead of `execution_dispatch`.
34. Update `gx_dispatch_worker.py` to import `parse_dispatch_payload` from `dq_plan_execution_payload` instead of `execution_dispatch`.
35. Update `trino_execution_pipeline.py` to import `_infer_rule_family` from `dq_plan_lowerers` instead of `runtime_lowerers`.
36. Update `main.py` to import `build_failure_envelope` and `build_compiled_artifact_for_engine` from `dq_plan_lowerers` instead of `runtime_lowerers`.
37. Update `tests/test_spark_expectations_adapter.py` to import `execute_engine_rule_payload` from `dq_plan_execution_orchestrator` instead of `execution_dispatch`.
38. Update `tests/test_trino_execution_pipeline.py` to import `process_engine_dispatch_message` from `dq_plan_execution_orchestrator` instead of `execution_dispatch`.
39. Update `tests/test_runtime_lowerer_registry.py` to import from `dq_plan_lowerers` instead of `runtime_lowerers`.
40. Verify all tests pass.

### Phase 7: Clean up and remove compatibility shims

**Goal:** Remove `execution_dispatch.py` and `runtime_lowerers.py` compat shims once all callers are updated.

41. Audit all remaining imports of `execution_dispatch` across the codebase (including `dq-api`, `dq-kafka-consumer`, and scripts). Update any stragglers to import from `dq_plan_execution*`.
42. Audit all remaining imports of `runtime_lowerers` across the codebase. Update any stragglers to import from `dq_plan_lowerers*`.
43. Audit all remaining imports of `execution_contract`. Update to import from `dq_plan_execution_contract`.
44. Once all callers are updated, remove the compat shim bodies from `execution_dispatch.py` and replace it with a deprecation warning that re-exports from `dq_plan_execution` with a warning log.
45. Remove the compat shim from `runtime_lowerers.py` and replace it with a deprecation warning that re-exports from `dq_plan_lowerers`.
46. Remove the compat shim from `execution_contract.py` and replace it with a deprecation warning that re-exports from `dq_plan_execution_contract`.
47. Verify all tests pass with zero deprecation warnings.

### Phase 8: Add module boundary tests

**Goal:** Protect the new architecture from regression.

48. Add a test that verifies `gx_dispatch_dispatch.py` does not import from `execution_dispatch`, `runtime_lowerers`, or any non-`dq_plan_*` / non-`gx_dispatch_*` module.
49. Add a test that verifies `dq_plan_execution*` modules do not import from `gx_dispatch_*` modules (enforce the one-way dependency).
50. Add a test that verifies `dq_plan_lowerers*` modules do not import from each other (no cross-engine coupling).
51. Add unit tests for `dq_plan_execution_payload.py` covering `parse_dispatch_payload`, `coerce_str`, and `coerce_int` with edge cases (empty strings, missing keys, type mismatches).
52. Add unit tests for `dq_plan_execution_api.py` covering `api_request` error handling and `build_execution_progress` boundary conditions.

### Phase 9: Final validation

**Goal:** Confirm nothing broke.

53. Run the full `dq-engine` test suite.
54. Run the Trino execution pipeline regression tests (`test_trino_execution_pipeline.py`, `test_trino_live_container.py`).
55. Run the Spark Expectations regression tests (`test_spark_expectations_adapter.py`, `test_spark_expectations_real_aistor_validation.py`).
56. Run the lowerer registry tests (`test_runtime_lowerer_registry.py`).
57. Run the GX dispatch worker tests (`test_gx_dispatch_worker.py`, `test_gx_dispatch_worker_custom_expectations.py`).
58. Verify the module architecture doc (`docs/technical/DQ_ENGINE_MODULE_ARCHITECTURE.md`) is updated to reflect the new `dq_plan_execution*` and `dq_plan_lowerers*` modules.

## Acceptance criteria

- `dq_plan_execution.py` is the public facade for engine-agnostic execution dispatch; it contains no implementation code.
- `dq_plan_execution_payload.py`, `dq_plan_execution_api.py`, `dq_plan_execution_orchestrator.py`, `dq_plan_execution_report.py`, `dq_plan_execution_persistence.py`, and `dq_plan_execution_streaming.py` own the six responsibility areas that were previously in `execution_dispatch.py`.
- `gx_dispatch_*` modules import only from `dq_plan_execution*` and `gx_dispatch_*` siblings (no `execution_dispatch`, no `runtime_lowerers`).
- `dq_plan_lowerers.py` is a thin registry facade; per-engine lowering logic lives in `dq_plan_lowerers_gx.py`, `dq_plan_lowerers_trino.py`, and `dq_plan_lowerers_soda.py`.
- `dq_plan_execution_types.py` owns the shared types (`DqWorkerConfig`, `DqWorkerExecutionError`, etc.) and `gx_dispatch_types.py` exists only as a deprecation shim.
- `runtime_lowerers.py` and `execution_dispatch.py` exist only as deprecation shims (or are fully removed).
- All existing tests pass with no behavior changes to supported runtime paths.
- No import cycles exist in the new module graph.
- Engine-specific dispatch modules follow the `<engine>_dispatch.py`, `<engine>_worker.py` naming pattern (consistent with `gx_dispatch_*`).

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Import cycles if `dq_plan_execution_orchestrator` imports from lowerers and lowerers import from execution contract | Enforce strict layering: orchestrator imports from lowerers, lowerers import from contract only. No upward imports. |
| Test churn if compat shims are removed too early | Keep shims alive until Phase 7 when all callers are audited and updated. |
| Behavior drift if lowerer modules build different failure envelopes | Centralize `build_failure_envelope` in `dq_plan_lowerers.py`; per-engine modules must use it. |
| Output generation (DB, S3, Kafka) leaks into engine-specific modules | Centralize output/reporting in `dq_plan_execution_report.py`, `dq_plan_execution_persistence.py`, and `dq_plan_execution_streaming.py`. Engine-specific modules should compose, not duplicate. |
| The `build_execution_progress` / `report_execution_progress` functions use GX-specific API paths | These are already generic enough. If GX-specific paths emerge, create a GX-specific override. |
| Engine-specific naming inconsistency | Follow `<engine>_execution_adapter.py` and `<engine>_dispatch.py` patterns consistently. Document the naming convention in the architecture doc. |
| Renaming existing files breaks imports | Rename `spark_expectations_adapter.py` → `spark_expectations_execution_adapter.py` and `trino_execution_pipeline.py` → `trino_execution_adapter.py` in Phase 1 with compat shims. Update all callers in Phase 6. |

## Module line-count targets (approximate)

| Module | Lines (est.) | Notes |
|---|---|---|
| `dq_plan_execution.py` | ~50 | Facade only |
| `dq_plan_execution_payload.py` | ~60 | Payload parsing, coercion, normalization |
| `dq_plan_execution_api.py` | ~80 | HTTP request helpers, token construction |
| `dq_plan_execution_orchestrator.py` | ~200 | Dispatch loop, report envelopes |
| `dq_plan_execution_contract.py` | ~86 | Renamed from `execution_contract.py` |
| `dq_plan_execution_report.py` | ~100 | Run reporting (aggregated + detailed), DB writes |
| `dq_plan_execution_persistence.py` | ~60 | S3/URI persistence, artifact storage |
| `dq_plan_execution_streaming.py` | ~40 | Kafka publishing, violation streaming |
| `dq_plan_lowerers.py` | ~130 | Registry, failure envelope, constants |
| `dq_plan_lowerers_gx.py` | ~30 | GX lowering only |
| `dq_plan_lowerers_trino.py` | ~30 | Trino lowering only |
| `dq_plan_lowerers_soda.py` | ~10 | Soda stub |
| `gx_execution_adapter.py` | TBD | GX execution (to be created) |
| `spark_expectations_execution_adapter.py` | ~989 | Renamed from `spark_expectations_adapter.py` |
| `trino_execution_adapter.py` | ~385 | Renamed from `trino_execution_pipeline.py` |
| `soda_execution_adapter.py` | ~10 | Soda execution stub |
| `sql_execution_adapter.py` | ~10 | SQL execution stub |

Total new modules: ~876 lines (vs. 761 lines in the three legacy modules combined).

## Recommended execution order

1. Phase 1 (skeleton + facade + type renaming) → Phase 2 (payload + API migration) → Phase 3 (orchestrator migration) — these three phases move code without breaking callers.
2. Phase 4 (lowerer split) → Phase 5 (update execution_dispatch lowerer import) — decouple the lowerer registry.
3. Phase 6 (update GX modules) → Phase 7 (remove shims) — establish the GX boundary and clean up.
4. Phase 8 (boundary tests) → Phase 9 (final validation) — protect the architecture and confirm nothing broke.

Each phase ends with a "all tests pass" checkpoint. No phase should be committed without passing all tests.
