# DQ-20 Execution Dispatch and Lowerer Module Split Plan

Status: Proposed

## Goal

Turn `execution_dispatch.py` into the shared abstraction layer for execution dispatch, keep `gx_dispatch_*` modules GX-only, and split lowerer-specific logic into per-runtime modules that reuse the shared `execution_*` helpers.

## Why this change is needed

Current `execution_dispatch.py` mixes several responsibilities:

- payload normalization and coercion
- API request/reporting
- execution routing
- report-summary shaping
- runtime compilation / lowerer selection

At the same time, `gx_dispatch_dispatch.py` still routes non-GX execution paths, and the lowerer modules still carry their own contract/reporting helpers in a few places.

That makes the execution layer harder to reason about, harder to test in isolation, and easy to extend in the wrong place.

## Current state

| Module | Current responsibility | Problem |
|---|---|---|
| `execution_dispatch.py` | Generic payload parsing, API/reporting helpers, engine execution routing, compile helpers | Too many responsibilities in one file |
| `gx_dispatch_dispatch.py` | GX grouped execution plus generic engine routing | Not GX-only |
| `runtime_lowerers.py` | Lowerer registry plus GX/Soda/Trino lowering helpers | Registry and engine logic are coupled |
| `spark_expectations_adapter.py` | Spark Expectations lowering and execution | Duplicates some shared execution contract helpers |
| `trino_execution_pipeline.py` | Trino execution pipeline | Already mostly separated, but should rely only on shared execution helpers |
| `gx_dispatch_api.py`, `gx_dispatch_payload.py`, `gx_dispatch_runtime.py`, `gx_dispatch_config.py` | GX support modules | Good shape, but still consume generic execution helpers |

## Target shape

### Shared execution abstraction

- `execution_dispatch.py`
  - stable public facade
  - re-exports or delegates to smaller modules
  - no large blocks of inline routing/reporting logic

- `execution_dispatch_payload.py`
  - `parse_dispatch_payload`
  - `coerce_str`
  - `coerce_int`
  - engine normalization helpers

- `execution_dispatch_api.py`
  - API request helpers
  - report-run/report-progress helpers
  - token/header construction

- `execution_dispatch_runtime.py`
  - engine dispatch orchestration
  - `execute_engine_rule_payload`
  - `process_engine_dispatch_message`
  - response summary shaping

### GX-only layer

- `gx_dispatch_*` modules should own only:
  - GX suite resolution
  - GX grouped execution
  - GX-specific telemetry/reporting
  - GX-only payload handling

- Any generic non-GX execution branch should move out of `gx_dispatch_dispatch.py`.

### Lowerer-specific modules

- `execution_lowerers.py`
  - shared lowerer registry / capability lookup
  - public entry point for resolving a lowerer by `engine_type`

- `execution_lowerers_gx.py`
- `execution_lowerers_spark_expectations.py`
- `execution_lowerers_trino.py`
- `execution_lowerers_soda.py` (only if/when Soda lowering is actually implemented)

Each lowerer module should reuse shared execution helpers for:

- artifact envelope construction
- execution metadata
- observability summary
- persistence

## Action plan

### Phase 1: Freeze the current contract surface

1. List all current imports of `execution_dispatch.py` and `runtime_lowerers.py`.
2. Add/adjust tests to pin the current public API before moving code.
3. Keep `execution_dispatch.py` as a compatibility facade during the refactor.

### Phase 2: Extract the shared execution helpers

1. Move payload parsing/coercion into `execution_dispatch_payload.py`.
2. Move API/reporting helpers into `execution_dispatch_api.py`.
3. Move engine routing and execution orchestration into `execution_dispatch_runtime.py`.
4. Keep `execution_dispatch.py` thin and import-only.

### Phase 3: Make GX modules GX-only

1. Remove the non-GX engine branch from `gx_dispatch_dispatch.py`.
2. Ensure GX dispatch only handles GX suite/grouped/join-pair flows.
3. Update `gx_dispatch_worker.py` and related tests to import the shared execution layer where needed.
4. Verify GX telemetry and reporting still flow through the GX API helpers.

### Phase 4: Split lowerers by runtime

1. Replace `runtime_lowerers.py` with a small registry facade over engine-specific lowerer modules.
2. Move GX lowering into `execution_lowerers_gx.py`.
3. Move Spark Expectations lowering into `execution_lowerers_spark_expectations.py`.
4. Move Trino lowering into `execution_lowerers_trino.py`.
5. Leave Soda as a fail-fast stub unless it becomes a supported runtime.

### Phase 5: Reuse shared execution contracts

1. Move duplicated execution metadata / observability helpers to `execution_contract.py` if they are still local to lowerer modules.
2. Make `spark_expectations_adapter.py` and `trino_execution_pipeline.py` depend on the shared contract helpers only.
3. Ensure lowerer modules do not build their own slightly different execution envelopes.

### Phase 6: Update callers and tests

1. Update `main.py` to resolve lowerers through the new registry facade.
2. Update all `dq-engine/tests/*` imports to the new module locations.
3. Add focused tests for the new module boundaries:
   - payload parsing
   - API/reporting helpers
   - GX-only dispatch behavior
   - per-runtime lowerer resolution

### Phase 7: Validate

1. Run the existing `dq-engine` test suite.
2. Run the Trino and Spark Expectations regression tests.
3. Verify no public behavior changed for supported GX and non-GX execution paths.

## Acceptance criteria

- `execution_dispatch.py` is a facade, not a catch-all implementation file.
- `gx_dispatch_dispatch.py` contains GX-only routing and no generic engine branch.
- Lowerer modules are split by runtime and share execution contract helpers.
- `runtime_lowerers.py` no longer owns both registry logic and engine implementations.
- Existing tests pass without changing supported runtime behavior.

## Risks

- Import cycles if the layering is not kept strict.
- Test churn if the public facade is removed too early.
- Behavior drift if lowerer modules start formatting envelopes independently.

## Recommended order

1. Extract shared execution helpers.
2. Make GX dispatch GX-only.
3. Split lowerers.
4. Update tests and callers.
5. Remove compatibility shims last.
